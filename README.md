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

## 11. Ops Server & Web Hosting

Perkakas pendamping untuk server tempat dashboard ini berjalan (bukan bagian
firmware ESP32). Semuanya **read-only** kecuali yang ditandai.

| Berkas | Fungsi |
|---|---|
| `cek-semua.ps1` | Satu perintah: menjalankan audit server + verifikasi domain, lalu menulis `laporan-ops.txt` |
| `audit-server.ps1` | Audit keamanan & performa: port terbuka, TLS, header keamanan, cache aset, kompresi, API tanpa auth |
| `cek-domain.ps1` | Verifikasi `clusternet.my.id` sudah lewat Cloudflare (`Server`/`cf-ray`) atau masih jalur langsung |
| `kumpulkan-info-server.sh` | Dijalankan **di host** (Linux/ZimaOS): CPU, RAM, disk, SMART, Docker, log error |
| `REKOMENDASI-OPTIMASI-SERVER.md` | Temuan audit + perbaikan berurutan P0→P2 (RouterOS, Caddy, portproxy) |
| `pindai-layanan.ps1` | Memindai host ZimaOS: port mana yang hidup, layanan apa itu (Immich, Grafana, ttyd, …), lalu mencetak blok Caddyfile siap tempel |
| `zima-hosting/panel-kelola.html` | **Panel visual** untuk mengatur pemetaan nama domain → layanan, tanpa mengedit Caddyfile dengan tangan (klik dua kali, jalan di browser, tanpa server) |
| `buka-panel.mjs` | Menyalakan panel pengelola di **alamat tetap** `http://127.0.0.1:8788/panel-kelola.html` lalu membukanya di browser — supaya tidak bergantung pada port acak fitur preview yang berubah tiap sesi |
| `zima-hosting/tautan-balik-grafana.mjs` | Menambahkan tautan "Kembali ke ClusterNet" ke **semua** dasbor Grafana; aman diulang, `--kering` untuk melihat rencananya saja |
| `zima-hosting/` | Paket web hosting: Cloudflare Tunnel + Caddy, tanpa port forwarding |
| `zima-hosting/CHECKLIST-CLOUDFLARE.md` | Checklist cetak tahap terakhir: token tunnel, Public Hostname, Access, dan pembersihan port forwarding lama |
| `zima-hosting/CATATAN-KENDALA.md` | Catatan kendala: gejala → sebab → solusi → verifikasi (Grafana kosong, SNMP MikroTik, cara masuk ke router/host) |
| `zima-hosting/PANDUAN-KUMA-NTFY.md` | Notifikasi **Uptime Kuma** ke iPhone lewat ntfy, memakai **topik terpisah** dari topik MikroTik |
| `zima-hosting/uji-kuma-ntfy.py` | Membuktikan kanal Kuma → ntfy hidup: status terakhir tiap monitor + apakah pesan asli dari Kuma benar-benar tiba |
| `uji-ntfy.py` | Uji ujung-ke-ujung kanal **router** → ntfy lewat router yang nyata (menjalankan `ntfy-kirim` sekali, lalu membaca penandanya dari server) |
| `uji-semua-ntfy.py` | Menguji **semua** kanal ntfy sekaligus (router, Kuma, udara × server utama/cadangan/LAN): baca topik, tulis probe, lalu baca kembali; `--json`, `--hanya`, `--tanpa-kirim` |
| `CATATAN-KERJA-2026-09-27.md` | Jurnal kerja 27 Sep 2026: kronologi perubahan, jejak berkas (repo & host), jebakan yang terbukti, dan sisa pekerjaan |
| `udara/notif-udara.sh` | Mengawasi sensor kualitas udara `192.168.20.13:88`: kirim **ntfy** saat sensor mati >5 menit (dengan kabar pulih) atau saat AQI memburuk |
| `udara/pasang-notif-udara.sh` | Memasang watcher di atas sebagai systemd timer tiap 1 menit (ZimaOS tanpa cron); idempoten |
| `udara/README.md` | Topik ntfy, ambang, cara pasang/langganan/mencopot, dan jebakan `priority` JSON yang harus berupa angka |
| `validasi-hosting.mjs` | Memeriksa **konsistensi** paket hosting secara offline (Caddyfile vs compose vs `.env` vs panduan) sebelum dipasang |
| `validasi-hosting.mjs --uji` | Uji diri: menyuntikkan 14 kerusakan ke salinan sementara untuk membuktikan pemeriksanya benar-benar bisa menolak |

Mulai dari sini:

```powershell
powershell -ExecutionPolicy Bypass -File .\cek-semua.ps1
```

Sebelum memasang paket hosting, pastikan berkasnya masih saling cocok (tanpa
Docker, tanpa jaringan):

```bash
node validasi-hosting.mjs         # periksa paket (kode keluar 1 = ada GAGAL)
node validasi-hosting.mjs --uji   # uji pemeriksanya sendiri
```

Catatan akses: API MikroTik (port 8728) sebaiknya hanya dijangkau dari LAN.
Bila ESP32 monitor dijalankan dari luar jaringan ini, tambahkan IP asalnya di
`/ip service set api address=...` agar tidak perlu membuka API ke publik.
