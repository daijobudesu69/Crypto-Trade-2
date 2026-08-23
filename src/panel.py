"""Stage 1.1 - perakitan panel: fitur cross-sectional, eksekutabilitas, agregat pasar.

Dijalankan setelah features.py menghasilkan data/interim/{SYMBOL}.parquet.
Output:
  data/panel.parquet/month=YYYY-MM/part.parquet   (partisi bulanan, brief §3.3)
  data/universe_log.csv                            (jumlah symbol eligible per hari)
  data/daily_market.csv                            (return BTC + agregat cross-section)
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

INTERIM = C.DATA / "interim"


def floor_to_step(qty: np.ndarray, step: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.floor(qty / step + 1e-9) * step


def add_executability(df: pd.DataFrame) -> pd.DataFrame:
    """Evaluasi per (tanggal, symbol) - brief §2.5. Bukan sekali di awal:
    notional tetap $6 tapi harga bergerak 2 tahun, jadi constraint time-varying."""
    step = df["step_size"].to_numpy(dtype=float)
    close = df["close_t"].to_numpy(dtype=float)
    min_qty = step if C.ASSUME_MINQTY_EQ_STEPSIZE else np.full_like(step, np.nan)
    min_not = np.where(df["symbol"].isin(C.MIN_NOTIONAL_OVERRIDE).to_numpy(),
                       df["symbol"].map(C.MIN_NOTIONAL_OVERRIDE).to_numpy(dtype=float),
                       C.DEFAULT_MIN_NOTIONAL)
    qty_ideal = C.NOTIONAL / close
    qty_actual = floor_to_step(qty_ideal, step)
    notional_actual = qty_actual * close
    quant_err = np.abs(notional_actual - C.NOTIONAL) / C.NOTIONAL

    df["min_qty_assumed"] = min_qty
    df["min_notional_assumed"] = min_not
    df["qty_ideal"] = qty_ideal
    df["qty_actual"] = qty_actual
    df["notional_actual"] = notional_actual
    df["quant_err"] = quant_err
    cond_a = min_not <= C.NOTIONAL
    cond_b = qty_actual >= min_qty
    df["exec_cond_a_min_notional"] = cond_a
    df["exec_cond_b_min_qty"] = cond_b
    for tol in C.QUANT_TOL_SENSITIVITY:
        df[f"executable_tol{int(tol*100)}"] = cond_a & cond_b & (quant_err <= tol)
    df["executable_100usd"] = df[f"executable_tol{int(C.QUANT_TOL*100)}"]
    for mn in C.MIN_NOTIONAL_SENSITIVITY:
        df[f"executable_mn{int(mn)}"] = (mn <= C.NOTIONAL) & cond_b & (quant_err <= C.QUANT_TOL)
    return df


def main() -> None:
    t0 = time.time()
    files = sorted(INTERIM.glob("*.parquet"))
    print(f"loading {len(files)} per-symbol frames ...", flush=True)
    parts = [pd.read_parquet(f) for f in files]
    df = pd.concat(parts, ignore_index=True)
    del parts
    df["date"] = pd.to_datetime(df["date"], utc=True)
    print(f"raw rows={len(df):,}  symbols={df['symbol'].nunique()}", flush=True)

    # ---------------------------------------------------------- delisting
    last_date = pd.to_datetime(df["last_data_date"], utc=True)
    end = pd.Timestamp(C.END_DATE, tz="UTC")
    df["is_delisted_in_window"] = last_date < end - pd.Timedelta(days=2)

    # ---------------------------------------------------------- eligibility (brief §2.3)
    df["eligible"] = (
        (df["n_hist_days"] >= C.MIN_HISTORY_DAYS)
        & df["close_t"].notna() & (df["close_t"] > 0)
        & df["entry_open"].notna() & (df["entry_open"] > 0)
        & df["step_size"].notna()
        & ~df["is_benchmark"]
    )

    df = add_executability(df)

    # ---------------------------------------------------------- cross-sectional
    el = df["eligible"].to_numpy()
    sub = df.loc[el]
    g = sub.groupby("date", sort=False)
    df.loc[el, "funding_xs_pct"] = (g["funding_24h_sum"].rank(pct=True, method="average") * 100).to_numpy()
    df.loc[el, "funding_xs_rank"] = g["funding_24h_sum"].rank(method="average").to_numpy()
    df.loc[el, "n_eligible_today"] = g["symbol"].transform("size").to_numpy()

    # tercile likuiditas cross-sectional harian (1 = paling tipis)
    pr = g["adv_usd_30"].rank(pct=True, method="first")
    terc = np.ceil(pr.to_numpy() * 3.0)
    terc = np.clip(terc, 1, 3)
    n_per_day = g["adv_usd_30"].transform("count").to_numpy()
    terc = np.where(n_per_day >= 6, terc, np.nan)
    df.loc[el, "liq_tercile"] = terc

    for H in C.HORIZONS_H:
        col = f"fwd_{H}h"
        xs_mean = g[col].transform("mean")
        df.loc[el, f"fwd_{H}h_neutral"] = (sub[col] - xs_mean).to_numpy()

    df["stop_pct_1atr"] = df["atr14_norm"]

    # ---------------------------------------------------------- agregat pasar harian
    btc = df.loc[df["symbol"] == "BTCUSDT", ["date"] + [f"fwd_{H}h" for H in C.HORIZONS_H]
                 + ["ret_24h", "funding_24h_sum"]]
    btc = btc.rename(columns={c: f"btc_{c}" for c in btc.columns if c != "date"})

    sub2 = df.loc[el]
    gg = sub2.groupby("date")
    daily = pd.DataFrame({
        "n_eligible": gg.size(),
        "n_executable": gg["executable_100usd"].sum(),
        "xs_mean_fwd_48h": gg["fwd_48h"].mean(),
        "xs_std_fwd_48h": gg["fwd_48h"].std(),
        "xs_mean_fwd_24h": gg["fwd_24h"].mean(),
        "xs_mean_fwd_72h": gg["fwd_72h"].mean(),
        "xs_mean_ret_24h": gg["ret_24h"].mean(),
        "xs_mean_funding_24h": gg["funding_24h_sum"].mean(),
        "xs_median_funding_24h": gg["funding_24h_sum"].median(),
        "xs_mean_adv_usd_30": gg["adv_usd_30"].mean(),
        "n_delisted_flagged": gg["is_delisted_in_window"].sum(),
    }).reset_index()
    daily["executable_rate"] = daily["n_executable"] / daily["n_eligible"]
    daily = daily.merge(btc, on="date", how="left")
    daily.to_csv(C.DATA / "daily_market.csv", index=False)

    ulog = daily[["date", "n_eligible", "n_executable", "executable_rate",
                  "n_delisted_flagged"]].copy()
    ulog.to_csv(C.DATA / "universe_log.csv", index=False)

    # ---------------------------------------------------------- tulis panel
    if C.PANEL.exists():
        shutil.rmtree(C.PANEL)
    C.PANEL.mkdir(parents=True, exist_ok=True)
    for m, part in df.groupby("month", sort=True):
        d = C.PANEL / f"month={m}"
        d.mkdir(parents=True, exist_ok=True)
        part.drop(columns=["month"]).to_parquet(d / "part.parquet", index=False)

    meta = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rows": int(len(df)),
        "symbols": int(df["symbol"].nunique()),
        "symbols_eligible_ever": int(df.loc[el, "symbol"].nunique()),
        "symbols_delisted_in_window": int(df.loc[df["is_delisted_in_window"], "symbol"].nunique()),
        "date_min": str(df["date"].min().date()),
        "date_max": str(df["date"].max().date()),
        "n_days": int(df["date"].nunique()),
        "eligible_rows": int(el.sum()),
        "executable_rows": int((df["executable_100usd"] & df["eligible"]).sum()),
        "assumptions": {
            "step_size": "derived from klines volume decimal exponent per (symbol, month)",
            "min_qty": "ASSUMED == step_size (exchangeInfo unreachable)",
            "min_notional": f"ASSUMED {C.DEFAULT_MIN_NOTIONAL} USDT, override {C.MIN_NOTIONAL_OVERRIDE}",
            "slippage_roundtrip": C.SLIPPAGE_ROUNDTRIP,
        },
    }
    (C.DATA / "panel_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))
    print(f"panel written in {(time.time()-t0)/60:.1f} min -> {C.PANEL}")


if __name__ == "__main__":
    main()
