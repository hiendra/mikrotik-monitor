# Panduan Backup — MikroTik Monitor

Dokumen ini menjelaskan cara menjaga file project agar **tidak hilang lagi**.
Ada 3 lapis pengamanan; sebaiknya pakai ketiganya.

| Lapis | Alat | Melindungi dari |
|---|---|---|
| 1 | **Git lokal** (folder `.git` di project) | salah edit, file tertimpa, ingin balik ke versi lama |
| 2 | **Zip bertanggal** (`backup.ps1`, otomatis tiap hari 23:00) | folder project terhapus / corrupt |
| 3 | **GitHub privat** | komputer rusak, hilang, atau diganti |

---

## 1. Git lokal — dipakai sehari-hari

Folder project sudah menjadi repo Git (branch `main`, commit pertama sudah ada).

**Setiap selesai mengedit, lakukan commit:**

```powershell
cd C:\temp\mikrotik_monitor
git status                          # lihat file yang berubah
git add -A                          # tandai semua perubahan
git commit -m "keterangan perubahan" # simpan sebagai snapshot
```

**Lihat riwayat & kembalikan file ke versi lama:**

```powershell
git log --oneline                   # daftar commit
git checkout <hash> -- nama_file    # ambil file dari commit tertentu
git restore --source=HEAD~1 file.h  # mundur 1 commit untuk file itu
```

**Isi identitas Git (sekali saja):**

```powershell
git config --global user.name "Nama Kamu"
git config --global user.email "email@kamu.com"
```

> Commit pertama sementara dibuat dengan identitas `my_nuc <my_nuc@localhost>`.
> Setelah mengisi identitas di atas, jalankan `git commit --amend --reset-author`
> untuk mengganti penulis commit terakhir (opsional).

> **PENTING:** `secrets.h` **tidak** ikut Git (ada di `.gitignore`).
> Kalau project di-clone di komputer lain, buat lagi file itu dari template:
> `copy secrets.h.example secrets.h` lalu isi nilainya.

---

## 2. Backup zip bertanggal

Jalankan skrip yang sudah disertakan:

```powershell
cd C:\temp\mikrotik_monitor
powershell -ExecutionPolicy Bypass -File .\backup.ps1
```

Hasil: `%USERPROFILE%\MikroTikMonitor-Backups\mikrotik_monitor_<tanggal>_<jam>.zip`
(20 backup terbaru disimpan, yang lebih lama dihapus otomatis).

> Folder `Documents` di komputer ini tidak bisa ditulisi PowerShell
> (karena OneDrive/proteksi folder), maka backup ditaruh di folder profil pengguna.

⚠️ **Arsip zip ini memuat `secrets.h` (kredensial asli).** Jangan diunggah ke
internet atau dibagikan.

### Otomatis tiap hari — SUDAH TERPASANG ✅

Task Scheduler sudah diatur dan **sudah diuji berhasil**:

| Item | Nilai |
|---|---|
| Nama task | `MikroTik Monitor Backup Harian` |
| Jadwal | Setiap hari, **23:00** |
| Yang dijalankan | `powershell -NoProfile -ExecutionPolicy Bypass -File "C:\temp\mikrotik_monitor\backup.ps1"` |
| Dijalankan sebagai | pengguna `my_nuc` (saat sedang login) |
| Log hasil | `%USERPROFILE%\MikroTikMonitor-Backups\backup.log` |
| Kalau jadwal terlewat | **menyusul** saat komputer dinyalakan lagi (`StartWhenAvailable`) |
| Saat pakai baterai | tetap jalan (tidak diblokir `DisallowStartIfOnBatteries`) |
| Batas waktu | 30 menit (`ExecutionTimeLimit`) |

**Cek jadwal berikutnya:**

```powershell
schtasks /query /tn "MikroTik Monitor Backup Harian"
```

**Jalankan sekarang (untuk mengetes):**

```powershell
schtasks /run /tn "MikroTik Monitor Backup Harian"
```

**Lihat hasil terakhir** — kolom *Last Result* harus `0` (= sukses):

```powershell
schtasks /query /tn "MikroTik Monitor Backup Harian" /v /fo LIST | findstr /i "Last Result Last Run Next Run"
```

Atau lewat tampilan: tekan `Win+R` → ketik `taskschd.msc` → cari task-nya di
*Task Scheduler Library*.

**Ubah jam backup / pasang ulang task:**

Skrip `install_backup_task.ps1` mendaftarkan task dengan setelan yang benar
(termasuk `StartWhenAvailable` dan izin baterai). Aman dijalankan berulang kali.

```powershell
cd C:\temp\mikrotik_monitor
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_backup_task.ps1 -Jam 22:30
```

Pakai skrip ini juga kalau nanti **pindah komputer**, folder project dipindah,
atau task-nya terhapus — jalankan sekali dari folder project yang baru, dan
task akan menyesuaikan sendiri ke lokasi itu.

**Matikan backup otomatis:**

```powershell
schtasks /delete /tn "MikroTik Monitor Backup Harian" /f
```

> **Catatan:** task ini berjalan **saat kamu login** (mode *Interactive only*),
> jadi tidak berjalan kalau kamu log out dari Windows. Kalau komputer mati pada
> jam 23:00, backup **menyusul sendiri** begitu komputer dinyalakan dan kamu
> login — jadi backup harian tetap tidak hilang.
>
> Ingat juga: backup hanya menyalin isi folder project. Pastikan hasil kerja
> terbaru sudah **disimpan di folder itu**, bukan masih ada di cache Arduino IDE.

---

## 3. GitHub privat (backup ke cloud)

Repo lokal sudah siap. Tinggal membuat repo di GitHub lalu push.

**a. Buat repository baru di <https://github.com/new>**
- Nama: `mikrotik-monitor`
- Visibilitas: **Private**
- Jangan centang "Add a README" (repo sudah punya file)

**b. Hubungkan & kirim (push):**

```powershell
cd C:\temp\mikrotik_monitor
git remote add origin https://github.com/USERNAME/mikrotik-monitor.git
git push -u origin main
```

Kalau ada GitHub CLI (`gh`), bisa lebih singkat:

```powershell
gh auth login
gh repo create mikrotik-monitor --private --source . --push
```

**c. Setelah terhubung, backup ke cloud tiap selesai kerja:**

```powershell
git add -A
git commit -m "update"
git push
```

### Verifikasi kredensial TIDAK ikut terkirim

```powershell
git ls-files | findstr /i secrets
```

Hasilnya harus **hanya** `secrets.h.example`. Kalau `secrets.h` muncul,
**jangan push** — beri tahu saya dulu.

---

## 4. Cara memulihkan kalau file hilang lagi

**Dari Git (paling cepat):**

```powershell
git log --oneline -- mikrotik_monitor.ino   # cari commit yang masih benar
git checkout <hash> -- mikrotik_monitor.ino # kembalikan file itu
```

**Dari arsip zip:**

1. Buka `%USERPROFILE%\MikroTikMonitor-Backups\`
2. Ekstrak zip terbaru ke folder baru
3. Buka `mikrotik_monitor.ino` di Arduino IDE

---

## 5. Ringkasan jadwal yang disarankan

| Kapan | Lakukan |
|---|---|
| Setiap selesai mengubah kode | `git add -A && git commit -m "..."` |
| Otomatis tiap hari 23:00 | zip dibuat sendiri oleh Task Scheduler |
| Minimal seminggu sekali | `git push` |
| Sebelum eksperimen besar | `git commit` dulu, supaya bisa dibalik |
