"""Stage 1.1 — konstanta terkunci & path.

Semua nilai di blok LOCKED berasal dari keputusan Dew (brief §2.4, action plan §0.1).
Jangan diubah, jangan dioptimasi, jangan diturunkan dari risk%/stop%.
"""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent.parent          # "C:/Crypto data 2"
DATA = ROOT / "data"
RAW = DATA / "raw"
RAW_KLINES = RAW / "klines"
RAW_FUNDING = RAW / "fundingRate"
PANEL = DATA / "panel.parquet"                          # direktori partisi bulanan
RESULTS = ROOT / "results"
for _p in (DATA, RAW, RAW_KLINES, RAW_FUNDING, PANEL, RESULTS):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- LOCKED (brief §2.4)
CAPITAL = 100.00
MARGIN_FRAC = 0.03
LEVERAGE = 2
NOTIONAL = 6.00            # = CAPITAL * MARGIN_FRAC * LEVERAGE — FIXED

# ---------------------------------------------------------------- periode (brief §2.2)
START_DATE = "2024-08-01"
END_DATE = "2026-07-31"
WARMUP_MONTHS = 2          # untuk fitur 30-hari sebelum START_DATE
FWD_TAIL_DAYS = 5          # hari kalender setelah END_DATE untuk label fwd_72h

# ---------------------------------------------------------------- universe (brief §2.3)
QUOTE = "USDT"
BENCHMARK_SYMBOLS = ("BTCUSDT", "ETHUSDT")   # keputusan Dew: benchmark saja, di luar pooled ablation
MIN_HISTORY_DAYS = 30

# ---------------------------------------------------------------- eksekutabilitas (brief §2.5)
# exchangeInfo tidak dapat diakses dari jaringan ini (semua domain binance.com diblokir).
# stepSize DITURUNKAN dari GCD volume klines per (symbol, bulan) — tervalidasi 5/5 pada
# symbol yang nilainya diketahui. Dua nilai di bawah ini ASUMSI, ditandai di semua output.
ASSUME_MINQTY_EQ_STEPSIZE = True
DEFAULT_MIN_NOTIONAL = 5.0                    # ASUMSI: standar bursa USDⓈ-M
MIN_NOTIONAL_OVERRIDE = {"BTCUSDT": 100.0, "ETHUSDT": 20.0}   # ASUMSI (nilai publik yang diketahui)
MIN_NOTIONAL_SENSITIVITY = (5.0, 10.0, 20.0)
QUANT_TOL = 0.10                              # brief §2.5 (c)
QUANT_TOL_SENSITIVITY = (0.05, 0.10, 0.20)

# ---------------------------------------------------------------- biaya (brief §5.1)
FEE_ROUNDTRIP = 0.0010                        # taker 0.05% x 2
SLIPPAGE_ROUNDTRIP = 0.0010                   # ASUMSI belum terverifikasi (konfirmasi Dew)
SLIPPAGE_SENSITIVITY = (0.0005, 0.0010, 0.0020)
COST_BASE = FEE_ROUNDTRIP + SLIPPAGE_ROUNDTRIP

# ---------------------------------------------------------------- label & window
HORIZONS_H = (24, 48, 72)
PRIMARY_H = 48

# ---------------------------------------------------------------- kriteria keputusan (brief §6)
KEEP_MIN_SPREAD_NET = 0.005
KEEP_MIN_TSTAT = 2.5
KEEP_MIN_NDAYS = 200
UNRELIABLE_NDAYS = 100

SEED = 20260823
BOOTSTRAP_REPS = 2000

BASE_URL = "https://data.binance.vision/data/futures/um"
S3_LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
