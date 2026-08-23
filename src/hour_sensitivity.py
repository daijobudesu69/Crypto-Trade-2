"""(d) Sensitivitas jam entry — apakah hasil bergantung pada pilihan 00:00 UTC?

Seluruh Stage 1.1 memakai instan keputusan 00:00 UTC. Kalau hasilnya berubah
drastis di jam lain, itu tanda temuannya rapuh terhadap pilihan yang sebenarnya
arbitrer. Uji ini hanya bisa MELEMAHKAN hasil yang ada, tidak bisa memperkuat
secara palsu — jadi aman dijalankan berapa kali pun.

Panel mini dibangun ulang di jam 0/4/8/12/16/20 UTC dengan konvensi
anti-lookahead yang sama: fitur dari data yang closed pada instan keputusan,
entry di open bar tepat pada instan itu, label 48 jam ke depan.
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
import stats as S

HOURS = (0, 4, 8, 12, 16, 20)
H = 48
COST = 0.0004
OUTD = C.DATA / "hours"


def build_symbol(sym: str):
    k, _ = F.load_klines(sym)
    if k.empty or len(k) < 24 * 40:
        return None
    f = F.load_funding(sym)
    if f.empty:
        return None
    idx = k.index
    op = k["open"].to_numpy(float)
    n = len(op)

    fwd = np.full(n, np.nan)
    if n > H:
        fwd[: n - H] = op[H:] / op[: n - H] - 1.0

    rt = f["rate"]
    ft = rt.index.to_numpy()
    cv = np.concatenate([[0.0], rt.cumsum().to_numpy()])
    last_f = rt.index[-1]

    rows = []
    for hh in HOURS:
        sel = np.where(idx.hour == hh)[0]
        if len(sel) < 40:
            continue
        t = idx[sel]
        # fitur: funding closed pada instan keputusan -> window (t-24h, t]
        a = np.searchsorted(ft, (t - pd.Timedelta(hours=24)).to_numpy(), side="right")
        b = np.searchsorted(ft, t.to_numpy(), side="right")
        f24 = cv[b] - cv[a]
        # biaya: funding selama hold -> (t, t+H]
        end_t = t + pd.Timedelta(hours=H)
        e = np.searchsorted(ft, end_t.to_numpy(), side="right")
        paid = np.where(np.asarray(end_t > last_f), np.nan, cv[e] - cv[b])
        s = pd.DataFrame({"ts": t, "hour": hh, "symbol": sym,
                          "entry_open": op[sel], "fwd_48h": fwd[sel],
                          "funding_24h_sum": f24, "funding_paid_48h": paid})
        # z-score vs 30 pengamatan terakhir pada JAM YANG SAMA
        v = s["funding_24h_sum"]
        s["funding_ts_z30"] = (v - v.rolling(30, min_periods=20).mean()) / \
                              v.rolling(30, min_periods=20).std().replace(0, np.nan)
        s["n_hist"] = np.arange(len(s))
        rows.append(s)
    if not rows:
        return None
    out = pd.concat(rows, ignore_index=True)
    out = out[(out.ts >= C.START_DATE) & (out.ts <= C.END_DATE)]
    out = out[out.n_hist >= 30]
    if out.empty:
        return None
    OUTD.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUTD / f"{sym}.parquet", index=False)
    return len(out)


def _w(s):
    try:
        return s, ("ok" if build_symbol(s) else "empty")
    except Exception as e:
        return s, f"ERR {type(e).__name__}: {e}"


def build_all():
    man = json.loads((C.RAW / "manifest.json").read_text())
    syms = sorted(s for s, v in man["symbols"].items() if v["klines"] or v["daily"])
    print(f"membangun panel mini di jam {HOURS} untuk {len(syms)} symbol ...", flush=True)
    t0 = time.time()
    ok = bad = 0
    errs = []
    with ProcessPoolExecutor(max_workers=10) as ex:
        for i, f in enumerate(as_completed([ex.submit(_w, s) for s in syms]), 1):
            sym_, st = f.result()
            ok += st == "ok"
            if st != "ok":
                bad += 1
                if st != "empty" and len(errs) < 10:
                    errs.append((sym_, st))
            if i % 200 == 0:
                print(f"  {i}/{len(syms)} ok={ok} {(time.time()-t0)/60:.1f}m", flush=True)
    print(f"done ok={ok} skip={bad} in {(time.time()-t0)/60:.1f} min")
    for sy, e in errs:
        print("  ERR", sy, e)
    if ok == 0:
        raise SystemExit("tidak ada symbol yang berhasil — hentikan, jangan lanjut analisa")


def analyse():
    d = pd.concat([pd.read_parquet(p) for p in sorted(OUTD.glob("*.parquet"))],
                  ignore_index=True)
    d = d.dropna(subset=["fwd_48h", "entry_open"])
    # JANGAN pakai astype("int64")//10**9 — pandas 3.0 menyimpan ts sebagai
    # datetime64[ms], jadi pembagian itu menggabungkan ~12 hari jadi satu grup
    # dan merusak seluruh ranking cross-sectional. factorize bebas resolusi.
    d["key"] = pd.factorize(d["ts"])[0]
    print(f"\npanel gabungan: {len(d):,} baris, {d.symbol.nunique()} symbol, "
          f"{d.hour.nunique()} jam\n")
    g = d.groupby("key")
    d["fwd_neutral"] = d["fwd_48h"] - g["fwd_48h"].transform("mean")
    d["xs_pct"] = g["funding_24h_sum"].rank(pct=True) * 100
    d["zrank"] = g["funding_ts_z30"].rank(pct=True, method="first")
    d["net"] = d["fwd_48h"] - COST - d["funding_paid_48h"]
    d["net_neu"] = d["fwd_neutral"] - COST - d["funding_paid_48h"]

    out = []
    print(f"{'jam':>4s} {'n':>8s} {'R0 net':>9s} {'t':>6s} | {'R1 D10-D1':>10s} {'t':>6s} | "
          f"{'R2 Q5-Q1':>9s} {'t':>6s} | {'H1 net':>9s} {'t':>6s} {'H1 neu':>8s} {'t':>6s}")
    for hh, s in d.groupby("hour"):
        k = s["key"].to_numpy()
        r0 = S.cluster_mean(s["net"].to_numpy(), k)
        d10, d1 = s[s.xs_pct > 90], s[s.xs_pct <= 10]
        r1 = S.cluster_diff(d10["net"].to_numpy(), d10["key"].to_numpy(),
                            d1["net"].to_numpy(), d1["key"].to_numpy())
        q5, q1 = s[s.zrank > 0.8], s[s.zrank <= 0.2]
        r2 = S.cluster_diff(q5["net"].to_numpy(), q5["key"].to_numpy(),
                            q1["net"].to_numpy(), q1["key"].to_numpy())
        h1 = s[(s.funding_24h_sum <= 0) & (s.zrank <= 0.20)]
        a = S.cluster_mean(h1["net"].to_numpy(), h1["key"].to_numpy())
        b = S.cluster_mean(h1["net_neu"].to_numpy(), h1["key"].to_numpy())
        print(f"{hh:4d} {len(s):8d} {r0['mean']*100:+8.3f}% {r0['t']:+6.2f} | "
              f"{r1['diff']*100:+9.3f}% {r1['t']:+6.2f} | {r2['diff']*100:+8.3f}% {r2['t']:+6.2f} | "
              f"{a['mean']*100:+8.3f}% {a['t']:+6.2f} {b['mean']*100:+7.3f}% {b['t']:+6.2f}")
        out.append({"hour": hh, "n": len(s), "r0_net": r0["mean"], "r0_t": r0["t"],
                    "r1_spread": r1["diff"], "r1_t": r1["t"],
                    "r2_spread": r2["diff"], "r2_t": r2["t"],
                    "h1_net": a["mean"], "h1_t": a["t"], "h1_n": a["n_obs"],
                    "h1_neutral": b["mean"], "h1_neutral_t": b["t"]})
    r = pd.DataFrame(out)
    r.to_csv(C.RESULTS / "hour_sensitivity.csv", index=False)
    print(f"\nH1 net antar jam: min {r.h1_net.min()*100:+.3f}%  max {r.h1_net.max()*100:+.3f}%  "
          f"rata-rata {r.h1_net.mean()*100:+.3f}%  jam dengan t>2: {(r.h1_t > 2).sum()}/{len(r)}")
    print(f"R2 spread antar jam: semua negatif? {bool((r.r2_spread < 0).all())}  "
          f"|t|>2.5 di {(r.r2_t.abs() > 2.5).sum()}/{len(r)} jam")
    print(f"-> {C.RESULTS/'hour_sensitivity.csv'}")


if __name__ == "__main__":
    if "--analyse" not in sys.argv:
        build_all()
    analyse()
