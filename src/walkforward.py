"""Stage 3 (dipercepat untuk satu hipotesis) — walk-forward pada irisan
`funding_24h_sum <= X` DAN `funding_ts_z30` di kuantil terbawah Y.

Kenapa hanya satu hipotesis: aturan ini ditemukan lewat pencarian di data yang
sama (14 run -> ambil dua yang nyaris lolos -> iris). Bonferroni mengoreksi
jumlah uji, TIDAK mengoreksi proses pemilihannya. Walk-forward adalah satu-satunya
alat yang tersisa untuk memisahkan "edge yang meluruh" dari "artefak periode".

Desain sesuai action plan §5:
  rolling 6 bulan train / 2 bulan test, step 2 bulan -> 9 fold dalam 24 bulan.
  Parameter di tiap fold diambil HANYA dari window train-nya.
Exit criteria §5: OOS expectancy > 0 di >=6 dari 9 fold, dan degradasi IS->OOS <50%.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import stats as S

COST = 0.0004                      # limit in + limit out (keputusan Dew)
FUND_GRID = [-0.0003, 0.0, 0.0003]  # ambang funding_24h_sum
ZQ_GRID = [0.10, 0.20, 0.30]        # kuantil terbawah funding_ts_z30
FIXED = (0.0, 0.20)                 # aturan yang ditemukan di full-sample


def load():
    d = pd.concat([pd.read_parquet(p) for p in sorted(C.PANEL.glob("month=*/part.parquet"))],
                  ignore_index=True)
    d = d[d["eligible"]].copy()
    d["dt"] = pd.to_datetime(d["date"], utc=True)
    d["di"] = d["dt"].values.astype("datetime64[D]").astype(np.int64)
    d["zrank"] = d.groupby("di")["funding_ts_z30"].rank(pct=True, method="first")
    d["net"] = d["fwd_48h"] - COST - d["funding_paid_48h"]
    d["net_neutral"] = d["fwd_48h_neutral"] - COST - d["funding_paid_48h"]
    return d.dropna(subset=["net"])


def sig(d, fth, zq):
    return (d["funding_24h_sum"] <= fth) & (d["zrank"] <= zq)


def folds(dmin, dmax, train_m=6, test_m=2, step_m=2):
    out = []
    start = pd.Timestamp(dmin).normalize().replace(day=1)
    while True:
        tr0 = start
        tr1 = tr0 + pd.DateOffset(months=train_m)
        te1 = tr1 + pd.DateOffset(months=test_m)
        if tr1 >= dmax:
            break
        if te1 > dmax + pd.Timedelta(days=1):
            # window test terakhir boleh parsial - kalau dibuang, periode paling
            # baru tidak pernah diuji sama sekali. Ditandai partial di output.
            if (dmax - tr1).days >= 25:
                out.append((tr0, tr1, dmax + pd.Timedelta(days=1)))
            break
        out.append((tr0, tr1, te1))
        start = start + pd.DateOffset(months=step_m)
    return out


def main():
    d = load()
    fs = folds(d["dt"].min(), d["dt"].max())
    print(f"panel {len(d):,} baris | {len(fs)} fold | biaya {COST*100:.2f}% round trip\n")
    print(f"{'fold':>4s} {'train':>21s} {'test':>21s} {'param terpilih':>16s} "
          f"{'IS net':>8s} {'OOS net':>8s} {'OOS t':>6s} {'n OOS':>6s} {'fixed OOS':>10s}")
    rows = []
    for i, (a, b, c) in enumerate(fs, 1):
        tr = d[(d.dt >= a) & (d.dt < b)]
        te = d[(d.dt >= b) & (d.dt < c)]
        best, best_v = None, -9e9
        for f_ in FUND_GRID:
            for z_ in ZQ_GRID:
                s = tr[sig(tr, f_, z_)]
                if len(s) < 300:
                    continue
                v = s["net"].mean()
                if v > best_v:
                    best_v, best = v, (f_, z_)
        if best is None:
            continue
        so = te[sig(te, *best)]
        sf = te[sig(te, *FIXED)]
        o = S.cluster_mean(so["net"].to_numpy(), so["di"].to_numpy())
        fx = S.cluster_mean(sf["net"].to_numpy(), sf["di"].to_numpy())
        rows.append({"fold": i, "train_start": a.date(), "test_start": b.date(),
                     "test_end": c.date(), "fund_th": best[0], "zq": best[1],
                     "is_net": best_v, "oos_net": o["mean"], "oos_t": o["t"],
                     "n_oos": o["n_obs"], "fixed_oos_net": fx["mean"], "fixed_oos_t": fx["t"]})
        print(f"{i:4d} {str(a.date())+'..'+str((b-pd.Timedelta(days=1)).date()):>21s} "
              f"{str(b.date())+'..'+str((c-pd.Timedelta(days=1)).date()):>21s} "
              f"{f'f<={best[0]*100:+.2f}% z<={best[1]:.0%}':>16s} "
              f"{best_v*100:+7.3f}% {o['mean']*100:+7.3f}% {o['t']:+6.2f} {o['n_obs']:6d} "
              f"{fx['mean']*100:+9.3f}%")
    r = pd.DataFrame(rows)
    r.to_csv(C.RESULTS / "walkforward_funding_intersection.csv", index=False)

    npos = int((r.oos_net > 0).sum())
    is_m, oos_m = r.is_net.mean(), r.oos_net.mean()
    degr = (1 - oos_m / is_m) * 100 if is_m > 0 else np.nan
    fx_pos = int((r.fixed_oos_net > 0).sum())
    print("\n" + "=" * 78)
    print("EXIT CRITERIA STAGE 3 (action plan §5)")
    print("=" * 78)
    print(f"  OOS expectancy > 0 di {npos} dari {len(r)} fold        "
          f"-> syarat >=6/9 : {'LOLOS' if npos >= 6 else 'GAGAL'}")
    print(f"  rata-rata IS  = {is_m*100:+.3f}%")
    print(f"  rata-rata OOS = {oos_m*100:+.3f}%")
    print(f"  degradasi IS->OOS = {degr:.1f}%                  "
          f"-> syarat <50% : {'LOLOS' if degr < 50 else 'GAGAL'}")
    print(f"\n  pembanding aturan TETAP (f<=0, z<=20%): OOS>0 di {fx_pos}/{len(r)} fold, "
          f"rata-rata {r.fixed_oos_net.mean()*100:+.3f}%")
    # gabungan seluruh OOS sebagai satu deret
    allo = []
    for _, x in r.iterrows():
        te = d[(d.dt >= pd.Timestamp(x.test_start, tz="UTC")) & (d.dt < pd.Timestamp(x.test_end, tz="UTC"))]
        allo.append(te[sig(te, x.fund_th, x.zq)])
    A = pd.concat(allo)
    g = S.cluster_mean(A["net"].to_numpy(), A["di"].to_numpy())
    gn = S.cluster_mean(A["net_neutral"].to_numpy(), A["di"].to_numpy())
    print(f"\n  SELURUH OOS digabung: net={g['mean']*100:+.3f}% CI[{g['ci_lo']*100:+.3f}%,"
          f"{g['ci_hi']*100:+.3f}%] t={g['t']:+.2f} n={g['n_obs']} hari={g['n_days']}")
    print(f"                        neutral-net={gn['mean']*100:+.3f}% t={gn['t']:+.2f}")
    print(f"  -> ${g['mean']*6*548:+.2f}/tahun pada notional $6, 3 slot")
    print(f"\n-> {C.RESULTS/'walkforward_funding_intersection.csv'}")


if __name__ == "__main__":
    main()
