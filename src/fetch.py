"""Stage 1.1 - download + cache data.binance.vision (capture-once, brief §3.4).

Satu pass download untuk seluruh kebutuhan Stage 1.1 s/d Stage 3:
  - klines 1H MENTAH (bukan agregat harian)
  - fundingRate per periode + timestamp

Universe diambil dari isi arsip, BUKAN dari exchangeInfo hari ini - inilah yang
membuat symbol delisted tetap masuk (brief §1 jebakan #1).

Catatan jaringan: fapi.binance.com / api.binance.com / www.binance.com tidak dapat
diakses dari mesin ini (ConnectTimeout). Hanya data.binance.vision yang reachable.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

NS = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
_local = threading.local()
_print_lock = threading.Lock()


def session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = "dew-stage1.1/1.0"
        a = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0)
        s.mount("https://", a)
        _local.s = s
    return s


def _get(url: str, timeout: int = 60, tries: int = 4):
    delay = 1.0
    for _ in range(tries):
        try:
            r = session().get(url, timeout=timeout)
            if r.status_code in (200, 404):
                return r
            if r.status_code in (403, 429, 500, 502, 503, 504):
                time.sleep(delay)
                delay *= 2
                continue
            return r
        except requests.RequestException:
            time.sleep(delay)
            delay *= 2
    return None


# ------------------------------------------------------------------ listing
def list_common_prefixes(prefix: str) -> list[str]:
    out, token = [], None
    while True:
        url = (C.S3_LIST + "?list-type=2&delimiter=/&max-keys=1000"
               + "&prefix=" + requests.utils.quote(prefix, safe=""))
        if token:
            url += "&continuation-token=" + requests.utils.quote(token, safe="")
        r = _get(url)
        if r is None or r.status_code != 200:
            return out
        root = ET.fromstring(r.content)
        out += [e.find("s3:Prefix", NS).text for e in root.findall("s3:CommonPrefixes", NS)]
        t = root.find("s3:NextContinuationToken", NS)
        if t is None:
            return out
        token = t.text


def discover_symbols() -> list[str]:
    """Semua symbol perp USDT yang PERNAH ada di arsip (termasuk delisted)."""
    prefixes = list_common_prefixes("data/futures/um/monthly/klines/")
    syms = [p.rstrip("/").split("/")[-1] for p in prefixes]
    # quote = USDT; buang kontrak delivery (mengandung "_", mis. BTCUSDT_240329)
    return sorted(s for s in syms if s.endswith(C.QUOTE) and "_" not in s)


# ------------------------------------------------------------------ month helpers
def month_range(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    ey, em = int(end[:4]), int(end[5:7])
    out = []
    while (y, m) <= (ey, em):
        out.append("%04d-%02d" % (y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def target_months() -> list[str]:
    sy, sm = int(C.START_DATE[:4]), int(C.START_DATE[5:7])
    sm -= C.WARMUP_MONTHS
    while sm <= 0:
        sm += 12
        sy -= 1
    return month_range("%04d-%02d" % (sy, sm), C.END_DATE[:7])


def tail_days() -> list[str]:
    d0 = date.fromisoformat(C.END_DATE)
    return [(d0 + timedelta(days=i)).isoformat() for i in range(1, C.FWD_TAIL_DAYS + 1)]


# ------------------------------------------------------------------ download
def _save_zip(url: str, dest: Path) -> str:
    """-> 'cached' | 'ok' | 'absent' | 'fail'"""
    if dest.exists() and dest.stat().st_size > 0:
        return "cached"
    r = _get(url)
    if r is None:
        return "fail"
    if r.status_code == 404:
        return "absent"
    if r.status_code != 200:
        return "fail"
    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        if not z.namelist():
            return "fail"
    except zipfile.BadZipFile:
        return "fail"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return "ok"


def jobs_for_symbol(sym: str, months: list[str], tails: list[str]) -> list[tuple]:
    j = []
    for m in months:
        j.append((C.BASE_URL + "/monthly/klines/%s/1h/%s-1h-%s.zip" % (sym, sym, m),
                  C.RAW_KLINES / sym / ("%s-1h-%s.zip" % (sym, m))))
        j.append((C.BASE_URL + "/monthly/fundingRate/%s/%s-fundingRate-%s.zip" % (sym, sym, m),
                  C.RAW_FUNDING / sym / ("%s-fundingRate-%s.zip" % (sym, m))))
    for d in tails:
        j.append((C.BASE_URL + "/daily/klines/%s/1h/%s-1h-%s.zip" % (sym, sym, d),
                  C.RAW_KLINES / sym / ("%s-1h-%s.zip" % (sym, d))))
    return j


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--limit", type=int, default=0, help="debug: batasi jumlah symbol")
    args = ap.parse_args()

    t0 = time.time()
    print("discovering universe from archive ...", flush=True)
    symbols = discover_symbols()
    if args.limit:
        symbols = symbols[: args.limit]
    months, tails = target_months(), tail_days()
    print("symbols=%d  months=%s..%s (%d)  tail_days=%d"
          % (len(symbols), months[0], months[-1], len(months), len(tails)), flush=True)

    jobs = [(s, u, p) for s in symbols for (u, p) in jobs_for_symbol(s, months, tails)]
    print("total file candidates: %d" % len(jobs), flush=True)

    stats = {"ok": 0, "cached": 0, "absent": 0, "fail": 0}
    have = {s: {"klines": [], "funding": [], "daily": []} for s in symbols}
    done = 0

    def run(job):
        sym, url, dest = job
        return sym, dest, _save_zip(url, dest)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run, j) for j in jobs]
        for f in as_completed(futs):
            sym, dest, res = f.result()
            stats[res] += 1
            if res in ("ok", "cached"):
                name = dest.name
                if "fundingRate" in name:
                    have[sym]["funding"].append(name.split("-fundingRate-")[-1][:-4])
                else:
                    tag = name.split("-1h-")[-1][:-4]
                    have[sym]["daily" if len(tag) == 10 else "klines"].append(tag)
            done += 1
            if done % 2000 == 0:
                with _print_lock:
                    print("  %d/%d  ok=%d cached=%d absent=%d fail=%d  %.1fm"
                          % (done, len(jobs), stats["ok"], stats["cached"], stats["absent"],
                             stats["fail"], (time.time() - t0) / 60), flush=True)

    for s in have:
        for k in have[s]:
            have[s][k] = sorted(have[s][k])
    alive = {s: v for s, v in have.items() if v["klines"] or v["daily"]}
    manifest = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "months": months,
        "tail_days": tails,
        "n_symbols_discovered": len(symbols),
        "n_symbols_with_data_in_window": len(alive),
        "stats": stats,
        "symbols": have,
    }
    (C.RAW / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print("\ndone in %.1f min: %s" % ((time.time() - t0) / 60, stats))
    print("symbols with klines in window: %d / %d" % (len(alive), len(symbols)))
    print("manifest -> %s" % (C.RAW / "manifest.json"))


if __name__ == "__main__":
    main()
