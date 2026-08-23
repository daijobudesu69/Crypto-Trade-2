# Stage 1.1 — Full Backtestable Ablation
## Brief eksekusi untuk Claude Code

**Status:** siap dieksekusi
**Capital:** $100 USD
**Sizing:** margin 3% ($3) × leverage 2x = **notional $6 fixed** — LOCKED, lihat §2.4
**Arah:** long + short
**Bobot portfolio:** equal-weight
**Scope:** semua layer yang bisa dibacktest dengan data yang tersedia penuh hari ini (klines + fundingRate). Layer OI/LSR/CVD **tidak** termasuk — itu Stage 4.

**Yang TIDAK dilakukan di Stage 1.1:** optimasi stop/target (Stage 2), walk-forward (Stage 3), tuning parameter apapun. Stage 1.1 hanya menjawab: **faktor mana yang punya kandungan prediktif, dan seberapa besar.**

---

## 1. Prinsip yang tidak boleh dilanggar

Empat hal ini yang biasanya membuat backtest crypto berbohong. Semuanya wajib ditangani eksplisit — kalau salah satu dilewat, hasilnya tidak bisa dipakai.

| # | Jebakan | Penanganan wajib |
|---|---|---|
| 1 | **Survivorship bias** | Universe harus mencakup symbol yang sudah **delisted**. Memecoin punya tingkat delisting tinggi; mengabaikannya membuat return terlihat jauh lebih baik dari kenyataan. `data.binance.vision` menyimpan arsip symbol delisted — pakai itu, jangan pakai `exchangeInfo` hari ini sebagai universe |
| 2 | **Cross-sectional correlation** | Semua altcoin bergerak bersama BTC. t-stat naif akan overstated 3–5×. **Wajib** cluster standard error per tanggal (atau Newey-West). Tanpa ini semua faktor akan terlihat signifikan |
| 3 | **Beta terselubung** | Faktor apapun yang berkorelasi dengan beta-BTC akan terlihat "prediktif" di pasar bull. **Wajib** laporkan versi market-neutral: kurangi mean return cross-section hari itu dari setiap coin |
| 4 | **Lookahead** | Fitur dihitung dari data yang closed pada t. Label diukur dari **open t+1**, bukan close t. Funding percentile dihitung dari snapshot yang benar-benar tersedia pada waktu keputusan |

---

## 2. Data

### 2.1 Sumber
- **Primer:** `https://data.binance.vision` — arsip ZIP bulanan, tanpa rate limit
  - `futures/um/monthly/klines/{SYMBOL}/1h/`
  - `futures/um/monthly/fundingRate/{SYMBOL}/`
- **Sekunder:** `https://fapi.binance.com/fapi/v1/exchangeInfo` — untuk `MIN_NOTIONAL`, `LOT_SIZE`, `tickSize`, status listing
- Tidak butuh API key. Semua endpoint publik.

### 2.2 Periode
`2024-08-01` → `2026-07-31` (24 bulan penuh).

### 2.3 Universe
- Semua perp USDⓈ-M yang **quote = USDT**, `contractType = PERPETUAL`
- **Termasuk symbol delisted** dalam periode tersebut (lihat §1 jebakan #1)
- Point-in-time: pada tiap tanggal rebalance, symbol eligible kalau punya ≥30 hari riwayat klines pada tanggal itu
- Eksklusi: BTCUSDT, ETHUSDT boleh dipertahankan sebagai kontrol/benchmark, tapi tandai terpisah

### 2.4 Sizing rule — LOCKED, jangan diubah

```
margin_per_trade = 3% × capital = $3.00
leverage         = 2x
NOTIONAL         = $6.00   ← FIXED, tidak bergantung stop, ATR, atau harga
```

Ini keputusan Dew dan bersifat final untuk Stage 1.1. **Jangan** menurunkan notional dari `risk% ÷ stop%`. Jangan menambahkan volatility targeting, risk parity, atau penyesuaian ukuran apapun.

Konsekuensi metodologis yang menguntungkan: notional tetap = **equal-weight portfolio**, dan itu persis asumsi yang dipakai R0–R8 (§4). Tidak ada re-weighting yang mencampur efek sizing ke dalam pengukuran faktor.

Konsekuensi yang harus dilaporkan: kerugian per trade **tidak** konstan. Pada stop 5% rugi $0.30, pada stop 20% rugi $1.20 (4×). Karena itu **semua metrik dilaporkan dalam persen return, bukan dollar** — ini yang menetralkan distorsinya. Lihat §5.

### 2.5 Filter eksekutabilitas — evaluasi per (date, symbol)

Notional tetap, tapi harga bergerak selama 2 tahun, jadi step-size constraint **berubah sepanjang waktu**. Evaluasi ulang tiap hari, bukan sekali di awal.

```python
NOTIONAL = 6.00
qty_ideal  = NOTIONAL / close_t
qty_actual = floor_to_step(qty_ideal, stepSize[symbol])
notional_actual = qty_actual * close_t

executable_100usd = (
    MIN_NOTIONAL[symbol] <= NOTIONAL                      # (a) batas minimum bursa
    and qty_actual >= minQty[symbol]                      # (b) lot minimum terpenuhi
    and abs(notional_actual - NOTIONAL) / NOTIONAL <= 0.10  # (c) error kuantisasi ≤ 10%
)
```

Ketiga syarat wajib. Yang paling sering menggagalkan:

| Syarat | Kegagalan tipikal |
|---|---|
| (a) | Symbol dengan `MIN_NOTIONAL = 20 USDT` — order $6 ditolak bursa, symbol tereksklusi total |
| (b) | `stepSize` kasar relatif harga → `floor(6/price)` = 0, tidak bisa buka posisi sama sekali |
| (c) | Pembulatan memaksa notional jauh dari $6 (mis. stepSize 0.1 pada harga 77.5 → notional $7.75, +29%) — merusak asumsi equal-weight |

Toleransi 10% di (c) adalah pilihan; laporkan juga sensitivitasnya pada 5% dan 20%.

### 2.6 Pelaporan ganda

Jalankan **semua run dua kali**: universe penuh, dan universe `executable_100usd == True`. Selisihnya menjawab: berapa banyak edge yang secara mekanis tidak bisa diakses dengan akun $100 dan sizing rule ini.

Laporkan juga `executable_rate` per hari dan per liquidity tercile — kalau eksekutabilitas berkorelasi dengan likuiditas, itu bias yang harus disebut eksplisit di temuan.

---

## 3. Panel fitur

Frekuensi: **harian**, snapshot pada `00:00 UTC`. Satu baris = (date, symbol).

### 3.1 Fitur

| Nama | Definisi |
|---|---|
| `funding_8h` | Funding rate periode terakhir sebelum snapshot |
| `funding_24h_sum` | Jumlah funding 3 periode terakhir |
| `funding_xs_pct` | Persentil `funding_24h_sum` di antara seluruh symbol eligible **pada tanggal yang sama** (0–100) |
| `funding_ts_z30` | Z-score `funding_24h_sum` vs 30 hari riwayat symbol itu sendiri |
| `vol_z30` | Z-score volume USD harian vs rata-rata 30 hari |
| `ret_24h` | Return 24 jam terakhir (close-to-close) |
| `ret_7d` | Return 7 hari |
| `atr14_norm` | ATR(14) harian ÷ close |
| `adv_usd_30` | Rata-rata dollar volume 30 hari |
| `liq_tercile` | Tercile `adv_usd_30` cross-sectional harian (1=paling tipis, 3=paling likuid) |
| `ema9_state` | +1 kalau close > EMA9(1H terakhir) dan slope EMA9 > 0; −1 kalau kebalikan; 0 lainnya |
| `ema21_state` | Sama, EMA21 |

### 3.2 Label

| Nama | Definisi |
|---|---|
| `fwd_24h`, `fwd_48h`, `fwd_72h` | Return dari **open t+1** ke open t+2 / t+3 / t+4 |
| `fwd_48h_neutral` | `fwd_48h` − mean(`fwd_48h`) seluruh symbol eligible pada tanggal t |

`fwd_48h` adalah label utama (sesuai hold window 1–2 hari). Dua lainnya untuk cek robustness horizon.

### 3.3 Output artefak
`data/panel.parquet` — partisi per bulan. Simpan juga `data/universe_log.csv` (jumlah symbol eligible per hari) untuk audit.

### 3.4 Capture-once — WAJIB, ini yang mencegah kerja dua kali

**Prinsip arsitektur:** biaya sesungguhnya ada di **download + parsing** (2 tahun × ~400 symbol × klines 1H). Run R0–R8 sendiri cuma groupby, hitungannya detik. Karena itu: satu kali pass download harus menangkap **semua** yang dibutuhkan Stage 1.1 **sampai** Stage 3, bukan hanya Stage 1.1.

Kolom di bawah ini **tidak dipakai** di R0–R8, tapi wajib disimpan sekarang.

| Yang disimpan | Dipakai di | Kalau dilewat sekarang |
|---|---|---|
| **Klines 1H mentah** (jangan hanya agregat harian) | Stage 2, 3 | Download ulang 2 tahun × 400 symbol dari nol |
| **MAE / MFE** per observasi, window 24/48/72h | **Stage 2** | Stage 2 harus scan ulang seluruh price path — pekerjaan terberat Stage 2, padahal bisa gratis sekarang |
| **Funding per periode + timestamp** (bukan hanya jumlah harian) | Stage 2, 6 | Tidak bisa menghitung funding aktual untuk hold window selain 48h |
| **exchangeInfo snapshot harian** (`stepSize`, `minQty`, `MIN_NOTIONAL`) | Stage 1.1, 6 | Filter bursa bisa berubah sepanjang waktu; universe historis jadi salah |
| **Symbol delisted** | Semua stage | Survivorship bias — hasil terlihat lebih baik dari kenyataan |
| **Return BTC + agregat cross-section harian** (mean, dispersi, funding market-wide) | Stage 1.2, 4 | Tidak bisa market-neutral maupun regime split |
| **Label 24h / 48h / 72h sekaligus** | Stage 1.2 | Re-run penuh hanya untuk cek robustness horizon |

#### MAE/MFE — kenapa ini item paling berharga di tabel

Untuk tiap observasi, catat pergerakan ekstrem selama window forward:

```
MAE_48h = pergerakan merugikan terbesar dari entry, dalam %   (seberapa dalam drawdown sebelum keluar)
MFE_48h = pergerakan menguntungkan terbesar dari entry, dalam %  (setinggi apa profit sempat naik)
```

Dengan dua kolom ini tersimpan, **Stage 2 berubah dari simulasi ulang jadi sekadar query**:
- "Stop 1.5× ATR akan kena atau tidak?" → `MAE_48h > 1.5 × atr14_norm`
- "Target 2R tercapai?" → `MFE_48h ≥ 2 × stop_pct`
- Grid ATR 0.8×–2.5× × RR 1.0–4.0 → filter dua kolom, tanpa menyentuh data mentah lagi

Biayanya sekarang: satu pass tambahan di data yang sudah di-load. Biayanya kalau dilewat: mengulang seluruh Stage 1.1.

**Catatan urutan MAE/MFE:** dari klines 1H tidak bisa dipastikan apakah high atau low tersentuh lebih dulu dalam satu bar. Simpan juga `bar_index_of_MAE` dan `bar_index_of_MFE` supaya Stage 2 bisa menerapkan asumsi konservatif (anggap stop kena duluan kalau berada di bar yang sama).

#### Yang TIDAK bisa ditangkap sekarang

OI, long/short ratio, dan taker ratio — retensi Binance hanya 30 hari, tidak ada arsip. Ini satu-satunya bagian yang wajib menunggu Stage 0, dan sifatnya **menambah kolom**, bukan mengulang pekerjaan. Panel dirancang supaya kolom-kolom itu bisa di-join belakangan lewat kunci `(date, symbol)`.

---

## 4. Runs ablation

Semua run: **long dan short terpisah**. Short return = `−1 × fwd_return`. Semua run dilaporkan gross dan net.

**Bobot portfolio: equal-weight**, konsisten dengan sizing rule notional tetap $6 (§2.4). Tidak ada weighting by ATR, likuiditas, atau conviction score di Stage 1.1.

| Run | Faktor | Bucketing | Menjawab |
|---|---|---|---|
| **R0** | Baseline | Equal-weight semua eligible | Base rate. Semua run lain dibandingkan ke sini |
| **R1** | `funding_xs_pct` | Quintile + decile untuk p0–10 dan p90–100 | **Pertanyaan utama:** di mana kandungan prediktif funding? Ekor atau tengah? |
| **R2** | `funding_ts_z30` | Quintile | Apakah z-score time-series menambah apapun di atas cross-sectional? |
| **R3** | `vol_z30` | Quintile | Volume surge punya edge? |
| **R4** | `ret_24h` | Quintile, **displit per `liq_tercile`** | **Uji hipotesis §8.2:** momentum di coin likuid, reversal di coin tipis? |
| **R5** | `atr14_norm` | Quintile | Kontrol — apakah funding cuma proxy volatilitas? |
| **R6** | `funding_xs_pct` × `liq_tercile` | 5×3 grid | Apakah edge funding beda per tier likuiditas? |
| **R7** | `funding_xs_pct` × `ret_24h` | 5×5 grid | **Uji klaim konflik §3:** apakah funding tinggi dan momentum positif benar-benar populasi yang sama? |
| **R8** | `ema9_state` vs `ema21_state` vs none | Conditional pada bucket terbaik dari R1 | Apakah trigger EMA menambah expectancy, atau hanya menambah ruang overfit? |

**Aturan:** jalankan satu per satu. Jangan menumpuk. R6/R7/R8 baru bermakna kalau R1/R4 menunjukkan sesuatu.

---

## 5. Metrik per bucket

**Semua metrik return dilaporkan dalam persen, bukan dollar.** Ini bukan preferensi presentasi — ini yang menetralkan konsekuensi notional tetap (§2.4). Dalam dollar, trade dengan stop 20% menyumbang kerugian 4× trade dengan stop 5%, sehingga statistik akan didominasi coin high-ATR. Dalam persen, tiap observasi berbobot sama dan faktor bisa dibandingkan bersih.

Sertakan `stop_pct` sebagai kolom diagnostik supaya distorsi dollar-nya tetap bisa diaudit belakangan, tapi jangan pakai untuk weighting.

Untuk tiap bucket di tiap run, laporkan:

| Metrik | Catatan |
|---|---|
| `n_obs`, `n_days`, `n_symbols` | Sample size. Bucket dengan `n_days < 100` ditandai tidak reliable |
| `mean_ret`, `median_ret` | Gross dan net |
| `t_stat_clustered` | **Clustered by date** — wajib (§1 jebakan #2) |
| `p_value_raw`, `p_value_bonferroni` | Koreksi untuk ~45 bucket yang diuji |
| `hit_rate` | % observasi return > 0 |
| `sharpe_daily_ann` | Dari time series return harian bucket (bukan dari pooled obs) |
| `mean_ret_neutral` | Versi market-neutral (§1 jebakan #3) |
| `max_dd` | Drawdown dari equity curve bucket |

### 5.1 Model biaya
```
fee        = 0.05% × 2 (taker in/out)          = 0.10%
funding    = actual funding paid over hold      = dari data, bukan asumsi
slippage   = 0.05% × 2                          = 0.10%   [asumsi — ganti dengan data live Stage 6]
------------------------------------------------------------
net_ret = gross_ret − 0.20% − funding_actual
```
Slippage 0.10% round-trip adalah **asumsi yang belum diverifikasi**. Tandai jelas di output. Jalankan juga sensitivitas pada 0.05% dan 0.20%.

Catatan: semua komponen biaya Binance USDⓈ-M bersifat persentase, tanpa fee tetap per order. Model biaya di atas karena itu **tidak berubah** oleh sizing rule — notional $6 dan notional $600 menghasilkan drag persen yang identik. Satu-satunya efek ukuran akun ada di eksekutabilitas (§2.5), bukan di biaya.

---

## 6. Kriteria keputusan (tetapkan sebelum melihat hasil)

Faktor dinyatakan **KEEP** hanya kalau memenuhi semua:

1. Spread antara bucket teratas dan terbawah **net** > 0.5% pada `fwd_48h`
2. `t_stat_clustered` > 2.5 (bukan 2.0 — kompensasi multiple testing)
3. Bertahan pada `mean_ret_neutral` (bukan sekadar beta BTC)
4. Monotonik atau punya pola tail yang jelas — bukan satu bucket menonjol acak di tengah
5. `n_days` ≥ 200 di bucket yang dimaksud
6. Bertahan saat universe dibatasi ke `executable_100usd == True`

Gagal salah satu → **KILL**. Jangan pertahankan faktor karena "terasa masuk akal" (§12 spec awal).

---

## 7. Deliverable

```
repo/
├─ data/
│  ├─ panel.parquet
│  └─ universe_log.csv
├─ results/
│  ├─ R0_baseline.csv ... R8_trigger.csv
│  ├─ funding_bucket_curve.png        # fwd_48h per decile funding — chart kunci
│  └─ summary.csv                      # semua run, semua bucket, satu tabel
├─ src/
│  ├─ fetch.py         # download + cache data.binance.vision
│  ├─ features.py      # bangun panel
│  ├─ ablation.py      # R0–R8
│  └─ stats.py         # clustered SE, bootstrap CI
└─ STAGE_1_1_FINDINGS.md
```

### `STAGE_1_1_FINDINGS.md` harus menjawab tiga pertanyaan secara eksplisit:

1. **Funding range untuk entry:** berdasarkan R1, bucket mana yang punya forward return positif signifikan untuk long, dan mana untuk short? Kalau tidak ada yang signifikan — **tulis itu**, jangan cari bucket terbaik dari noise.
2. **Faktor mana KEEP, mana KILL** — dengan effect size + confidence interval per faktor.
3. **Berapa banyak edge yang hilang** karena constraint `executable_100usd`.

Setiap angka disertai `n` dan confidence interval. Tidak ada angka telanjang.

---

## 8. Catatan implementasi

- **Reproducibility:** seed tetap, versi library di-pin, hash dataset dicatat
- **Caching:** data.binance.vision ZIP di-cache lokal; jangan re-download tiap run
- **Ukuran data:** ~400 symbol × 24 bulan × klines 1H ≈ beberapa GB. Proses per bulan, jangan load semua ke memori
- **vectorbt** untuk sweep, tapi R0–R7 sebenarnya cuma groupby-aggregate pada panel — pandas/polars sudah cukup dan lebih transparan. Pakai vectorbt di Stage 2 saat butuh simulasi path-dependent (stop/target)
- **Jangan** tambahkan filter, parameter, atau faktor yang tidak ada di §4. Kalau muncul ide baru saat kerja, catat di `STAGE_1_1_FINDINGS.md` untuk stage berikutnya — jangan sisipkan ke run yang sedang berjalan

---

## 9. Yang perlu dikonfirmasi ke Dew sebelum eksekusi

1. Repo GitHub tujuan (nama + apakah baru atau existing)
2. Apakah slippage 0.10% round-trip diterima sebagai asumsi awal, atau ada angka dari pengalaman eksekusi manual selama ini
3. Apakah BTCUSDT/ETHUSDT dimasukkan ke universe atau hanya sebagai benchmark
