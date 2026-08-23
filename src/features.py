"""Stage 1.1 - bangun panel harian dari arsip 1H (brief §3).

Konvensi waktu (anti-lookahead, brief §1 jebakan #4)
---------------------------------------------------
Satu baris = (date d, symbol). Instan keputusan = d 00:00:00 UTC.
  * FITUR  : hanya dari bar 1H yang sudah CLOSED pada d 00:00 UTC
             (bar terakhir = yang dibuka d-1 23:00) dan funding dengan
             fundingTime <= d 00:00. Bar harian terakhir yang lengkap = hari d-1.
  * close_t: close bar 1H yang berakhir tepat d 00:00 = harga di instan keputusan.
  * ENTRY  : open bar 1H yang dibuka d 00:00 = "open t+1" dengan t = d-1.
  * LABEL  : fwd_H = open(d + H jam) / open(d) - 1.
Tidak ada jeda antara sinyal dan entry, dan tidak ada satu pun bar setelah
d 00:00 yang menyentuh sisi fitur.

stepSize (brief §2.5)
---------------------
exchangeInfo tidak dapat diakses (semua domain binance.com diblokir dari mesin ini).
stepSize DITURUNKAN dari arsip: kolom volume tiap bar 1H adalah jumlah quantity
trade, sehingga kelipatan stepSize. Eksponen desimal terkecil dari seluruh volume
dalam satu bulan = stepSize bulan itu. Tervalidasi tepat pada BTCUSDT (0.001),
ETHUSDT (0.001), XRPUSDT (0.1), DOGEUSDT (1), 1000PEPEUSDT (1).
minQty dan MIN_NOTIONAL tidak dapat diturunkan -> ASUMSI, lihat config.py.
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
              "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
FUND_COLS = ["calc_time", "funding_interval_hours", "last_funding_rate"]

INTERIM = C.DATA / "interim"
HOUR_MS = 3_600_000


# ------------------------------------------------------------------ util
def _read_zip_csv(path: Path, ncols_expect: int) -> pd.DataFrame | None:
    try:
        with zipfile.ZipFile(path) as z:
            name = z.namelist()[0]
            raw = z.read(name)
    except (zipfile.BadZipFile, IndexError, OSError):
        return None
    if not raw:
        return None
    first = raw.split(b"\n", 1)[0].decode("utf-8", "replace")
    header = 0 if not first.split(",")[0].strip().lstrip("-").isdigit() else None
    try:
        df = pd.read_csv(io.BytesIO(raw), header=header, dtype=str)
    except Exception:
        return None
    if df.shape[1] < ncols_expect:
        return None
    return df


def _to_epoch_ms(s: pd.Series) -> pd.Series:
    """Arsip Binance memakai ms untuk file lama dan microsecond untuk file baru."""
    v = pd.to_numeric(s, errors="coerce")
    return np.where(v > 1e14, v / 1000.0, v)


def derive_step(vol_strings) -> float:
    """stepSize = 10^(eksponen desimal terkecil di antara seluruh volume != 0)."""
    min_exp = None
    n = 0
    for v in vol_strings:
        try:
            d = Decimal(v)
        except (InvalidOperation, TypeError):
            continue
        if d == 0:
            continue
        e = d.normalize().as_tuple().exponent
        n += 1
        if min_exp is None or e < min_exp:
            min_exp = e
    if min_exp is None or n < 20:
        return float("nan")
    min_exp = int(max(-8, min(4, min_exp)))
    return float(Decimal(1).scaleb(min_exp))


def _ema(x: np.ndarray, span: int) -> np.ndarray:
    a = 2.0 / (span + 1.0)
    out = np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def _state(close: np.ndarray, ema: np.ndarray) -> np.ndarray:
    slope = np.concatenate([[np.nan], np.diff(ema)])
    up = (close > ema) & (slope > 0)
    dn = (close < ema) & (slope < 0)
    return np.where(up, 1, np.where(dn, -1, 0)).astype(float)


# ------------------------------------------------------------------ per symbol
def load_klines(sym: str) -> tuple[pd.DataFrame, dict]:
    """1H bars pada grid jam penuh + stepSize per bulan."""
    d = C.RAW_KLINES / sym
    if not d.is_dir():
        return pd.DataFrame(), {}
    frames, steps = [], {}
    for p in sorted(d.glob(f"{sym}-1h-*.zip")):
        df = _read_zip_csv(p, 6)
        if df is None or df.empty:
            continue
        df = df.iloc[:, :12]
        df.columns = KLINE_COLS[: df.shape[1]]
        tag = p.name.split("-1h-")[-1][:-4]
        if len(tag) == 7:                                  # file bulanan -> stepSize bulan itu
            steps[tag] = derive_step(df["volume"].tolist())
        frames.append(df)
    if not frames:
        return pd.DataFrame(), {}
    k = pd.concat(frames, ignore_index=True)
    k["open_time"] = _to_epoch_ms(k["open_time"])
    for c in ("open", "high", "low", "close", "volume", "quote_volume"):
        k[c] = pd.to_numeric(k[c], errors="coerce")
    k = k.dropna(subset=["open_time"]).drop_duplicates("open_time").sort_values("open_time")
    k["ts"] = pd.to_datetime(k["open_time"], unit="ms", utc=True)
    k = k.set_index("ts")[["open", "high", "low", "close", "volume", "quote_volume"]]
    full = pd.date_range(k.index[0].floor("h"), k.index[-1].floor("h"), freq="h", tz="UTC")
    return k.reindex(full), steps


def load_funding(sym: str) -> pd.DataFrame:
    d = C.RAW_FUNDING / sym
    if not d.is_dir():
        return pd.DataFrame(columns=["ts", "rate"]).set_index("ts")
    frames = []
    for p in sorted(d.glob(f"{sym}-fundingRate-*.zip")):
        df = _read_zip_csv(p, 3)
        if df is None or df.empty:
            continue
        df = df.iloc[:, :3]
        df.columns = FUND_COLS
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["rate"], index=pd.DatetimeIndex([], tz="UTC", name="ts"))
    f = pd.concat(frames, ignore_index=True)
    f["t"] = _to_epoch_ms(f["calc_time"])
    f["rate"] = pd.to_numeric(f["last_funding_rate"], errors="coerce")
    f = f.dropna(subset=["t", "rate"]).drop_duplicates("t").sort_values("t")
    f["ts"] = pd.to_datetime(f["t"], unit="ms", utc=True)
    return f.set_index("ts")[["rate"]]


def mae_mfe(k: pd.DataFrame, entry_pos: np.ndarray, H: int) -> dict:
    """Ekstrem forward window H bar dari entry (brief §3.4). Didefinisikan untuk LONG:
    mae = pergerakan merugikan terbesar (<=0), mfe = menguntungkan terbesar (>=0).
    Untuk SHORT keduanya bertukar tanda: mae_short = -mfe_long, mfe_short = -mae_long."""
    hi, lo, op = k["high"].to_numpy(), k["low"].to_numpy(), k["open"].to_numpy()
    n = len(hi)
    pad = np.full(H, np.nan)
    hi_p, lo_p = np.concatenate([hi, pad]), np.concatenate([lo, pad])
    win_h = np.lib.stride_tricks.sliding_window_view(hi_p, H)[entry_pos]
    win_l = np.lib.stride_tricks.sliding_window_view(lo_p, H)[entry_pos]
    valid = np.isfinite(win_h)
    nbars = valid.sum(axis=1)
    allnan = nbars == 0
    with np.errstate(invalid="ignore"):
        mx = np.where(allnan, np.nan, np.nanmax(np.where(valid, win_h, -np.inf), axis=1))
        mn = np.where(allnan, np.nan, np.nanmin(np.where(np.isfinite(win_l), win_l, np.inf), axis=1))
        imx = np.where(allnan, -1, np.nanargmax(np.where(valid, win_h, -np.inf), axis=1))
        imn = np.where(allnan, -1, np.nanargmin(np.where(np.isfinite(win_l), win_l, np.inf), axis=1))
    e = op[entry_pos]
    # window tidak lengkap (mis. delisting di tengah hold) -> tandai lewat n_bars
    return {
        f"mfe_{H}h": mx / e - 1.0,
        f"mae_{H}h": mn / e - 1.0,
        f"mfe_bar_{H}h": imx.astype(float),
        f"mae_bar_{H}h": imn.astype(float),
        f"n_bars_{H}h": nbars.astype(float),
    }


def build_symbol(sym: str) -> pd.DataFrame | None:
    k, steps = load_klines(sym)
    if k.empty or len(k) < 24 * (C.MIN_HISTORY_DAYS + 2):
        return None
    f = load_funding(sym)

    # ---- bar harian: hari D = [D 00:00, D+1 00:00)
    g = k.groupby(k.index.floor("D"))
    dly = pd.DataFrame({
        "o": g["open"].first(), "h": g["high"].max(), "l": g["low"].min(),
        "c": g["close"].last(), "qv": g["quote_volume"].sum(),
        "nbar": g["close"].count(),
    })
    dly = dly.reindex(pd.date_range(dly.index[0], dly.index[-1], freq="D", tz="UTC"))
    has = dly["nbar"].fillna(0) > 0

    # ---- fitur time-series pada bar harian D (semua closed pada D+1 00:00)
    c = dly["c"]
    prev_c = c.shift(1)
    tr = pd.concat([dly["h"] - dly["l"], (dly["h"] - prev_c).abs(), (dly["l"] - prev_c).abs()],
                   axis=1).max(axis=1)
    atr14 = tr.rolling(14, min_periods=14).mean()
    ft = pd.DataFrame(index=dly.index)
    ft["close_t"] = c
    ft["ret_24h"] = c / c.shift(1) - 1
    ft["ret_7d"] = c / c.shift(7) - 1
    ft["atr14_norm"] = atr14 / c
    ft["dollar_vol_24h"] = dly["qv"]
    ft["adv_usd_30"] = dly["qv"].rolling(30, min_periods=20).mean()
    sd = dly["qv"].rolling(30, min_periods=20).std()
    ft["vol_z30"] = (dly["qv"] - ft["adv_usd_30"]) / sd.replace(0, np.nan)
    ft["n_hist_days"] = has.cumsum()

    # ---- EMA state 1H pada bar terakhir hari D (berakhir D+1 00:00)
    cl = k["close"].ffill()
    ok = cl.notna().to_numpy()
    st9 = pd.Series(np.nan, index=k.index)
    st21 = pd.Series(np.nan, index=k.index)
    if ok.sum() > 50:
        arr = cl.to_numpy(dtype=float)
        first = int(np.argmax(ok))
        a = arr[first:]
        st9.iloc[first:] = _state(a, _ema(a, 9))
        st21.iloc[first:] = _state(a, _ema(a, 21))
    ft["ema9_state"] = st9.groupby(st9.index.floor("D")).last().reindex(ft.index)
    ft["ema21_state"] = st21.groupby(st21.index.floor("D")).last().reindex(ft.index)

    # ---- funding closed <= D+1 00:00
    # Grouping digeser 1 mikrodetik supaya window jadi (D 00:00, D+1 00:00]: event
    # tepat pada D+1 00:00 (jam funding standar Binance) ikut ke sisi FITUR, dan
    # window biaya hold di bawah memakai (d 00:00, d+H] -> tidak ada event yang
    # terhitung dua kali maupun hilang.
    if not f.empty:
        r = f["rate"]
        by_day = r.groupby((r.index - pd.Timedelta(microseconds=1)).floor("D"))
        ft["funding_8h"] = by_day.last().reindex(ft.index)
        ft["funding_24h_sum"] = by_day.sum().reindex(ft.index)
        ft["n_funding_day"] = by_day.count().reindex(ft.index)
    else:
        ft["funding_8h"] = np.nan
        ft["funding_24h_sum"] = np.nan
        ft["n_funding_day"] = np.nan
    fs = ft["funding_24h_sum"]
    m30 = fs.rolling(30, min_periods=20).mean()
    s30 = fs.rolling(30, min_periods=20).std()
    ft["funding_ts_z30"] = (fs - m30) / s30.replace(0, np.nan)

    # ---- geser: baris tanggal d memakai fitur dari bar harian D = d-1
    ft.index = ft.index + pd.Timedelta(days=1)

    # ---- entry & label pada tanggal d
    lab = pd.DataFrame(index=dly.index)
    lab["entry_open"] = dly["o"]
    for H in C.HORIZONS_H:
        lab[f"fwd_{H}h"] = dly["o"].shift(-H // 24) / dly["o"] - 1

    pan = lab.join(ft, how="inner")
    pan["symbol"] = sym

    # ---- MAE/MFE dari bar 1H, mulai bar yang dibuka d 00:00
    pos = k.index.get_indexer(pan.index)
    keep = pos >= 0
    pan, pos = pan[keep], pos[keep]
    if pan.empty:
        return None
    for H in C.HORIZONS_H:
        for col, val in mae_mfe(k, pos, H).items():
            pan[col] = val

    # ---- funding dibayar selama hold: (d 00:00, d + H jam]
    if not f.empty:
        rt = f["rate"]
        cum = rt.cumsum()
        idx = rt.index
        base = np.searchsorted(idx.to_numpy(), pan.index.to_numpy(), side="right")
        cv = np.concatenate([[0.0], cum.to_numpy()])
        last_f = idx[-1]
        for H in C.HORIZONS_H:
            hold_end = pan.index + pd.Timedelta(hours=H)
            end = np.searchsorted(idx.to_numpy(), hold_end.to_numpy(), side="right")
            paid = cv[end] - cv[base]
            nev = (end - base).astype(float)
            # arsip funding berhenti sebelum akhir hold (mis. bulan berjalan belum
            # terbit, atau symbol delisted) -> biaya TIDAK diketahui, jangan diam-diam
            # dianggap nol.
            incomplete = np.asarray(hold_end > last_f)
            pan[f"funding_paid_{H}h"] = np.where(incomplete, np.nan, paid)
            pan[f"n_fund_ev_{H}h"] = np.where(incomplete, np.nan, nev)
    else:
        for H in C.HORIZONS_H:
            pan[f"funding_paid_{H}h"] = np.nan
            pan[f"n_fund_ev_{H}h"] = np.nan

    # ---- stepSize bulan berjalan (fallback: modus seluruh periode)
    pan["month"] = pan.index.strftime("%Y-%m")
    sser = pd.Series(steps, dtype=float)
    sser = sser[sser.notna()]
    fallback = float(sser.mode().iloc[0]) if not sser.empty else np.nan
    pan["step_size"] = pan["month"].map(steps).astype(float)
    pan["step_size"] = pan["step_size"].fillna(fallback)
    pan["step_size_source"] = np.where(pan["month"].isin(sser.index), "month_gcd", "fallback_mode")

    last_data = dly.index[has.to_numpy()][-1] if has.any() else pd.NaT
    first_data = dly.index[has.to_numpy()][0] if has.any() else pd.NaT
    pan["last_data_date"] = last_data
    pan["first_data_date"] = first_data
    pan["is_benchmark"] = sym in C.BENCHMARK_SYMBOLS

    pan = pan.loc[(pan.index >= C.START_DATE) & (pan.index <= C.END_DATE)]
    if pan.empty:
        return None
    pan.index.name = "date"
    return pan.reset_index()


def _worker(sym: str):
    try:
        df = build_symbol(sym)
    except Exception as e:                                   # jangan hentikan 800 symbol lain
        return sym, f"ERR {type(e).__name__}: {e}", 0
    if df is None or df.empty:
        return sym, "empty", 0
    INTERIM.mkdir(parents=True, exist_ok=True)
    df.to_parquet(INTERIM / f"{sym}.parquet", index=False)
    return sym, "ok", len(df)


def main() -> None:
    man = json.loads((C.RAW / "manifest.json").read_text())
    symbols = sorted(s for s, v in man["symbols"].items() if v["klines"] or v["daily"])
    print(f"building per-symbol features for {len(symbols)} symbols ...", flush=True)
    t0 = time.time()
    ok = bad = 0
    errs = []
    with ProcessPoolExecutor(max_workers=10) as ex:
        futs = {ex.submit(_worker, s): s for s in symbols}
        for i, fu in enumerate(as_completed(futs), 1):
            sym, status, n = fu.result()
            if status == "ok":
                ok += 1
            else:
                bad += 1
                if status != "empty":
                    errs.append((sym, status))
            if i % 100 == 0:
                print(f"  {i}/{len(symbols)}  ok={ok} skipped={bad}  {(time.time()-t0)/60:.1f}m",
                      flush=True)
    print(f"per-symbol done: ok={ok} skipped={bad} in {(time.time()-t0)/60:.1f} min")
    for s, e in errs[:20]:
        print("  ERR", s, e)
    (C.DATA / "feature_errors.json").write_text(json.dumps(errs, indent=1))


if __name__ == "__main__":
    main()
