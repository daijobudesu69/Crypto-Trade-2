"""Stage 1.1 - inferensi. Standard error WAJIB di-cluster per tanggal (brief §1 jebakan #2).

Tanpa clustering, seluruh altcoin yang bergerak bersama BTC dihitung sebagai
observasi independen dan t-stat menjadi overstated 3-5x. Semua fungsi di sini
memakai cluster = tanggal, dengan koreksi finite-sample G/(G-1) * (N-1)/(N-k).
"""
from __future__ import annotations

import numpy as np
from scipy import stats as sps


def cluster_ols(y: np.ndarray, X: np.ndarray, groups: np.ndarray):
    """OLS dengan cluster-robust covariance. -> (beta, se, G, N)"""
    y = np.asarray(y, dtype=float)
    X = np.asarray(X, dtype=float)
    m = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X, groups = y[m], X[m], np.asarray(groups)[m]
    N, k = X.shape
    if N <= k:
        return np.full(k, np.nan), np.full(k, np.nan), 0, N
    XtX = X.T @ X
    try:
        XtXi = np.linalg.inv(XtX)
    except np.linalg.LinAlgError:
        return np.full(k, np.nan), np.full(k, np.nan), 0, N
    beta = XtXi @ (X.T @ y)
    e = y - X @ beta
    u = X * e[:, None]
    _, gi = np.unique(groups, return_inverse=True)
    G = gi.max() + 1
    if G < 2:
        return beta, np.full(k, np.nan), G, N
    S = np.zeros((k, k))
    agg = np.zeros((G, k))
    np.add.at(agg, gi, u)
    S = agg.T @ agg
    c = (G / (G - 1.0)) * ((N - 1.0) / (N - k))
    V = XtXi @ S @ XtXi * c
    se = np.sqrt(np.clip(np.diag(V), 0, None))
    return beta, se, G, N


def cluster_mean(x, dates, alpha: float = 0.05) -> dict:
    """Mean + SE/t/p/CI dengan cluster per tanggal."""
    x = np.asarray(x, dtype=float)
    d = np.asarray(dates)
    m = np.isfinite(x)
    x, d = x[m], d[m]
    n = len(x)
    if n == 0:
        return dict(n_obs=0, n_days=0, mean=np.nan, se=np.nan, t=np.nan,
                    p=np.nan, ci_lo=np.nan, ci_hi=np.nan)
    beta, se, G, N = cluster_ols(x, np.ones((n, 1)), d)
    mu, s = float(beta[0]), float(se[0])
    if not np.isfinite(s) or s == 0 or G < 2:
        return dict(n_obs=N, n_days=G, mean=mu, se=np.nan, t=np.nan,
                    p=np.nan, ci_lo=np.nan, ci_hi=np.nan)
    t = mu / s
    df = G - 1
    p = 2 * sps.t.sf(abs(t), df)
    q = sps.t.ppf(1 - alpha / 2, df)
    return dict(n_obs=N, n_days=G, mean=mu, se=s, t=t, p=p,
                ci_lo=mu - q * s, ci_hi=mu + q * s)


def cluster_diff(x_a, d_a, x_b, d_b, alpha: float = 0.05) -> dict:
    """Selisih mean bucket A - B, SE cluster per tanggal pada gabungan A dan B."""
    x = np.concatenate([np.asarray(x_a, float), np.asarray(x_b, float)])
    d = np.concatenate([np.asarray(d_a), np.asarray(d_b)])
    g = np.concatenate([np.ones(len(x_a)), np.zeros(len(x_b))])
    X = np.column_stack([np.ones(len(x)), g])
    beta, se, G, N = cluster_ols(x, X, d)
    diff, s = float(beta[1]), float(se[1])
    if not np.isfinite(s) or s == 0 or G < 2:
        return dict(diff=diff, se=np.nan, t=np.nan, p=np.nan,
                    ci_lo=np.nan, ci_hi=np.nan, n_days=G, n_obs=N)
    t = diff / s
    df = G - 1
    return dict(diff=diff, se=s, t=t, p=2 * sps.t.sf(abs(t), df),
                ci_lo=diff - sps.t.ppf(1 - alpha / 2, df) * s,
                ci_hi=diff + sps.t.ppf(1 - alpha / 2, df) * s, n_days=G, n_obs=N)


def cluster_bootstrap_ci(x, dates, reps: int = 2000, alpha: float = 0.05, seed: int = 0):
    """CI bootstrap dengan resampling TANGGAL (bukan observasi) - menjaga korelasi
    cross-section di dalam hari."""
    x = np.asarray(x, dtype=float)
    d = np.asarray(dates)
    m = np.isfinite(x)
    x, d = x[m], d[m]
    if len(x) == 0:
        return np.nan, np.nan
    uq, gi = np.unique(d, return_inverse=True)
    G = len(uq)
    if G < 5:
        return np.nan, np.nan
    order = np.argsort(gi, kind="stable")
    xs = x[order]
    counts = np.bincount(gi, minlength=G)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    csum = np.concatenate([[0.0], np.cumsum(xs)])
    gsum = csum[starts + counts] - csum[starts]
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, G, size=(reps, G))
    tot = gsum[pick].sum(axis=1)
    cnt = counts[pick].sum(axis=1)
    means = np.where(cnt > 0, tot / np.maximum(cnt, 1), np.nan)
    return (float(np.nanpercentile(means, 100 * alpha / 2)),
            float(np.nanpercentile(means, 100 * (1 - alpha / 2))))


def sharpe_ann(daily_mean: np.ndarray, horizon_h: int) -> float:
    """Sharpe dari deret return harian bucket (brief §5), bukan dari pooled obs.

    Deret ini OVERLAPPING (return H jam disampel tiap hari), jadi std terestimasi
    dari observasi yang tumpang tindih. Jumlah periode independen per tahun =
    365 / (H/24). Autokorelasi akibat overlap membuat SE Sharpe understated -
    ditandai di FINDINGS."""
    v = np.asarray(daily_mean, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < 10 or v.std(ddof=1) == 0:
        return np.nan
    per_year = 365.0 / (horizon_h / 24.0)
    return float(v.mean() / v.std(ddof=1) * np.sqrt(per_year))


def max_drawdown(daily_mean: np.ndarray, horizon_h: int) -> float:
    """Equity curve model tranche: tiap hari 1/k kapital dibuka, k = H/24 tranche
    berjalan bersamaan, sehingga kontribusi harian = return_H / k."""
    v = np.asarray(daily_mean, dtype=float)
    v = v[np.isfinite(v)]
    if len(v) < 10:
        return np.nan
    k = horizon_h / 24.0
    eq = np.cumprod(1.0 + v / k)
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min())


def bonferroni(p: float, m: int) -> float:
    if not np.isfinite(p):
        return np.nan
    return float(min(1.0, p * m))
