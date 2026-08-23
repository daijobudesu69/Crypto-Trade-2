"""Run R14-R18 — faktor (a) Order Block/FVG, (b) Volume Profile/swing, (c) regime BTC.

Aturan main sama: long/short terpisah, equal-weight, SE cluster per tanggal,
versi market-neutral dilaporkan, biaya limit 0.04% round trip.

PERINGATAN MULTIPLE TESTING: ini keluarga uji ke-15 dan seterusnya. Setiap run
tambahan menaikkan peluang menemukan "sesuatu" secara kebetulan. Kolom
p_value_bonferroni memakai TOTAL uji kumulatif seluruh proyek, bukan hanya
uji di file ini.
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

COST = 0.0004
UNIVERSES = ("full", "exec")
DIRECTIONS = ("long", "short")
PRIOR_TESTS = 264          # kumulatif dari R0-R13 + prioritas 1-3


def rets(df, direction):
    sign = 1.0 if direction == "long" else -1.0
    fwd = df["fwd_48h"].to_numpy(float)
    neu = df["fwd_48h_neutral"].to_numpy(float)
    fund = df["funding_paid_48h"].to_numpy(float)
    return sign * fwd - COST - sign * fund, sign * neu - COST - sign * fund


def describe(sub, direction, run, universe, bucket, btype):
    net, neu = rets(sub, direction)
    d = sub["di"].to_numpy()
    a = S.cluster_mean(net, d)
    b = S.cluster_mean(neu, d)
    return {"run": run, "universe": universe, "direction": direction, "bucket": bucket,
            "bucket_type": btype, "n_obs": a["n_obs"], "n_days": a["n_days"],
            "n_symbols": int(sub["symbol"].nunique()),
            "mean_ret_net": a["mean"], "t_stat_clustered": a["t"], "p_value_raw": a["p"],
            "ci_lo_net": a["ci_lo"], "ci_hi_net": a["ci_hi"],
            "mean_ret_neutral_net": b["mean"], "t_stat_neutral_net": b["t"],
            "hit_rate_net": float(np.nanmean(net > 0))}


def run_buckets(df, bcol, run, universe, btype):
    out = []
    w = df.assign(_b=np.asarray(bcol))
    w = w[pd.notna(w["_b"])]
    for b, sub in w.groupby("_b", sort=True):
        if len(sub) < 200:
            continue
        for d in DIRECTIONS:
            out.append(describe(sub, d, run, universe, str(b), btype))
    return out


def spread(df, bcol, top, bot, run, universe):
    w = df.assign(_b=np.asarray(bcol))
    rows = []
    for direction in DIRECTIONS:
        a, b = w[w["_b"] == top], w[w["_b"] == bot]
        if len(a) < 200 or len(b) < 200:
            continue
        na, _ = rets(a, direction)
        nb, _ = rets(b, direction)
        r = S.cluster_diff(na, a["di"].to_numpy(), nb, b["di"].to_numpy())
        rows.append({"run": run, "universe": universe, "direction": direction,
                     "comparison": f"{top} - {bot}", "diff_net": r["diff"],
                     "t_stat_clustered": r["t"], "p_value_raw": r["p"],
                     "ci_lo": r["ci_lo"], "ci_hi": r["ci_hi"], "n_obs": r["n_obs"]})
    return rows


def qb(df, col, q=5):
    g = df.groupby("di")[col]
    r = g.rank(pct=True, method="first")
    n = g.transform("count")
    b = np.clip(np.ceil(r.to_numpy() * q), 1, q)
    b = np.where((n.to_numpy() >= q * 3) & np.isfinite(df[col].to_numpy()), b, np.nan)
    return pd.Series([f"Q{int(x)}" if np.isfinite(x) else None for x in b],
                     index=df.index, dtype=object)


def main():
    t0 = time.time()
    pan = A.load_panel()
    pan["dt"] = pd.to_datetime(pan["date"], utc=True)
    pan["di"] = pan["dt"].values.astype("datetime64[D]").astype(np.int64)
    ext = pd.concat([pd.read_parquet(f) for f in sorted((C.DATA / "ext").glob("*.parquet"))],
                    ignore_index=True)
    ext["date"] = pd.to_datetime(ext["date"], utc=True)
    d = pan.merge(ext, on=["date", "symbol"], how="inner")
    print(f"panel={len(pan):,}  setelah join faktor tambahan={len(d):,} "
          f"({d.symbol.nunique()} symbol, {d.date.nunique()} hari)", flush=True)

    rows, spreads = [], []
    for universe in UNIVERSES:
        u = d if universe == "full" else d[d["executable_100usd"]]
        u = u.reset_index(drop=True)
        print(f"\n=== universe={universe} rows={len(u):,} ===", flush=True)

        # ---- R14 Fair Value Gap
        b = pd.Series(np.select(
            [u.fvg_in_bull == 1, u.fvg_in_bear == 1],
            ["in_bull_FVG", "in_bear_FVG"], default="outside"), dtype=object)
        rows += run_buckets(u, b, "R14", universe, "fvg_position")
        spreads += spread(u, b, "in_bull_FVG", "in_bear_FVG", "R14", universe)
        rows += run_buckets(u, qb(u, "fvg_dist_bull"), "R14", universe, "fvg_dist_bull_quintile")

        # ---- R15 Order Block
        b = pd.Series(np.select(
            [u.ob_in_bull == 1, u.ob_in_bear == 1],
            ["in_bull_OB", "in_bear_OB"], default="outside"), dtype=object)
        rows += run_buckets(u, b, "R15", universe, "ob_position")
        spreads += spread(u, b, "in_bull_OB", "in_bear_OB", "R15", universe)
        u2 = u.assign(ob_imb=u.ob_bull_n - u.ob_bear_n)
        rows += run_buckets(u2, qb(u2, "ob_imb"), "R15", universe, "ob_imbalance_quintile")
        spreads += spread(u2, qb(u2, "ob_imb"), "Q5", "Q1", "R15", universe)

        # ---- R16 Volume Profile
        rows += run_buckets(u, qb(u, "vp_poc_dist"), "R16", universe, "poc_dist_quintile")
        spreads += spread(u, qb(u, "vp_poc_dist"), "Q5", "Q1", "R16", universe)
        rows += run_buckets(u, qb(u, "vp_node_rank"), "R16", universe, "node_rank_quintile")
        spreads += spread(u, qb(u, "vp_node_rank"), "Q5", "Q1", "R16", universe)
        b = pd.Series(np.select([u.vp_value_area == 1, u.vp_value_area == -1],
                                ["above_VA", "below_VA"], default="inside_VA"), dtype=object)
        rows += run_buckets(u, b, "R16", universe, "value_area")
        spreads += spread(u, b, "above_VA", "below_VA", "R16", universe)

        # ---- R17 jarak ke swing level
        rows += run_buckets(u, qb(u, "dist_swing_high"), "R17", universe, "dist_swing_high_q")
        spreads += spread(u, qb(u, "dist_swing_high"), "Q5", "Q1", "R17", universe)
        rows += run_buckets(u, qb(u, "dist_swing_low"), "R17", universe, "dist_swing_low_q")
        spreads += spread(u, qb(u, "dist_swing_low"), "Q5", "Q1", "R17", universe)

    # ---- R18 split regime BTC (hanya universe executable)
    print("\n=== R18 regime BTC ===", flush=True)
    dm = pd.read_csv(C.DATA / "daily_market.csv", parse_dates=["date"])
    dm["date"] = pd.to_datetime(dm["date"], utc=True)
    btc = dm[["date", "btc_ret_24h"]].copy()
    btc["btc_trend_7d"] = btc["btc_ret_24h"].rolling(7, min_periods=5).sum()
    e = d[d["executable_100usd"]].merge(btc, on="date", how="left")
    e["regime"] = np.where(e["btc_trend_7d"] > 0, "BTC_bull", "BTC_bear")
    e["zrank"] = e.groupby("di")["funding_ts_z30"].rank(pct=True, method="first")
    e["H1"] = (e["funding_24h_sum"] <= 0) & (e["zrank"] <= 0.20)
    for reg, sub in e.groupby("regime"):
        rows += run_buckets(sub, pd.Series(["ALL"] * len(sub), index=sub.index, dtype=object),
                            "R18", reg, "baseline")
        rows += run_buckets(sub, pd.Series(np.where(sub.H1, "H1_signal", "rest"), dtype=object),
                            "R18", reg, "H1")
        spreads += spread(sub, pd.Series(np.where(sub.H1, "H1_signal", "rest"), dtype=object),
                          "H1_signal", "rest", "R18", reg)
        for f_, nm in [(qb(sub, "funding_xs_pct"), "R1_funding_xs"),
                       (qb(sub, "funding_ts_z30"), "R2_funding_tsz")]:
            spreads += spread(sub, f_, "Q5", "Q1", "R18_" + nm, reg)

    res = pd.DataFrame(rows)
    m = PRIOR_TESTS + int((res["universe"] == "full").sum())
    res["n_tests_cumulative"] = m
    res["p_value_bonferroni"] = res["p_value_raw"].map(lambda p: S.bonferroni(p, m))
    res.to_csv(C.RESULTS / "ext_summary.csv", index=False)
    sp = pd.DataFrame(spreads)
    sp["p_value_bonferroni"] = sp["p_value_raw"].map(lambda p: S.bonferroni(p, m))
    sp.to_csv(C.RESULTS / "ext_spreads.csv", index=False)
    (C.RESULTS / "ext_notes.json").write_text(json.dumps(
        {"cost": COST, "n_tests_cumulative": m,
         "source_a": "Smart Money Concepts [LuxAlgo] CC BY-NC-SA 4.0"}, indent=1))
    print(f"\nrows={len(res)} spreads={len(sp)} m_kumulatif={m} "
          f"{(time.time()-t0)/60:.1f} min -> results/ext_summary.csv")


if __name__ == "__main__":
    main()
