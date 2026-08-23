# Hypothesis Register

Aturan yang **dikunci sebelum** diuji pada data yang belum ada. Tujuannya satu:
begitu sebuah aturan ditemukan lewat pencarian di data lama, satu-satunya uji
yang tidak bisa dicurangi adalah uji pada data yang belum pernah dilihat siapapun.

Setiap entri: definisi persis, tanggal dikunci, dan prediksi yang bisa salah.
Dilarang mengubah definisi setelah data baru masuk. Kalau ingin varian lain,
daftarkan sebagai entri baru.

---

## H1 — Funding negatif + z-score funding terendah, LONG

**Dikunci:** 2026-08-23
**Ditemukan lewat:** pencarian post-hoc di panel 2024-08-01..2026-07-31
(14 run ablation → dua kandidat nyaris lolos → irisan keduanya diuji).
Karena itu hasil in-sample-nya **tidak** bisa dianggap bukti.

### Definisi (final, tidak boleh diubah)

Pada tiap tanggal `d` pukul 00:00 UTC, untuk tiap symbol perp USDT Binance
USDⓈ-M yang punya ≥30 hari riwayat klines:

```
funding_24h_sum   = jumlah funding rate dalam (d-1 00:00, d 00:00]
funding_ts_z30    = (funding_24h_sum - mean30) / std30   (riwayat symbol sendiri)
zrank             = peringkat persentil funding_ts_z30 di antara symbol
                    eligible pada tanggal d

SINYAL LONG bila:  funding_24h_sum <= 0  DAN  zrank <= 0.20
```

- Entry: open bar 1H pukul `d` 00:00 UTC
- Exit: open bar 1H 48 jam kemudian (tanpa stop/target)
- Sizing: notional $6.00 fixed, equal-weight
- Biaya: fee maker 0.02%×2 + slippage 0 (limit order dianggap fill) = 0.04%
  round trip, ditambah funding aktual yang dibayar selama hold
- Hanya symbol dengan `executable_100usd == True`

### Prediksi yang bisa salah

Pada data 2026-08-01 dan sesudahnya, mean net return per observasi **> 0**
dengan t clustered per tanggal **> 2,0**.

### Yang sudah diketahui (in-sample + walk-forward, BUKAN bukti)

| Ukuran | Nilai |
|---|---|
| Full-sample net | +0,493% (t=2,17), n=33.708 |
| Spread vs sisanya | +0,741% CI [+0,461%, +1,021%] (t=5,20) |
| Walk-forward OOS gabungan | +0,634% CI [+0,049%, +1,219%] (t=2,13), n=22.045 |
| Fold OOS positif | 8 dari 9 |
| Degradasi IS→OOS | 18,0% |
| **Fold terakhir (Jun–Jul 2026)** | **+0,053% (t=0,08); aturan tetap −0,423%** |

### Kekhawatiran yang belum terjawab

1. Efeknya **meluruh**: paruh-1 +0,901%, paruh-2 +0,236%, fold terakhir ~0.
   Bisa berarti edge yang sudah diarbitrase habis, bukan edge yang stabil.
2. Aturan ini hasil pencarian. Bonferroni mengoreksi jumlah uji, bukan proses
   pemilihannya.
3. Frekuensi sinyal ~46/hari, jauh melebihi kapasitas 3 slot. Aturan pemilihan
   di antara 46 kandidat **belum ditentukan** dan akan menambah derajat bebas baru.

### Status

**BELUM TERVALIDASI.** Jangan dipakai live. Evaluasi ulang setelah ada
≥3 bulan data baru (target: 2026-11-01).

---

## Koreksi 2026-08-23 (sore) — stop loss membunuh H1

Ditemukan saat Dew menanyakan dasar angka stop 3%: **saya yang mengarang 3%**,
Dew hanya pernah menetapkan RR 2:1 dan SL maksimum 5%.

Saat diuji ulang dalam batasan itu, ditemukan kesalahan akuntansi yang lebih
serius: seluruh hitungan ber-stop sebelumnya mengkredit funding **48 jam penuh**
ke trade yang keluar di jam ke-2. Karena 71% keuntungan H1 berasal dari funding
yang diterima, itu melebih-lebihkan setiap baris ber-stop.

Setelah funding dihitung sampai jam keluar sebenarnya (path scan 1H):

| SL | TP | median jam keluar | komponen harga | funding diterima | net | t |
|---|---|---:|---:|---:|---:|---:|
| 1% | 2% | 2 | -0,125% | +0,0199% | **-0,145%** | -4,77 |
| 2% | 4% | 6 | -0,082% | +0,0305% | -0,091% | -1,46 |
| 3% | 6% | 13 | -0,096% | +0,0483% | -0,088% | -0,95 |
| 4% | 8% | 19 | -0,138% | +0,0705% | -0,107% | -0,90 |
| 5% | 10% | 30 | -0,181% | +0,0926% | -0,129% | -0,91 |
| tanpa SL/TP | — | 48 | +0,197% | +0,3788% | **+0,536%** | +2,30 |

**Setiap tingkat stop negatif.** Mekanismenya: stop memotong hold, hold pendek
mengumpulkan funding jauh lebih sedikit (0,02% vs 0,38%), sementara komponen
harganya negatif di semua tingkat.

Konsekuensi: **"Skema 2" (H1 + stop 3%/target 6%) DIBATALKAN.** Yang bertahan
hanya H1 tanpa stop, keluar di 48 jam. Angka portofolio Skema 2 yang pernah
dilaporkan ($120,84 lalu $106,57) keduanya salah.

### Ambang: kenapa tetap `<= 0` dan `rank <= 20%`, bukan yang lebih ketat

Grid in-sample memang lebih suka ambang ketat (funding <=-0,05% -> +0,749%;
z <=-1,50 -> +1,007%). Tapi walk-forward dengan grid diperluas ke ambang ketat:

| Grid | OOS gabungan | t | CI 95% | degradasi |
|---|---:|---:|---|---:|
| Longgar (f<=0, rank<=20%) | +0,634% | **+2,13** | [+0,049%, +1,219%] | 18,0% |
| Diperluas ke ketat | +0,658% | +1,70 | **[-0,102%, +1,419%]** | 28,6% |

Ambang ketat menaikkan mean tapi menurunkan t dan membuat CI melewati nol —
sinyalnya jadi terlalu sedikit. Ambang longgar dipertahankan karena lebih tahan
di luar sampel, bukan karena lebih bagus di dalam sampel.
