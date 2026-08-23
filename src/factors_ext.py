"""Faktor tambahan (a) Order Block & FVG, (b) Volume Profile & swing level.

(a) Port lanjutan dari "Smart Money Concepts [LuxAlgo]" (Pine v5), © LuxAlgo,
    CC BY-NC-SA 4.0 — bagian yang belum diport di src/smc.py:
      drawFairValueGaps() / deleteFairValueGaps()
      storeOrdeBlock() / deleteOrderBlocks()
    Parameter default LuxAlgo dipertahankan: auto threshold FVG, filter ATR(200)
    untuk order block, mitigasi High/Low, internal length 5.

(b) Pengganti liquidation heatmap sesuai dokumen strategi §6:
      Volume Profile (VPVR) dari klines 1H — POC & posisi harga di profil
      Swing high/low — jarak harga ke swing terdekat

Semua fitur disampel pada instan keputusan (bar 1H yang closed tepat d 00:00 UTC),
konvensi anti-lookahead yang sama dengan src/features.py.
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
import smc as SMC

EXT = C.DATA / "ext"
VP_WINDOW = 720          # 30 hari bar 1H untuk volume profile
VP_BINS = 50
ATR_LEN = 200


def _atr(H, L, Cl, n=ATR_LEN):
    pc = np.concatenate([[np.nan], Cl[:-1]])
    tr = np.nanmax(np.vstack([H - L, np.abs(H - pc), np.abs(L - pc)]), axis=0)
    out = np.full(len(tr), np.nan)
    s = pd.Series(tr).rolling(n, min_periods=n // 2).mean().to_numpy()
    out[:] = s
    return out


# ------------------------------------------------------------------ FVG
def fair_value_gaps(O, H, L, Cl):
    """Port drawFairValueGaps + deleteFairValueGaps (timeframe = chart, 1H)."""
    n = len(Cl)
    delta = np.full(n, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        delta[1:] = (Cl[:-1] - O[:-1]) / (O[:-1] * 100.0)
    cum = np.nancumsum(np.abs(np.nan_to_num(delta)))
    idx = np.arange(1, n + 1)
    thr = cum / idx * 2.0

    bull_n = np.zeros(n, np.int16)
    bear_n = np.zeros(n, np.int16)
    in_bull = np.zeros(n, np.int8)
    in_bear = np.zeros(n, np.int8)
    d_bull = np.full(n, np.nan)
    d_bear = np.full(n, np.nan)

    act_bull = []   # (top, bottom)
    act_bear = []
    for t in range(2, n):
        if np.isfinite(L[t]) and np.isfinite(H[t - 2]) and np.isfinite(Cl[t - 1]):
            if L[t] > H[t - 2] and Cl[t - 1] > H[t - 2] and delta[t] > thr[t]:
                act_bull.append((L[t], H[t - 2]))
            if H[t] < L[t - 2] and Cl[t - 1] < L[t - 2] and -delta[t] > thr[t]:
                act_bear.append((H[t], L[t - 2]))
        # mitigasi
        act_bull = [g for g in act_bull if not (np.isfinite(L[t]) and L[t] < g[1])]
        act_bear = [g for g in act_bear if not (np.isfinite(H[t]) and H[t] > g[0])]
        bull_n[t], bear_n[t] = len(act_bull), len(act_bear)
        c = Cl[t]
        if np.isfinite(c):
            if act_bull:
                in_bull[t] = int(any(g[1] <= c <= g[0] for g in act_bull))
                d_bull[t] = min(abs(c - g[0]) for g in act_bull) / c
            if act_bear:
                in_bear[t] = int(any(g[0] <= c <= g[1] for g in act_bear))
                d_bear[t] = min(abs(c - g[1]) for g in act_bear) / c
    return dict(fvg_bull_n=bull_n, fvg_bear_n=bear_n, fvg_in_bull=in_bull,
                fvg_in_bear=in_bear, fvg_dist_bull=d_bull, fvg_dist_bear=d_bear)


# ------------------------------------------------------------------ Order Block
def order_blocks(H, L, Cl, size=SMC.INTERNAL_LEN):
    """Port storeOrdeBlock + deleteOrderBlocks pada struktur internal."""
    n = len(Cl)
    atr = _atr(H, L, Cl)
    hv = (H - L) >= (2 * atr)
    pH = np.where(hv, L, H)          # parsedHigh ala LuxAlgo
    pL = np.where(hv, H, L)

    piv_hi, piv_lo, _ = SMC.detect_legs(H, L, size)
    bull_n = np.zeros(n, np.int16)
    bear_n = np.zeros(n, np.int16)
    in_bull = np.zeros(n, np.int8)
    in_bear = np.zeros(n, np.int8)
    d_bull = np.full(n, np.nan)
    d_bear = np.full(n, np.nan)

    cur_hi = cur_lo = np.nan
    hi_bar = lo_bar = -1
    hi_cross = lo_cross = True
    obs_bull, obs_bear = [], []       # (barHigh, barLow)
    for t in range(n):
        if piv_hi[t] and t - size >= 0:
            cur_hi, hi_bar, hi_cross = H[t - size], t - size, False
        if piv_lo[t] and t - size >= 0:
            cur_lo, lo_bar, lo_cross = L[t - size], t - size, False
        c = Cl[t]
        if (not hi_cross) and np.isfinite(cur_hi) and np.isfinite(c) and c > cur_hi:
            hi_cross = True
            seg = pL[hi_bar:t + 1]
            if len(seg) and np.isfinite(seg).any():
                k = hi_bar + int(np.nanargmin(seg))
                obs_bull.append((pH[k], pL[k]))
        if (not lo_cross) and np.isfinite(cur_lo) and np.isfinite(c) and c < cur_lo:
            lo_cross = True
            seg = pH[lo_bar:t + 1]
            if len(seg) and np.isfinite(seg).any():
                k = lo_bar + int(np.nanargmax(seg))
                obs_bear.append((pH[k], pL[k]))
        # mitigasi (default HIGHLOW)
        if np.isfinite(L[t]):
            obs_bull = [o for o in obs_bull if not (L[t] < o[1])]
        if np.isfinite(H[t]):
            obs_bear = [o for o in obs_bear if not (H[t] > o[0])]
        obs_bull, obs_bear = obs_bull[-100:], obs_bear[-100:]
        bull_n[t], bear_n[t] = len(obs_bull), len(obs_bear)
        if np.isfinite(c):
            if obs_bull:
                in_bull[t] = int(any(o[1] <= c <= o[0] for o in obs_bull))
                d_bull[t] = min(abs(c - o[0]) for o in obs_bull) / c
            if obs_bear:
                in_bear[t] = int(any(o[1] <= c <= o[0] for o in obs_bear))
                d_bear[t] = min(abs(c - o[1]) for o in obs_bear) / c
    return dict(ob_bull_n=bull_n, ob_bear_n=bear_n, ob_in_bull=in_bull,
                ob_in_bear=in_bear, ob_dist_bull=d_bull, ob_dist_bear=d_bear)


# ------------------------------------------------------------------ Volume Profile
def volume_profile(H, L, Cl, V, at_idx):
    """VPVR pada window trailing. -> jarak ke POC dan posisi harga di profil."""
    tp = (H + L + Cl) / 3.0
    poc_d = np.full(len(at_idx), np.nan)
    node = np.full(len(at_idx), np.nan)
    va = np.full(len(at_idx), np.nan)
    for j, t in enumerate(at_idx):
        a = max(0, t - VP_WINDOW + 1)
        p, w = tp[a:t + 1], V[a:t + 1]
        m = np.isfinite(p) & np.isfinite(w) & (w > 0)
        if m.sum() < 100:
            continue
        p, w = p[m], w[m]
        lo, hi = p.min(), p.max()
        if not (hi > lo):
            continue
        h, edges = np.histogram(p, bins=VP_BINS, range=(lo, hi), weights=w)
        c = Cl[t]
        if not np.isfinite(c) or c <= 0:
            continue
        poc = (edges[np.argmax(h)] + edges[np.argmax(h) + 1]) / 2
        poc_d[j] = (c - poc) / c
        b = int(np.clip(np.searchsorted(edges, c) - 1, 0, VP_BINS - 1))
        node[j] = h[b] / h.max() if h.max() > 0 else np.nan
        # value area 70%: posisi harga relatif terhadap batas VA
        order = np.argsort(h)[::-1]
        cs = np.cumsum(h[order])
        keep = order[: np.searchsorted(cs, 0.7 * h.sum()) + 1]
        va[j] = 1.0 if b > keep.max() else (-1.0 if b < keep.min() else 0.0)
    return poc_d, node, va


# ------------------------------------------------------------------ per symbol
def build_symbol(sym: str):
    k, _ = F.load_klines(sym)
    if k.empty or len(k) < 24 * 40:
        return None
    O = k["open"].to_numpy(float)
    H = k["high"].to_numpy(float)
    L = k["low"].to_numpy(float)
    Cl = k["close"].ffill().to_numpy(float)
    V = k["quote_volume"].to_numpy(float)

    df = pd.DataFrame(index=k.index)
    for d_ in (fair_value_gaps(O, H, L, Cl), order_blocks(H, L, Cl)):
        for kk, vv in d_.items():
            df[kk] = vv

    sw = SMC.structure(H, L, Cl, SMC.SWING_LEN)
    with np.errstate(invalid="ignore"):
        df["dist_swing_high"] = (sw["hi"] - Cl) / Cl
        df["dist_swing_low"] = (Cl - sw["lo"]) / Cl

    dec_mask = df.index.hour == 23
    at = np.where(dec_mask)[0]
    if len(at) == 0:
        return None
    poc, node, va = volume_profile(H, L, Cl, V, at)

    out = df.iloc[at].copy()
    out["vp_poc_dist"] = poc
    out["vp_node_rank"] = node
    out["vp_value_area"] = va
    out["date"] = (out.index + pd.Timedelta(hours=1)).normalize()
    out = out.set_index("date")
    out = out[(out.index >= C.START_DATE) & (out.index <= C.END_DATE)]
    if out.empty:
        return None
    out["symbol"] = sym
    EXT.mkdir(parents=True, exist_ok=True)
    out.reset_index().to_parquet(EXT / f"{sym}.parquet", index=False)
    return len(out)


def _w(s):
    try:
        return s, ("ok" if build_symbol(s) else "empty")
    except Exception as e:
        return s, f"ERR {type(e).__name__}: {e}"


def main():
    man = json.loads((C.RAW / "manifest.json").read_text())
    syms = sorted(s for s, v in man["symbols"].items() if v["klines"] or v["daily"])
    print(f"faktor tambahan (OB/FVG/VPVR/swing) untuk {len(syms)} symbol ...", flush=True)
    t0 = time.time()
    ok = bad = 0
    errs = []
    with ProcessPoolExecutor(max_workers=10) as ex:
        for i, f in enumerate(as_completed([ex.submit(_w, s) for s in syms]), 1):
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
    for s, e in errs[:8]:
        print("  ERR", s, e)


if __name__ == "__main__":
    main()
