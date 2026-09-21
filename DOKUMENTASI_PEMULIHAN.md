# Dokumentasi Pemulihan File — MikroTik Monitor

> Dibuat: 21 September 2026
> Status: **BERHASIL DIPULIHKAN & DIVERIFIKASI (berhasil dikompilasi)**

---

## 1. Ringkasan

File versi **terbaru** dari sketch MikroTik Monitor (yang terakhir di-upload ke modul
ESP32) hilang dari folder project. Folder project ternyata berisi versi **lebih lama**.
Seluruh file versi terbaru — kode utama, semua header, bahkan file kredensial baru —
**berhasil dipulihkan utuh** dari cache build Arduino IDE, dan sudah dibuktikan
**berhasil dikompilasi**.

- Versi yang dipulihkan : **firmware v1.1**, hasil build **20 Sep 2026 21:29**
- Lokasi hasil pemulihan : folder `recovered/mikrotik_monitor/`
- Verifikasi : kompilasi sukses → 1.040.073 byte (**79%**) flash, 102.252 byte (**31%**) RAM

---

## 2. Apa yang hilang, apa yang dipulihkan

Folder project (`...project/mikrotik_monitor`) ternyata berisi versi **20 Sep 14:22**.
Versi terbaru punya **2.010 baris** kode (file lama hanya 1.296 baris) — sekitar
**±700 baris perubahan** yang hilang.

| File | Di folder project (lama) | Hasil pemulihan (terbaru) |
|---|---|---|
| `mikrotik_monitor.ino` | 50.464 B / 1.296 baris | **78.843 B / 2.010 baris** |
| `config.h` | 4.945 B | 3.733 B (pakai `secrets.h`) |
| `storage.h` | 5.540 B | 8.048 B (field baru) |
| `mikrotik_api.h` | 15.562 B | 16.889 B |
| `keyboard.h` | 5.955 B | 6.075 B |
| `fonts.h` | 713 B | 905 B |
| `icons.h` | 4.966 B | 5.225 B |
| `touch.h` | 2.757 B | 2.874 B |
| `secrets.h` | — (tidak ada) | 844 B (**file baru**) |
| `README.md` | 4.256 B | 10.494 B |
| `roboto/` | 3 file | 3 file (isinya diperbarui) |

Semua file di atas sudah dipulihkan ke **`recovered/mikrotik_monitor/`**.

---

## 3. Dari mana dipulihkan (sumber & bukti)

Arduino IDE **menyalin seluruh isi sketch** (termasuk semua header) ke folder cache
build setiap kali melakukan compile/upload. Salinan itulah yang jadi sumber pemulihan:

```
%LOCALAPPDATA%\arduino\sketches\853EEC992D987A3E7B2C72B3A126DC33\sketch\
```

Di dalamnya tersimpan snapshot lengkap: `mikrotik_monitor.ino.cpp`,
`config.h`, `storage.h`, `mikrotik_api.h`, `keyboard.h`, `fonts.h`, `icons.h`,
`touch.h`, `secrets.h`, `roboto/`, dan `README.md`.

Bukti bahwa ini memang versi terakhir: baris `#line` di dalamnya menunjuk ke path
project ini sendiri:

```
#line 1 "C:\Users\my_nuc\AppData\Local\Programs\@codebufffreebuff-desktop\project\mikrotik_monitor\mikrotik_monitor.ino"
```

---

## 4. Cara rekonstruksi dilakukan

File `.ino.cpp` di cache adalah hasil *preprocessing* Arduino, jadi tidak bisa dipakai
mentah. Yang dipakai adalah **`mikrotik_monitor.ino.cpp.merged`** — versi gabungan yang
masih mempertahankan source asli beserta direktif `#line`.

Langkah:

1. Buang semua baris direktif `#line ...` (penanda posisi yang disisipkan compiler).
2. Buang baris `#include <Arduino.h>` yang ditambahkan otomatis.
3. Hasilnya: **2.010 baris source asli, persis**.

Validation: hasil rekonstruksi di-`diff` dengan sumber di cache → **0 perbedaan**.

Header (`config.h`, `storage.h`, dll.) juga dibersihkan dari satu baris `#line` yang
disisipkan di awal, sehingga kembali ke bentuk source aslinya.

---

## 5. Verifikasi (bukti file utuh & bisa dipakai)

Hasil pemulihan dikompilasi ulang dengan toolchain Arduino yang sama:

```
arduino-cli compile --fqbn esp32:esp32:esp32 recovered/mikrotik_monitor
```

Hasil:

```
Sketch uses 1040073 bytes (79%) of program storage space.
Global variables use 102252 bytes (31%) of dynamic memory,
leaving 225428 bytes for local variables.
```

**Sukses tanpa error.** Ini membuktikan kode utama + seluruh header hasil pemulihan
saling cocok dan siap di-upload ke ESP32.

---

## 6. Timeline versi (dari cache build)

| Waktu | Ukuran `.ino.cpp` | Lokasi cache | Catatan |
|---|---|---|---|
| 19 Sep 15:54 | 46.842 B | `arduino/sketches/0376D47A…` | |
| 19 Sep 22:57 | 46.842 B | `Temp/arduino-language-server375683262` | |
| 20 Sep 14:20 | 54.764 B | `arduino/sketches/10B32037…` | mendekati isi folder project sekarang |
| 20 Sep 15:37 | 58.213 B | `Temp/mkt_build` | |
| 20 Sep 15:40 | 58.213 B | `Temp/mkt_nosec` | |
| **20 Sep 21:29** | **92.513 B** | **`arduino/sketches/853EEC99…`** | **TERAKHIR — inilah yang dipulihkan** |

> Catatan: ukuran `.ino.cpp` lebih besar dari source asli karena berisi tambahan
> direktif `#line` dan blok prototipe fungsi yang disisipkan compiler. Ukuran source
> asli = 78.843 B / 2.010 baris.

---

## 7. Fitur baru yang berhasil diselamatkan

Dibanding file lama di folder project, versi terbaru (yang dipulihkan) memiliki:

- **Settings bertab** → `NETWORK` / `APPEARANCE` / `DEVICE` (fungsi `drawSettingsTabs`, `settingsRow`).
- **Kredensial dipindah ke `secrets.h`** (file baru, seharusnya masuk `.gitignore`);
  `config.h` memberi fallback kosong bila `secrets.h` belum ada.
- **Kredensial router bisa diatur di layar**: `API Port`, `User`, `Password` MikroTik
  (fungsi `onApiPort`, `onMTUser`, `onMTPass`, `onSnmpPort`).
- **Profil WiFi tersimpan** (sampai 5 slot): aksi **connect / forget** per jaringan
  (`drawWifiActionPopup`, `openWifiAction`, `wifiDoConnect`, `wifiDoForget`).
- **Efek Glow neon pada grafik** yang bisa ON/OFF (`chartGlow`, `drawGlowPopup`, `blend565`).
- **Auto Lock + layar kunci** (`autoLock`, `drawAutoLockPopup`, `drawLockScreen`, `confirmLock`).
- **Pilih interface untuk 2 kartu Dashboard** (`dashIface1`/`dashIface2`, `toggleDash`,
  `dashSelected`, `resolveDashIfaces`, `findIfaceByName`, `ifaceEligibleCount`).
- **Popup trafik live per client PPP** (`drawPPPTrafficPopup`, `drawPPPTrafficData`, `popupPPP`).
- **Versi firmware di layar boot**: menampilkan "ver 1.1" (`APP_VER`).
- **Popup konfirmasi** sebelum scan WiFi (`confirmScan`) dan sebelum kunci layar.
- Perubahan `mikrotik_api.h`: `connect(ip, port, user, pass)` dengan port & user/pass dinamis.

---

## 8. Cara memakai hasil pemulihan

**Opsi A — pakai langsung (disarankan):**

1. Buka folder `recovered/mikrotik_monitor/` di project ini.
2. Salin **semua isinya** ke folder sketch kerja kamu (ganti file lama).
   - Pastikan `secrets.h` juga ikut disalin bila belum ada.
3. Buka `mikrotik_monitor.ino` di Arduino IDE → **Upload** ke ESP32 (port COM16).

**Opsi B — bandingkan dulu:**
Buka berdampingan `mikrotik_monitor.ino` (lama) vs `recovered/mikrotik_monitor/mikrotik_monitor.ino`
untuk melihat semua perubahan sebelum mengganti.

---

## 9. Peringatan penting

- ⚠️ **`secrets.h` berisi kredensial asli** (WiFi, IP + user/password router). Jangan
  pernah di-commit ke repository publik atau dikirim ke orang lain. File ini sudah
  disiapkan untuk masuk `.gitignore`.
- ⚠️ Folder cache Arduino **bisa terhapus otomatis** (pembersihan temp / update IDE).
  Setelah memakai hasil pemulihan, segera simpan salinan permanen.
- ℹ️ Line-ending `mikrotik_monitor.ino` hasil pemulihan sudah dirapikan; isi kode
  identik dengan sumber di cache.

---

## 10. Langkah pencegahan ke depan

1. **Pakai Git** untuk project ini (commit tiap perubahan selesai) — ini mencegah
   kejadian serupa terulang.
2. Simpan **backup** folder sketch ke lokasi lain (cloud/USB) secara berkala.
3. Tambahkan `secrets.h` ke `.gitignore` sebelum `git init` (agar kredensial aman).
4. Jangan mengandalkan cache build sebagai penyimpanan — ia bersifat sementara.
