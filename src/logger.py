"""Stage 0 — data logger harian (action plan §2).

MASALAH AKSES (terverifikasi, bukan dugaan)
-------------------------------------------
  fapi.binance.com dari mesin Dew (Indonesia) : ConnectTimeout — blokir ISP
  fapi.binance.com dari GitHub Actions (US)   : HTTP 451 "restricted location"
  api.bybit.com / www.okx.com dari mesin Dew  : ConnectTimeout
  api.gateio.ws                               : HTTP 200 — JALAN
  data.binance.vision                         : HTTP 200 (arsip klines/funding saja)

Jadi data posisi (OI / long-short / taker / likuidasi) tidak bisa diambil dari
Binance sama sekali dari lokasi manapun yang tersedia. Sumber pengganti:
**Gate.io** `/futures/usdt/contract_stats`, yang justru memuat lebih banyak
field daripada empat endpoint Binance yang diminta action plan §2:

  open_interest, open_interest_usd     <- setara openInterestHist
  lsr_account, top_lsr_account         <- setara globalLongShortAccountRatio
  top_lsr_size, top_long_size          <- setara topLongShortPositionRatio
  lsr_taker, long_taker_size           <- setara takerlongshortRatio
  long_liq_usd, short_liq_usd          <- likuidasi (Binance TIDAK menyediakan ini;
                                          dokumen strategi §6 menganggapnya mustahil)
  mark_price, last_funding_rate, long_users, short_users

PERINGATAN YANG WAJIB DIBAWA KE ANALISIS
----------------------------------------
Ini posisi trader **Gate.io**, bukan Binance. Basis trader-nya berbeda.
Boleh dipakai sebagai proksi untuk menguji apakah positioning punya kandungan
prediktif, TIDAK boleh diklaim sebagai OI Binance. Overlap symbol dengan
universe Binance: 595 dari 769 (77%).

Kelebihan tak terduga: Gate.io menyimpan ~42 hari riwayat 1 jam (Binance hanya
30), jadi tiap run menangkap lebih banyak dan gap lebih tahan kalau logger telat.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

GATE = "https://api.gateio.ws/api/v4"
BINANCE = "https://fapi.binance.com"
OUT = Path(__file__).resolve().parent.parent / "oi_logs"
INTERVAL = "1h"
LIMIT = 1000                    # ~42 hari riwayat per panggilan
_local = threading.local()
_lock = threading.Lock()


def sess() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"Accept": "application/json",
                          "User-Agent": "dew-stage0-logger/2.0"})
        s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16))
        _local.s = s
    return s


def get(url: str, params: dict | None = None, tries: int = 4):
    delay = 1.0
    for _ in range(tries):
        try:
            r = sess().get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (418, 429, 503):
                time.sleep(float(r.headers.get("Retry-After", delay)))
                delay *= 2
                continue
            if r.status_code >= 500:
                time.sleep(delay)
                delay *= 2
                continue
            return None
        except requests.RequestException:
            time.sleep(delay)
            delay *= 2
    return None


def probe() -> dict:
    """Cek sumber mana yang hidup dari lokasi ini. Selalu dicatat ke manifest."""
    out = {}
    for name, url in [("gate", GATE + "/futures/usdt/contracts?limit=1"),
                      ("binance_fapi", BINANCE + "/fapi/v1/ping")]:
        try:
            r = sess().get(url, timeout=15)
            out[name] = {"status": r.status_code,
                         "body": " ".join(r.text[:120].split())}
        except requests.RequestException as e:
            out[name] = {"status": None, "body": f"{type(e).__name__}"}
    return out


def gate_contracts() -> list[str]:
    j = get(GATE + "/futures/usdt/contracts")
    if not j:
        return []
    return sorted(c["name"] for c in j if not c.get("in_delisting"))


def gate_stats(contract: str):
    j = get(GATE + "/futures/usdt/contract_stats",
            {"contract": contract, "interval": INTERVAL, "limit": LIMIT})
    if not isinstance(j, list) or not j:
        return None
    df = pd.DataFrame(j)
    df["contract"] = contract
    df["symbol"] = contract.replace("_", "")      # kunci join ke universe Binance
    return df


def binance_exchange_info(dest: Path) -> bool:
    """Bonus kalau Binance kebetulan bisa diakses: simpan filter LOT_SIZE asli,
    yang selama ini hanya bisa diturunkan dari GCD volume klines."""
    j = get(BINANCE + "/fapi/v1/exchangeInfo")
    if not j:
        return False
    rows = []
    for s in j.get("symbols", []):
        if s.get("contractType") != "PERPETUAL" or s.get("quoteAsset") != "USDT":
            continue
        f = {x["filterType"]: x for x in s.get("filters", [])}
        rows.append({"symbol": s["symbol"], "status": s.get("status"),
                     "stepSize": f.get("LOT_SIZE", {}).get("stepSize"),
                     "minQty": f.get("LOT_SIZE", {}).get("minQty"),
                     "tickSize": f.get("PRICE_FILTER", {}).get("tickSize"),
                     "minNotional": f.get("MIN_NOTIONAL", {}).get("notional"),
                     "onboardDate": s.get("onboardDate")})
    pd.DataFrame(rows).to_parquet(dest / "binance_exchangeInfo.parquet",
                                  index=False, compression="zstd")
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit-symbols", type=int, default=0)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    t0 = time.time()
    now = datetime.now(timezone.utc)
    dest = Path(args.out) / f"date={now.strftime('%Y-%m-%d')}"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Stage 0 logger — {now.isoformat()}", flush=True)

    pr = probe()
    for k, v in pr.items():
        print(f"  probe {k:13s} HTTP {v['status']}  {v['body'][:90]}", flush=True)
    if pr.get("gate", {}).get("status") != 200:
        print("FATAL: Gate.io tidak bisa diakses dari lokasi ini.", file=sys.stderr)
        json.dump({"utc": now.isoformat(), "probe": pr, "status": "failed"},
                  open(dest / "manifest.json", "w"), indent=1)
        sys.exit(1)

    # Jangan panggil Binance kalau probe sudah bilang mati — retry 4x dengan
    # timeout 30s membuang ~2 menit tiap run tanpa hasil.
    if pr.get("binance_fapi", {}).get("status") == 200:
        got_binance = binance_exchange_info(dest)
    else:
        got_binance = False
    print(f"  binance exchangeInfo: "
          f"{'TERSIMPAN' if got_binance else 'dilewati (probe gagal)'}", flush=True)

    syms = gate_contracts()
    if args.limit_symbols:
        syms = syms[: args.limit_symbols]
    print(f"  kontrak perp USDT Gate.io: {len(syms)}", flush=True)

    # --- inkremental: hanya simpan baris yang BELUM pernah tercatat.
    # Run pertama menarik ~42 hari (bootstrap), run berikutnya hanya ~24 baris
    # per kontrak per hari. Tanpa ini repo tumbuh ~18 GB/tahun.
    state_f = Path(args.out) / "_state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {}
    frames, done, fails = [], 0, 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(gate_stats, s): s for s in syms}
        for f in as_completed(futs):
            df = f.result()
            if df is None:
                fails += 1
            else:
                last = state.get(df["contract"].iloc[0])
                if last is not None:
                    df = df[df["time"] > last]
                if len(df):
                    frames.append(df)
            done += 1
            if done % 200 == 0:
                with _lock:
                    print(f"  {done}/{len(syms)}  {time.time()-t0:.0f}s", flush=True)

    manifest = {"utc": now.isoformat(), "source": "gateio_contract_stats",
                "interval": INTERVAL, "limit": LIMIT, "probe": pr,
                "n_contracts": len(syms), "n_failed": fails,
                "binance_exchangeinfo": got_binance}
    if frames:
        d = pd.concat(frames, ignore_index=True).drop_duplicates(["contract", "time"])
        d = d.sort_values(["contract", "time"])
        # kolom duplikat dari API (nilainya sama persis dengan pasangannya)
        d = d.drop(columns=[c for c in ("short_liq_usd_new", "long_liq_usd_new")
                            if c in d.columns])
        for c, t in d.groupby("contract")["time"].max().items():
            state[c] = int(t)
        state_f.write_text(json.dumps(state))
        d.to_parquet(dest / "gate_contract_stats.parquet", index=False, compression="zstd")
        manifest.update({
            "rows": int(len(d)), "symbols": int(d["contract"].nunique()),
            "time_min": datetime.fromtimestamp(int(d["time"].min()), timezone.utc).isoformat(),
            "time_max": datetime.fromtimestamp(int(d["time"].max()), timezone.utc).isoformat(),
            "columns": list(d.columns)})
        print(f"  gate_contract_stats: {len(d):,} baris / {d['contract'].nunique()} kontrak "
              f"({manifest['time_min'][:10]} .. {manifest['time_max'][:10]})", flush=True)
    else:
        manifest["status"] = "no_new_data"
        print("  tidak ada baris baru sejak run terakhir", flush=True)

    manifest["elapsed_sec"] = round(time.time() - t0, 1)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1))
    size = sum(p.stat().st_size for p in dest.glob("*")) / 1e6
    print(f"selesai {manifest['elapsed_sec']}s, {size:.1f} MB -> {dest}")


if __name__ == "__main__":
    main()
