"""Stage 1.1 - chart kunci: fwd_48h per decile funding_xs_pct (brief §7).

Menampilkan tiga ukuran berdampingan supaya perbedaan antara "sinyal ada" dan
"sinyal bisa dipanen" terlihat langsung:
  gross          - return mentah
  neutral gross  - setelah mean cross-section harian dikurangi (uji beta, §1 #3)
  net            - setelah fee 0.10% + slippage 0.10% + funding aktual yang dibayar
Error bar = 95% CI dengan standard error di-cluster per tanggal.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C


def panel(ax, d: pd.DataFrame, title: str) -> None:
    d = d.copy()
    d["k"] = d["bucket"].str[1:].astype(int)
    d = d.sort_values("k")
    x = np.arange(len(d))
    series = [
        ("gross", "mean_ret_gross", None, None, "#8c8c8c", "o"),
        ("market-neutral (gross)", "mean_ret_neutral", "ci_lo_neutral", "ci_hi_neutral", "#1f77b4", "s"),
        ("net (fee+slip+funding)", "mean_ret_net", "ci_lo_net", "ci_hi_net", "#d62728", "D"),
    ]
    for i, (lbl, col, lo, hi, c, mk) in enumerate(series):
        off = (i - 1) * 0.18
        y = d[col].to_numpy() * 100
        if lo is not None:
            err = np.vstack([y - d[lo].to_numpy() * 100, d[hi].to_numpy() * 100 - y])
            ax.errorbar(x + off, y, yerr=np.abs(err), fmt=mk, color=c, ms=5, lw=1.4,
                        capsize=3, label=lbl)
        else:
            ax.plot(x + off, y, mk, color=c, ms=5, label=lbl, alpha=0.8)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"D{k}\nn={int(n/1000)}k" for k, n in zip(d["k"], d["n_obs"])], fontsize=7)
    ax.set_xlabel("decile funding_xs_pct  (D1 = funding terendah, D10 = tertinggi)", fontsize=8)
    ax.set_ylabel("mean return 48 jam (%)", fontsize=8)
    ax.set_title(title, fontsize=9)
    ax.grid(alpha=0.25, lw=0.5)
    ax.tick_params(labelsize=7)


def main() -> None:
    r = pd.read_csv(C.RESULTS / "summary.csv")
    d = r[(r["run"] == "R1") & (r["bucket_type"] == "decile") & (r["horizon_h"] == C.PRIMARY_H)]

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 8.5))
    combos = [("full", "long"), ("full", "short"), ("exec", "long"), ("exec", "short")]
    names = {"full": "universe penuh", "exec": "universe executable @ $6"}
    for ax, (u, dr) in zip(axes.ravel(), combos):
        sub = d[(d["universe"] == u) & (d["direction"] == dr)]
        panel(ax, sub, f"{dr.upper()} — {names[u]}")
    axes[0, 0].legend(fontsize=7, loc="best")
    fig.suptitle(
        "R1 — forward return 48h per decile funding cross-sectional\n"
        "Binance USDS-M perp USDT, 2024-08-01 s/d 2026-07-31, equal-weight, "
        "SE di-cluster per tanggal (95% CI)",
        fontsize=10)
    fig.text(0.5, 0.005,
             "Biaya: fee 0.10% + slippage 0.10% (ASUMSI belum terverifikasi) + funding aktual "
             "selama hold. Sinyal gross yang kuat hilang setelah biaya — lihat STAGE_1_1_FINDINGS.md",
             ha="center", fontsize=7.5, style="italic")
    fig.tight_layout(rect=(0, 0.02, 1, 0.94))
    out = C.RESULTS / "funding_bucket_curve.png"
    fig.savefig(out, dpi=160)
    print("->", out)

    # chart pendamping: exec_rate harian (gate §2.5)
    ulog = pd.read_csv(C.DATA / "universe_log.csv", parse_dates=["date"])
    fig2, ax = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    ax[0].plot(ulog["date"], ulog["n_eligible"], lw=1, color="#1f77b4", label="eligible")
    ax[0].plot(ulog["date"], ulog["n_executable"], lw=1, color="#d62728", label="executable @ $6")
    ax[0].set_ylabel("jumlah symbol", fontsize=8); ax[0].legend(fontsize=8)
    ax[0].grid(alpha=0.25, lw=0.5); ax[0].tick_params(labelsize=7)
    ax[0].set_title("Universe harian — eligible vs executable pada notional $6", fontsize=10)
    ax[1].plot(ulog["date"], ulog["executable_rate"] * 100, lw=1, color="#2ca02c")
    ax[1].set_ylabel("executable_rate (%)", fontsize=8); ax[1].grid(alpha=0.25, lw=0.5)
    ax[1].tick_params(labelsize=7); ax[1].set_ylim(70, 100)
    fig2.tight_layout()
    out2 = C.RESULTS / "universe_executable_rate.png"
    fig2.savefig(out2, dpi=160)
    print("->", out2)


if __name__ == "__main__":
    main()
