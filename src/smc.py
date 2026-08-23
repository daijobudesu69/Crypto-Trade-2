"""Stage 1.1+ — port algoritma Smart Money Concepts [LuxAlgo] ke Python.

Sumber algoritma: "Smart Money Concepts [LuxAlgo]" (Pine v5), © LuxAlgo,
lisensi CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/).
Port ini non-komersial, untuk riset. Share-alike berlaku untuk turunannya.

Yang diport (bagian struktur saja, bukan order block / FVG / zona):
  leg(size)          -> deteksi leg bullish/bearish
  getCurrentStructure-> pivot swing high / swing low
  displayStructure   -> BOS / CHoCH + trend bias

Parameter default LuxAlgo dipertahankan apa adanya:
  swingsLengthInput = 50   (struktur swing)
  internal size     = 5    (struktur internal)
  internalFilterConfluenceInput = false  -> bullishBar/bearishBar = true

Perbedaan yang disengaja: tidak ada bagian gambar/label. Dan `crossover` dihitung
terhadap level pivot bar sebelumnya, sama seperti perilaku ta.crossover di Pine
ketika level berubah.
"""
from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import features as F

SMC_DIR = C.DATA / "smc"
SWING_LEN = 50
INTERNAL_LEN = 5

BULLISH, BEARISH = 1, -1
EV_NONE, EV_BULL_BOS, EV_BULL_CHOCH, EV_BEAR_BOS, EV_BEAR_CHOCH = 0, 1, 2, 3, 4
EV_NAME = {0: "none", 1: "bull_BOS", 2: "bull_CHoCH", 3: "bear_BOS", 4: "bear_CHoCH"}


def detect_legs(H: np.ndarray, L: np.ndarray, size: int):
    """Port leg() + startOfNewLeg(). -> (piv_high_at, piv_low_at) index bar pivot."""
    n = len(H)
    if n <= size + 2:
        return np.zeros(n, bool), np.zeros(n, bool), np.zeros(n, np.int8)
    sw = np.lib.stride_tricks.sliding_window_view
    maxw = np.nanmax(sw(H, size), axis=1)
    minw = np.nanmin(sw(L, size), axis=1)
    new_hi = np.zeros(n, bool)
    new_lo = np.zeros(n, bool)
    # Pine: high[size] > ta.highest(size)  ->  H[t-size] > max(H[t-size+1 .. t])
    with np.errstate(invalid="ignore"):
        new_hi[size:] = H[: n - size] > maxw[1: n - size + 1]
        new_lo[size:] = L[: n - size] < minw[1: n - size + 1]
    leg = np.full(n, -1, np.int8)
    leg[new_lo] = 1          # BULLISH_LEG
    leg[new_hi] = 0          # BEARISH_LEG (if/elif Pine: newLegHigh menang)
    # forward fill, keadaan awal var leg = 0
    idx = np.where(leg >= 0, np.arange(n), 0)
    np.maximum.accumulate(idx, out=idx)
    leg = np.where(np.arange(n) >= (np.argmax(leg >= 0) if (leg >= 0).any() else n),
                   leg[idx], 0).astype(np.int8)
    ch = np.zeros(n, np.int8)
    ch[1:] = leg[1:] - leg[:-1]
    piv_low = ch == 1        # startOfBullishLeg -> pivot LOW terbentuk
    piv_high = ch == -1      # startOfBearishLeg -> pivot HIGH terbentuk
    return piv_high, piv_low, leg


def structure(H, L, Cl, size, other_hi=None, other_lo=None):
    """Port displayStructure(). -> dict array per bar."""
    n = len(Cl)
    piv_hi, piv_lo, _ = detect_legs(H, L, size)
    hi_lvl = np.full(n, np.nan)
    lo_lvl = np.full(n, np.nan)
    trend = np.zeros(n, np.int8)
    event = np.zeros(n, np.int8)

    cur_hi = np.nan
    cur_lo = np.nan
    hi_crossed = True
    lo_crossed = True
    t_bias = 0
    prev_hi = np.nan
    prev_lo = np.nan

    for t in range(n):
        # --- getCurrentStructure: pivot dari bar t-size
        if piv_hi[t] and t - size >= 0:
            cur_hi = H[t - size]
            hi_crossed = False
        if piv_lo[t] and t - size >= 0:
            cur_lo = L[t - size]
            lo_crossed = False

        ev = EV_NONE
        c, cp = Cl[t], Cl[t - 1] if t > 0 else np.nan
        # --- displayStructure: crossover(close, swingHigh)
        extra = True if other_hi is None else (cur_hi != other_hi[t])
        if (not hi_crossed) and np.isfinite(cur_hi) and np.isfinite(cp) and extra:
            if c > cur_hi and cp <= (prev_hi if np.isfinite(prev_hi) else cur_hi):
                ev = EV_BULL_CHOCH if t_bias == BEARISH else EV_BULL_BOS
                hi_crossed = True
                t_bias = BULLISH
        extra = True if other_lo is None else (cur_lo != other_lo[t])
        if ev == EV_NONE and (not lo_crossed) and np.isfinite(cur_lo) and np.isfinite(cp) and extra:
            if c < cur_lo and cp >= (prev_lo if np.isfinite(prev_lo) else cur_lo):
                ev = EV_BEAR_CHOCH if t_bias == BULLISH else EV_BEAR_BOS
                lo_crossed = True
                t_bias = BEARISH

        hi_lvl[t] = cur_hi
        lo_lvl[t] = cur_lo
        trend[t] = t_bias
        event[t] = ev
        prev_hi, prev_lo = cur_hi, cur_lo
    return {"hi": hi_lvl, "lo": lo_lvl, "trend": trend, "event": event}


def bars_since(ev: np.ndarray, codes) -> np.ndarray:
    n = len(ev)
    out = np.full(n, np.nan)
    last = -1
    hit = np.isin(ev, codes)
    for t in range(n):
        if hit[t]:
            last = t
        if last >= 0:
            out[t] = t - last
    return out


def build_symbol(sym: str):
    k, _ = F.load_klines(sym)
    if k.empty or len(k) < 24 * 40:
        return None
    H = k["high"].to_numpy(float)
    L = k["low"].to_numpy(float)
    Cl = k["close"].ffill().to_numpy(float)
    sw = structure(H, L, Cl, SWING_LEN)
    it = structure(H, L, Cl, INTERNAL_LEN, other_hi=sw["hi"], other_lo=sw["lo"])

    df = pd.DataFrame(index=k.index)
    df["smc_swing_trend"] = sw["trend"]
    df["smc_internal_trend"] = it["trend"]
    df["smc_swing_event"] = sw["event"]
    df["smc_internal_event"] = it["event"]
    df["smc_bars_since_swing_ev"] = bars_since(sw["event"], [1, 2, 3, 4])
    df["smc_bars_since_int_bull_choch"] = bars_since(it["event"], [EV_BULL_CHOCH])
    df["smc_bars_since_int_bear_choch"] = bars_since(it["event"], [EV_BEAR_CHOCH])
    df["smc_bars_since_int_ev"] = bars_since(it["event"], [1, 2, 3, 4])
    # posisi harga dalam range swing terakhir (premium/discount ala LuxAlgo)
    rng = sw["hi"] - sw["lo"]
    with np.errstate(invalid="ignore", divide="ignore"):
        df["smc_range_pos"] = np.where(rng > 0, (Cl - sw["lo"]) / rng, np.nan)
    # jenis event terakhir (swing & internal), untuk bucketing kategorikal
    def last_ev(e):
        out = np.zeros(len(e), np.int8)
        cur = 0
        for t in range(len(e)):
            if e[t] != 0:
                cur = e[t]
            out[t] = cur
        return out
    df["smc_last_swing_ev"] = last_ev(sw["event"])
    df["smc_last_int_ev"] = last_ev(it["event"])

    # sampel pada instan keputusan: bar 1H yang CLOSED tepat pukul d 00:00 UTC,
    # yaitu bar yang dibuka d-1 23:00. Sama persis dengan konvensi features.py.
    dec = df[df.index.hour == 23].copy()
    dec["date"] = (dec.index + pd.Timedelta(hours=1)).normalize()
    dec = dec.set_index("date")
    dec = dec[(dec.index >= C.START_DATE) & (dec.index <= C.END_DATE)]
    if dec.empty:
        return None
    dec["symbol"] = sym
    SMC_DIR.mkdir(parents=True, exist_ok=True)
    dec.reset_index().to_parquet(SMC_DIR / f"{sym}.parquet", index=False)
    return len(dec)


def _w(sym):
    try:
        n = build_symbol(sym)
    except Exception as e:
        return sym, f"ERR {type(e).__name__}: {e}"
    return sym, "ok" if n else "empty"


def main():
    import json
    man = json.loads((C.RAW / "manifest.json").read_text())
    syms = sorted(s for s, v in man["symbols"].items() if v["klines"] or v["daily"])
    print(f"SMC LuxAlgo port: {len(syms)} symbol, swing={SWING_LEN} internal={INTERNAL_LEN}",
          flush=True)
    t0 = time.time()
    ok = bad = 0
    errs = []
    with ProcessPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_w, s): s for s in syms}
        for i, f in enumerate(as_completed(futs), 1):
            s, st = f.result()
            if st == "ok":
                ok += 1
            else:
                bad += 1
                if st != "empty":
                    errs.append((s, st))
            if i % 150 == 0:
                print(f"  {i}/{len(syms)} ok={ok} skip={bad} {(time.time()-t0)/60:.1f}m", flush=True)
    print(f"done ok={ok} skip={bad} in {(time.time()-t0)/60:.1f} min")
    for s, e in errs[:10]:
        print("  ERR", s, e)


if __name__ == "__main__":
    main()
