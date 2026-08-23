# Dew Futures Screener — Strategy Spec & Validation Roadmap

**Hold window:** 1–2 hari
**Universe:** Altcoin/memecoin perpetual futures (DOGE, SHIB, PEPE, PENGU, dll.)
**Exchange:** Binance USDⓈ-M Futures
**Status:** Belum divalidasi. Dokumen ini adalah spesifikasi + rencana kerja, bukan strategi siap-live.
**Terakhir diupdate:** 21 Agustus 2026

---

## 0. TL;DR untuk yang buru-buru

- Framework 3-lapis: **Hard Gate** (syarat mutlak) → **Soft Gate** (skor, diranking) → **Context** (atur ukuran posisi, bukan pilih coin).
- Threshold apapun yang muncul di dokumen ini dan **tidak** berlabel "TERUKUR" adalah **hipotesis awal**, bukan aturan final. Semua harus diuji lewat ablation test sebelum dipakai live.
- Data Binance untuk backtest lengkap 2 tahun: **klines** dan **funding rate**. Data OI/long-short/taker ratio **cuma tersimpan 30 hari** — logger harus jalan dari sekarang.
- Liquidation heatmap **diganti** dengan Volume Profile (VPVR) + swing high/low, karena heatmap adalah estimasi vendor yang tidak bisa di-backtest.
- Jangan live-trading sebelum Fase 1–4 (lihat §7) selesai.

---

## 1. Tiga Lapis Filter

Analogi: **Hard gate = satpam** (gagal satu = batal, tanpa nego). **Soft gate = rapor** (dijumlah jadi skor, yang tertinggi menang). **Context = cuaca** (tidak menentukan pilih coin, menentukan boleh keluar rumah atau tidak, dan bawa payung sebesar apa).

### 1.1 Hard Gate

| # | Indikator | Threshold (starting point — HARUS diverifikasi ulang) | Kenapa hard |
|---|---|---|---|
| 1 | Likuiditas perp | Lihat §2 (bukan angka tetap, turunan dari ukuran portofolio) | Kalau tipis, bisa masuk tapi tidak bisa keluar saat panik |
| 2 | Spread + depth | Spread < 0.05%, depth memadai dalam 0.5% dari mid, **diukur berulang** (bukan sekali saat tenang) | Slippage diam-diam memakan RR |
| 3 | Risk cap | Max 1–2% risk/trade, max 3 posisi terbuka, stop trading harian di −5% | Satu-satunya hal yang menjamin strategi bertahan cukup lama untuk diuji |
| 4 | Event blackout | Skip jika ada FOMC/CPI/NFP dalam window hold | Hold 1–2 hari pasti kena event — ini judi berita, bukan trading |
| 5 | Regime BTC | BTC tidak baru saja break support daily dalam 24 jam terakhir | Memecoin beta 2–3x ke BTC. Kalau kapal induk bocor, tidak penting posisi di kabin mana |

### 1.2 Soft Gate

| Indikator | Cara skor | Bobot awal (BELUM TERUKUR) | Catatan |
|---|---|---|---|
| Volume surge | Z-score vs rata-rata 30 hari | 20% | |
| OI + arah harga (4 kuadran) | Lihat matriks di §5 | 25% | Paling informatif secara teori — OI naik + harga naik = uang baru masuk |
| Funding rate | Persentil cross-sectional (lihat §3) | 10% | Riset: R² hanya ~12.5% terhadap price move 7 hari — bobot kecil sengaja |
| Momentum 24h | Positif, **hanya berlaku jika lolos liquidity gate ketat** | 15% | Di coin tipis, arahnya justru terbalik jadi reversal signal |
| Market structure | BOS/CHoCH searah | 20% | Trigger entry, lihat §4 |
| CVD divergence | Konfirmasi 15M + 1H | 10% | Timing, bukan seleksi |

Ambang eksekusi awal: skor ≥ 70/100 — **ini juga tebakan, harus dikalibrasi ulang setelah backtest.**

**Aturan wajib:** setelah ablation test (§7 Fase 1), bobot yang marginal contribution-nya nol dibuang. Jangan biarkan bobot tebakan ini jadi permanen.

### 1.3 Context

| Indikator | Fungsi |
|---|---|
| Struktur BTC jangka pendek | Naikkan/turunkan size, bukan pilih coin |
| BTC dominance | Naik = uang lari ke BTC, alt sepi. Turun = alt punya ruang |
| Funding rate market-wide | Semua coin panas = market overleveraged = kecilkan size |
| Makro (DXY, yield, kebijakan Fed) | On/off switch harian, bukan pemilih coin |
| On-chain (MVRV, NUPL, STH cost basis) | Konteks siklus 6–12 bulan — **tidak relevan** untuk keputusan hold 1–2 hari |

---

## 2. Liquidity Gate — Cara Hitung yang Benar (bukan angka tetap)

**Kesalahan yang harus dihindari:** memakai angka absolut seperti "$100M volume 24h" tanpa derivasi. Itu tebakan.

**Formula:**
```
Notional posisi = (Risk% ÷ Stop%) × Portfolio
```
Contoh: risk 1%, stop 5% (ATR-based) → `Notional = 0.2 × Portfolio`

Aturan: jangan jadi >0.1–1% dari volume harian coin tersebut. Kalikan buffer 10x karena likuiditas bisa menguap 80–90% saat cascade — persis saat dibutuhkan.

| Portfolio | Notional posisi | Volume 24h minimum (buffer 10x @1% ADV) |
|---|---|---|
| $10K | $2,000 | ~$200K |
| $50K | $10,000 | ~$1M |
| $200K | $40,000 | ~$4M |

**Catatan penting:** volume 24h adalah proxy yang lemah untuk pertanyaan sebenarnya — *"bisa nggak keluar posisi $X dalam beberapa detik saat harga jatuh 8%?"* Volume tinggi bisa berasal dari wash trading atau satu spike lama. Yang benar-benar menjawab pertanyaan itu adalah **spread + order book depth**, diukur berulang kali (bukan snapshot sekali).

**Cara dapat angka nyata (bukan tebakan):**
```
GET https://fapi.binance.com/fapi/v1/ticker/24hr
```
Ambil field `quoteVolume`, sort descending, hitung berapa banyak coin yang lolos threshold sesuai portfolio size Anda. Jalankan ini setiap hari lewat logger — dalam sebulan Anda punya distribusi nyata, bukan angka bulat dari internet.

---

## 3. Funding Rate — Cross-Sectional, Bukan Threshold Absolut

**Masalah dengan threshold absolut** (misal "funding < 0.05%"): filter ini mekanis berkonflik dengan filter "OI naik + harga naik" — karena OI melonjak + harga naik secara struktural menghasilkan funding tinggi. Filter absolut membuang persis populasi yang ingin diseleksi filter lain.

**Masalah dengan window waktu tetap (7 hari vs 30 hari):**
- 7 hari = ~21 periode funding (8 jam) → terlalu sedikit, satu outlier menggeser hasil.
- 30 hari = ~90 periode → lebih stabil, tapi lambat adaptasi terhadap regime baru.
- **Masalah yang lebih dalam:** coin tenang yang tiba-tiba pump — distribusi 30 harinya didominasi periode sepi, jadi funding normal saat pump (misal 0.06%) terbaca sebagai persentil ekstrem. Window pendek cuma menunda masalah ini, tidak menyelesaikannya.

**Solusi: bandingkan ke cross-section, bukan ke sejarah sendiri.**
> "Funding coin X hari ini 0.055%. Dari seluruh coin yang lolos liquidity gate hari ini, itu peringkat sekian — persentil sekian."

Ini otomatis kebal terhadap perubahan regime pasar secara keseluruhan.

**Apa itu "persentil 40–75":**
Urutkan semua pembacaan funding (misal 90 titik dalam 30 hari, atau cross-section semua coin hari ini) dari kecil ke besar. Persentil 40 = titik ke-36 dari 90. Persentil 75 = titik ke-68.

| Zona | Interpretasi awal (belum teruji) |
|---|---|
| < p40 | Tidak ada yang peduli, tidak ada bahan bakar |
| p40–p75 | Ada minat, belum sesak — "zona nyaman" hipotesis |
| > p75 | Long menumpuk, risiko jadi exit liquidity |
| > p90 | Sangat crowded |

**Cara validasi yang benar (bukan pilih dulu baru cek):** bagi funding percentile jadi 5 bucket (0–20, 20–40, 40–60, 60–80, 80–100). Ukur forward return 48 jam di tiap bucket dari data historis `/fapi/v1/fundingRate` (tersedia penuh). **Data yang menentukan zona mana yang dipakai — bukan asumsi awal siapapun.**

**Rekomendasi implementasi:** pakai dua fitur terpisah — cross-sectional percentile (fitur utama) dan time-series z-score 30 hari (fitur pendamping). Biarkan ablation test memutuskan kontribusi masing-masing.

---

## 4. Trigger Entry: BOS/CHoCH + EMA9

**Prinsip:** BOS/CHoCH dan EMA9 adalah dua alat untuk pekerjaan berbeda — jangan dicampur jadi satu definisi.

- BOS/CHoCH didefinisikan oleh **swing point aktual** (harga menembus swing high/low sebelumnya) — objektif.
- EMA9 hanyalah rata-rata 9 candle terakhir — tidak tahu apa-apa soal swing point. Memakainya untuk *mendefinisikan struktur* menurunkan kualitas sinyal.

**Urutan yang benar — EMA9 sebagai pengatur waktu masuk, bukan penentu struktur:**

```
1. STRUKTUR (harga murni)  → CHoCH/BOS menentukan arah
2. PULLBACK                → tunggu harga mundur ke area value
3. TRIGGER (EMA9)          → candle close di atas/bawah EMA9 + slope searah
4. ENTRY
```

**Contoh konkret (bullish, 1H, hold 1–2 hari):**
1. CHoCH terjadi — harga break swing high terakhir setelah downtrend → bias berubah bullish.
2. Harga pullback.
3. Trigger: candle 1H close di atas EMA9 **dan** EMA9 slope positif.
4. Stop: di bawah swing low yang membentuk CHoCH — **bukan** di bawah EMA9 (EMA9 bergerak terus, jadi target bergerak yang naik mendekati harga — bisa memicu stop dari noise).
5. Invalidasi: candle close di bawah swing low tersebut.

**Timeframe EMA9:** 1H (memori ~9 jam) cocok untuk hold 1–2 hari. Di 15M terlalu berisik — bisa 20 trigger sehari dengan mayoritas palsu.

**Wajib diuji sebelum dipakai:** bandingkan tiga versi via ablation test — (a) struktur saja, (b) struktur + EMA9, (c) struktur + EMA21. Kalau (b) tidak mengalahkan (a) dari sisi expectancy, buang EMA9. Setiap indikator tambahan yang tidak terbukti hanya menambah ruang overfitting.

---

## 5. Matriks OI (4 Kuadran)

| Kondisi | Interpretasi |
|---|---|
| Harga naik + OI naik | Trend kuat, fresh long masuk |
| Harga naik + OI turun | Short covering, potensi exhaustion |
| Harga turun + OI naik | Fresh short masuk, bearish valid |
| Harga turun + OI turun | Long liquidation — hati-hati, potensi bottom fishing |

Catatan: layer ini secara teori paling informatif (bobot 25% di soft gate), tapi **baru bisa dibacktest ~30 hari sejak logger mulai jalan** — lihat §6.

---

## 6. Ganti Liquidation Heatmap: Volume Profile + Swing High/Low

**Kenapa heatmap harus diganti:**
- Binance membatasi stream likuidasi publik (`!forceOrder`) — heatmap Coinglass adalah **estimasi/model**, bukan data likuidasi nyata.
- Tidak ada arsip historis untuk heatmap → **tidak bisa dibacktest**.
- Semua retail trader melihat heatmap yang sama → edge yang dipakai bersama-sama bukan edge lagi.

**Pengganti (ranking terbaik):**

| # | Pengganti | Sumber data | Kenapa lebih baik |
|---|---|---|---|
| 1 | Volume Profile (VPVR) | Klines Binance — gratis, historis penuh | Menunjukkan harga di mana **transaksi nyata** terjadi. High Volume Node = magnet harga. Low Volume Node = zona harga lewat cepat |
| 2 | Swing high/low sebelumnya | Klines Binance | Di sinilah stop loss orang **benar-benar** ditaruh — tidak perlu model |
| 3 | Perubahan OI di level harga tertentu | OI history (30 hari) | Menunjukkan di mana leverage menumpuk |
| 4 | Estimated Leverage Ratio | OI ÷ saldo exchange | Mengukur "ketegangan" pasar secara keseluruhan |
| 5 | Order book depth | Depth endpoint (snapshot only) | Likuiditas nyata yang menunggu — tapi bisa hilang dalam sedetik dan bisa di-spoof, pakai hati-hati |

**Rekomendasi:** pakai #1 + #2 sebagai pengganti utama. Keduanya gratis, deterministik, dan **bisa dibacktest penuh** — tidak seperti heatmap.

---

## 7. Ekonomi Biaya (Binance)

Biaya USDⓈ-M Futures untuk regular user: **maker 0.02%, taker 0.05%** (diskon 10% jika bayar pakai BNB).

Estimasi round-trip:

| Komponen | Best case | Elevated |
|---|---|---|
| Fee (taker in/out) | 0.10% | 0.10% |
| Funding (3–6 periode selama hold) | 0.03% | 0.30% |
| Slippage memecoin | 0.05% | 0.15% |
| **Total drag** | **0.18%** | **0.55%** |

Breakeven win rate:
- RR 2:1 murni → 33.3%
- RR efektif 1.69:1 (setelah stop 3% + drag) → **37.2%**

**Kesimpulan: biaya bukan pembunuh utama strategi ini** (hanya menambah ~4pp ke required win rate). Yang lebih berbahaya: stop terlalu ketat relatif volatilitas memecoin, dan seleksi universe yang salah (lihat §8).

Optimasi murah: masuk pakai limit order (maker 0.02%) memotong fee round-trip dari 0.10% → 0.07%.

---

## 8. Isu Struktural yang Harus Diperbaiki Sebelum Live

### 8.1 Stop 3% terlalu ketat untuk memecoin
Daily sigma DOGE/PEPE realistis 5–7%. Stop 3% ≈ 0.5 sigma — probabilitas ke-stop dari noise murni (bukan thesis salah) sangat tinggi.
**Fix:** stop harus ATR-based (≥1× ATR harian), bukan persentase tetap.

### 8.2 Filter momentum 24h positif bisa berlawanan arah di coin iliquid
Riset akademik: cryptocurrency dengan return hari sebelumnya **rendah** secara signifikan mengungguli yang **tinggi** — efek reversal harian ini disebabkan iliquiditas mayoritas coin. Hanya coin paling likuid yang menunjukkan momentum harian, bukan reversal.
Momentum crypto terdokumentasi positif di horizon 2–4 minggu, dengan reversal signifikan di atas 1 bulan — **horizon 1–2 hari berada di bawah jendela momentum yang terbukti**.
**Fix:** filter momentum 24h hanya berlaku setelah lolos liquidity gate ketat. Di bawah itu, logikanya kemungkinan harus dibalik (reversal, bukan momentum).

### 8.3 Sample size — bottleneck terbesar
Dengan filter stack ketat, estimasi frekuensi sinyal realistis: 1–3 per minggu.
- Target 100 trade ÷ 2/minggu = ~12 bulan trading live.
- Dengan win rate sejati 40% vs breakeven 37%, standard error di n=100 sekitar 4.9pp — **edge lebih kecil dari noise-nya**. Perlu n≈400 untuk membedakan 40% dari 37% dengan keyakinan wajar.
**Fix:** backtest pooled cross-section (semua coin sekaligus), bukan menunggu sinyal live satu-satu.

---

## 9. Data Binance — Apa yang Bisa Dibacktest Sekarang vs Nanti

**Prinsip:** semua data market Binance bersifat publik — **tidak perlu API key** untuk riset/backtest/logging. API key hanya dibutuhkan untuk eksekusi order, cek saldo, atau baca posisi sendiri.

| Endpoint | Retensi historis | Bisa backtest sekarang? |
|---|---|---|
| `/fapi/v1/klines` | **Penuh** sejak listing | ✅ Ya — tulang punggung backtest: VPVR, swing high/low, ATR, EMA9 |
| `/fapi/v1/fundingRate` | **Penuh** | ✅ Ya — backtest bucket persentil funding vs forward return |
| `/futures/data/openInterestHist` | **30 hari saja** ⚠️ | ⚠️ Baru bisa mulai ~30 hari setelah logger jalan |
| `/futures/data/globalLongShortAccountRatio` | **30 hari saja** ⚠️ | ⚠️ Sama |
| `/futures/data/takerlongshortRatio` (CVD) | **30 hari saja** ⚠️ | ⚠️ Sama |
| `/fapi/v1/depth` | Snapshot saat ini saja, tidak ada arsip di manapun | ❌ Tidak untuk backtest |
| `/fapi/v1/ticker/24hr` | Rolling 24 jam live, tidak menyimpan histori harian | ❌ Tidak untuk backtest (berguna untuk cek liquidity gate real-time) |

**Konsekuensi:** backtest layer OI/LSR/CVD baru bisa dilakukan lengkap **~30 hari setelah logger dinyalakan**. Jangan tunggu itu untuk mulai kerja — layer klines & funding sudah bisa dibacktest 2 tahun ke belakang hari ini.

**Base URL:** `https://fapi.binance.com`
**Untuk backtest historis skala besar (lebih baik dari API):** `data.binance.vision` — arsip resmi berisi klines, funding, aggTrades dalam file ZIP harian/bulanan, download langsung tanpa rate limit (API dibatasi ~1500 candle/request).
**Rate limit API:** ~2400 weight/menit per IP — cukup untuk scan ratusan symbol per hari.

**Catatan Indonesia:** akses data publik biasanya tidak masalah dari mana saja, tapi untuk eksekusi order perlu cek status regulasi Bappebti terkini sebelum live — belum diverifikasi di sini.

---

## 10. Roadmap Validasi

### Fase 0 — Sekarang (jangan ditunda)
Deploy data logger harian: snapshot OI, long/short ratio (global + top trader), taker buy/sell volume, funding, mark price, untuk seluruh universe perp yang lolos liquidity gate. Simpan ke CSV/Parquet di repo GitHub.
**Setiap hari tertunda = data OI/LSR yang hilang permanen** (retensi Binance cuma 30 hari, tidak ada cara ambil lebih jauh dari manapun).

### Fase 1 — Ablation test (layer yang sudah bisa dibacktest)
Pakai vectorbt, universe: semua perp Binance yang lolos liquidity gate, 2 tahun data klines + funding. Uji satu per satu, **jangan ditumpuk sekaligus**:
1. Baseline: buy random / buy semua → return dasar
2. + volume z-score filter saja
3. + funding percentile bucket saja
4. + price momentum 24h saja (dengan & tanpa liquidity split)
5. + EMA9 trigger vs tanpa EMA9 vs EMA21
6. Interaksi liquidity × momentum (uji hipotesis reversal §8.2)

Ukur marginal contribution tiap filter ke Sharpe/expectancy. Yang tidak menambah nilai → buang, jangan dipertahankan karena "terasa masuk akal."

### Fase 2 — Stop/target optimization
Grid ATR multiplier (0.8×–2.5×) vs RR target. Cari expectancy tertinggi, bukan win rate tertinggi.

### Fase 3 — Walk-forward validation
Rolling 6-bulan train / 2-bulan test. Jangan pakai parameter optimum dari full-sample (overfitting risk).

### Fase 4 — Gabungkan layer OI (setelah data 30 hari terkumpul)
Backtest kuadran OI (§5) begitu data logger cukup panjang. Integrasikan ke soft gate score, ulangi ablation test dengan layer penuh.

### Fase 5 — Paper trading
Minimum 60 hari sebelum modal riil, target ≥30–50 trade tervalidasi paper untuk cross-check terhadap hasil backtest.

---

## 11. Conviction Summary (skor keyakinan tiap klaim)

| Klaim | Skor | Alasan |
|---|---|---|
| Kerangka 3-lapis (hard/soft/context) valid secara struktur | 80% | Praktik standar top-down, bukan hasil pengujian spesifik ke strategi ini |
| Filter funding absolut berkonflik dengan filter OI+momentum | 88% | Deterministik — sudah terbukti dari backtest awal (sinyal nol) |
| Momentum 24h salah arah di coin iliquid | 72% | Literatur akademik konsisten, tapi belum diverifikasi di dataset Binance spesifik |
| Stop 3% terlalu ketat untuk memecoin | 80% | Rasio ATR jelas secara matematis |
| Biaya trading membunuh strategi ini | 15% | Drag hanya ~4pp — bukan masalah utama |
| Strategi layak live **sekarang** | 20% | Belum ada satu layer pun yang tervalidasi lewat backtest |
| Strategi bisa layak setelah Fase 1–5 selesai | 55% | Realistis, tapi bukan jaminan — tergantung hasil ablation |

---

## 12. Prinsip Kerja ke Depan

Setiap angka/threshold yang muncul di sistem ini — dari siapapun, termasuk dari sesi ini — harus lolos satu pertanyaan: **"data apa yang menghasilkan angka ini, dan bisa direproduksi tidak?"** Kalau tidak ada jawabannya, angka itu berstatus **parameter yang harus diuji**, bukan aturan yang harus dipatuhi.

Threshold `$100M volume`, `window 30 hari`, dan `persentil 40–75` di percakapan awal semuanya adalah tebakan yang terbukti salah/tidak berdasar saat ditanya sumbernya. Dokumen ini sudah mengoreksi ketiganya dengan metode derivasi yang bisa direproduksi (§2, §3) — tapi angka hasil derivasi pun tetap harus diverifikasi ulang dengan data aktual begitu logger dan backtest jalan.
