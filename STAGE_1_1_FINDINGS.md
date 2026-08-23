# Stage 1.1 — Temuan

**Periode:** 2024-08-01 s/d 2026-07-31 (730 hari)
**Universe:** Binance USDS-M perp quote USDT, termasuk yang delisted
**Sizing:** notional $6.00 fixed (margin 3% × 2x), equal-weight — LOCKED, tidak diubah
**Label utama:** `fwd_48h` (open t+1 → open t+3)
**Dijalankan:** 2026-08-23

Semua angka di dokumen ini disertai `n` dan confidence interval 95% dengan
standard error **di-cluster per tanggal**. Return dalam **persen**, bukan dollar.

---

## 0. Ringkasan eksekutif

**Tidak ada satu pun faktor yang lolos kriteria KEEP §6 brief.** Sembilan run
dijalankan; nol faktor dipertahankan. Sesuai exit criteria Stage 1
(action plan §3): kalau nol faktor lolos, strategi tidak jalan dalam bentuk
sekarang, dan Stage 2 tidak boleh dimulai di atasnya.

Tiga hal yang ditemukan, berurutan dari yang paling penting:

1. **Funding cross-sectional punya kandungan prediktif yang nyata dan kuat —
   tapi nilainya persis sebesar biaya untuk memanennya.** Selisih gross antara
   decile funding tertinggi dan terendah adalah **+1.017%** per 48 jam
   (t=5.77, n=57.668 observasi). Setelah dikurangi funding yang benar-benar
   dibayar + fee + slippage, selisihnya tinggal **+0.177%, CI 95% [−0.167%,
   +0.520%], t=1.01** — tidak bisa dibedakan dari nol. Sinyalnya ada; edge-nya
   tidak ada.

2. **Arah sinyalnya berlawanan dengan hipotesis §1.4 action plan.** Funding
   tinggi (p90+) diikuti return **lebih tinggi**, bukan lebih rendah. Hipotesis
   "long sesak → kandidat short" **ditolak** pada horizon 48 jam: short di
   decile tertinggi memberi neutral return **−0.594%** (t=−4.59). Yang benar
   justru kebalikannya, dan itupun tidak tradeable setelah biaya.

3. **Arsip Binance terus menerbitkan klines bervolume nol untuk perp yang sudah
   mati.** 44 symbol punya >50% hari tanpa satupun trade; 33.028 observasi
   (9.52% dari panel eligible) punya `fwd_48h` **persis 0**. Ini bukan
   survivorship bias biasa — ini kebalikannya, dan tidak terdeteksi kalau
   delisting diukur dari "kapan file arsip berhenti" (dengan ukuran itu hanya
   7 symbol yang delisted). Butuh keputusan Anda sebelum Stage 1.2.

Hipotesis §8.2 (momentum di coin likuid, reversal di coin tipis) juga **ditolak**
— lihat R4.

---

## 1. Empat jebakan — bagaimana masing-masing ditangani

| # | Jebakan | Penanganan | Bukti di output |
|---|---|---|---|
| 1 | Survivorship | Universe dibangun dari isi arsip `data.binance.vision`, **bukan** dari `exchangeInfo` hari ini. 832 direktori symbol USDT ditemukan, 810 punya data di periode, 752 pernah eligible. 7 symbol delisted di dalam periode tetap ikut sampai hari terakhirnya (AERGO, BDXN, BTCST, EOS, FRONT, MATIC, SXP) | `data/raw/manifest.json`, `data/panel_meta.json` |
| 2 | Korelasi cross-section | Semua SE di-cluster per tanggal (cluster-robust OLS, koreksi finite-sample G/(G−1)·(N−1)/(N−k)), G=730 hari. Ditambah cluster bootstrap 2.000 replikasi dengan resampling **tanggal**, bukan observasi | `src/stats.py`, kolom `t_stat_clustered`, `boot_ci_*` |
| 3 | Beta terselubung | Setiap bucket dilaporkan juga sebagai `mean_ret_neutral` = return dikurangi mean cross-section hari itu. Ini yang membunuh satu-satunya hasil yang tampak signifikan (lihat §3.3) | kolom `mean_ret_neutral`, `mean_ret_neutral_net` |
| 4 | Lookahead | Instan keputusan = d 00:00 UTC. Fitur **hanya** dari bar 1H yang closed pada d 00:00; entry = open bar d 00:00; label dari open itu. Diverifikasi: `close_t` == `entry_open` pada BTCUSDT (64601.8 vs 64601.8) — bar yang berakhir dan bar yang dibuka adalah instan yang sama, jadi tidak ada jeda maupun tumpang tindih | docstring `src/features.py` |

---

## 2. GATE — eksekutabilitas notional $6 (output pertama yang diminta)

Dievaluasi **per (tanggal, symbol)**, 346.870 observasi. Tabel lengkap:
`results/GATE_executability.md`, `results/gate_stepsize_price.csv`,
`results/gate_per_symbol.csv`.

### 2.1 Hasil gate — LOLOS

| Ukuran | n | % |
|---|---:|---:|
| Observasi eligible | 346.870 | 100% |
| executable, toleransi kuantisasi 5% | 305.677 | 88.1% |
| **executable, toleransi 10% (baseline §2.5)** | **323.243** | **93.2%** |
| executable, toleransi 20% | 334.064 | 96.3% |

Mayoritas universe **bisa** ditradingkan di $6. Desain tidak perlu dibahas ulang
karena constraint ini.

### 2.2 Syarat mana yang mengikat

| Syarat | Gagal | Catatan |
|---|---:|---|
| (a) `MIN_NOTIONAL ≤ $6` | 0 (0.00%) | **Karena asumsi** MIN_NOTIONAL=5 USDT — tidak terverifikasi, lihat §7.1 |
| (b) `qty_actual ≥ minQty` | 4.835 (1.39%) | |
| (c) error kuantisasi >10% | 18.792 (5.42%) | **Ini yang paling sering mengikat** |

Conviction 70% di action plan §10 ("step size, bukan MIN_NOTIONAL, adalah
constraint yang paling mengikat") **terkonfirmasi** — dengan catatan bahwa
syarat (a) tidak benar-benar diuji karena datanya tidak bisa diambil.

### 2.3 Distribusi stepSize × harga

| stepSize | n symbol | n obs | median harga | median step×harga | % dari $6 | exec_rate |
|---|---:|---:|---:|---:|---:|---:|
| 0.001 | 17 | 9.275 | 443.35 | 0.443 | 7.39% | 71.1% |
| 0.01 | 126 | 18.378 | 14.24 | 0.142 | 2.37% | 80.1% |
| 0.1 | 128 | 80.211 | 0.773 | 0.077 | 1.29% | 92.6% |
| 1 | 484 | 239.006 | 0.055 | 0.055 | 0.92% | 95.3% |

Aturannya sederhana dan deterministik: **satu step harus ≤ ~10% dari $6, yaitu
≤ $0.60**. Symbol dengan `step × harga > $0.60` mulai gagal; di atas ~$1.2
gagal total.

### 2.4 Vonis per symbol

| Vonis | n symbol | % |
|---|---:|---:|
| always executable (≥99% hari) | 553 | 73.5% |
| mostly (50–99%) | 121 | 16.1% |
| sometimes (>0–50%) | 54 | 7.2% |
| **never** | 24 | 3.2% |

24 symbol tidak pernah bisa dibuka di $6. Hampir semuanya perp berharga tinggi:
AAVEUSDT (step 0.1 @ ~$172 → satu step = $17.18 = 286% dari notional), plus
perp saham/komoditas (ASML, SPY, QQQ, MSFT, XAUT, …).

175 symbol berubah status sepanjang waktu — bukti langsung bahwa constraint
ini **time-varying** dan benar dievaluasi harian, bukan sekali di awal.
Contoh paling tajam: AVAXUSDT (step 1, harga $5.89–$54.02) hanya executable
0.1% dari 730 hari; SOLUSDT 33.8%; BNBUSDT 21.4%.

### 2.5 Bias likuiditas — arahnya berlawanan dengan dugaan

| liq_tercile | n obs | exec_rate | median harga | median ADV 30d |
|---|---:|---:|---:|---:|
| 1 (paling tipis) | 115.389 | **96.4%** | $0.071 | $1,9 jt |
| 2 (tengah) | 115.633 | 95.2% | $0.094 | $8,4 jt |
| 3 (paling likuid) | 115.848 | **88.1%** | $0.302 | $52,9 jt |

Yang tersaring keluar oleh constraint $6 adalah coin **likuid berharga tinggi**,
bukan coin tipis. Ini penting dan dibahas lagi di §5.

---

## 3. PERTANYAAN 1 — Funding range untuk entry

> "Berdasarkan R1, bucket mana yang punya forward return positif signifikan
> untuk long, dan mana untuk short?"

### Jawaban: **tidak ada.**

Nol bucket funding — dari 10 decile × 2 arah × 2 universe = 40 uji — memenuhi
"positif dan signifikan" secara net setelah koreksi multiple testing dan setelah
uji market-neutral. Sesuai instruksi brief §7, itu ditulis apa adanya dan tidak
digantikan dengan bucket terbaik dari noise.

Chart: `results/funding_bucket_curve.png`

### 3.1 Tabel R1 — decile, LONG, universe penuh, fwd_48h

| decile | n obs | n hari | net mean | CI 95% net | t | market-neutral (gross) | CI 95% neutral | t |
|---|---:|---:|---:|---|---:|---:|---|---:|
| D1 (funding terendah) | 31.320 | 730 | −0.185% | [−0.572, +0.202] | −0.94 | **−0.436%** | [−0.591, −0.281] | −5.51 |
| D2 | 30.523 | 705 | −0.247% | [−0.661, +0.167] | −1.17 | −0.030% | [−0.129, +0.069] | −0.59 |
| D3 | 30.554 | 674 | −0.128% | [−0.564, +0.307] | −0.58 | −0.028% | [−0.134, +0.077] | −0.53 |
| D4 | 30.504 | 639 | −0.023% | [−0.553, +0.506] | −0.09 | −0.003% | [−0.106, +0.099] | −0.06 |
| D5 | 30.844 | 628 | −0.514% | [−1.101, +0.073] | −1.72 | −0.149% | [−0.245, −0.052] | −3.03 |
| D6 | 34.372 | 587 | −1.294% | [−1.966, −0.621] | −3.78 | −0.156% | [−0.246, −0.065] | −3.37 |
| D7 | 36.645 | 528 | −0.701% | [−1.453, +0.051] | −1.83 | −0.043% | [−0.170, +0.085] | −0.66 |
| D8 | 45.451 | 509 | −0.141% | [−0.641, +0.359] | −0.55 | +0.085% | [+0.002, +0.168] | 2.01 |
| D9 | 23.935 | 536 | +0.167% | [−0.398, +0.731] | 0.58 | +0.104% | [−0.055, +0.263] | 1.29 |
| D10 (funding tertinggi) | 26.348 | 729 | −0.008% | [−0.465, +0.448] | −0.04 | **+0.594%** | [+0.340, +0.848] | 4.59 |

Untuk SHORT semua tanda market-neutral terbalik persis (D1 +0.436% t=+5.51,
D10 −0.594% t=−4.59); net-nya juga tidak ada yang lolos.

### 3.2 Yang sebenarnya terjadi: sinyalnya nyata, tapi harganya pas

Selisih decile teratas−terbawah, universe penuh, 48 jam (`results/spreads.csv`):

| Ukuran | D10 − D1 | t | Q5 − Q1 | t |
|---|---:|---:|---:|---:|
| gross | **+1.017%** | 5.77 | +0.789% | 5.86 |
| market-neutral gross | **+1.030%** | 6.39 | +0.596% | 5.66 |
| **net** (fee+slip+funding aktual) | **+0.177%** | 1.01 | +0.291% | 2.18 |
| net + market-neutral | +0.188% | 1.18 | +0.093% | 0.90 |

Gross-nya besar dan sangat signifikan. Neutral-gross-nya sama besar — jadi ini
**bukan** beta BTC yang menyamar. Tapi begitu funding yang benar-benar dibayar
dimasukkan, hampir seluruhnya hilang. Di D1 rata-rata funding yang **diterima**
selama 48 jam hold adalah 0.643%; di D10 yang **dibayar** 0.192%. Selisih
funding 0.835% ditambah biaya 0.20% ≈ persis sebesar edge gross 1.017%.

Ini adalah pemisahan peran A (biaya carry) vs peran B (sinyal crowding) di
action plan §1.2, diukur langsung: **peran B ada, besarnya ~1% per 48 jam, dan
peran A menagihnya habis.**

Konsistensi lintas horizon (market-neutral gross, LONG, universe penuh) —
sinyalnya stabil dan tumbuh dengan horizon, jadi ini bukan artefak satu window:

| bucket | 24h | 48h | 72h |
|---|---:|---:|---:|
| D1 | −0.212% (t=−3.71) | −0.436% (t=−5.51) | −0.658% (t=−6.89) |
| D10 | +0.276% (t=3.24) | +0.594% (t=4.59) | +0.938% (t=5.28) |

### 3.3 Satu-satunya bucket yang tampak signifikan — dan kenapa dibuang

SHORT D6 (funding persentil 50–60): net **+0.894%**, CI [+0.221%, +1.566%],
t=2.61, n=34.372, 587 hari. Lolos t>2.5. Dibuang karena **tiga** alasan
independen, semuanya sudah ditetapkan sebelum melihat hasil:

1. **Kriteria 3 (market-neutral):** versi net + market-neutral = **−0.017%**,
   t=−0.44. Seluruh "edge"-nya adalah beta short di periode pasar turun, bukan
   properti funding. Persis jebakan #3.
2. **Kriteria 4 (pola):** D6 adalah bucket **tengah** yang menonjol sendirian,
   dengan tetangganya (D5, D7) tidak signifikan. Brief secara eksplisit
   menyebut pola ini sebagai tanda noise, bukan sinyal.
3. **Struktur data:** cross-section funding penuh **ties**. Pada hari biasa,
   median **28.5%** symbol punya nilai `funding_24h_sum` yang identik (maksimum
   85.8% dalam satu hari) — mayoritas alt duduk persis di funding netral.
   Akibatnya decile tengah bukan decile: ukurannya timpang (D8 = 45.451 obs vs
   D9 = 23.935) dan batas-batasnya jatuh di tengah blok nilai kembar. D6
   "menonjol" adalah artefak partisi blok ties, bukan temuan.

Setelah koreksi Bonferroni global (m=194 uji), p-value D6 short = 1.000.
Dengan Bonferroni per-keluarga (m=20 di R1), p = 0.279. Tidak lolos di
kedua-duanya.

### 3.4 Implikasi untuk aturan operasional §1.5 action plan

| Aturan sementara | Status setelah Stage 1.1 |
|---|---|
| Long: funding ≤ 0.05%/8h sebagai **cap biaya** | **Tetap valid** — dan sekarang ada buktinya. Cap ini aritmatika, bukan prediksi, dan data menunjukkan biaya funding memang sebesar sinyalnya |
| Short: funding ≥ p90 sebagai tailwind | **Salah arah sebagai selector.** Short di D10 memberi neutral return −0.594% (t=−4.59, n=26.348). Anda menerima funding, tapi kehilangan lebih banyak di harga |
| Bucket p10–p90 tidak informatif | **Terkonfirmasi**, dengan alasan tambahan: bucket tengah bahkan tidak terdefinisi dengan baik karena ties |
| Hipotesis §1.4 "sinyal di ekor" | **Setengah benar.** Sinyal memang di ekor (D1 dan D10 yang punya t besar, tengahnya nol). Tapi **arahnya terbalik** dari yang dihipotesiskan |

---

## 4. PERTANYAAN 2 — Faktor mana KEEP, mana KILL

Kriteria KEEP (§6 brief, ditetapkan sebelum melihat hasil, harus lolos **semua**):
(1) spread net > 0.5% pada fwd_48h · (2) t_clustered > 2.5 · (3) bertahan
market-neutral · (4) monotonik atau pola ekor jelas · (5) n_days ≥ 200 ·
(6) bertahan di universe executable.

| Run | Faktor | Spread net (Q5−Q1) | CI 95% | t | Gross | 1 | 2 | 3 | 4 | 5 | 6 | Vonis |
|---|---|---:|---|---:|---:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **R1** | `funding_xs_pct` | +0.291% | [+0.029, +0.553] | 2.18 | +0.789% (t=5.86) | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | **KILL** |
| **R2** | `funding_ts_z30` | −0.437% | [−0.584, −0.289] | −5.82 | −0.240% (t=−3.27) | ✗ | ✓ | ✓ | ✓ | ✓ | ✓ | **KILL** (gagal 1) |
| **R3** | `vol_z30` | +0.008% | [−0.170, +0.187] | 0.09 | −0.145% (t=−1.65) | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | **KILL** |
| **R4** | `ret_24h` | −0.190% | [−0.437, +0.056] | −1.52 | −0.215% (t=−1.82) | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | **KILL** |
| **R5** | `atr14_norm` | +0.189% | [−0.073, +0.452] | 1.41 | +0.036% (t=0.23) | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | **KILL** |
| **R6** | funding × likuiditas | +0.448% (L3) | [+0.039, +0.857] | 2.15 | +1.107% (t=5.34) | ✗ | ✗ | ✗ | — | ✓ | ✗ | **KILL** |
| **R7** | funding × momentum | — | — | — | — | ✗ | ✗ | — | ✗ | ✓ | ✗ | **KILL** |
| **R8** | trigger EMA9/EMA21 | +0.023% | [−0.533, +0.579] | 0.08 | — | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | **KILL** |

Nilai spread untuk arah LONG; SHORT adalah cerminnya (tanda terbalik, |t| sama).

### R2 — satu-satunya yang nyaris lolos, dan kenapa tetap KILL

`funding_ts_z30` (z-score funding vs 30 hari riwayat symbol itu sendiri) adalah
hasil paling kuat di seluruh Stage 1.1:

- spread net Q5−Q1 = **−0.437%**, CI [−0.584%, −0.289%], t=**−5.82**,
  n=128.140, 730 hari
- bertahan Bonferroni global (m=194): **p < 0.001**
- bertahan market-neutral: neutral-net −0.434%, t=−5.78
- bertahan di universe executable: −0.469%, t=−5.93 (**menguat**, bukan melemah)
- bertahan lintas horizon: 24h −0.332% (t=−2.33), 48h −0.464%, 72h −0.531%
  (t=−2.19) untuk Q5 long
- sebagian nyata, bukan cuma biaya: spread **gross** −0.240%, t=−3.27

Arahnya: coin yang funding-nya melonjak relatif sejarahnya sendiri **turun**
sesudahnya. Ini justru hipotesis crowding §1.4 — hanya saja hidup di normalisasi
**time-series**, bukan cross-sectional.

**Tetap KILL karena gagal kriteria 1: 0.437% < 0.5%.** Aturan itu ditetapkan
sebelum data dilihat dan tidak akan diubah setelah melihatnya. Yang lebih
menentukan secara praktis: **tidak ada bucket tunggal yang net-nya positif.**
Q1 (bucket terbaik untuk long) memberi net −0.027%, CI [−0.413%, +0.358%],
t=−0.14, n=63.784. Spread-nya nyata, tapi hanya bisa dipanen sebagai posisi
long-short berpasangan — dan itu bukan strategi yang sedang dibangun (§0.1
action plan: posisi tunggal, maksimal 3, notional $6).

### R4 — hipotesis §8.2 ditolak

Klaim: momentum 24h berlaku di coin likuid, terbalik jadi reversal di coin tipis.

| liq_tercile | spread net Q5−Q1 | CI 95% | t | gross | t |
|---|---:|---|---:|---:|---:|
| 1 (paling tipis) | −0.089% | [−0.471, +0.293] | −0.46 | −0.065% | −0.42 |
| 2 (tengah) | −0.419% | [−0.747, −0.090] | −2.50 | −0.453% | −2.74 |
| 3 (paling likuid) | −0.069% | [−0.425, +0.287] | −0.38 | −0.153% | −0.86 |

Tidak ada gradien likuiditas. Reversal justru paling kuat di tercile **tengah**
dan absen di kedua ujung — pola non-monotonik yang tidak punya interpretasi
mekanis. Coin likuid **tidak** menunjukkan momentum. Hipotesis ditolak,
conviction 72% di dokumen strategi §11 harus diturunkan.

### R5 — funding bukan proxy volatilitas

Kontrol lolos: spread ATR +0.189%, CI [−0.073%, +0.452%], t=1.41, gross +0.036%
(t=0.23). Volatilitas sendiri tidak memprediksi apa-apa, jadi sinyal funding di
R1 **bukan** volatilitas yang menyamar. (Catatan: di universe diagnostik tanpa
coin mati, R5 naik jadi +0.326%, t=2.57 — lihat §6.1.)

### R7 — klaim konflik struktural §3 hanya setengah benar

Grid 5×5 (funding quintile × ret_24h quintile), jumlah observasi per sel,
LONG, universe penuh:

| funding \ momentum | M1 | M2 | M3 | M4 | M5 |
|---|---:|---:|---:|---:|---:|
| F1 | 14.871 | 11.309 | 10.762 | 10.324 | 14.577 |
| F3 | 11.153 | 14.198 | 14.969 | 14.024 | 10.872 |
| **F5** | **13.149** | 7.836 | 7.422 | 8.092 | **13.784** |

Klaim §3 dokumen strategi: "OI melonjak + harga naik secara struktural
menghasilkan funding tinggi, jadi filter funding absolut membuang persis
populasi yang ingin diseleksi filter lain."

Data: funding tertinggi (F5) **bimodal** terhadap momentum — menumpuk di M1
(momentum paling negatif) **dan** M5, kosong di tengah. Jadi funding tinggi
bukan sekadar teman momentum positif; funding tinggi adalah penanda
**pergerakan besar ke arah manapun**. Konflik mekanis yang dikhawatirkan
memang ada, tapi hanya untuk separuh populasi F5.

Return-nya: baris funding mendominasi, kolom momentum hampir tidak menambah
apa-apa. Net baris F5 berkisar +0.098% s/d +0.225% (semua |t| < 1) tanpa pola
lintas momentum.

### R8 — trigger EMA tidak menambah expectancy

Untuk LONG tidak ada bucket R1 yang lolos ambang kondisional (t≥2.5 dan net>0),
jadi R8 dijalankan di seluruh universe eligible sesuai aturan yang dikodekan
sebelumnya. Universe executable, fwd_48h:

| kondisi | n obs | net mean | t | neutral-net | t |
|---|---:|---:|---:|---:|---:|
| tanpa trigger | 323.233 | −0.325% | −1.63 | −0.173% | −9.47 |
| ema9_state = +1 | 144.419 | −0.320% | −1.24 | −0.220% | −6.42 |
| ema9_state = −1 | 148.418 | −0.342% | −1.45 | −0.141% | −3.95 |
| ema21_state = +1 | 138.630 | −0.441% | −1.72 | −0.229% | −6.53 |
| ema21_state = −1 | 155.096 | −0.232% | −0.97 | −0.136% | −3.85 |

Diuji langsung sebagai selisih dengan SE cluster: `ema9_state`(+1) − (−1) =
**+0.023%**, CI [−0.533%, +0.579%], t=0.08, n=291.019. `ema21_state`(+1) − (−1) =
**−0.209%**, CI [−0.766%, +0.347%], t=−0.74, n=291.235. Keduanya nol. Pada ukuran market-neutral,
`state=+1` **lebih buruk** dari `state=−1` di kedua EMA. Uji (b) vs (a) di §4
dokumen strategi: **(b) tidak mengalahkan (a) → buang EMA9.**

Catatan: bucket `state=0` (n≈30.000) punya hit rate 0.0% — itu bukan sinyal,
itu coin yang harganya tidak bergerak sama sekali (lihat §6.1).

### R0 — base rate

| universe | arah | n obs | gross | t | net | CI 95% net | t | hit rate |
|---|---|---:|---:|---:|---:|---|---:|---:|
| penuh | long | 346.858 | −0.155% | −0.85 | −0.330% | [−0.717, +0.058] | −1.67 | 40.4% |
| penuh | short | 346.858 | +0.155% | 0.85 | −0.070% | [−0.458, +0.317] | −0.36 | 47.1% |
| executable | long | 323.233 | −0.149% | −0.81 | −0.325% | [−0.715, +0.065] | −1.63 | 40.3% |
| executable | short | 323.233 | +0.149% | 0.81 | −0.075% | [−0.465, +0.315] | −0.38 | 47.1% |

Base rate memegang alt perp secara equal-weight selama 48 jam adalah negatif
setelah biaya, di kedua arah. Setiap faktor harus mengangkat dari sini; tidak
ada yang berhasil.

Sensitivitas slippage (R0 long, net): 0.05%/sisi → −0.280%; **0.10%/sisi →
−0.330%**; 0.20%/sisi → −0.430%. Kesimpulan tidak berubah di rentang manapun.

---

## 5. PERTANYAAN 3 — Berapa banyak edge yang hilang karena `executable_100usd`

### Jawaban langsung: 6.8% observasi hilang, tapi kehilangannya tidak acak — dan yang hilang justru bagian yang paling bersinyal.

| Ukuran | Universe penuh | Universe executable | Perubahan |
|---|---:|---:|---:|
| observasi eligible | 346.870 | 323.243 | **−6.8%** |
| symbol median per hari | 470 | 443,5 | −5.6% |
| R1 spread gross D10−D1 | +1.017% (t=5.77) | +0.900% (t=5.06) | −11.5% |
| R1 spread net Q5−Q1 | +0.291% (t=2.18) | +0.242% (t=1.77) | −16.8%, **kehilangan signifikansi** |
| R6 spread net, tercile likuid | +0.448% (t=2.15) | +0.310% (t=1.46) | **−30.8%, kehilangan signifikansi** |
| R2 spread net Q5−Q1 | −0.437% (t=−5.82) | −0.469% (t=−5.93) | **+7.3% (menguat)** |

Mekanismenya jelas dan bisa dilacak ke §2.5: `exec_rate` di tercile paling
likuid hanya **88.1%** versus **96.4%** di tercile paling tipis, karena coin
likuid cenderung berharga tinggi sehingga satu `stepSize` menjadi porsi besar
dari $6. Sementara itu R6 menunjukkan sinyal funding **gross** justru menguat
dengan likuiditas:

| tercile | R6 spread gross Q5−Q1 | t | spread net | t |
|---|---:|---:|---:|---:|
| 1 (tipis) | +0.059% | 0.29 | −0.172% | −0.83 |
| 2 (tengah) | +0.716% | 4.05 | +0.313% | 1.76 |
| 3 (likuid) | **+1.107%** | 5.34 | +0.448% | 2.15 |

Jadi constraint $6 memotong tepat di tempat sinyalnya tinggal. Setiap hasil
yang berada di ambang signifikansi di universe penuh jatuh ke bawah ambang di
universe executable.

**Tapi kualifikasi yang jujur:** karena tidak ada faktor yang lolos KEEP di
universe penuh sekalipun, secara praktis **tidak ada edge yang benar-benar
hilang** — yang hilang adalah margin dari hasil yang memang sudah tidak lolos.
Constraint $6 bukan penyebab Stage 1.1 gagal. Kalaupun akun sebesar $10.000
dipakai dan seluruh universe executable, kesimpulan KEEP/KILL tidak berubah.

Satu-satunya faktor yang **menguat** di universe executable adalah R2 — konsisten
dengan asal-usulnya sebagai efek biaya funding, yang tidak bergantung likuiditas.

---

## 6. Temuan data yang butuh keputusan Anda sebelum Stage 1.2

### 6.1 Perp zombie — 9.5% panel adalah coin yang tidak diperdagangkan

Arsip `data.binance.vision` **tidak berhenti** saat sebuah perp berhenti
diperdagangkan. Ia terus menerbitkan bar 1H dengan volume 0 dan harga datar.

| Ukuran | Nilai |
|---|---:|
| observasi dengan `dollar_vol_24h == 0` | 32.146 (9.3%) |
| observasi dengan `fwd_48h` **persis 0** | 33.028 (9.52%) |
| observasi dengan \|`fwd_48h`\| < 0.2% (di bawah biaya) | 41.780 (12.04%) |
| symbol dengan ≥1 hari volume nol | 124 dari 752 |
| symbol dengan >50% hari volume nol | **44** |
| symbol dengan **100%** hari volume nol selama 730 hari | AGIXUSDT, OCEANUSDT, WAVESUSDT |

Dan jumlahnya tumbuh: 224 observasi zombie pada 2024-08, menjadi 3.438 pada
2026-07.

Konsekuensi: mendeteksi delisting dari "kapan file arsip berhenti" hanya
menemukan **7** symbol. Angka sebenarnya jauh lebih besar; delisting efektif
ditandai oleh volume menjadi nol, bukan oleh file yang berhenti. Observasi ini
menyumbang net **persis −0.20%** (biaya murni) ke kedua arah dan mengumpul di
bucket tertentu — `ema_state = 0` misalnya adalah detektor zombie, bukan sinyal.

Saya **tidak** memasukkan filter ini ke run R0–R8 (brief melarang menyisipkan
filter baru). Sebagai gantinya seluruh run dijalankan ulang di universe
diagnostik ketiga bernama `live_diag` (= executable **dan** volume hari itu > 0),
tersedia di `results/summary.csv`. Ringkasnya kesimpulan KEEP/KILL **tidak
berubah**, kecuali:

- R5 (ATR) spread net naik dari +0.189% (t=1.41) jadi **+0.326%**, CI
  [+0.077%, +0.575%], t=2.57 — masih gagal kriteria 1 dan Bonferroni, tapi
  perlu dilihat ulang di Stage 1.2
- R3 (volume z-score) spread gross jadi signifikan (−0.192%, t=−2.16) sementara
  net tetap nol

**Keputusan yang saya minta:** apakah `dollar_vol_24h > 0` (atau ambang volume
yang lebih tegas) menjadi bagian dari definisi eligible mulai Stage 1.2?
Menurut saya ya — instrumen tanpa satupun trade dalam 24 jam tidak bisa dimasuki
maupun ditinggalkan, jadi ini koreksi validitas data, bukan penambahan faktor.
Tapi itu perubahan definisi universe dan keputusannya milik Anda.

### 6.2 Ties funding merusak definisi persentil

Median **28.5%** symbol per hari berbagi nilai `funding_24h_sum` yang identik
(maksimum 85.8%). Contoh 2026-07-31: dari 746 symbol eligible, 151 punya persis
0.000250 dan 49 punya persis 0.

Akibatnya `funding_xs_pct` bukan persentil kontinu, dan "decile"-nya timpang
(D8 = 45.451 obs vs D9 = 23.935). Ekornya (D1, D10) tetap terdefinisi baik
karena di sana nilainya benar-benar tersebar — dan memang di sanalah semua
t-stat yang besar berada. Bucket tengah sebaiknya tidak dipakai sama sekali.

Untuk Stage 1.2: bucket berdasarkan **nilai funding absolut** dengan ambang
tetap (mis. ≤0, 0–0.01%, 0.01–0.05%, >0.05% per 8h) akan lebih jujur daripada
persentil, karena struktur distribusinya diskret.

### 6.3 Cakupan funding 92.0%

`funding_paid_48h` tersedia untuk 92.02% observasi eligible. Penyebabnya bukan
bug: untuk 48 symbol arsip `fundingRate` bulanannya berhenti lebih awal dari
arsip klines-nya (contoh MEMEFIUSDT: funding hanya 2025-04 s/d 2025-08 padahal
klines sampai 2026-08). Baris tanpa data funding **tidak** diasumsikan berbiaya
nol — nilainya NaN dan baris itu keluar dari statistik net. Konsekuensinya
R1/R6/R7 (yang butuh funding untuk bucketing) memakai ~320.500 observasi
sementara R0/R3/R4/R5 memakai 346.858.

Ditemukan juga: sebagian symbol memakai interval funding **4 jam**, bukan 8 jam.
Karena itu `funding_24h_sum` diimplementasikan sebagai jumlah seluruh event
dalam 24 jam terakhir, bukan "3 periode terakhir" seperti bunyi §3.1 brief —
untuk symbol 8-jam keduanya identik, untuk symbol 4-jam hanya yang pertama benar.

### 6.4 Universe berisi perp non-kripto

49 symbol adalah perp saham/ETF/komoditas (AAPLUSDT, NVDAUSDT, SPYUSDT, QQQUSDT,
XAUTUSDT, PAXGUSDT, bahkan OPENAIUSDT dan ANTHROPICUSDT), semuanya listing
setelah 2025-04-26. Totalnya 3.670 observasi = **1.06%** dari panel eligible,
jadi dampaknya ke hasil dapat diabaikan. Secara definisi §2.3 mereka memang
lolos (perp USDS-M quote USDT), tapi mereka bukan target strategi alt/memecoin
dan ikut menarik mean cross-section yang dipakai untuk market-neutral.
Tidak saya buang. Rekomendasi untuk Stage 1.2: tandai dan keluarkan.

---

## 7. Asumsi & keterbatasan — dibaca sebelum memakai angka manapun

### 7.1 exchangeInfo tidak dapat diakses (paling penting)

`fapi.binance.com`, `api.binance.com`, dan `www.binance.com` semuanya
ConnectTimeout dari mesin ini (kemungkinan blokir tingkat ISP; browser tool juga
ditolak). Hanya `data.binance.vision` yang reachable. Konsekuensi:

| Field | Sumber sebenarnya | Status |
|---|---|---|
| `stepSize` | **Diturunkan** dari eksponen desimal volume klines per (symbol, bulan) | Tervalidasi tepat 5/5 pada symbol yang nilainya diketahui: BTCUSDT 0.001, ETHUSDT 0.001, XRPUSDT 0.1, DOGEUSDT 1, 1000PEPEUSDT 1. Metode ini valid karena volume bar = jumlah quantity trade, jadi selalu kelipatan stepSize. Kelebihan tak terduga: hasilnya **point-in-time per bulan** dan tetap ada untuk symbol delisted — dua hal yang snapshot exchangeInfo hari ini tidak bisa berikan |
| `minQty` | **ASUMSI** = `stepSize` | Benar untuk mayoritas perp USDS-M tapi **tidak terverifikasi** |
| `MIN_NOTIONAL` | **ASUMSI** 5 USDT (BTCUSDT 100, ETHUSDT 20) | **Tidak terverifikasi.** Ini sebabnya syarat (a) gagal 0.00% di §2.2 — bukan temuan, melainkan konsekuensi asumsi. Kalau ada symbol dengan MIN_NOTIONAL 20 USDT seperti dikhawatirkan action plan §0.3, symbol itu **salah** dihitung executable di sini |

**Yang bisa Anda lakukan:** buka `https://fapi.binance.com/fapi/v1/exchangeInfo`
lewat VPN/HP, simpan ke `data/exchangeInfo_YYYY-MM-DD.json`. Saya cross-validasi
`minQty`/`MIN_NOTIONAL` untuk symbol yang masih listed dan revisi tabel gate.
Symbol delisted tetap harus memakai derivasi.

### 7.2 Slippage 0.10% round-trip adalah asumsi, bukan pengukuran

Sesuai konfirmasi Anda, dipakai sebagai baseline dengan sensitivitas 0.05% dan
0.20% dijalankan di semua bucket (kolom `mean_net_slip*bp`). Kesimpulan tidak
berubah di rentang manapun. Angka nyata baru ada dari Stage 6.

### 7.3 Multiple testing

Total 194 uji bucket dijalankan pada horizon utama di universe penuh — jauh
lebih banyak dari "~45" yang diperkirakan brief §5, karena grid R6 (5×3) dan R7
(5×5) menyumbang banyak sel. Dilaporkan dua koreksi berdampingan:
`p_value_bonferroni` (m=194, global) dan `p_value_bonferroni_family`
(m = jumlah bucket di dalam run itu saja). Tidak ada kesimpulan yang berubah
di antara keduanya.

### 7.4 Sharpe dan max drawdown bersifat indikatif

Deret return harian bucket bersifat **overlapping** (return 48 jam disampel
tiap hari), sehingga autokorelasinya membuat standard error Sharpe understated.
`max_dd` memakai model tranche (k = H/24 tranche berjalan bersamaan, kontribusi
harian = return_H / k). Keduanya diberikan untuk perbandingan antar bucket, bukan
sebagai proyeksi kinerja.

### 7.5 BTCUSDT/ETHUSDT

Sesuai keputusan Anda: ditandai `is_benchmark`, **tidak** masuk pooled ablation
maupun perhitungan mean cross-section untuk market-neutral, tapi tetap ada di
panel sebagai kontrol dan sumber return BTC (`data/daily_market.csv`).

---

## 8. Ide untuk stage berikutnya — TIDAK dimasukkan ke run manapun

Dicatat sesuai instruksi, tidak disisipkan ke R0–R8.

1. **Bucket funding berbasis nilai absolut, bukan persentil** (§6.2). Struktur
   ties membuat persentil menyesatkan di tengah distribusi.
2. **Uji spread long-short sebagai strategi tersendiri.** R1 dan R2 keduanya
   memberi spread signifikan sementara tidak ada leg tunggal yang positif.
   Kalau desain diizinkan memegang dua posisi berlawanan, R2 layak diuji ulang
   sebagai market-neutral pair. Ini perubahan desain strategi, bukan parameter.
3. **`funding_ts_z30` × `funding_xs_pct` sebagai interaksi** — keduanya
   signifikan gross dengan arah **berlawanan**, yang berarti keduanya tidak
   mengukur hal yang sama. Interaksi ini tidak ada di §4 dan tidak dijalankan.
4. **Cek apakah efek R1 hidup di funding basis atau di harga.** Sinyal gross
   +1.017% dan drag funding 0.835% nyaris sama besar — perlu dipastikan ini
   bukan identitas mekanis (funding memang dihitung dari premium harga).
   Kalau ternyata identitas, R1 bukan sinyal sama sekali.
5. **Arsip `futures/um/daily/metrics/` ada di data.binance.vision** dan berisi
   `sum_open_interest`, `count_toptrader_long_short_ratio`, dan sejenisnya.
   Kalau retensinya lebih dari 30 hari, sebagian **Stage 4 tidak perlu menunggu
   logger Stage 0.** Belum saya verifikasi — di luar scope Stage 1.1, tapi
   layak dicek lebih dulu karena bisa memajukan jadwal berbulan-bulan.
6. **MAE/MFE sudah tersimpan** untuk window 24/48/72h berikut `bar_index`-nya.
   Stage 2 cukup query dua kolom; tidak perlu menyentuh price path lagi.

---

## 9. Reproduksi

```
python src/fetch.py       # download+cache arsip (5,8 menit, 29.145 file, 0 gagal, 457 MB)
python src/features.py    # fitur per symbol -> data/interim/   (0,7 menit)
python src/panel.py       # panel + cross-section -> data/panel.parquet
python src/gate_table.py  # gate eksekutabilitas -> results/GATE_executability.md
python src/ablation.py    # R0..R8 -> results/           (1,3 menit)
python src/chart.py       # funding_bucket_curve.png
```

Lingkungan: Python 3.14.5, pandas 3.0.3, numpy 2.4.6, pyarrow 25.0.1,
scipy 1.18.1, matplotlib 3.11.1. Seed 20260823 (bootstrap). Panel:
371.408 baris, 776 symbol, 730 hari, 47 kolom mentah + turunan.

Kolom yang disimpan tapi **belum dipakai** R0–R8 (capture-once §3.4):
klines 1H mentah di `data/raw/`, `mae_*`/`mfe_*`/`mae_bar_*`/`mfe_bar_*` untuk
24/48/72h, `funding_paid_*` + `n_fund_ev_*` per horizon, `step_size` per bulan,
`stop_pct_1atr`, label 24h dan 72h, dan `data/daily_market.csv`
(return BTC, mean/dispersi cross-section, funding market-wide per hari).

---

## 10. Rekomendasi

Exit criteria Stage 1 (action plan §3): *"Kalau nol faktor lolos → strategi
tidak jalan, hentikan, jangan lanjut ke Stage 2."*

Nol faktor lolos. Rekomendasi saya: **jangan mulai Stage 2.** Mengoptimasi
stop/target di atas faktor yang tidak punya kandungan prediktif net hanya akan
menghasilkan permukaan expectancy yang cantik dan palsu.

Yang layak dikerjakan sebelum memutuskan strategi ini mati:

1. Putuskan §6.1 (zombie perp) — ini mempengaruhi 9.5% panel dan jawabannya
   mengubah beberapa angka di ambang.
2. Kirim `exchangeInfo` (§7.1) supaya syarat (a) gate benar-benar teruji.
3. Verifikasi §8.4 — apakah efek R1 identitas mekanis atau sinyal sungguhan.
   Kalau identitas, R1 bukan sekadar KILL, tapi tidak pernah ada.
4. Kalau Anda bersedia mengubah desain ke posisi berpasangan, R2 layak
   diuji ulang (§8.2). Itu keputusan strategi, bukan tuning parameter, dan
   harus dinyatakan eksplisit sebelum dijalankan.
5. Stage 0 logger tetap jalan paralel — Stage 1.1 tidak mengubah apapun di sana,
   dan layer OI/LSR/CVD adalah satu-satunya sumber informasi yang belum diuji.
