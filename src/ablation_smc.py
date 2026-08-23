"""Run ablation SMC (R9-R13) — struktur pasar sebagai patokan entry.

Ini yang TIDAK PERNAH diuji di R0-R8: brief §4 tidak memasukkan struktur pasar,
padahal dokumen strategi §4 menempatkan BOS/CHoCH sebagai penentu arah utama dan
EMA9 hanya sebagai pengatur waktu masuk.

Aturan main sama dengan R0-R8: long/short terpisah, equal-weight, universe penuh
dan executable, SE di-cluster per tanggal, versi market-neutral dilaporkan.

Biaya: limit order masuk+keluar tanpa slippage (instruksi Dew) = 0.04% round trip.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import stats as S
import ablation as A
import smc as SMC

COST = 0.0004     # limit in + limit out, dianggap selalu fill
UNIVERSES = ("full", "exec")
DIRECTIONS = ("long", "short")


def returns(df, direction, H):
    sign = 1.0 if direction == "long" else -1.0
    fwd = df[f"fwd_{H}h"].to_numpy(float)
    neu = df[f"fwd_{H}h_neutral"].to_numpy(float)
    fund = df[f"funding_paid_{H}h"].to_numpy(float)
    return (sign * fwd, sign * fwd - COST - sign * fund,
            sign * neu, sign * neu - COST - sign * fund)


def describe(sub, direction, H, run, universe, bucket, btype):
    g, n, ng, nn = returns(sub, direction, H)
    d = sub["date_i"].to_numpy()
    rec = {"run": run, "universe": universe, "direction": direction, "horizon_h": H,
           "bucket": bucket, "bucket_type": btype,
           "n_obs": int(np.isfinite(g).sum()),
           "n_days": int(pd.unique(d[np.isfinite(g)]).size),
           "n_symbols": int(sub.loc[np.isfinite(g), "symbol"].nunique())}
    if rec["n_obs"] == 0:
        return rec
    cg, cn = S.cluster_mean(g, d), S.cluster_mean(n, d)
    cng, cnn = S.cluster_mean(ng, d), S.cluster_mean(nn, d)
    tmp = pd.DataFrame({"d": d, "net": n})
    daily = tmp.groupby("d")["net"].mean()
    rec.update({
        "mean_ret_gross": cg["mean"], "t_stat_gross": cg["t"],
        "mean_ret_net": cn["mean"], "t_stat_clustered": cn["t"], "p_value_raw": cn["p"],
        "ci_lo_net": cn["ci_lo"], "ci_hi_net": cn["ci_hi"],
        "mean_ret_neutral": cng["mean"], "t_stat_neutral": cng["t"],
        "mean_ret_neutral_net": cnn["mean"], "t_stat_neutral_net": cnn["t"],
        "hit_rate_net": float(np.nanmean(n > 0)),
        "sharpe_daily_ann": S.sharpe_ann(daily.to_numpy(), H),
        "max_dd": S.max_drawdown(daily.to_numpy(), H),
        "reliable": bool(rec["n_days"] >= C.UNRELIABLE_NDAYS)})
    lo, hi = S.cluster_bootstrap_ci(n, d, reps=C.BOOTSTRAP_REPS, seed=C.SEED)
    rec["boot_ci_lo_net"], rec["boot_ci_hi_net"] = lo, hi
    return rec


def run_buckets(df, bcol, run, universe, btype, horizons=(48,)):
    out = []
    w = df.assign(_b=np.asarray(bcol))
    w = w[w["_b"].notna()]
    for b, sub in w.groupby("_b", sort=True):
        for H in horizons:
            for d in DIRECTIONS:
                out.append(describe(sub, d, H, run, universe, str(b), btype))
    return out


def spread(df, bcol, top, bot, run, universe, H=48):
    w = df.assign(_b=np.asarray(bcol))
    rows = []
    for direction in DIRECTIONS:
        a, b = w[w["_b"] == top], w[w["_b"] == bot]
        if a.empty or b.empty:
            continue
        ga, na, nga, nna = returns(a, direction, H)
        gb, nb, ngb, nnb = returns(b, direction, H)
        da, db = a["date_i"].to_numpy(), b["date_i"].to_numpy()
        r = S.cluster_diff(na, da, nb, db)
        rg = S.cluster_diff(ga, da, gb, db)
        rnn = S.cluster_diff(nna, da, nnb, db)
        rows.append({"run": run, "universe": universe, "direction": direction,
                     "comparison": f"{top} - {bot}", "diff_gross": rg["diff"], "t_gross": rg["t"],
                     "diff_net": r["diff"], "t_stat_clustered": r["t"], "p_value_raw": r["p"],
                     "ci_lo": r["ci_lo"], "ci_hi": r["ci_hi"],
                     "diff_neutral_net": rnn["diff"], "t_neutral_net": rnn["t"],
                     "n_days": r["n_days"], "n_obs": r["n_obs"]})
    return rows


def main():
    t0 = time.time()
    panel = A.load_panel()
    files = sorted((C.DATA / "smc").glob("*.parquet"))
    print(f"memuat SMC dari {len(files)} symbol ...", flush=True)
    s = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    s["date"] = pd.to_datetime(s["date"], utc=True)
    df = panel.merge(s, on=["date", "symbol"], how="inner")
    print(f"panel eligible={len(panel):,}  setelah join SMC={len(df):,}  "
          f"({df.symbol.nunique()} symbol, {df.date.nunique()} hari)", flush=True)

    ev = {v: k for k, v in SMC.EV_NAME.items()}
    rows, spreads, notes = [], [], {}

    for universe in UNIVERSES:
        d = df if universe == "full" else df[df["executable_100usd"]]
        d = d.reset_index(drop=True)
        print(f"\n=== universe={universe} rows={len(d):,} ===", flush=True)

        # R9 — bias struktur SWING (length 50)
        b9 = pd.Series(np.where(d.smc_swing_trend == 1, "swing_BULL",
                       np.where(d.smc_swing_trend == -1, "swing_BEAR", None)), dtype=object)
        rows += run_buckets(d, b9, "R9", universe, "swing_trend")
        spreads += spread(d, b9, "swing_BULL", "swing_BEAR", "R9", universe)

        # R10 — bias struktur INTERNAL (length 5)
        b10 = pd.Series(np.where(d.smc_internal_trend == 1, "int_BULL",
                        np.where(d.smc_internal_trend == -1, "int_BEAR", None)), dtype=object)
        rows += run_buckets(d, b10, "R10", universe, "internal_trend")
        spreads += spread(d, b10, "int_BULL", "int_BEAR", "R10", universe)

        # R11 — jenis event terakhir (swing & internal)
        for col, tag in [("smc_last_swing_ev", "swing"), ("smc_last_int_ev", "int")]:
            b = d[col].map(lambda x: f"{tag}_{SMC.EV_NAME.get(int(x), 'none')}"
                           if pd.notna(x) else None)
            rows += run_buckets(d, b, "R11", universe, f"last_event_{tag}")
            spreads += spread(d, b, f"{tag}_bull_CHoCH", f"{tag}_bear_CHoCH", "R11", universe)
            spreads += spread(d, b, f"{tag}_bull_BOS", f"{tag}_bear_BOS", "R11", universe)

        # R12 — keselarasan swing x internal (3x3)
        lab = {1: "BULL", -1: "BEAR", 0: "NONE"}
        b12 = pd.Series([f"S{lab.get(int(a),'NONE')}|I{lab.get(int(b),'NONE')}"
                         for a, b in zip(d.smc_swing_trend.fillna(0), d.smc_internal_trend.fillna(0))],
                        dtype=object)
        rows += run_buckets(d, b12, "R12", universe, "swing_x_internal")
        spreads += spread(d, b12, "SBULL|IBULL", "SBEAR|IBEAR", "R12", universe)

        # R13 — alur lengkap dokumen strategi §4:
        #        CHoCH menentukan arah -> EMA9 sebagai trigger
        #        (CHoCH internal terjadi dalam 24 jam terakhir DAN ema9_state searah)
        recent = 24
        bull = (d.smc_bars_since_int_bull_choch <= recent)
        bear = (d.smc_bars_since_int_bear_choch <= recent)
        b13 = []
        for bl, br, e9 in zip(bull.fillna(False), bear.fillna(False), d.ema9_state.fillna(0)):
            if bl and not br:
                b13.append("CHoCH_bull+EMA9up" if e9 == 1 else "CHoCH_bull_noEMA")
            elif br and not bl:
                b13.append("CHoCH_bear+EMA9dn" if e9 == -1 else "CHoCH_bear_noEMA")
            else:
                b13.append(None)
        rows += run_buckets(d, pd.Series(b13, dtype=object), "R13", universe, "choch_plus_ema")

    res = pd.DataFrame(rows)
    m = int(((res["universe"] == "full") & (res["horizon_h"] == 48)).sum())
    res["n_tests_bonferroni"] = m
    res["p_value_bonferroni"] = res["p_value_raw"].map(lambda p: S.bonferroni(p, m))
    res = res.sort_values(["run", "universe", "bucket_type", "bucket", "direction"])
    res.to_csv(C.RESULTS / "smc_summary.csv", index=False)
    sp = pd.DataFrame(spreads)
    sp["p_value_bonferroni"] = sp["p_value_raw"].map(lambda p: S.bonferroni(p, m))
    sp.to_csv(C.RESULTS / "smc_spreads.csv", index=False)
    for r_ in ["R9", "R10", "R11", "R12", "R13"]:
        res[res.run == r_].to_csv(C.RESULTS / f"{r_}_smc.csv", index=False)
    notes["n_tests_bonferroni"] = m
    notes["cost_roundtrip"] = COST
    notes["source"] = "Smart Money Concepts [LuxAlgo], CC BY-NC-SA 4.0"
    (C.RESULTS / "smc_notes.json").write_text(json.dumps(notes, indent=1))
    print(f"\nrows={len(res)}  m={m}  {(time.time()-t0)/60:.1f} min -> results/smc_summary.csv")


if __name__ == "__main__":
    main()
