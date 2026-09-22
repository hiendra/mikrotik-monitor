# MikroTik Monitor — ESP32 TFT Dashboard

Dashboard monitoring MikroTik (RouterOS) berbasis ESP32 + layar sentuh TFT 2.4",
tema **Dark Cyber** (navy + aksen cyan neon + kartu glass).

## 1. Hardware

| Komponen | Keterangan |
|---|---|
| Board | ESP32-2432S024 (CYD 2.4", ST7789 320×240 landscape, rotasi 3) |
| Touch | XPT2046 (resistif, SPI) |
| LED RGB | R=GPIO 4, G=GPIO 17, B=GPIO 16, **active LOW** (catatan: G/B tertukar di sebagian board) |
| Backlight | GPIO 27, PWM 5 kHz 8-bit |
| WiFi | STA mode, sleep dimatikan |

> **Penting (hasil diagnosa warna):** panel ST7789 varian ini butuh
> `TFT_RGB_ORDER TFT_BGR` di `User_Setup.h` + `tft.invertDisplay(false)`
> setelah `tft.init()`. Tanpa ini merah→kuning, hijau→ungu, putih→hitam.

## 2. Sumber Data

| Sumber | Fungsi |
|---|---|
| MikroTik API TCP **8728** (user & password dibaca dari `secrets.h`) | resource, identity, interface list, health, `/ppp/active` |
| SNMP v2c (community dibaca dari `secrets.h`, port 161) | CPU, memori, uptime, traffic counter |
| Ping lokal | gateway + internet (Cloudflare) |

## 3. Menu (sidebar, 6 halaman)

| # | Halaman | Isi |
|---|---|---|
| 0 | Dashboard | CPU, MEM, Temp, Volt, ping, USERS, 2 kartu interface + area chart |
| 1 | INTERFACES | Daftar ethernet UP + TX/RX real-time (bold, rata kanan) |
| 2 | WiFi INFO | SSID, RSSI, MAC, IPv4, GW, DNS (ESP32) |
| 3 | SETTINGS | 9 baris (lihat §4) |
| 4 | TRAFFIC | Grafik area besar per interface + selector `<` `>` |
| 5 | PPP ACTIVE | Daftar user PPPoE aktif (s/d 80) + durasi sesi + scroll `<<` `>>` `>>>` |

## 4. Settings

| Baris | Aksi |
|---|---|
| MikroTik IP / SNMP / Refresh | Keyboard layar |
| WiFi | Scan → pilih SSID → input password (tampil polos) |
| Theme | Toggle Dark / Light (tersimpan) |
| Bright | Popup `-` / `+` (10–100%), live |
| Screen | Popup: 1 / 5 / 10 menit / Always ON (0). Sentuh untuk bangun |
| LED | Popup `-` / `+` kecerahan LED RGB (10–100%) |
| Reset | Dialog konfirmasi YA/BATAL (reset → wajib daftar WiFi ulang) |

## 5. Penyimpanan (NVS `mktmonitor`)

`ip`, `comm`, `ssid`, `wpass`, `snmp_port`, `refresh`, `dark`,
`wconf`, `bright`, `scrto`, `ledbr`. Default: theme gelap, bright 100%,
screen always ON, LED 100%.

## 6. Tema & Tampilan

- `struct Theme { bg, header, card, text, dim, border, bg2 }` (`config.h`).
- Macro `COLOR_*` di `.ino` di-`#undef`/`#define` ulang agar membaca
  `theme.*` saat runtime → toggle theme berfungsi penuh.
- Background = warna kartu (`0x1108`, flat, senada); kartu digambar via
  `drawGlassCard()` (fill + border + highlight atas).
- Font: **FreeSans non-bold** (9/12/18pt) + GLCD 8px. Roboto hasil konversi
  sendiri terbukti blur → dikembalikan ke FreeSans.
- Icon: Material Design Icons 16×16 1-bit (`icons.h`, generate via
  `gen_icons.py` + `mdi.ttf`, preview `preview_icons.py`).

## 7. LED RGB Status

Hijau = WiFi+API normal · Merah = WiFi/API gagal ·
Biru = scan/connect · Ungu = layar mati. Update tiap loop (PWM, ikut `ledbr`).

## 8. Build & Flash

```powershell
$CLI = "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
& $CLI compile --fqbn esp32:esp32:esp32 "C:\temp\mikrotik_monitor"
& $CLI upload -p COM16 --fqbn esp32:esp32:esp32 "C:\temp\mikrotik_monitor"
```

Monitor serial: `capture.ps1` (bawaan tools, 115200 baud).
Tunggu `=== READY ===`. Masalah umum: WiFi scan gagal → radio butuh
`WiFi.disconnect()` + jeda sebelum scan (sudah ditangani: blocking scan +
retry + pakai ulang hasil uji scan).

## 9. Struktur File

```
mikrotik_monitor/
  mikrotik_monitor.ino   # utama (UI, touch, loop)
  config.h               # pin, layout, palet warna, struct Theme
  fonts.h                # mapping FONT_XS/SM/MD/LG
  icons.h                # bitmap MDI (digenerate)
  roboto/                # header font Roboto (arsip, tidak dipakai)
  storage.h              # Settings + NVS
  mikrotik_api.h         # klien API RouterOS
  snmp_client.h          # klien SNMP + ping
  touch.h / keyboard.h   # driver sentuh + keyboard layar
```

## 10. Batasan Diketahui

- Maks 80 interface / 80 user PPP (array statis, ~50 KB RAM).
- Chart 60 titik per interface; overflow 32-bit dihindari (aritmetika 64-bit).
- Series chart kecil diberi tinggi minimum 3px + urutan gambar terbesar-dulu.
