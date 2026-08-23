"""Stage 1.1 - GATE: distribusi (stepSize x harga) untuk seluruh universe perp.

Dijalankan SEBELUM ablation. Pertanyaan yang dijawab: berapa banyak coin yang
benar-benar bisa ditradingkan pada notional $6 (brief §2.5)?

Constraint dievaluasi per (tanggal, symbol) - bukan sekali di awal - karena
notional tetap $6 sementara harga bergerak 2 tahun.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 50)


def load_panel(cols=None) -> pd.DataFrame:
    parts = sorted(C.PANEL.glob("month=*/part.parquet"))
    df = pd.concat([pd.read_parquet(p, columns=cols) for p in parts], ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df


def _step_label(s: float) -> str:
    if not np.isfinite(s):
        return "n/a"
    return f"{s:g}"


def _price_bucket(p: float) -> str:
    if not np.isfinite(p) or p <= 0:
        return "n/a"
    e = int(np.floor(np.log10(p)))
    e = max(-8, min(5, e))
    lo, hi = 10.0 ** e, 10.0 ** (e + 1)
    return f"[{lo:g}, {hi:g})"


def main() -> None:
    cols = ["date", "symbol", "close_t", "step_size", "step_size_source", "eligible",
            "is_benchmark", "is_delisted_in_window", "adv_usd_30", "liq_tercile",
            "qty_ideal", "qty_actual", "notional_actual", "quant_err",
            "exec_cond_a_min_notional", "exec_cond_b_min_qty",
            "executable_tol5", "executable_tol10", "executable_tol20",
            "executable_100usd", "n_hist_days"]
    df = load_panel(cols)
    el = df[df["eligible"]].copy()
    print(f"panel rows={len(df):,}  eligible (date,symbol) rows={len(el):,}  "
          f"symbols={el['symbol'].nunique()}  days={el['date'].nunique()}")

    # ---------------------------------------------------------------- per symbol
    g = el.groupby("symbol")
    per_sym = pd.DataFrame({
        "n_days": g.size(),
        "step_size_mode": g["step_size"].agg(lambda s: s.mode().iloc[0] if not s.mode().empty else np.nan),
        "step_changed": g["step_size"].nunique() > 1,
        "price_median": g["close_t"].median(),
        "price_min": g["close_t"].min(),
        "price_max": g["close_t"].max(),
        "adv_usd_30_median": g["adv_usd_30"].median(),
        "quant_err_median": g["quant_err"].median(),
        "exec_rate": g["executable_100usd"].mean(),
        "exec_rate_tol5": g["executable_tol5"].mean(),
        "exec_rate_tol20": g["executable_tol20"].mean(),
        "fail_min_qty_rate": (~g["exec_cond_b_min_qty"].mean().astype(bool)).astype(float)
        if False else 1 - g["exec_cond_b_min_qty"].mean(),
        "delisted_in_window": g["is_delisted_in_window"].max(),
    }).reset_index()
    per_sym["step_x_price_median"] = per_sym["step_size_mode"] * per_sym["price_median"]
    per_sym["step_notional_pct_of_6"] = per_sym["step_x_price_median"] / C.NOTIONAL * 100
    per_sym["verdict"] = np.select(
        [per_sym["exec_rate"] >= 0.99, per_sym["exec_rate"] >= 0.5, per_sym["exec_rate"] > 0],
        ["always", "mostly", "sometimes"], default="never")
    per_sym = per_sym.sort_values(["step_x_price_median"], ascending=False)
    per_sym.to_csv(C.RESULTS / "gate_per_symbol.csv", index=False)

    # ---------------------------------------------------------------- cross-tab
    el["step_lbl"] = el["step_size"].map(_step_label)
    el["price_lbl"] = el["close_t"].map(_price_bucket)
    ct = (el.groupby(["step_lbl", "price_lbl"])
            .agg(n_obs=("symbol", "size"),
                 n_symbols=("symbol", "nunique"),
                 exec_rate=("executable_100usd", "mean"),
                 median_quant_err=("quant_err", "median"),
                 median_step_notional=("step_size", lambda s: np.nan))
            .reset_index())
    tmp = el.assign(step_notional=el["step_size"] * el["close_t"])
    ct["median_step_notional"] = (tmp.groupby(["step_lbl", "price_lbl"])["step_notional"]
                                  .median().reindex(pd.MultiIndex.from_frame(
                                      ct[["step_lbl", "price_lbl"]])).to_numpy())
    ct["step_notional_pct_of_6"] = ct["median_step_notional"] / C.NOTIONAL * 100
    ct = ct.sort_values("n_obs", ascending=False)
    ct.to_csv(C.RESULTS / "gate_stepsize_price.csv", index=False)

    # ---------------------------------------------------------------- ringkas
    lines = []
    A = lines.append
    A("# GATE — eksekutabilitas notional $6.00 (brief §2.5)\n")
    A(f"Universe eligible: **{el['symbol'].nunique()} symbol**, "
      f"**{len(el):,}** observasi (tanggal, symbol), {el['date'].nunique()} hari "
      f"({el['date'].min().date()} s/d {el['date'].max().date()}).\n")
    A("`stepSize` diturunkan dari eksponen desimal volume klines per (symbol, bulan); "
      "`minQty` diasumsikan = `stepSize`; `MIN_NOTIONAL` diasumsikan 5 USDT "
      "(BTC 100 / ETH 20). exchangeInfo tidak dapat diakses dari jaringan ini.\n")

    A("\n## 1. Vonis per symbol\n")
    vc = per_sym["verdict"].value_counts().reindex(["always", "mostly", "sometimes", "never"]).fillna(0)
    A("| Vonis | Definisi | n symbol | % |")
    A("|---|---|---:|---:|")
    defs = {"always": "executable ≥99% hari hidupnya", "mostly": "50–99%",
            "sometimes": ">0–50%", "never": "0% — tidak pernah bisa dibuka di $6"}
    for k in ["always", "mostly", "sometimes", "never"]:
        A(f"| {k} | {defs[k]} | {int(vc[k])} | {vc[k]/len(per_sym)*100:.1f}% |")

    A("\n## 2. Observasi (tanggal, symbol)\n")
    A("| Ukuran | Nilai |")
    A("|---|---:|")
    A(f"| Observasi eligible | {len(el):,} |")
    for tol in C.QUANT_TOL_SENSITIVITY:
        c = f"executable_tol{int(tol*100)}"
        A(f"| executable, toleransi kuantisasi {int(tol*100)}% | "
          f"{el[c].sum():,} ({el[c].mean()*100:.1f}%) |")
    A(f"| gagal syarat (a) MIN_NOTIONAL ≤ $6 | "
      f"{(~el['exec_cond_a_min_notional']).sum():,} ({(~el['exec_cond_a_min_notional']).mean()*100:.2f}%) |")
    A(f"| gagal syarat (b) qty_actual ≥ minQty | "
      f"{(~el['exec_cond_b_min_qty']).sum():,} ({(~el['exec_cond_b_min_qty']).mean()*100:.2f}%) |")
    fail_c = el["exec_cond_a_min_notional"] & el["exec_cond_b_min_qty"] & (el["quant_err"] > C.QUANT_TOL)
    A(f"| lolos (a)+(b) tapi gagal (c) error kuantisasi >10% | {fail_c.sum():,} ({fail_c.mean()*100:.2f}%) |")

    A("\n## 3. Eksekutabilitas per tercile likuiditas (cek bias §2.6)\n")
    lt = el.dropna(subset=["liq_tercile"]).groupby("liq_tercile").agg(
        n_obs=("symbol", "size"), exec_rate=("executable_100usd", "mean"),
        median_price=("close_t", "median"), median_adv=("adv_usd_30", "median"))
    A("| liq_tercile | n_obs | exec_rate | median harga | median ADV 30d USD |")
    A("|---|---:|---:|---:|---:|")
    for i, r in lt.iterrows():
        A(f"| {int(i)} ({'tipis' if i==1 else 'tengah' if i==2 else 'likuid'}) | {int(r['n_obs']):,} | "
          f"{r['exec_rate']*100:.1f}% | {r['median_price']:.6g} | {r['median_adv']:,.0f} |")

    A("\n## 4. Distribusi stepSize (seluruh universe)\n")
    sd = (el.groupby("step_lbl")
            .agg(n_obs=("symbol", "size"), n_symbols=("symbol", "nunique"),
                 exec_rate=("executable_100usd", "mean"),
                 median_price=("close_t", "median"),
                 median_quant_err=("quant_err", "median"))
            .reset_index())
    sd["step_num"] = sd["step_lbl"].astype(float)
    sd = sd.sort_values("step_num")
    A("| stepSize | n symbol | n obs | median harga | median step×harga (% dari $6) | exec_rate |")
    A("|---|---:|---:|---:|---:|---:|")
    for _, r in sd.iterrows():
        sn = r["step_num"] * r["median_price"]
        A(f"| {r['step_lbl']} | {int(r['n_symbols'])} | {int(r['n_obs']):,} | {r['median_price']:.6g} | "
          f"{sn:.4g} ({sn/C.NOTIONAL*100:.2f}%) | {r['exec_rate']*100:.1f}% |")

    A("\n## 5. Cross-tab stepSize × harga — 25 sel terbesar\n")
    A("| stepSize | bucket harga | n symbol | n obs | median step×harga | % dari $6 | exec_rate |")
    A("|---|---|---:|---:|---:|---:|---:|")
    for _, r in ct.head(25).iterrows():
        A(f"| {r['step_lbl']} | {r['price_lbl']} | {int(r['n_symbols'])} | {int(r['n_obs']):,} | "
          f"{r['median_step_notional']:.4g} | {r['step_notional_pct_of_6']:.2f}% | {r['exec_rate']*100:.1f}% |")

    never = per_sym[per_sym["verdict"] == "never"]
    A(f"\n## 6. Symbol yang TIDAK PERNAH executable di $6 (n={len(never)})\n")
    if never.empty:
        A("Tidak ada.\n")
    else:
        A("| symbol | stepSize | median harga | step×harga | % dari $6 | n hari |")
        A("|---|---:|---:|---:|---:|---:|")
        for _, r in never.sort_values("step_x_price_median", ascending=False).head(40).iterrows():
            A(f"| {r['symbol']} | {r['step_size_mode']:g} | {r['price_median']:.6g} | "
              f"{r['step_x_price_median']:.4g} | {r['step_notional_pct_of_6']:.1f}% | {int(r['n_days'])} |")

    part = per_sym[per_sym["verdict"].isin(["mostly", "sometimes"])]
    A(f"\n## 7. Symbol yang eksekutabilitasnya berubah sepanjang waktu (n={len(part)})\n")
    A("Ini yang membuktikan constraint bersifat time-varying: harga bergerak, "
      "stepSize tetap, sehingga status bisa berubah tanpa perubahan aturan bursa.\n")
    if not part.empty:
        A("| symbol | stepSize | harga min | harga max | exec_rate | n hari |")
        A("|---|---:|---:|---:|---:|---:|")
        for _, r in part.sort_values("exec_rate").head(40).iterrows():
            A(f"| {r['symbol']} | {r['step_size_mode']:g} | {r['price_min']:.6g} | {r['price_max']:.6g} | "
              f"{r['exec_rate']*100:.1f}% | {int(r['n_days'])} |")

    dly = el.groupby("date")["executable_100usd"].agg(["mean", "size"])
    A("\n## 8. exec_rate harian\n")
    A(f"- rata-rata harian: **{dly['mean'].mean()*100:.1f}%**")
    A(f"- minimum harian: {dly['mean'].min()*100:.1f}% ({dly['mean'].idxmin().date()})")
    A(f"- maksimum harian: {dly['mean'].max()*100:.1f}% ({dly['mean'].idxmax().date()})")
    A(f"- symbol eligible/hari: median {dly['size'].median():.0f} "
      f"(min {dly['size'].min()}, max {dly['size'].max()})")

    out = "\n".join(lines) + "\n"
    (C.RESULTS / "GATE_executability.md").write_text(out, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
