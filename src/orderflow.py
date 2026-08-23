"""R19-R21 — order flow / CVD dari kolom taker klines.

Dokumen strategi §1.2 memberi bobot 10% ke "CVD divergence", dan §9 menyatakan
takerlongshortRatio "retensi 30 hari, tidak bisa dibacktest". Itu benar untuk
endpoint /futures/data/takerlongshortRatio, TAPI kolom `taker_buy_volume` dan
`taker_buy_quote_volume` ada di setiap baris klines dan arsipnya penuh 2 tahun.
Jadi lapisan ini bisa dibacktest sepenuhnya dan belum pernah diuji.

Ini satu-satunya lapisan ARAH (capital gain) yang tersisa dan belum diuji —
berbeda dari H1 yang ternyata carry.

Fitur (semua dari bar yang closed pada instan keputusan d 00:00 UTC):
  tk_ratio_24h   proporsi volume yang dieksekusi taker BELI dalam 24 jam
  tk_ratio_z30   z-score rasio itu vs 30 hari riwayat symbol sendiri
  cvd_24h        (beli - jual) / total, 24 jam    -> arah tekanan bersih
  cvd_72h        idem 72 jam                       -> tekanan jangka menengah
  cvd_div        divergensi: harga turun tapi CVD naik (akumulasi) = +1,
                 harga naik tapi CVD turun (distribusi) = -1, selain itu 0
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import features as F

OUTD = C.DATA / "orderflow"


def build(sym: str):
    d = C.RAW_KLINES / sym
    if not d.is_dir():
        return None
    frames = []
    for p in sorted(d.glob(f"{sym}-1h-*.zip")):
        df = F._read_zip_csv(p, 11)
        if df is None or df.empty or df.shape[1] < 11:
            continue
        df = df.iloc[:, :12]
        df.columns = F.KLINE_COLS[: df.shape[1]]
        frames.append(df)
    if not frames:
        return None
    k = pd.concat(frames, ignore_index=True)
    k["open_time"] = F._to_epoch_ms(k["open_time"])
    for c in ("close", "quote_volume", "taker_buy_quote_volume"):
        k[c] = pd.to_numeric(k[c], errors="coerce")
    k = k.dropna(subset=["open_time"]).drop_duplicates("open_time").sort_values("open_time")
    k["ts"] = pd.to_datetime(k["open_time"], unit="ms", utc=True)
    k = k.set_index("ts")[["close", "quote_volume", "taker_buy_quote_volume"]]
    k = k.reindex(pd.date_range(k.index[0].floor("h"), k.index[-1].floor("h"),
                                freq="h", tz="UTC"))
    qv = k["quote_volume"].fillna(0)
    tb = k["taker_buy_quote_volume"].fillna(0)
    net = 2 * tb - qv                      # beli - jual

    out = pd.DataFrame(index=k.index)
    for w, tag in ((24, "24h"), (72, "72h")):
        sq = qv.rolling(w, min_periods=w // 2).sum()
        sn = net.rolling(w, min_periods=w // 2).sum()
        out[f"cvd_{tag}"] = (sn / sq.replace(0, np.nan))
    sq24 = qv.rolling(24, min_periods=12).sum()
    out["tk_ratio_24h"] = tb.rolling(24, min_periods=12).sum() / sq24.replace(0, np.nan)

    # sampel di bar yang closed tepat d 00:00 UTC (bar jam 23:00)
    dec = out[out.index.hour == 23].copy()
    cl = k["close"].ffill()
    dec["close_t"] = cl[cl.index.hour == 23]
    r = dec["tk_ratio_24h"]
    dec["tk_ratio_z30"] = (r - r.rolling(30, min_periods=20).mean()) / \
                          r.rolling(30, min_periods=20).std().replace(0, np.nan)
    # divergensi: arah harga 24 jam vs arah CVD 24 jam
    pr = dec["close_t"].pct_change()
    cv = dec["cvd_24h"]
    dec["cvd_div"] = np.where((pr < 0) & (cv > 0), 1,
                              np.where((pr > 0) & (cv < 0), -1, 0))
    dec["date"] = (dec.index + pd.Timedelta(hours=1)).normalize()
    dec = dec.set_index("date")
    dec = dec[(dec.index >= C.START_DATE) & (dec.index <= C.END_DATE)]
    if dec.empty:
        return None
    dec["symbol"] = sym
    OUTD.mkdir(parents=True, exist_ok=True)
    dec.reset_index().to_parquet(OUTD / f"{sym}.parquet", index=False)
    return len(dec)


def _w(s):
    try:
        return s, ("ok" if build(s) else "empty")
    except Exception as e:
        return s, f"ERR {type(e).__name__}: {e}"


def main():
    man = json.loads((C.RAW / "manifest.json").read_text())
    syms = sorted(s for s, v in man["symbols"].items() if v["klines"] or v["daily"])
    print(f"order flow / CVD untuk {len(syms)} symbol ...", flush=True)
    t0 = time.time(); ok = bad = 0; errs = []
    with ProcessPoolExecutor(max_workers=10) as ex:
        for i, f in enumerate(as_completed([ex.submit(_w, s) for s in syms]), 1):
            s, st = f.result()
            ok += st == "ok"
            if st != "ok":
                bad += 1
                if st != "empty" and len(errs) < 6:
                    errs.append((s, st))
            if i % 200 == 0:
                print(f"  {i}/{len(syms)} ok={ok} {(time.time()-t0)/60:.1f}m", flush=True)
    print(f"done ok={ok} skip={bad} in {(time.time()-t0)/60:.1f} min")
    for s, e in errs:
        print("  ERR", s, e)
    if ok == 0:
        raise SystemExit("nol symbol berhasil")


if __name__ == "__main__":
    main()
