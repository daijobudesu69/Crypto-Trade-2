"""Stage 0 — data logger harian (action plan §2).

Retensi Binance untuk OI / long-short ratio / taker ratio hanya 30 hari, dan
arsip `data.binance.vision/futures/um/daily/metrics/` BERHENTI 13 Januari 2022
(sudah diverifikasi). Artinya data ini hanya ada ke depan: setiap hari tanpa
logger = data hilang permanen, tidak bisa diambil dari manapun.

PENTING — kenapa ini jalan di GitHub Actions, bukan di mesin Dew:
fapi.binance.com tidak dapat diakses dari mesin lokal (ConnectTimeout, semua
domain binance.com diblokir). Runner GitHub Actions tidak terkena blokir itu.

Endpoint (semua publik, tanpa API key):
  /futures/data/openInterestHist            <- 30 hari retensi
  /futures/data/globalLongShortAccountRatio <- 30 hari
  /futures/data/topLongShortPositionRatio   <- 30 hari
  /futures/data/takerlongshortRatio         <- 30 hari
  /fapi/v1/premiumIndex                     <- snapshot, semua symbol sekaligus
  /fapi/v1/ticker/24hr                      <- snapshot, semua symbol sekaligus
  /fapi/v1/exchangeInfo                     <- stepSize/minQty/MIN_NOTIONAL
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

BASE = "https://fapi.binance.com"
OUT = Path(__file__).resolve().parent.parent / "oi_logs"
PERIOD = "1h"
LIMIT = 72                      # 3 hari, tumpang tindih supaya gap tertutup
HIST = [
    ("openInterestHist", "/futures/data/openInterestHist"),
    ("globalLongShortAccountRatio", "/futures/data/globalLongShortAccountRatio"),
    ("topLongShortPositionRatio", "/futures/data/topLongShortPositionRatio"),
    ("takerlongshortRatio", "/futures/data/takerlongshortRatio"),
]
_local = threading.local()
_lock = threading.Lock()


def sess() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = "dew-stage0-logger/1.0"
        s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=16, pool_maxsize=16))
        _local.s = s
    return s


def get(path: str, params: dict | None = None, tries: int = 4):
    delay = 1.0
    for _ in range(tries):
        try:
            r = sess().get(BASE + path, params=params, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (418, 429):          # rate limit
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


def perp_usdt_symbols(info: dict) -> list[str]:
    return sorted(s["symbol"] for s in info["symbols"]
                  if s.get("contractType") == "PERPETUAL"
                  and s.get("quoteAsset") == "USDT"
                  and s.get("status") == "TRADING")


def flatten_exchange_info(info: dict) -> pd.DataFrame:
    rows = []
    for s in info["symbols"]:
        if s.get("contractType") != "PERPETUAL" or s.get("quoteAsset") != "USDT":
            continue
        f = {x["filterType"]: x for x in s.get("filters", [])}
        rows.append({
            "symbol": s["symbol"], "status": s.get("status"),
            "pricePrecision": s.get("pricePrecision"),
            "quantityPrecision": s.get("quantityPrecision"),
            "stepSize": f.get("LOT_SIZE", {}).get("stepSize"),
            "minQty": f.get("LOT_SIZE", {}).get("minQty"),
            "maxQty": f.get("LOT_SIZE", {}).get("maxQty"),
            "tickSize": f.get("PRICE_FILTER", {}).get("tickSize"),
            "minNotional": f.get("MIN_NOTIONAL", {}).get("notional"),
            "onboardDate": s.get("onboardDate"),
        })
    return pd.DataFrame(rows)


def fetch_hist(sym: str) -> dict:
    out = {}
    for name, path in HIST:
        j = get(path, {"symbol": sym, "period": PERIOD, "limit": LIMIT})
        if isinstance(j, list) and j:
            df = pd.DataFrame(j)
            df["symbol"] = sym
            out[name] = df
        time.sleep(0.02)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit-symbols", type=int, default=0)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    t0 = time.time()
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    dest = Path(args.out) / f"date={day}"
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Stage 0 logger — {now.isoformat()} -> {dest}", flush=True)

    info = get("/fapi/v1/exchangeInfo")
    if info is None:
        print("FATAL: exchangeInfo tidak bisa diambil", file=sys.stderr)
        sys.exit(1)
    ex = flatten_exchange_info(info)
    ex.to_parquet(dest / "exchangeInfo.parquet", index=False, compression="zstd")
    syms = perp_usdt_symbols(info)
    if args.limit_symbols:
        syms = syms[: args.limit_symbols]
    print(f"  exchangeInfo: {len(ex)} symbol perp USDT ({len(syms)} TRADING)", flush=True)

    for nm, path in [("premiumIndex", "/fapi/v1/premiumIndex"),
                     ("ticker24hr", "/fapi/v1/ticker/24hr")]:
        j = get(path)
        if j:
            pd.DataFrame(j).to_parquet(dest / f"{nm}.parquet", index=False, compression="zstd")
            print(f"  {nm}: {len(j)} baris", flush=True)

    buckets = {n: [] for n, _ in HIST}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex_:
        futs = {ex_.submit(fetch_hist, s): s for s in syms}
        for f in as_completed(futs):
            for k, v in f.result().items():
                buckets[k].append(v)
            done += 1
            if done % 100 == 0:
                with _lock:
                    print(f"  {done}/{len(syms)} symbol  {time.time()-t0:.0f}s", flush=True)

    manifest = {"utc": now.isoformat(), "date": day, "n_symbols": len(syms),
                "period": PERIOD, "limit": LIMIT, "files": {}}
    for name, frames in buckets.items():
        if not frames:
            print(f"  WARNING: {name} kosong", flush=True)
            continue
        df = pd.concat(frames, ignore_index=True)
        tcol = "timestamp" if "timestamp" in df.columns else "createTime"
        if tcol in df.columns:
            df = df.drop_duplicates(subset=["symbol", tcol])
        df.to_parquet(dest / f"{name}.parquet", index=False, compression="zstd")
        manifest["files"][name] = {"rows": int(len(df)),
                                   "symbols": int(df["symbol"].nunique())}
        print(f"  {name}: {len(df):,} baris / {df['symbol'].nunique()} symbol", flush=True)

    manifest["elapsed_sec"] = round(time.time() - t0, 1)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=1))
    size = sum(p.stat().st_size for p in dest.glob("*")) / 1e6
    print(f"selesai {manifest['elapsed_sec']}s, {size:.1f} MB -> {dest}")


if __name__ == "__main__":
    main()
