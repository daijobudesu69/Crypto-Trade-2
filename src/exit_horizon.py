"""Uji horizon exit pada sinyal H1 — menjawab: kenapa 48 jam?

Panel utama hanya punya label 24/48/72 jam. Di sini dihitung ulang dari klines
1H untuk horizon 8/12/24/36/48/72/96 jam, plus funding aktual per horizon.
"""
from __future__ import annotations
import json, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C, features as F

HORIZONS = (8, 12, 24, 36, 48, 72, 96)
OUTD = C.DATA / "horizons"


def build(sym: str):
    k, _ = F.load_klines(sym)
    if k.empty or len(k) < 24 * 40:
        return None
    f = F.load_funding(sym)
    idx, op = k.index, k["open"].to_numpy(float)
    hi, lo = k["high"].to_numpy(float), k["low"].to_numpy(float)
    n = len(op)
    sel = np.where(idx.hour == 0)[0]
    if len(sel) < 40:
        return None
    out = pd.DataFrame({"date": idx[sel], "symbol": sym, "entry": op[sel]})
    for H in HORIZONS:
        fw = np.full(n, np.nan)
        if n > H:
            fw[: n - H] = op[H:] / op[: n - H] - 1.0
        out[f"fwd_{H}"] = fw[sel]
        # MAE/MFE dalam window H
        pad = np.full(H, np.nan)
        wh = np.lib.stride_tricks.sliding_window_view(np.concatenate([hi, pad]), H)[sel]
        wl = np.lib.stride_tricks.sliding_window_view(np.concatenate([lo, pad]), H)[sel]
        with np.errstate(invalid="ignore"):
            out[f"mae_{H}"] = np.nanmin(wl, axis=1) / op[sel] - 1
            out[f"mfe_{H}"] = np.nanmax(wh, axis=1) / op[sel] - 1
    if not f.empty:
        rt = f["rate"]; ft = rt.index.to_numpy()
        cv = np.concatenate([[0.0], rt.cumsum().to_numpy()])
        last = rt.index[-1]
        b = np.searchsorted(ft, idx[sel].to_numpy(), side="right")
        for H in HORIZONS:
            end_t = idx[sel] + pd.Timedelta(hours=H)
            e = np.searchsorted(ft, end_t.to_numpy(), side="right")
            out[f"fund_{H}"] = np.where(np.asarray(end_t > last), np.nan, cv[e] - cv[b])
    else:
        for H in HORIZONS:
            out[f"fund_{H}"] = np.nan
    out = out[(out.date >= C.START_DATE) & (out.date <= C.END_DATE)]
    if out.empty:
        return None
    OUTD.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUTD / f"{sym}.parquet", index=False)
    return len(out)


def _w(s):
    try:
        return s, ("ok" if build(s) else "empty")
    except Exception as e:
        return s, f"ERR {type(e).__name__}: {e}"


def main():
    man = json.loads((C.RAW / "manifest.json").read_text())
    syms = sorted(s for s, v in man["symbols"].items() if v["klines"] or v["daily"])
    t0 = time.time(); ok = bad = 0; errs = []
    with ProcessPoolExecutor(max_workers=10) as ex:
        for i, fu in enumerate(as_completed([ex.submit(_w, s) for s in syms]), 1):
            s, st = fu.result()
            ok += st == "ok"
            if st != "ok":
                bad += 1
                if st != "empty" and len(errs) < 5: errs.append((s, st))
            if i % 250 == 0: print(f"  {i}/{len(syms)} ok={ok} {(time.time()-t0)/60:.1f}m", flush=True)
    print(f"done ok={ok} skip={bad} in {(time.time()-t0)/60:.1f} min")
    for s, e in errs: print("  ERR", s, e)


if __name__ == "__main__":
    main()
