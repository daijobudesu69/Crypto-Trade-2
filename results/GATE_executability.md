# GATE — eksekutabilitas notional $6.00 (brief §2.5)

Universe eligible: **752 symbol**, **346,870** observasi (tanggal, symbol), 730 hari (2024-08-01 s/d 2026-07-31).

`stepSize` diturunkan dari eksponen desimal volume klines per (symbol, bulan); `minQty` diasumsikan = `stepSize`; `MIN_NOTIONAL` diasumsikan 5 USDT (BTC 100 / ETH 20). exchangeInfo tidak dapat diakses dari jaringan ini.


## 1. Vonis per symbol

| Vonis | Definisi | n symbol | % |
|---|---|---:|---:|
| always | executable ≥99% hari hidupnya | 553 | 73.5% |
| mostly | 50–99% | 121 | 16.1% |
| sometimes | >0–50% | 54 | 7.2% |
| never | 0% — tidak pernah bisa dibuka di $6 | 24 | 3.2% |

## 2. Observasi (tanggal, symbol)

| Ukuran | Nilai |
|---|---:|
| Observasi eligible | 346,870 |
| executable, toleransi kuantisasi 5% | 305,677 (88.1%) |
| executable, toleransi kuantisasi 10% | 323,243 (93.2%) |
| executable, toleransi kuantisasi 20% | 334,064 (96.3%) |
| gagal syarat (a) MIN_NOTIONAL ≤ $6 | 0 (0.00%) |
| gagal syarat (b) qty_actual ≥ minQty | 4,835 (1.39%) |
| lolos (a)+(b) tapi gagal (c) error kuantisasi >10% | 18,792 (5.42%) |

## 3. Eksekutabilitas per tercile likuiditas (cek bias §2.6)

| liq_tercile | n_obs | exec_rate | median harga | median ADV 30d USD |
|---|---:|---:|---:|---:|
| 1 (tipis) | 115,389 | 96.4% | 0.07144 | 1,936,903 |
| 2 (tengah) | 115,633 | 95.2% | 0.09375 | 8,407,526 |
| 3 (likuid) | 115,848 | 88.1% | 0.3022 | 52,862,147 |

## 4. Distribusi stepSize (seluruh universe)

| stepSize | n symbol | n obs | median harga | median step×harga (% dari $6) | exec_rate |
|---|---:|---:|---:|---:|---:|
| 0.001 | 17 | 9,275 | 443.35 | 0.4434 (7.39%) | 71.1% |
| 0.01 | 126 | 18,378 | 14.244 | 0.1424 (2.37%) | 80.1% |
| 0.1 | 128 | 80,211 | 0.7726 | 0.07726 (1.29%) | 92.6% |
| 1 | 484 | 239,006 | 0.05514 | 0.05514 (0.92%) | 95.3% |

## 5. Cross-tab stepSize × harga — 25 sel terbesar

| stepSize | bucket harga | n symbol | n obs | median step×harga | % dari $6 | exec_rate |
|---|---|---:|---:|---:|---:|---:|
| 1 | [0.01, 0.1) | 385 | 104,207 | 0.03637 | 0.61% | 100.0% |
| 1 | [0.1, 1) | 315 | 73,410 | 0.2403 | 4.00% | 97.5% |
| 1 | [0.001, 0.01) | 168 | 36,713 | 0.004542 | 0.08% | 100.0% |
| 0.1 | [0.1, 1) | 99 | 35,257 | 0.03489 | 0.58% | 100.0% |
| 0.1 | [1, 10) | 97 | 28,472 | 0.2114 | 3.52% | 98.2% |
| 1 | [1, 10) | 76 | 12,474 | 1.829 | 30.48% | 32.0% |
| 1 | [0.0001, 0.001) | 37 | 9,631 | 0.000507 | 0.01% | 100.0% |
| 0.1 | [0.01, 0.1) | 44 | 9,048 | 0.006168 | 0.10% | 100.0% |
| 0.01 | [1, 10) | 20 | 6,862 | 0.04465 | 0.74% | 100.0% |
| 0.1 | [10, 100) | 25 | 6,466 | 2.003 | 33.39% | 28.1% |
| 0.01 | [10, 100) | 64 | 5,860 | 0.2164 | 3.61% | 96.6% |
| 0.01 | [100, 1000) | 70 | 4,298 | 2.878 | 47.97% | 26.5% |
| 0.001 | [100, 1000) | 9 | 3,383 | 0.3729 | 6.22% | 98.8% |
| 0.001 | [1000, 10000) | 9 | 3,296 | 3.648 | 60.80% | 20.2% |
| 0.001 | [10, 100) | 5 | 2,582 | 0.04279 | 0.71% | 100.0% |
| 1 | [1e-05, 0.0001) | 6 | 1,369 | 3.77e-05 | 0.00% | 100.0% |
| 0.01 | [0.1, 1) | 3 | 924 | 0.002393 | 0.04% | 100.0% |
| 0.1 | [100, 1000) | 2 | 789 | 16.5 | 275.03% | 0.0% |
| 1 | [10, 100) | 7 | 766 | 19.83 | 330.42% | 0.0% |
| 0.01 | [1000, 10000) | 8 | 298 | 13.35 | 222.52% | 0.0% |
| 1 | [100, 1000) | 1 | 243 | 167.4 | 2790.33% | 0.0% |
| 1 | [1e-06, 1e-05) | 2 | 193 | 3.4e-06 | 0.00% | 100.0% |
| 0.1 | [0.001, 0.01) | 4 | 169 | 0.000835 | 0.01% | 100.0% |
| 0.01 | [0.01, 0.1) | 2 | 136 | 0.0008004 | 0.01% | 100.0% |
| 0.001 | [10000, 100000) | 1 | 14 | 11.22 | 187.08% | 0.0% |

## 6. Symbol yang TIDAK PERNAH executable di $6 (n=24)

| symbol | stepSize | median harga | step×harga | % dari $6 | n hari |
|---|---:|---:|---:|---:|---:|
| ASMLUSDT | 0.01 | 1765.57 | 17.66 | 294.3% | 21 |
| AAVEUSDT | 0.1 | 171.755 | 17.18 | 286.3% | 730 |
| SNDKUSDT | 0.01 | 1629.21 | 16.29 | 271.5% | 86 |
| ANTHROPICUSDT | 0.01 | 1616.05 | 16.16 | 269.3% | 30 |
| SKHYNIXUSDT | 0.01 | 1293.47 | 12.93 | 215.6% | 30 |
| OPENAIUSDT | 0.01 | 1282.15 | 12.82 | 213.7% | 37 |
| LLYUSDT | 0.01 | 1192.92 | 11.93 | 198.8% | 31 |
| MUUSDT | 0.01 | 954.145 | 9.541 | 159.0% | 86 |
| COSTUSDT | 0.01 | 934.54 | 9.345 | 155.8% | 23 |
| STXXUSDT | 0.01 | 838.5 | 8.385 | 139.8% | 21 |
| SPYUSDT | 0.01 | 744.25 | 7.442 | 124.0% | 87 |
| QQQUSDT | 0.01 | 715.66 | 7.157 | 119.3% | 87 |
| BRKBUSDT | 0.01 | 495.14 | 4.951 | 82.5% | 45 |
| XAUTUSDT | 0.001 | 4269.56 | 4.27 | 71.2% | 98 |
| TSMUSDT | 0.01 | 423.48 | 4.235 | 70.6% | 87 |
| DELLUSDT | 0.01 | 415.01 | 4.15 | 69.2% | 29 |
| MSFTUSDT | 0.01 | 393.31 | 3.933 | 65.6% | 73 |
| AVGOUSDT | 0.01 | 389.92 | 3.899 | 65.0% | 73 |
| CIENUSDT | 0.01 | 388.5 | 3.885 | 64.8% | 10 |
| GOOGLUSDT | 0.01 | 363.795 | 3.638 | 60.6% | 98 |
| VUSDT | 0.01 | 351.44 | 3.514 | 58.6% | 45 |
| HDUSDT | 0.01 | 338.01 | 3.38 | 56.3% | 48 |
| JPMUSDT | 0.01 | 336.14 | 3.361 | 56.0% | 45 |
| ADBEUSDT | 0.01 | 227.27 | 2.273 | 37.9% | 21 |

## 7. Symbol yang eksekutabilitasnya berubah sepanjang waktu (n=175)

Ini yang membuktikan constraint bersifat time-varying: harga bergerak, stepSize tetap, sehingga status bisa berubah tanpa perubahan aturan bursa.

| symbol | stepSize | harga min | harga max | exec_rate | n hari |
|---|---:|---:|---:|---:|---:|
| AVAXUSDT | 1 | 5.89 | 54.024 | 0.1% | 730 |
| TSLAUSDT | 0.01 | 297.06 | 448.52 | 0.6% | 155 |
| PAXGUSDT | 0.001 | 3197.25 | 5537.49 | 0.6% | 462 |
| XAUUSDT | 0.001 | 3990.93 | 5520 | 1.0% | 203 |
| QNTUSDT | 0.1 | 56.07 | 165.94 | 1.8% | 730 |
| LITEUSDT | 0.01 | 599.65 | 961.81 | 2.1% | 48 |
| BXUSDT | 0.01 | 118.28 | 133.95 | 4.2% | 24 |
| CRMUSDT | 0.01 | 156.81 | 188.88 | 6.9% | 29 |
| KLACUSDT | 0.01 | 171.95 | 222.49 | 10.0% | 10 |
| ICPUSDT | 1 | 2.06 | 15.236 | 11.4% | 730 |
| UNIUSDT | 1 | 2.394 | 18.613 | 11.5% | 730 |
| CRDOUSDT | 0.01 | 176.02 | 266.67 | 12.5% | 24 |
| AMZNUSDT | 0.01 | 197.58 | 274.88 | 13.3% | 143 |
| FTMUSDT | 1 | 0.2916 | 1.4321 | 18.1% | 730 |
| ARMUSDT | 0.01 | 212.13 | 385.14 | 18.9% | 37 |
| LRCXUSDT | 0.01 | 268.82 | 324.69 | 20.0% | 10 |
| BNBUSDT | 0.01 | 464.2 | 1306.84 | 21.4% | 730 |
| CBRSUSDT | 0.01 | 168.59 | 236.44 | 22.7% | 44 |
| BSVUSDT | 0.1 | 10.82 | 83.42 | 23.2% | 730 |
| MKRUSDT | 0.001 | 900.3 | 2799.2 | 23.3% | 730 |
| YFIUSDT | 0.001 | 1621 | 13996 | 23.4% | 730 |
| NVDAUSDT | 0.01 | 191.43 | 237.86 | 23.5% | 98 |
| PENDLEUSDT | 1 | 1.0146 | 6.8474 | 23.7% | 730 |
| TRBUSDT | 0.1 | 12.783 | 94.628 | 23.8% | 730 |
| COHRUSDT | 0.01 | 221.99 | 409.4 | 24.3% | 37 |
| AMDUSDT | 0.01 | 428.29 | 579.93 | 28.1% | 57 |
| BTCDOMUSDT | 0.001 | 2509.8 | 5711.6 | 28.2% | 730 |
| NEARUSDT | 1 | 0.961 | 8.029 | 28.6% | 730 |
| AXSUSDT | 1 | 0.804 | 9.571 | 29.9% | 730 |
| XPTUSDT | 0.001 | 1552.19 | 2400.37 | 30.1% | 153 |
| NBISUSDT | 0.01 | 151.01 | 279.51 | 32.4% | 37 |
| XPDUSDT | 0.001 | 1178.6 | 1804.8 | 32.7% | 153 |
| COINUSDT | 0.01 | 143.32 | 215.48 | 32.9% | 143 |
| QCOMUSDT | 0.01 | 148.92 | 239.17 | 33.3% | 57 |
| SOLUSDT | 0.01 | 62.16 | 261.9 | 33.8% | 730 |
| IBMUSDT | 0.01 | 205.18 | 303.88 | 34.5% | 29 |
| BEUSDT | 0.01 | 166.78 | 344.55 | 35.1% | 37 |
| EWYUSDT | 0.01 | 145.46 | 219.11 | 36.1% | 108 |
| CAKEUSDT | 1 | 1.1609 | 4.3656 | 36.6% | 730 |
| METAUSDT | 0.01 | 542.9 | 680.12 | 36.7% | 98 |

## 8. exec_rate harian

- rata-rata harian: **92.4%**
- minimum harian: 80.4% (2024-12-08)
- maksimum harian: 97.6% (2025-12-27)
- symbol eligible/hari: median 470 (min 266, max 746)
