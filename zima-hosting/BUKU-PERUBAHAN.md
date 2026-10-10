# Buku Perubahan — tamanmarina.my.id

Catatan setiap penambahan/perubahan program pada dasbor warga, beserta cara
mengembalikannya (rollback). Entri terbaru ada di paling atas.

> **Cara pakai:** sebelum mulai perubahan besar, jalankan
> `pwsh -NoProfile -File ./zima-hosting/cadangkan-tamanmarina.ps1 -Nama <label> -Catatan "<apa yang akan diubah>"`.
> Snapshot + entri di buku ini dibuat sekaligus. Setelah selesai dan lolos uji,
> terbitkan dengan `-Catatan "<ringkasan>"` agar jejaknya lengkap.
> Rollback: `kembalikan-tamanmarina.ps1 -Cadangan <nama snapshot> -Sandi <sandi>`.

---

## Riwayat

<!-- BUKU:ENTRI -->

### 2026-10-10 14:47 · Tarik — Seluruh keadaan live tamanmarina (aset web + sumber auth) ke repo

Keadaan live ditarik ke lokal agar repo kembali menjadi sumber kebenaran: 13 aset
web diunduh lewat HTTPS dan 5 berkas auth (tidak dilayani publik) di-dump base64
dari host. Seluruh 18 berkas terverifikasi sha256 identik dengan host/container.
Isi yang masuk: 12 rute backend baru (`warga`, `umkm`, `aduan`, `iuran/saya`,
`iuran/verifikasi`, `jenis-iuran`, `metode-publik`, `konten`), fungsi penyimpanan
baru (`ambilKonten`/`simpanKonten`, `ambilUmkm`/`aturUmkm`, `ambilAduan`/`aturAduan`,
`ambilRosterWarga`, `ambilTagihanWarga`/`aturTagihanWarga`, `aturMetodePembayaran`,
`aturAkuntansi`), izin baru `pengaduan.kelola`, dan 6 tab dasbor baru (Kelola
Informasi, Data Warga, Aduan, Iuran, Metode Pembayaran, UMKM).

- **Berkas**: `situs/tamanmarina/*` (13), `auth/*` (5); snapshot keadaan lokal lama: `cadangan-tamanmarina/2026-10-10-sebelum-tarik-live/`
- **Uji**: sha256 18/18 cocok dengan host/container; `node --check` atas 10 berkas `.js`/`.mjs` → 10 OK; `node validasi-hosting.mjs` → 83 lolos / 0 GAGAL (exit 0)
- **Rollback**: `MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-10-sebelum-tarik-live -Sandi '<sandi ZimaOS>'`
- **Belum diputuskan**: tab "Status Seluruh Sistem" hilang dari live (id `tmSistemGrid` dkk. lenyap dari `index.html`, `pengaturan.js` tak lagi memanggil `/api/sistem`) sehingga rute `/api/sistem` kini mati — perlu konfirmasi apakah disengaja

### 2026-10-06 20:40 · Terbit — Perbaikan tab Pengaturan (struktur HTML, CSS tab, isi tabel dari API), hapus 9 layanan clusternet dari Status Sistem, pindahkan pembayaran/akuntansi ke endpoint ber-izin

- **Berkas**: `index.html`, `dasbor.css`, `dasbor.js`, `pengguna.js`, `pengaturan.js`, `masuk.html`, `masuk.css`, `masuk.js`, `hero.svg`, `Dockerfile`, `izin.mjs`, `penyimpanan.mjs`, `server.mjs`, `mula.sh`, `Caddyfile`
- **Uji**: verifikasi luar lolos: halaman 200 + penanda bagian + 9 aset + /api/health + /masuk + /sensor/api/data + clusternet/udara tetap 200
- **Rollback**: cadangan-tamanmarina/2026-10-06-sesudah-crud-pengaturan -> MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-06-sesudah-crud-pengaturan -Sandi '<sandi>'


### 2026-10-06 05:53 · Terbit — Terbit ulang (isi tidak berubah) untuk menguji jalur buku catatan

Isi yang diterbitkan sama seperti sebelumnya; penerbitan ini membuktikan bahwa
`terbitkan-tamanmarina.ps1 -Catatan` menulis entri buku secara otomatis dan
menunjuk titik pulih terbaru.

- **Berkas**: `index.html`, `dasbor.css`, `dasbor.js`, `pengguna.js`, `pengaturan.js`, `masuk.html`, `masuk.css`, `masuk.js`, `hero.svg`, `Dockerfile`, `izin.mjs`, `penyimpanan.mjs`, `server.mjs`, `mula.sh`, `Caddyfile`
- **Uji**: verifikasi luar lolos: halaman 200 + penanda bagian + 9 aset + /api/health + /masuk + /sensor/api/data + clusternet/udara tetap 200
- **Rollback**: cadangan-tamanmarina/2026-10-06-sesudah-crud-pengaturan -> MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-06-sesudah-crud-pengaturan -Sandi '<sandi>'


### 2026-10-06 05:48 · Cadangan — 2026-10-06-sesudah-crud-pengaturan

Keadaan baik setelah CRUD Pengaturan terbit: tombol Ubah/Hapus per baris, daftar Pengaturan Lain, /data/pengaturan.json dengan bidang lain. Uji 57/0, aset live cocok bita-per-bita.

- **Berkas**: `index.html`, `dasbor.css`, `dasbor.js`, `pengguna.js`, `pengaturan.js`, `masuk.html`, `masuk.css`, `masuk.js`, `hero.svg`, `Dockerfile`, `izin.mjs`, `penyimpanan.mjs`, `server.mjs`, `mula.sh`, `Caddyfile`
- **Rollback**: snapshot: cadangan-tamanmarina/2026-10-06-sesudah-crud-pengaturan (lihat CATATAN-CADANGAN.md di dalamnya). Kembalikan: MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-06-sesudah-crud-pengaturan -Sandi '<sandi ZimaOS>'


### 2026-10-06 05:53 · Pemasangan — Sistem buku catatan & rollback penuh

Setiap penambahan program kini meninggalkan dua jejak otomatis: titik pulih di
`cadangan-tamanmarina/<nama>/` dan entri di buku ini. `kembalikan-tamanmarina.ps1`
diperbaiki agar memulihkan **seluruh** berkas (sebelumnya hanya 4 aset: skrip
lama tidak mengembalikan `pengguna.js`, `pengaturan.js`, `masuk.*`, dan seluruh
`auth/`, sehingga rollback fitur akun/pengaturan tidak pernah utuh).

- **Berkas**: `BUKU-PERUBAHAN.md` (baru), `buku-catatan.ps1` (baru), `cadangkan-tamanmarina.ps1`, `terbitkan-tamanmarina.ps1`, `kembalikan-tamanmarina.ps1`, `DASBOR-TAMANMARINA.md`
- **Uji**: parse pwsh 4/4 skrip OK; snapshot + entri buku terbentuk; rollback uji ke snapshot identik mengembalikan 14 berkas dan hash berkas tidak berubah; `node validasi-hosting.mjs` → 83/0/0; terbit ulang lolos verifikasi luar
- **Rollback**: pemasangan ini hanya menyentuh alat repo + dokumentasi (tidak ada berkas situs/auth yang berubah) — batalkan lewat git bila perlu; tidak ada yang perlu diterbitkan ulang

### 2026-10-06 · Terbit — CRUD Pengaturan (tambah/ubah/hapus) + daftar "Pengaturan Lain"

Setiap baris di hub Pengaturan Sistem kini punya mode **lihat** (teks + tombol
`Ubah`/`Hapus`) dan mode **ubah** (input + `Selesai`/`Batal`), berlaku untuk
master iuran, ambang approval, dan daftar baru "Pengaturan Lain" (pasangan
nama–nilai bebas). Perubahan baru mengikat setelah `Simpan Pengaturan`; tombol
`Batalkan Perubahan` memuat ulang isi dari server. Backend menambah bidang
`lain` di `/data/pengaturan.json` dengan validasi ketat (maks 30 baris iuran /
10 ambang / 30 pengaturan lain, nama ≤ 80, nilai ≤ 300 karakter).

- **Berkas**: `index.html`, `dasbor.css`, `pengaturan.js`, `auth/server.mjs`, `auth/penyimpanan.mjs`, `.uji-tmp/uji.sh`, `DASBOR-TAMANMARINA.md`
- **Uji**: `bash .uji-tmp/uji.sh` → 57/0 ; `node validasi-hosting.mjs` → 83/0/0 ; uji browser klik asli (tambah/ubah/batal/hapus/simpan) lolos
- **Rollback**: snapshot `2026-10-05-sebelum-pengaturan` (berisi `pengaturan.js` pra-CRUD + `server.mjs` pra-`lain`) —
  `MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-05-sebelum-pengaturan -Sandi '<sandi>'`
- **Catatan pasca-deploy**: `/data/pengaturan.json` di host yang sudah ada tetap dipakai; bidang `lain` yang belum ada otomatis diisi `[]` oleh server.

### 2026-10-05 · Terbit — Hub Pengaturan Sistem (13 layanan, master iuran & ambang)

Seksi `#pengaturan` yang tadinya statis menjadi hub admin nyata: probe status
13 layanan project (`/api/sistem`, cache 15 detik), master iuran + ambang
approval tersimpan di server (`/api/pengaturan`), matriks peran dari
`/api/peran`, dan info backend dari `/api/health`.

- **Berkas**: `index.html`, `dasbor.css`, `pengaturan.js` (baru), `pengguna.js`, `auth/server.mjs`, `auth/penyimpanan.mjs`, `auth/mula.sh`, `terbitkan-tamanmarina.ps1`, `cadangkan-tamanmarina.ps1`
- **Uji**: `bash .uji-tmp/uji.sh` → 46/0 ; `node validasi-hosting.mjs` → 83/0/0
- **Rollback**: snapshot `2026-10-05-sebelum-akun` (keadaan sebelum hub & sebelum modul akun)

### 2026-10-05 · Terbit — Modul Akun (masuk, kelola pengguna, audit)

Backend `tm-auth` (tanpa dependensi npm) + halaman `/masuk` + modul
`pengguna.js`: sesi cookie `tm_sesi`, tiga peran (warga/pengurus/admin), kelola
pengguna, audit log, ganti sandi, rate limit login.

- **Berkas**: `pengguna.js`, `masuk.html`, `masuk.css`, `masuk.js`, `auth/*` (server.mjs, penyimpanan.mjs, izin.mjs, Dockerfile), `docker-compose.yml`, `Caddyfile`
- **Uji**: harness `.uji-tmp/uji.sh` (saat itu 36 cek) → 36/0
- **Rollback**: snapshot `2026-10-05-live` (kondisi live sebelum modul akun)

---

## Cara membaca entri

- **Aksi** — `Cadangan` (titik pulih dibuat), `Terbit` (dipasang ke ZimaOS), `Kembali` (rollback dijalankan).
- **Rollback** — nama snapshot di `zima-hosting/cadangan-tamanmarina/<nama>/` beserta perintah persisnya. Snapshot selalu memuat `CATATAN-CADANGAN.md` sendiri.
- **Uji** — bukti yang harus lolos sebelum dianggap selesai.

Rujukan lengkap: `zima-hosting/DASBOR-TAMANMARINA.md` (bagian 5 & 7).
