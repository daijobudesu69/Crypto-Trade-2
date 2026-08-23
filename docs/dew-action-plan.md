# Dew Futures Screener — Action Plan (Stage 0–6)

**Capital:** $100 USD
**Hold window:** 1–2 hari
**Universe:** Binance USDⓈ-M perpetual (alt/memecoin)
**Dibuat:** 23 Agustus 2026
**Catatan penamaan:** semua "Fase" di `dew-futures-screener-strategy.md` §7/§10 diganti menjadi **Stage** di dokumen ini. Mapping: Fase 0→Stage 0, Fase 1→Stage 1, Fase 2→Stage 2, Fase 3→Stage 3, Fase 4→Stage 4, Fase 5→Stage 5. Stage 6 (live micro) baru.

---

## 0. Konsekuensi capital $100 — baca ini dulu

Ini mengubah tiga hal di spec awal. Bukan detail kosmetik.

### 0.1 Sizing rule — LOCKED

Keputusan Dew, final. Tidak diturunkan dari stop distance.

```
Margin per trade = 3% × $100 = $3.00
Leverage         = 2x
NOTIONAL         = $6.00   ← fixed, tidak bergantung stop/ATR/harga
Max 3 posisi     → total notional $18 (18% capital), margin $9 (9%)
```

Karakternya: **ukuran posisi tetap, kerugian berubah-ubah** (kebalikan dari sizing risk-based, di mana kerugian tetap dan ukuran berubah).

| Stop | Rugi kena stop | Setara risk% capital |
|---|---|---|
| 5% | −$0.30 | 0.30% |
| 10% | −$0.60 | 0.60% |
| 15% | −$0.90 | 0.90% |
| 20% | −$1.20 | 1.20% |

Risk efektif 0.3–1.2% per trade — **di bawah** rentang 1–2% di spec awal. Posisi lebih konservatif dari desain awal, bukan lebih agresif.

Keuntungan metodologis: notional tetap = **equal-weight**, persis asumsi run ablation R0–R8. Tidak ada re-weighting yang mencampur efek sizing ke pengukuran faktor.
Konsekuensi yang dikelola: trade high-ATR menyumbang rugi dollar 4× trade low-ATR. Dinetralkan dengan melaporkan semua metrik dalam **persen**, bukan dollar.

### 0.2 Liquidity gate berhenti jadi constraint kapasitas

$6 notional muat di perp manapun yang listed di Binance. Tabel §2 spec awal (`$10K → $200K volume`) **tidak berlaku** — extrapolasi ke bawah memberi gate di bawah $1K volume 24h, yang meloloskan 100% universe.

**Reframe:** liquidity gate tetap dipakai, tapi tujuannya berubah dari *"bisa keluar posisi?"* menjadi *"apakah sinyal di coin ini punya arah yang sama dengan coin likuid?"* — persis isu §8.2 (momentum vs reversal). Jadi likuiditas masuk sebagai **conditioning variable di backtest**, bukan hard gate. Stage 1.1 yang menentukan di mana potongnya, kalau ada.

### 0.3 Constraint yang benar-benar mengikat: MIN_NOTIONAL + step size

Dengan notional tetap $6, constraint-nya tidak lagi bergantung volatilitas — tapi jadi **bergantung harga**, dan harga bergerak sepanjang backtest.

| Syarat | Ambang | Kegagalan tipikal |
|---|---|---|
| `MIN_NOTIONAL ≤ $6` | Standar bursa 5 USDT | Symbol dengan MIN_NOTIONAL 20 USDT → **tereksklusi total**, order $6 ditolak |
| `floor(6 ÷ price, stepSize) ≥ minQty` | Per symbol | stepSize kasar relatif harga → quantity membulat ke 0, posisi tidak bisa dibuka |
| Error kuantisasi ≤ 10% | Toleransi pilihan | stepSize 0.1 @ harga 77.5 → notional aktual $7.75 (+29%), merusak equal-weight |

Contoh HYPE @ 77.544: qty ideal 0.07738. Kalau stepSize 0.001 → notional $5.97 ✅. Kalau stepSize 0.1 → notional $7.75 ❌ (margin terpakai $3.88, melebihi aturan 3%).

**Aksi:** Stage 0 menarik `exchangeInfo` harian dan menyimpan `MIN_NOTIONAL`, `stepSize`, `minQty` per symbol. Stage 1.1 mengevaluasi eksekutabilitas **per (tanggal, symbol)** — bukan sekali di awal, karena harga berubah.

### 0.4 $100 adalah akun validasi, bukan akun profit

Pada notional $6, stop 10%, RR 2:1 → menang +$1.20, kalah −$0.60.
Win rate 40% → expectancy +$0.12/trade. Pada 2 sinyal/minggu ≈ **+$12/tahun**. Itu bukan penghasilan, itu biaya sekolah.

Fungsi akun $100 yang benar: mengukur **slippage & fill realita vs asumsi backtest**, dan menguji disiplin eksekusi. Angka yang dikumpulkan di sini (selisih harga sinyal vs harga fill) adalah input untuk Stage 3, dan nilainya jauh lebih besar dari P&L-nya.

Implikasi: jangan naikkan risk% untuk "mengejar angka". Kalau Stage 1–5 memberi hasil positif, yang di-scale adalah capital, bukan risk fraction.

---

## 1. Funding rate — range untuk entry

### 1.1 Status jujur

**Saya tidak bisa menentukan range yang tervalidasi dari sesi ini.** Akses ke `fapi.binance.com` dan `data.binance.vision` diblokir. Menyebut angka persentil sekarang = persis kesalahan yang dikoreksi di §12 spec awal.

Yang bisa saya lakukan: memisahkan dua peran funding yang selama ini dicampur, dan menurunkan satu batas yang **tidak butuh backtest**.

### 1.2 Funding punya dua peran berbeda — pisahkan

| Peran | Sifat | Butuh backtest? | Conviction |
|---|---|---|---|
| **A. Biaya carry** | Deterministik — Anda benar-benar membayar/menerima uang ini | Tidak | 95% |
| **B. Sinyal crowding** | Prediktif — funding tinggi = long sesak = potensi reversal | Ya | 55% |

Spec awal (§3, tabel zona p40/p75/p90) mencampur keduanya jadi satu tabel. Itu sumber kebingungannya.

### 1.3 Peran A — batas atas yang bisa diturunkan sekarang

Funding dibayar tiap 8 jam (3×/hari) untuk mayoritas perp. Hold 1–2 hari = **3–6 periode**.

```
Cap per periode = Budget funding total ÷ 6 periode (worst case hold 2 hari)
```

Ambil budget funding dari §7 spec awal (elevated case = 0.30% dari total drag 0.55%):

| Budget funding total (2 hari) | Cap per periode 8h | Sebagai kelipatan neutral (0.01%) |
|---|---|---|
| 0.15% (konservatif) | 0.025% | 2.5× |
| **0.30% (baseline §7)** | **0.050%** | **5×** |
| 0.60% (agresif) | 0.100% | 10× |

**Untuk LONG, cap default: funding ≤ 0.05% per 8h.**

Angka 0.05% ini kebetulan sama dengan threshold yang ditolak di §3 spec awal — tapi asal-usulnya berbeda. Di sana angka bulat tanpa derivasi. Di sini turunan dari budget drag 0.30% ÷ 6 periode. Input yang bisa diperdebatkan adalah **budget 0.30%**-nya (itu pilihan kebijakan), bukan aritmatikanya.

**Implementasi yang benar:** jangan hard-code 0.05%. Konversi cap ini ke persentil cross-section **setiap hari**:

```
cap_percentile_hari_ini = persentil dari 0.05% dalam distribusi funding
                          seluruh coin yang eligible hari ini
```

Kalau seluruh pasar panas dan 0.05% jatuh di p20, Anda otomatis dapat sinyal "market overleveraged, kecilkan size" — persis fungsi Context layer §1.3. Self-calibrating, tidak perlu maintenance manual.

### 1.4 Peran B — kenapa "zona nyaman p40–p75" kemungkinan salah arah

Ini poin kontrarian, dan saya labeli hipotesis.

Kalau funding punya kandungan prediktif, **isi informasinya ada di ekor, bukan di tengah**. Bucket tengah (p40–p75) adalah definisi dari "funding tidak mengatakan apa-apa tentang coin ini". Memilih zona tengah = sengaja menyeleksi populasi paling tidak informatif, lalu menyebutnya filter.

Dukungan tidak langsung: §1.2 spec awal sendiri mencatat R² funding vs price move 7 hari hanya **~12.5%**. Hubungan selemah itu, secara linear, hampir pasti tidak seragam di seluruh distribusi — kalau ada tanda tangan, tempatnya di p90+ atau p<10.

**Hipotesis yang harus diuji Stage 1.1 (conviction 55%):**

| Bucket funding | Hipotesis peran |
|---|---|
| p0–p10 (sering negatif) | Short sesak → **tailwind untuk long** (short squeeze fuel) + Anda **dibayar** untuk long |
| p10–p90 | Tidak informatif sebagai selector. Jangan filter di sini — biarkan layer lain (struktur, volume) yang menyeleksi |
| p90+ | Long sesak → **kandidat short**, bukan long yang dihindari |

Perhatikan bahwa ini menyelesaikan konflik struktural §3 (funding gate vs OI+momentum filter): funding berhenti jadi *penolak kandidat* dan jadi *pemilih arah*. Setup "OI naik + harga naik + funding p95" tidak dibuang — dia dibaca ulang sebagai setup short, bukan long yang gagal filter.

Ini juga alasan Stage 1.1 diuji **long + short**. Menguji long-only akan membuang setengah informasi bucket ekstrem.

### 1.5 Range operasional sementara (dipakai sampai Stage 1.1 selesai)

| Arah | Aturan | Basis | Status |
|---|---|---|---|
| **Long** | funding ≤ 0.05% per 8h (dikonversi ke persentil harian) | Derivasi biaya §1.3 | Dipakai |
| **Long** | tidak ada batas bawah | Klaim "< p40 = tidak ada bahan bakar" tidak punya dukungan apapun | Dihapus |
| **Short** | funding ≥ p90 cross-sectional = tailwind (Anda menerima funding) | Derivasi biaya, arah terbalik | Dipakai |
| **Semua** | bucket p10–p90 tidak dipakai sebagai selector | Hipotesis §1.4 | **Diuji di Stage 1.1** |

**Satu-satunya angka yang saya pertahankan tanpa backtest adalah cap biaya (0.05%), karena itu aritmatika, bukan prediksi.** Semua yang lain menunggu data.

---

## 2. Stage 0 — Data logger (jalankan paralel, mulai hari ini)

Retensi Binance untuk OI/LSR/taker ratio hanya 30 hari. Setiap hari tanpa logger = data hilang permanen.

| Item | Endpoint | Frekuensi |
|---|---|---|
| Open interest hist | `/futures/data/openInterestHist` | 1×/hari, period=1h, limit max |
| Global long/short acct ratio | `/futures/data/globalLongShortAccountRatio` | 1×/hari |
| Top trader long/short | `/futures/data/topLongShortPositionRatio` | 1×/hari |
| Taker buy/sell vol | `/futures/data/takerlongshortRatio` | 1×/hari |
| Funding + mark price | `/fapi/v1/premiumIndex` | 1×/hari |
| Ticker 24h | `/fapi/v1/ticker/24hr` | 1×/hari |
| **Exchange info** | `/fapi/v1/exchangeInfo` | 1×/hari — **wajib**, untuk MIN_NOTIONAL/LOT_SIZE (§0.2) |

Output: Parquet harian ke repo GitHub, partisi `date=YYYY-MM-DD`. Tanpa API key (semua endpoint publik).

**Exit criteria Stage 0:** logger jalan 30 hari berturut tanpa gap → Stage 4 unblocked.

---

## 3. Stage 1 — Ablation, layer yang sudah bisa dibacktest

Data yang tersedia penuh hari ini: **klines** (2 tahun) + **fundingRate** (2 tahun). Itu cukup untuk menguji semua layer kecuali OI/LSR/CVD.

### Stage 1.1 — Full backtestable ablation ← **yang kita jalankan sekarang**
Spec lengkap ada di `stage-1.1-backtest-brief.md`. Ringkas: bangun panel fitur harian untuk seluruh universe perp (termasuk yang sudah delisted), lalu jalankan 9 run ablation terisolasi (R0–R8), long + short, dengan standard error di-cluster per tanggal.

### Stage 1.2 — Keep/kill decision
Untuk tiap faktor: pertahankan hanya kalau efeknya bertahan setelah (a) demeaning cross-sectional harian, (b) koreksi multiple testing, (c) dikurangi biaya. Faktor yang lolos hanya di gross return → buang.

**Exit criteria Stage 1:** daftar faktor yang lolos + effect size dengan confidence interval. Kalau nol faktor lolos → strategi tidak jalan, hentikan, jangan lanjut ke Stage 2.

---

## 4. Stage 2 — Stop / target optimization

Grid: ATR multiplier 0.8×–2.5× (step 0.1) × RR target 1.0–4.0 (step 0.25).
Objective: **expectancy per trade**, bukan win rate, bukan total return.
Constraint tambahan (baru, dari §0.2): buang kombinasi yang menghasilkan notional < MIN_NOTIONAL pada capital $100.

**Exit criteria:** permukaan expectancy yang stabil (bukan puncak tunggal terisolasi — itu tanda overfit).

---

## 5. Stage 3 — Walk-forward validation

Rolling 6 bulan train / 2 bulan test, step 2 bulan → ~9 fold dalam 2 tahun.
Parameter di tiap fold diambil **hanya** dari window train-nya. Dilarang memakai parameter full-sample.
Tambahkan: injeksi slippage dari data live Stage 6 kalau sudah ada.

**Exit criteria:** out-of-sample expectancy > 0 di ≥6 dari 9 fold, dan degradasi IS→OOS < 50%.

---

## 6. Stage 4 — Integrasi layer OI / LSR / CVD

Blocked sampai Stage 0 mengumpulkan ≥30 hari (idealnya 90+).
Uji matriks 4 kuadran §5 spec awal sebagai faktor terpisah, lalu ulangi ablation dengan layer penuh.
Peringatan: window 30–90 hari terlalu pendek untuk kesimpulan kuat. Perlakukan Stage 4 sebagai *tidak menolak*, bukan *mengkonfirmasi*.

---

## 7. Stage 5 — Paper trading

Minimum 60 hari, target ≥30–50 trade. Sinyal digenerate otomatis, eksekusi dicatat manual.
Yang diukur: bukan P&L, tapi **selisih paper vs backtest** (frekuensi sinyal, harga fill, waktu hold aktual).

**Exit criteria:** frekuensi sinyal paper dalam ±40% dari prediksi backtest, dan tidak ada bug logika yang muncul.

---

## 8. Stage 6 — Live micro ($100)

Baru dimulai setelah Stage 1–5 lolos semua exit criteria.
Sizing per §0.1: margin $3 × 2x = notional $6. Max 3 posisi (notional $18, margin $9). Daily stop −5% = −$5 — pada rugi rata-rata $0.60/trade, praktis tidak terjangkau dengan 3 posisi, jadi batas efektifnya adalah jumlah posisi, bukan daily stop.
Tujuan tunggal: mengukur slippage nyata dan menguji disiplin. **Bukan** menghasilkan uang.
Review setelah 50 trade: kalau expectancy live berada dalam CI backtest → pertimbangkan scale capital (bukan scale risk%).

---

## 9. Ringkasan urutan & blocker

| Stage | Isi | Blocker | Bisa mulai |
|---|---|---|---|
| 0 | Data logger | — | **Sekarang** |
| **1.1** | **Full ablation (klines+funding)** | — | **Sekarang** |
| 1.2 | Keep/kill | Stage 1.1 | Setelah 1.1 |
| 2 | ATR/RR grid | Stage 1.2 | Setelah 1.2 |
| 3 | Walk-forward | Stage 2 | Setelah 2 |
| 4 | Layer OI | Stage 0 ≥30 hari | ~Sept 2026 |
| 5 | Paper trading | Stage 3 + 4 | Setelah 3&4 |
| 6 | Live $100 | Stage 5 | Setelah 5 |

Stage 0 dan Stage 1.1 **paralel** — tidak saling menunggu.

---

## 10. Conviction (diperbarui)

| Klaim | Skor | Basis |
|---|---|---|
| Liquidity gate tidak mengikat di notional $6 | 95% | Aritmatika, deterministik |
| Notional tetap $6 = equal-weight, cocok dengan desain ablation R0–R8 | 90% | Konsekuensi logis langsung, bukan temuan empiris |
| Step size (bukan MIN_NOTIONAL) adalah constraint yang paling sering mengikat di notional $6 | 70% | Aritmatika jelas, tapi distribusi stepSize di universe perp belum diverifikasi — output Stage 0 |
| Metrik dalam persen menetralkan distorsi dollar dari notional tetap | 88% | Benar secara statistik untuk perbandingan faktor; tidak menetralkan distorsi di P&L portfolio riil |
| Cap funding 0.05%/8h untuk long | 80% | Aritmatika benar; input budget 0.30% adalah pilihan kebijakan, bukan temuan |
| Batas bawah funding ("< p40 = no fuel") tidak berdasar | 85% | Tidak ada mekanisme maupun bukti yang pernah dikemukakan |
| Sinyal funding ada di ekor, bukan di tengah | 55% | Konsisten dengan R²=12.5%, tapi belum diuji di data Binance |
| Funding sebagai pemilih arah > funding sebagai penolak kandidat | 65% | Menyelesaikan konflik struktural §3 secara logis; belum diuji |
| Strategi layak live sekarang | 15% | Turun dari 20% — constraint MIN_NOTIONAL baru teridentifikasi |
| Layak setelah Stage 1–5 | 50% | Turun dari 55% — capital $100 membatasi universe, sample size makin tipis |
