#line 1 "C:\\Users\\my_nuc\\AppData\\Local\\Programs\\@codebufffreebuff-desktop\\project\\mikrotik_monitor\\README.md"
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

Seluruh data diambil dari **MikroTik API TCP 8728** — 5 permintaan per refresh
(dulu 6). RouterOS API **wajib login**, jadi user & password diperlukan. Nilainya
bisa diubah dari Settings → NETWORK (disimpan di NVS); default awal diambil dari
`secrets.h` (`MT_USER` / `MT_PASS`):

| Perintah API | Data |
|---|---|
| `/system/resource/print` | CPU load, total/free memory, uptime, board-name, versi RouterOS |
| `/interface/print` | daftar interface + `rx-byte`/`tx-byte` + status `running` |
| `/system/health/print` | suhu, tegangan |
| `/ppp/active/print` | jumlah user PPP aktif + daftar sesi. Tiap sesi dicocokkan ke interface dinamis di `/interface/print`: pola `<...>` yang mengandung nama user (`<user>` untuk PPP client, `<pppoe-user>` untuk PPPoE server) |

> **SNMP dan ping tidak digunakan.** Klien SNMP (`snmp_client.h`) tidak pernah
> di-`#include` dari `mikrotik_monitor.ino` sehingga sudah dihapus. Fitur ping
> juga tidak ada di kode; kartu PING di Dashboard sudah digantikan kartu BOARD +
> versi RouterOS.
>
> `/system/identity/print` juga sudah tidak dipanggil lagi — datanya tidak pernah
> ditampilkan di UI, jadi pengambilannya hanya membuang satu round-trip.

## 3. Menu (sidebar, 6 halaman)

| # | Halaman | Isi |
|---|---|---|
| 0 | Dashboard | CPU, MEM, Temp, Volt, BOARD, UPTIME, USERS, 2 kartu interface + area chart. **Pintasan:** tap kartu interface (kanan) → INTERFACES, tap kartu USERS → PPP ACTIVE |
| 1 | INTERFACES | Daftar ethernet UP + TX/RX real-time + **kotak centang** pemilih kartu grafik Dashboard (maks 2; >5 baris bisa di-scroll) |
| 2 | WiFi INFO | SSID, RSSI, MAC, IPv4, GW, DNS (ESP32) |
| 3 | SETTINGS | 3 tab: NETWORK / APPEARANCE / DEVICE (lihat §4) |
| 4 | TRAFFIC | Grafik area besar per interface + label sumbu Y (K/M/G) + gridline + selector `<` `>` di baris judul, dan **footer Tx/Rx** menempel dasar layar (grafik mengambil seluruh ruang di antaranya) |
| 5 | PPP ACTIVE | Daftar user PPPoE aktif (s/d 80) + durasi sesi + scroll `<<<` (halaman pertama) `<<` `>>` `>>>` (halaman akhir). **Tap user** → popup Tx/Rx live interface client dalam bps (tanpa grafik), refresh tiap 1 detik, ditutup lewat tombol **TUTUP** |

Kartu grafik Dashboard memakai interface yang dicentang di halaman INTERFACES
(maks 2 = jumlah kartu, disimpan per **nama** di NVS `dif1`/`dif2`). Bila belum
ada yang dicentang, dashboard otomatis memakai dua ethernet running pertama.
Saat sudah 2 dicentang lalu mencentang yang ketiga, pilihan terlama tergeser.

Halaman **SELECT WIFI** (scan dari Settings → DEVICE) tidak langsung konek saat
baris disentuh: muncul popup konfirmasi berisi nama SSID, sinyal, status kunci,
dan tombol **CONNECT** / **LUPAKAN** / **BATAL**. Tombol **LUPAKAN** hanya
muncul untuk SSID yang punya profil tersimpan (ditandai `*` di daftar) dan
menghapus profil itu dari NVS — jaringan tetap ada di daftar hasil scan.
`CONNECT` untuk profil tersimpan langsung konek; untuk SSID baru membuka
keyboard password.

## 4. Settings (3 tab)

Tab dipilih lewat bar di bawah header: `NETWORK` · `APPEARANCE` · `DEVICE`.

### Tab NETWORK

| Baris | Aksi |
|---|---|
| MikroTik IP | Keyboard layar |
| API Port | Keyboard layar (validasi 1–65535; ganti port memicu reconnect otomatis) |
| User | Keyboard layar — user login RouterOS API (default dari `secrets.h`) |
| Password | Keyboard layar, input bertopeng (`*`); ganti user/pass memicu login ulang |
| SNMP | Keyboard layar (community) |
| SNMP Port | Keyboard layar (validasi 1–65535) |

### Tab APPEARANCE

| Baris | Aksi |
|---|---|
| Refresh | Keyboard layar (detik) |
| Theme | Popup pilih Dark / Light (highlight), terapkan saat **OK** ditekan |
| Bright | Popup `-` / `+` (10–100%), live |
| Screen | Popup: 1 / 5 / 10 menit / Always ON (0) (highlight), terapkan saat **OK**. Sentuh untuk bangun; selain `Always ON`, habisnya waktu juga **mengunci layar** |
| LED | Popup `-` / `+` kecerahan LED RGB (10–100%) |
| Glow | Popup ON/OFF (highlight), terapkan saat **OK** ditekan |
| Auto Lock | Popup ON/OFF (highlight), terapkan saat **OK**. **ON** = layar ikut terkunci otomatis saat screen timeout habis (default ON) |

### Tab DEVICE

| Baris | Aksi |
|---|---|
| WiFi | Popup konfirmasi **SCAN WIFI?** (OK/BATAL) → daftar SSID → popup **CONNECT / LUPAKAN / BATAL** → input password untuk SSID baru |
| Reset | Dialog konfirmasi YA/BATAL (reset → wajib daftar WiFi ulang) |

## 5. Penyimpanan (NVS `mktmonitor`)

`ip`, `comm`, `ssid`, `wpass`, `snmp_port`, `api_port`, `mtuser`, `mtpass`,
`refresh`, `dark`, `wconf`, `bright`, `scrto`, `ledbr`, `glow`, `alock`, `dif1`, `dif2`,
`wcount` + `wssid0..4`/`wpass0..4` (profil WiFi tersimpan, MRU maks 5; `[0]` = aktif).
Default: theme gelap, bright 100%, screen always ON, LED 100%, API port 8728,
glow ON, kartu Dashboard otomatis (`dif1`/`dif2` kosong), dan `mtuser`/`mtpass`
dari `secrets.h`.

> `comm` dan `snmp_port` masih disimpan di NVS dan bisa diedit dari Settings,
> tetapi belum ada kode yang memakainya karena SNMP tidak aktif (§2).

## 6. Tema & Tampilan

- `struct Theme { bg, header, card, text, dim, border, bg2 }` (`config.h`).
- Macro `COLOR_*` di `.ino` di-`#undef`/`#define` ulang agar membaca
  `theme.*` saat runtime → toggle theme berfungsi penuh.
- Grafik garis: isi area **gradient fade** dari warna garis ke warna kartu
  (efek masking, tanpa garis tepi), gridline putus-putus halus. Efek **glow
  neon** pada garis bisa dimatikan lewat Settings → Glow (tersimpan di NVS).
- Background = warna kartu (`0x1108`, flat, senada); kartu digambar via
  `drawGlassCard()` (fill + border + highlight atas).
- Header: judul tanpa aksen garis; garis pemisah bawah header tetap ada.
  Tulisan judul "MikroTik-Monitor" dibuat **miring** memakai FreeSans Oblique 9pt
  (`FONT_ITAL` di `fonts.h`). Karena hanya satu font, tidak ada masalah
  keselarasan garis dasar antar varian.
- Layar boot menyapa singkat sebelum konek: judul **MikroTik**, lalu **ver 1.1**
  dan **created by clusternet** di bawahnya, ditutup `Loading...`. Nomor versi
  diambil dari `APP_VER` di `config.h`, jadi cukup ubah satu tempat saat rilis.
- **Kunci layar:** ikon gembok di ujung kiri header (samping judul) — terbuka
  (`ICON_UNLOCK`) saat normal, merah (`ICON_LOCK`) saat terkunci. Tap ikon →
  popup konfirmasi **KUNCI LAYAR?** (tombol **TUTUP KUNCI** / **BATAL**) →
  overlay **LAYAR TERKUNCI**; semua sentuhan diabaikan kecuali tombol
  **BUKA KUNCI** (masa tenggang 400 ms agar sentuhan resistif berulang tidak
  langsung membukanya).
- **Auto-lock:** saat screen timeout habis (Settings → Screen 1/5/10 menit),
  layar ikut terkunci otomatis; sentuhan pertama hanya menyalakan backlight dan
  menampilkan layar kunci. Bisa dimatikan lewat Settings → APPEARANCE →
  **Auto Lock** (`NVS: alock`, default ON). `Always ON` (0) tidak pernah
  mengunci. Status kunci hanya di RAM (tidak ikut reboot).
- Font: **FreeSans non-bold** (9/12/18pt) + GLCD 8px. Roboto hasil konversi
  sendiri terbukti blur → dikembalikan ke FreeSans.
- Icon: Material Design Icons 16×16 1-bit (`icons.h`, generate via
  `gen_icons.py` + `mdi.ttf`, preview `preview_icons.py`).

## 7. LED RGB Status

Hijau = WiFi+API normal · Merah = WiFi/API gagal ·
Biru = scan/connect · Ungu = layar mati. Update tiap loop (PWM, ikut `ledbr`).

## 8. Build & Flash

### Kredensial (secrets.h)

WiFi, IP MikroTik, user/password router, dan SNMP community **tidak** ada di
`config.h`. Semuanya ada di `secrets.h`:

```bash
cp secrets.h.example secrets.h   # Windows: copy secrets.h.example secrets.h
```

`secrets.h` sudah masuk `.gitignore`, jadi tidak ikut ter-commit. Kalau file itu
belum dibuat, build tetap berhasil tetapi nilai default menjadi kosong —
perangkat belum bisa konek sampai diisi lewat Settings (IP, user & password
MikroTik, SNMP) atau scan WiFi.

```powershell
$CLI = "C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
& $CLI compile --fqbn esp32:esp32:esp32 "C:\temp\mikrotik_monitor"
& $CLI upload -p COM16 --fqbn esp32:esp32:esp32 "C:\temp\mikrotik_monitor"
```

> ⚠️ Compile/flash **folder yang benar-benar Anda edit**. Proyek ini pernah punya
> beberapa salinan (mis. `C:\temp\mikrotik_monitor` vs workspace Freebuff
> Desktop) yang isinya bisa berbeda — salah pilih = meng-upload kode lama.

Monitor serial: `capture.ps1` (bawaan tools, 115200 baud).
Tunggu `=== READY ===`. Masalah umum: WiFi scan gagal → radio butuh
`WiFi.disconnect()` + jeda sebelum scan (sudah ditangani: blocking scan +
retry + pakai ulang hasil uji scan).

## 9. Struktur File

```
mikrotik_monitor/
  mikrotik_monitor.ino   # utama (UI, touch, loop)
  secrets.h.example      # template kredensial (di-commit, isinya placeholder)
  secrets.h              # kredensial asli — di-ignore git, JANGAN di-commit
  config.h               # pin terpakai, palet warna, struct Theme (layout ada di .ino)
  fonts.h                # mapping FONT_XS/SM/MD/LG
  icons.h                # bitmap MDI (digenerate)
  roboto/                # header font Roboto (arsip, tidak dipakai)
  storage.h              # Settings + NVS
  mikrotik_api.h         # klien API RouterOS
  touch.h / keyboard.h   # driver sentuh + keyboard layar
```

## 10. Batasan Diketahui

- Maks 80 interface / 80 user PPP. Array statis (interface + PPP + chart 60 titik x
  80 slot) memakai ±52 KB; total *global variables* saat build 102 KB (31%),
  sudah termasuk stack WiFi/TCP.
- Chart 60 titik per interface; overflow 32-bit dihindari (aritmetika 64-bit).
- Series chart kecil diberi tinggi minimum 3px + urutan gambar terbesar-dulu.
