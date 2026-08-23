# Handoff ke Claude Code — Stage 1.1

**Cara pakai:** simpan tiga file dokumen ke folder proyek (lihat §1), buka Claude Code di folder itu, lalu paste isi §2 sebagai prompt pertama.

---

## 1. Lokasi proyek

**Root proyek: `C:\Crypto data 2`**

Semua pekerjaan Stage 1.1 terjadi di sini. Struktur sudah dibuat:

```
C:\Crypto data 2\
├── CLAUDE-CODE-HANDOFF.md          ← file ini
├── .gitignore                       ← data/ sudah diblokir (ukurannya GB)
├── docs\
│   ├── dew-action-plan.md           ✅ sudah ada
│   ├── stage-1.1-backtest-brief.md  ✅ sudah ada
│   └── dew-futures-screener-strategy.md   ⬅ PERLU DI-EXPORT MANUAL
├── data\      (kosong — diisi Claude Code)
├── results\   (kosong — diisi Claude Code)
└── src\       (kosong — diisi Claude Code)
```

### ⚠️ Nama folder mengandung spasi

`C:\Crypto data 2` punya spasi di namanya. Setiap path di shell/script wajib dikutip:

```bash
cd "C:\Crypto data 2"
python "src/fetch.py" --out "C:/Crypto data 2/data"
```

Di Python, gunakan `pathlib.Path` dan jangan pernah menyusun path lewat konkatenasi string mentah.

### Dokumen yang masih kurang

`dew-futures-screener-strategy.md` ada di project knowledge Claude.ai (project **"Bitcoin Invest & Trade"**) dan harus di-export manual ke `docs\`.

Bukan blocker — dua dokumen lain sudah self-contained. Tapi tanpa itu, konteks §3 (konflik funding vs OI) dan §8.2 (momentum vs reversal) hilang, padahal itu dasar run R4 dan R7.

---

## 2. Prompt untuk Claude Code (copy-paste utuh)

```
Saya mau kamu eksekusi Stage 1.1 dari proyek backtest crypto futures saya.

ROOT PROYEK: C:\Crypto data 2
Semua output ditulis di dalam folder ini. Jangan menulis di luar folder ini.
PERHATIAN: nama folder mengandung SPASI. Kutip semua path di shell/script,
dan pakai pathlib.Path di Python — jangan konkatenasi string mentah.

BACA DULU, JANGAN LANGSUNG CODING:
1. docs/stage-1.1-backtest-brief.md  ← spesifikasi utama, ikuti persis
2. docs/dew-action-plan.md           ← konteks stage & keputusan yang sudah dikunci
3. docs/dew-futures-screener-strategy.md ← latar belakang strategi (kalau ada)

Setelah baca, konfirmasi 3 hal di §9 brief sebelum menulis kode apapun.

=== PARAMETER YANG DIKUNCI — JANGAN DIUBAH, JANGAN DIOPTIMASI ===
- Capital: $100 USD
- Sizing: margin 3% ($3) x leverage 2x = NOTIONAL $6.00 FIXED
- Notional TIDAK diturunkan dari risk%/stop%. Tidak ada volatility targeting,
  tidak ada risk parity, tidak ada penyesuaian ukuran apapun.
- Bobot portfolio: equal-weight
- Arah: long DAN short, dilaporkan terpisah
- Periode: 2024-08-01 s/d 2026-07-31
- Universe: semua perp USDT Binance USDS-M, TERMASUK yang sudah delisted

=== SCOPE ===
Stage 1.1 = bangun panel data + jalankan 9 run ablation (R0-R8) sesuai §4 brief.

Yang TIDAK dikerjakan sekarang:
- Optimasi stop/target (itu Stage 2)
- Walk-forward (Stage 3)
- Layer OI/LSR/CVD (Stage 4 — datanya belum ada)
- Tuning parameter apapun

=== 4 HAL YANG PALING SERING BIKIN BACKTEST CRYPTO BOHONG ===
Semuanya WAJIB ditangani, jangan ada yang dilewat (§1 brief):
1. Survivorship bias  -> universe HARUS termasuk symbol delisted.
   Jangan pakai exchangeInfo hari ini sebagai universe historis.
2. Cross-sectional correlation -> standard error WAJIB di-cluster per tanggal.
   Tanpa ini semua faktor akan palsu-signifikan karena semua altcoin gerak bareng BTC.
3. Beta terselubung -> wajib laporkan versi market-neutral (kurangi mean
   return cross-section harian).
4. Lookahead -> fitur dari data yang closed di t, label dari OPEN t+1.

=== ANTI KERJA DUA KALI — PALING PENTING (§3.4 brief) ===
Yang mahal itu download+parsing, bukan analisisnya. Satu pass download harus
menangkap semua kebutuhan sampai Stage 3. Wajib disimpan walaupun R0-R8 tidak
memakainya:

- Klines 1H MENTAH (jangan cuma agregat harian)
- MAE/MFE per observasi untuk window 24h/48h/72h  <-- ini yang paling berharga
- bar_index_of_MAE dan bar_index_of_MFE (untuk asumsi konservatif Stage 2)
- Funding per periode + timestamp (bukan cuma jumlah harian)
- exchangeInfo snapshot harian: stepSize, minQty, MIN_NOTIONAL
- Symbol delisted
- Return BTC + agregat cross-section harian (mean, dispersi, funding market-wide)
- Label 24h/48h/72h sekaligus

Dengan MAE/MFE tersimpan, Stage 2 nanti cukup query dua kolom, tidak perlu
scan ulang price path sama sekali.

=== KONSTRAIN EKSEKUSI $100 (§2.5 brief) ===
Evaluasi per (tanggal, symbol), BUKAN sekali di awal — harga bergerak 2 tahun
jadi constraint-nya time-varying:

  qty_ideal  = 6.00 / close_t
  qty_actual = floor_to_step(qty_ideal, stepSize)
  executable = MIN_NOTIONAL <= 6.00
               AND qty_actual >= minQty
               AND abs(qty_actual*close_t - 6.00)/6.00 <= 0.10

Laporkan SEMUA run dua kali: universe penuh, dan universe executable saja.

=== OUTPUT PERTAMA YANG SAYA MAU LIHAT ===
Sebelum run ablation, kasih saya tabel ini dulu:
distribusi (stepSize x harga) untuk seluruh universe perp, diurutkan.
Saya mau tahu berapa banyak coin yang benar-benar bisa ditradingkan di notional $6.
Ini gate — kalau mayoritas universe gagal, desainnya perlu dibahas ulang
sebelum lanjut.

=== DELIVERABLE ===
Struktur repo ada di §7 brief. Yang wajib:
- data/panel.parquet (partisi bulanan)
- results/R0..R8 csv + summary.csv
- results/funding_bucket_curve.png
- STAGE_1_1_FINDINGS.md yang menjawab 3 pertanyaan di §7 brief secara eksplisit

Aturan pelaporan: setiap angka disertai n dan confidence interval.
Tidak ada angka telanjang. Kalau tidak ada bucket yang signifikan,
TULIS ITU — jangan cari bucket terbaik dari noise.

=== GIT ===
Init repo, .gitignore untuk data/ (ukurannya GB), commit per milestone,
push ke GitHub. Konfirmasi dulu nama repo-nya ke saya.

=== KALAU ADA IDE BARU ===
Catat di STAGE_1_1_FINDINGS.md untuk stage berikutnya. JANGAN sisipkan
faktor/filter/parameter baru ke run yang sedang berjalan.
```

---

## 3. Checklist sebelum kirim prompt

- [x] Folder `C:\Crypto data 2` dengan struktur `docs\ data\ results\ src\`
- [x] `docs\dew-action-plan.md`
- [x] `docs\stage-1.1-backtest-brief.md`
- [x] `.gitignore` (data/ diblokir)
- [ ] `docs\dew-futures-screener-strategy.md` di-export dari project knowledge — opsional, disarankan
- [ ] Claude Code dibuka di `C:\Crypto data 2` (bukan di subfolder)
- [ ] Siap menjawab 3 pertanyaan §9 brief: nama repo GitHub, angka slippage dari pengalaman eksekusi manual, status BTC/ETH di universe

---

## 4. Yang harus dijalankan paralel — jangan tunggu Stage 1.1

Logger Stage 0 (§2 action plan). Setiap hari tanpa logger = data OI/LSR hilang permanen, retensi Binance cuma 30 hari dan tidak ada arsip di manapun.

Prompt terpisah untuk Claude Code:

```
Buat data logger harian sesuai §2 dew-action-plan.md.
Tarik 7 endpoint yang terdaftar di tabel, simpan Parquet partisi date=YYYY-MM-DD,
push ke GitHub via cron/GitHub Actions harian.
Semua endpoint publik, tidak perlu API key.
Prioritaskan yang retensinya 30 hari (openInterestHist, globalLongShortAccountRatio,
topLongShortPositionRatio, takerlongshortRatio) — itu yang hilang kalau telat.
exchangeInfo juga wajib, untuk stepSize/minQty/MIN_NOTIONAL.
```

Logger ini juga yang menghasilkan tabel `stepSize × harga` yang diminta di §2.
