"""Stage 1.1 - run ablation R0..R8 (brief §4).

Aturan yang dipatuhi:
  * satu run per faktor, tidak ditumpuk
  * long dan short DIPISAH (short return = -1 x fwd return)
  * bobot portfolio equal-weight (konsisten notional tetap $6, brief §2.4)
  * setiap run dijalankan DUA KALI: universe penuh dan universe executable (§2.6)
  * semua metrik dalam PERSEN return, bukan dollar (§5)
  * standard error di-cluster per tanggal (§1 jebakan #2)
  * versi market-neutral dilaporkan (§1 jebakan #3)
  * tidak ada faktor/filter/parameter di luar §4
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

UNIVERSES = ("full", "exec", "live_diag")
DIRECTIONS = ("long", "short")


# ------------------------------------------------------------------ data
def load_panel() -> pd.DataFrame:
    parts = sorted(C.PANEL.glob("month=*/part.parquet"))
    df = pd.concat([pd.read_parquet(p) for p in parts], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df = df[df["eligible"]].copy()
    df["date_i"] = df["date"].values.astype("datetime64[D]").astype(np.int64)
    return df


def returns(df: pd.DataFrame, direction: str, H: int, slippage: float | None = None):
    """-> (gross, net, neutral_gross, neutral_net) dalam persen return."""
    sign = 1.0 if direction == "long" else -1.0
    cost = C.FEE_ROUNDTRIP + (C.SLIPPAGE_ROUNDTRIP if slippage is None else slippage)
    fwd = df[f"fwd_{H}h"].to_numpy(dtype=float)
    neu = df[f"fwd_{H}h_neutral"].to_numpy(dtype=float)
    fund = df[f"funding_paid_{H}h"].to_numpy(dtype=float)
    gross = sign * fwd
    net = sign * fwd - cost - sign * fund
    n_gross = sign * neu
    n_net = sign * neu - cost - sign * fund
    return gross, net, n_gross, n_net


# ------------------------------------------------------------------ bucketing
def qbucket_by_date(df: pd.DataFrame, col: str, q: int, prefix: str = "Q") -> pd.Series:
    """Bucket kuantil CROSS-SECTIONAL per tanggal (bukan pooled) supaya ukuran
    bucket seimbang sepanjang waktu dan tidak menyerap drift level faktor."""
    g = df.groupby("date_i")[col]
    r = g.rank(pct=True, method="first")
    n = g.transform("count")
    b = np.ceil(r.to_numpy() * q)
    b = np.clip(b, 1, q)
    b = np.where((n.to_numpy() >= q * 3) & np.isfinite(df[col].to_numpy()), b, np.nan)
    out = pd.Series(np.where(np.isfinite(b), [f"{prefix}{int(x)}" if np.isfinite(x) else ""
                                              for x in b], None), index=df.index, dtype=object)
    return out


def pct_bucket(df: pd.DataFrame, col: str, width: int, prefix: str) -> pd.Series:
    """Bucket dari kolom yang SUDAH berupa persentil 0-100 (funding_xs_pct)."""
    v = df[col].to_numpy(dtype=float)
    b = np.ceil(v / width)
    b = np.clip(b, 1, 100 // width)
    return pd.Series([f"{prefix}{int(x)}" if np.isfinite(x) else None for x in b],
                     index=df.index, dtype=object)


# ------------------------------------------------------------------ metrik
def describe(sub: pd.DataFrame, direction: str, H: int, run: str, universe: str,
             bucket: str, bucket_type: str, do_boot: bool) -> dict:
    gross, net, n_gross, n_net = returns(sub, direction, H)
    d = sub["date_i"].to_numpy()
    rec = {
        "run": run, "universe": universe, "direction": direction, "horizon_h": H,
        "bucket": bucket, "bucket_type": bucket_type,
        "n_obs": int(np.isfinite(gross).sum()),
        "n_days": int(pd.unique(d[np.isfinite(gross)]).size),
        "n_symbols": int(sub.loc[np.isfinite(gross), "symbol"].nunique()),
    }
    if rec["n_obs"] == 0:
        return rec

    cm_g = S.cluster_mean(gross, d)
    cm_n = S.cluster_mean(net, d)
    cm_ng = S.cluster_mean(n_gross, d)
    cm_nn = S.cluster_mean(n_net, d)

    rec.update({
        "mean_ret_gross": cm_g["mean"], "se_gross": cm_g["se"], "t_stat_gross": cm_g["t"],
        "median_ret_gross": float(np.nanmedian(gross)),
        "mean_ret_net": cm_n["mean"], "se_net": cm_n["se"],
        "t_stat_clustered": cm_n["t"], "p_value_raw": cm_n["p"],
        "ci_lo_net": cm_n["ci_lo"], "ci_hi_net": cm_n["ci_hi"],
        "median_ret_net": float(np.nanmedian(net)),
        "mean_ret_neutral": cm_ng["mean"], "t_stat_neutral": cm_ng["t"],
        "ci_lo_neutral": cm_ng["ci_lo"], "ci_hi_neutral": cm_ng["ci_hi"],
        "mean_ret_neutral_net": cm_nn["mean"], "t_stat_neutral_net": cm_nn["t"],
        "hit_rate_gross": float(np.nanmean(gross > 0)),
        "hit_rate_net": float(np.nanmean(net > 0)),
    })

    # deret harian bucket = portfolio equal-weight di dalam hari
    tmp = pd.DataFrame({"d": d, "net": net, "gross": gross})
    daily = tmp.groupby("d")["net"].mean()
    rec["mean_ret_net_dayeq"] = float(daily.mean())
    rec["sharpe_daily_ann"] = S.sharpe_ann(daily.to_numpy(), H)
    rec["max_dd"] = S.max_drawdown(daily.to_numpy(), H)

    # sensitivitas slippage (§5.1) - hanya mean, biaya adalah pergeseran konstan
    for sl in C.SLIPPAGE_SENSITIVITY:
        _, nt, _, _ = returns(sub, direction, H, slippage=sl)
        rec[f"mean_net_slip{int(sl*10000)}bp"] = float(np.nanmean(nt))

    rec["funding_cov"] = float(np.isfinite(sub[f"funding_paid_{H}h"].to_numpy()).mean())
    rec["mean_stop_pct_1atr"] = float(np.nanmean(sub["stop_pct_1atr"].to_numpy()))
    rec["mean_funding_paid"] = float(np.nanmean(sub[f"funding_paid_{H}h"].to_numpy()))
    rec["reliable"] = bool(rec["n_days"] >= C.UNRELIABLE_NDAYS)

    if do_boot:
        lo, hi = S.cluster_bootstrap_ci(net, d, reps=C.BOOTSTRAP_REPS, seed=C.SEED)
        rec["boot_ci_lo_net"], rec["boot_ci_hi_net"] = lo, hi
    return rec


def run_buckets(df: pd.DataFrame, bucket_col: pd.Series, run: str, universe: str,
                bucket_type: str, horizons=None) -> list[dict]:
    out = []
    horizons = horizons or C.HORIZONS_H
    work = df.assign(_b=bucket_col.to_numpy())
    work = work[work["_b"].notna()]
    for b, sub in work.groupby("_b", sort=True):
        for H in horizons:
            for direction in DIRECTIONS:
                out.append(describe(sub, direction, H, run, universe, str(b), bucket_type,
                                    do_boot=(H == C.PRIMARY_H)))
    return out


def spread(df: pd.DataFrame, bcol: pd.Series, top: str, bot: str, run: str,
           universe: str, H: int) -> list[dict]:
    work = df.assign(_b=bcol.to_numpy())
    rows = []
    for direction in DIRECTIONS:
        a = work[work["_b"] == top]
        b = work[work["_b"] == bot]
        if a.empty or b.empty:
            continue
        ga, na, nga, nna = returns(a, direction, H)
        gb, nb, ngb, nnb = returns(b, direction, H)
        da, db = a["date_i"].to_numpy(), b["date_i"].to_numpy()
        r = S.cluster_diff(na, da, nb, db)
        rg = S.cluster_diff(ga, da, gb, db)
        rn = S.cluster_diff(nga, da, ngb, db)
        rnn = S.cluster_diff(nna, da, nnb, db)
        rows.append({"run": run, "universe": universe, "direction": direction, "horizon_h": H,
                     "comparison": f"{top} - {bot}",
                     "diff_gross": rg["diff"], "t_gross": rg["t"], "p_gross": rg["p"],
                     "diff_net": r["diff"], "se": r["se"],
                     "t_stat_clustered": r["t"], "p_value_raw": r["p"],
                     "ci_lo": r["ci_lo"], "ci_hi": r["ci_hi"],
                     "diff_neutral_gross": rn["diff"], "t_neutral_gross": rn["t"],
                     "ci_lo_neutral": rn["ci_lo"], "ci_hi_neutral": rn["ci_hi"],
                     "diff_neutral_net": rnn["diff"], "t_neutral_net": rnn["t"],
                     "n_days": r["n_days"], "n_obs": r["n_obs"]})
    return rows


# ------------------------------------------------------------------ runs
def main() -> None:
    t0 = time.time()
    panel = load_panel()
    print(f"panel eligible rows={len(panel):,}  symbols={panel['symbol'].nunique()}  "
          f"days={panel['date'].nunique()}", flush=True)

    all_rows: list[dict] = []
    spread_rows: list[dict] = []
    notes: dict = {}

    for universe in UNIVERSES:
        if universe == "full":
            df = panel
        elif universe == "exec":
            df = panel[panel["executable_100usd"]].copy()
        else:
            # DIAGNOSTIK (di luar spesifikasi brief): executable DAN benar-benar
            # diperdagangkan pada hari itu. Arsip Binance terus menerbitkan klines
            # bervolume nol untuk perp yang sudah mati - lihat FINDINGS §zombie.
            df = panel[panel["executable_100usd"] & (panel["dollar_vol_24h"] > 0)].copy()
        df = df.reset_index(drop=True)
        print(f"\n=== universe={universe}  rows={len(df):,} ===", flush=True)

        # ---- R0 baseline
        b0 = pd.Series(["ALL"] * len(df), index=df.index, dtype=object)
        r0 = run_buckets(df, b0, "R0", universe, "baseline")
        all_rows += r0
        print("  R0 done", flush=True)

        # ---- R1 funding_xs_pct: quintile + decile
        q1 = pct_bucket(df, "funding_xs_pct", 20, "Q")
        d1 = pct_bucket(df, "funding_xs_pct", 10, "D")
        all_rows += run_buckets(df, q1, "R1", universe, "quintile")
        all_rows += run_buckets(df, d1, "R1", universe, "decile")
        spread_rows += spread(df, q1, "Q5", "Q1", "R1", universe, C.PRIMARY_H)
        spread_rows += spread(df, d1, "D10", "D1", "R1", universe, C.PRIMARY_H)
        print("  R1 done", flush=True)

        # ---- R2 funding_ts_z30 quintile
        q2 = qbucket_by_date(df, "funding_ts_z30", 5)
        all_rows += run_buckets(df, q2, "R2", universe, "quintile")
        spread_rows += spread(df, q2, "Q5", "Q1", "R2", universe, C.PRIMARY_H)
        print("  R2 done", flush=True)

        # ---- R3 vol_z30 quintile
        q3 = qbucket_by_date(df, "vol_z30", 5)
        all_rows += run_buckets(df, q3, "R3", universe, "quintile")
        spread_rows += spread(df, q3, "Q5", "Q1", "R3", universe, C.PRIMARY_H)
        print("  R3 done", flush=True)

        # ---- R4 ret_24h quintile x liq_tercile
        q4 = qbucket_by_date(df, "ret_24h", 5)
        all_rows += run_buckets(df, q4, "R4", universe, "quintile_pooled")
        spread_rows += spread(df, q4, "Q5", "Q1", "R4", universe, C.PRIMARY_H)
        lt = df["liq_tercile"]
        q4x = pd.Series(np.where(q4.notna() & lt.notna(),
                                 q4.astype(str) + "|L" + lt.fillna(0).astype(int).astype(str),
                                 None), index=df.index, dtype=object)
        all_rows += run_buckets(df, q4x, "R4", universe, "quintile_x_liqtercile")
        for L in (1, 2, 3):
            spread_rows += spread(df, q4x, f"Q5|L{L}", f"Q1|L{L}", "R4", universe, C.PRIMARY_H)
        print("  R4 done", flush=True)

        # ---- R5 atr14_norm quintile (kontrol)
        q5 = qbucket_by_date(df, "atr14_norm", 5)
        all_rows += run_buckets(df, q5, "R5", universe, "quintile")
        spread_rows += spread(df, q5, "Q5", "Q1", "R5", universe, C.PRIMARY_H)
        print("  R5 done", flush=True)

        # ---- R6 funding quintile x liq_tercile
        q6 = pd.Series(np.where(q1.notna() & lt.notna(),
                                q1.astype(str) + "|L" + lt.fillna(0).astype(int).astype(str),
                                None), index=df.index, dtype=object)
        all_rows += run_buckets(df, q6, "R6", universe, "funding_x_liqtercile")
        for L in (1, 2, 3):
            spread_rows += spread(df, q6, f"Q5|L{L}", f"Q1|L{L}", "R6", universe, C.PRIMARY_H)
        print("  R6 done", flush=True)

        # ---- R7 funding quintile x ret_24h quintile
        q7 = pd.Series(np.where(q1.notna() & q4.notna(),
                                q1.astype(str) + "|M" + q4.astype(str).str[1:], None),
                       index=df.index, dtype=object)
        all_rows += run_buckets(df, q7, "R7", universe, "funding_x_momentum")
        print("  R7 done", flush=True)

        # ---- R8 trigger EMA, kondisional pada bucket terbaik R1
        r1_rows = [r for r in all_rows
                   if r["run"] == "R1" and r["universe"] == universe
                   and r["horizon_h"] == C.PRIMARY_H and r["bucket_type"] == "decile"
                   and r.get("n_days", 0) >= C.KEEP_MIN_NDAYS]
        best = None
        for direction in DIRECTIONS:
            cand = [r for r in r1_rows if r["direction"] == direction
                    and np.isfinite(r.get("t_stat_clustered", np.nan))]
            if not cand:
                continue
            top = max(cand, key=lambda r: r["t_stat_clustered"])
            if top["t_stat_clustered"] >= C.KEEP_MIN_TSTAT and top["mean_ret_net"] > 0:
                best = best or {}
                best[direction] = top["bucket"]
        notes[f"R8_conditioning_{universe}"] = best if best else "none_significant"

        for direction in DIRECTIONS:
            cond = (best or {}).get(direction)
            sub = df if cond is None else df[d1 == cond]
            tag = "ALLELIGIBLE" if cond is None else cond
            for feat in ("ema9_state", "ema21_state"):
                bb = pd.Series(np.where(sub[feat].notna(),
                                        feat.replace("_state", "") + "=" +
                                        sub[feat].fillna(0).astype(int).astype(str), None),
                               index=sub.index, dtype=object)
                for b, ss in sub.assign(_b=bb).dropna(subset=["_b"]).groupby("_b"):
                    all_rows.append(describe(ss, direction, C.PRIMARY_H, "R8", universe,
                                             f"{tag}|{b}", f"trigger_{feat}", do_boot=True))
            all_rows.append(describe(sub, direction, C.PRIMARY_H, "R8", universe,
                                     f"{tag}|none", "trigger_none", do_boot=True))
        print("  R8 done", flush=True)

    res = pd.DataFrame(all_rows)

    # ---- koreksi multiple testing (brief §5): m = jumlah uji bucket pada horizon
    # utama, universe penuh, R1..R8, kedua arah.
    m = int(((res["horizon_h"] == C.PRIMARY_H) & (res["universe"] == "full")
             & (res["run"] != "R0")).sum())
    res["n_tests_bonferroni"] = m
    res["p_value_bonferroni"] = res["p_value_raw"].map(lambda p: S.bonferroni(p, m))
    notes["n_tests_bonferroni"] = m

    # Bonferroni "keluarga": hanya bucket di dalam run yang sama (horizon utama,
    # universe penuh, kedua arah). Lebih longgar dari m global, dilaporkan
    # berdampingan supaya pembaca bisa melihat keduanya.
    fam = (res[(res["horizon_h"] == C.PRIMARY_H) & (res["universe"] == "full")]
           .groupby("run")["bucket"].size())
    res["n_tests_family"] = res["run"].map(fam)
    res["p_value_bonferroni_family"] = [
        S.bonferroni(p, int(k)) if np.isfinite(p) and np.isfinite(k) else np.nan
        for p, k in zip(res["p_value_raw"], res["n_tests_family"])]
    notes["n_tests_family"] = {k: int(v) for k, v in fam.items()}

    res = res.sort_values(["run", "universe", "direction", "horizon_h", "bucket_type", "bucket"])
    res.to_csv(C.RESULTS / "summary.csv", index=False)
    names = {"R0": "R0_baseline", "R1": "R1_funding_xs", "R2": "R2_funding_tsz",
             "R3": "R3_vol_z30", "R4": "R4_momentum_liq", "R5": "R5_atr_control",
             "R6": "R6_funding_x_liq", "R7": "R7_funding_x_momentum", "R8": "R8_trigger"}
    for r, nm in names.items():
        res[res["run"] == r].to_csv(C.RESULTS / f"{nm}.csv", index=False)

    sp = pd.DataFrame(spread_rows)
    sp["p_value_bonferroni"] = sp["p_value_raw"].map(lambda p: S.bonferroni(p, m))
    sp.to_csv(C.RESULTS / "spreads.csv", index=False)

    (C.RESULTS / "ablation_notes.json").write_text(json.dumps(notes, indent=1, default=str))
    print(f"\nrows={len(res)}  bonferroni m={m}  done in {(time.time()-t0)/60:.1f} min")
    print(f"-> {C.RESULTS/'summary.csv'}")


if __name__ == "__main__":
    main()
