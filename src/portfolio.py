"""Simulasi portofolio dengan sizing DINAMIS — koreksi dari Dew.

Model lama (brief §2.4) memukul rata notional $6.00 tetap. Yang benar:
    margin  = 3% x EKUITAS BERJALAN
    notional = margin x 2 (leverage)
Kalau ekuitas turun ke $90, notional ikut turun ke $5.40. Ini mengubah:
  1. kurva ekuitas jadi majemuk (compounding), bukan linear
  2. gate eksekutabilitas jadi bergerak — notional menyusut, makin banyak koin
     gagal syarat stepSize
Return dalam PERSEN tidak berubah; yang berubah adalah lintasan dolarnya.

Batas dari action plan §0.1 dipatuhi: maksimal 3 posisi terbuka bersamaan.
Karena hold 48 jam, itu berarti ~1,5 entry baru per hari — bukan 3.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import stats as S

COST = 0.0004
MARGIN_FRAC = 0.03
LEVERAGE = 2
MAX_SLOTS = 3
HOLD_DAYS = 2
START_EQUITY = 100.0


def load():
    d = pd.concat([pd.read_parquet(p) for p in sorted(C.PANEL.glob("month=*/part.parquet"))],
                  ignore_index=True)
    d = d[d["eligible"]].copy()
    d["dt"] = pd.to_datetime(d["date"], utc=True)
    d["di"] = d["dt"].values.astype("datetime64[D]").astype(np.int64)
    d["zrank"] = d.groupby("di")["funding_ts_z30"].rank(pct=True, method="first")
    d["net"] = d["fwd_48h"] - COST - d["funding_paid_48h"]
    # hasil dengan stop 3% / target 6% (dari MAE/MFE, bias optimis ~0.08pp di
    # stop ketat - ditandai, jangan dianggap presisi)
    st = 0.03
    hs = d["mae_48h"] <= -st
    ht = d["mfe_48h"] >= 2 * st
    sf = hs & (~ht | (d["mae_bar_48h"] <= d["mfe_bar_48h"]))
    tf = ht & ~sf
    d["net_stop"] = np.where(sf, -st, np.where(tf, 2 * st, d["fwd_48h"])) \
        - COST - d["funding_paid_48h"]
    return d.dropna(subset=["net", "close_t", "step_size"])


def executable(notional, close, step):
    """Gate §2.5 dievaluasi pada notional BERJALAN, bukan $6 tetap."""
    q = np.floor(notional / close / step + 1e-9) * step
    return (q >= step) & (np.abs(q * close - notional) / notional <= C.QUANT_TOL)


def simulate(d, signal_mask, pick, ret_col="net", seed=0, slots=MAX_SLOTS,
             margin_frac=MARGIN_FRAC, dynamic=True):
    """-> (equity_curve, trades DataFrame)"""
    rng = np.random.default_rng(seed)
    s = d[signal_mask].copy()
    days = np.sort(d["di"].unique())
    by_day = {k: v for k, v in s.groupby("di")}
    eq = START_EQUITY
    open_pos = []          # (exit_day, notional, ret)
    curve, trades = [], []
    for day in days:
        # 1. tutup posisi yang jatuh tempo
        still = []
        for xd, nom, r in open_pos:
            if xd <= day:
                eq += nom * r
                trades.append({"exit_day": day, "notional": nom, "ret": r, "pnl": nom * r})
            else:
                still.append((xd, nom, r))
        open_pos = still
        curve.append({"di": day, "equity": eq, "open": len(open_pos)})
        if eq <= 0:
            break
        # 2. buka posisi baru di slot kosong
        free = slots - len(open_pos)
        if free <= 0 or day not in by_day:
            continue
        cand = by_day[day]
        notional = (eq * margin_frac * LEVERAGE) if dynamic else (START_EQUITY * margin_frac * LEVERAGE)
        ok = executable(notional, cand["close_t"].to_numpy(), cand["step_size"].to_numpy())
        cand = cand[ok & np.isfinite(cand[ret_col].to_numpy())]
        if cand.empty:
            continue
        if pick == "random":
            cand = cand.iloc[rng.permutation(len(cand))]
        elif pick == "min_funding":
            cand = cand.sort_values("funding_24h_sum")
        for _, row in cand.head(free).iterrows():
            open_pos.append((day + HOLD_DAYS, notional, row[ret_col]))
    cv = pd.DataFrame(curve)
    return cv, pd.DataFrame(trades)


def stats_of(cv, tr):
    if tr.empty:
        return dict(final=np.nan, ret=np.nan, n=0, maxdd=np.nan, win=np.nan)
    e = cv["equity"].to_numpy()
    peak = np.maximum.accumulate(e)
    years = len(cv) / 365.0
    return dict(final=e[-1], ret=(e[-1] / START_EQUITY) ** (1 / years) - 1,
                n=len(tr), maxdd=float((e / peak - 1).min()),
                win=float((tr["ret"] > 0).mean()), avg=float(tr["ret"].mean()),
                avg_pnl=float(tr["pnl"].mean()))


def main():
    d = load()
    H1 = ((d["funding_24h_sum"] <= 0) & (d["zrank"] <= 0.20)).fillna(False)
    print(f"panel {len(d):,} baris | sinyal H1: {int(H1.sum()):,} "
          f"({H1.sum()/d['di'].nunique():.1f}/hari)\n")
    print("Sizing DINAMIS: margin 3% x ekuitas berjalan x leverage 2x, maks 3 posisi, hold 48 jam\n")
    print(f"{'skema':38s} {'ekuitas akhir':>13s} {'CAGR':>8s} {'trade':>6s} "
          f"{'win':>6s} {'maxDD':>7s} {'$/trade':>8s}")

    rows = []
    def report(label, mask, pick, col, seeds=(0,), **kw):
        outs = []
        for sd in seeds:
            cv, tr = simulate(d, mask, pick, col, seed=sd, **kw)
            outs.append(stats_of(cv, tr))
        f = np.array([o["final"] for o in outs])
        r = np.array([o["ret"] for o in outs])
        dd = np.array([o["maxdd"] for o in outs])
        o0 = outs[0]
        extra = f"  (rentang {f.min():.0f}-{f.max():.0f} dari {len(seeds)} seed)" if len(seeds) > 1 else ""
        print(f"{label:38s} {np.median(f):12.2f}$ {np.median(r)*100:+7.2f}% {o0['n']:6d} "
              f"{o0['win']*100:5.1f}% {np.median(dd)*100:6.1f}% {o0['avg_pnl']:+7.3f}{extra}")
        rows.append({"skema": label, "equity_median": float(np.median(f)),
                     "cagr": float(np.median(r)), "n_trades": o0["n"],
                     "win_rate": o0["win"], "maxdd": float(np.median(dd))})

    seeds = tuple(range(30))
    report("Baseline: koin acak, tanpa filter", pd.Series(True, index=d.index),
           "random", "net", seeds)
    report("Skema 1: H1, pilih acak, tanpa stop", H1, "random", "net", seeds)
    report("Skema 2: H1, pilih acak, stop 3%/6%", H1, "random", "net_stop", seeds)
    report("Skema 3: H1, funding paling negatif", H1, "min_funding", "net")
    report("Skema 3b: + stop 3%/6%", H1, "min_funding", "net_stop")
    print()
    report("Skema 3 dgn notional TETAP $6", H1, "min_funding", "net", dynamic=False)
    report("Skema 3 dgn 6 slot (langgar aturan)", H1, "min_funding", "net", slots=6)
    pd.DataFrame(rows).to_csv(C.RESULTS / "portfolio_sim.csv", index=False)

    # berapa banyak sinyal yang lolos gate pada notional yang menyusut
    print("\ngate eksekutabilitas vs ukuran notional:")
    sig = d[H1]
    for eq in (100, 90, 75, 50, 30):
        nom = eq * MARGIN_FRAC * LEVERAGE
        ok = executable(nom, sig["close_t"].to_numpy(), sig["step_size"].to_numpy())
        print(f"  ekuitas ${eq:3d} -> notional ${nom:5.2f} : {ok.mean()*100:5.1f}% sinyal executable")
    print(f"\n-> {C.RESULTS/'portfolio_sim.csv'}")


if __name__ == "__main__":
    main()
