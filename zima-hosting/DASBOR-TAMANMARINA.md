# Dasbor Warga — tamanmarina.my.id

Dokumen ini adalah rujukan utama bila akan **mengubah** dasbor warga Taman Marina
Metland Cibitung. Isinya: peta berkas, aturan yang tidak boleh dilanggar,
cara mengubah & menerbitkan, cara memverifikasi, dan cara **rollback**.

> Alamat hidup: `https://tamanmarina.my.id` dan `https://www.tamanmarina.my.id`
> (keduanya blok Caddy yang sama). Halaman **statis** tanpa basis data; data
> hidupnya tiga: kartu Info Lingkungan (sensor udara), **modul akun**
> (masuk/kelola pengguna), dan **hub Pengaturan Sistem** (status seluruh layanan
> project, master iuran, ambang approval) — semuanya dilayani container
> `tm-auth` lewat `/api/*`; lihat bagian 4b.

---

## 1. Peta berkas

| Berkas | Peran |
|---|---|
| `zima-hosting/situs/tamanmarina/index.html` | Seluruh markup halaman + semua bagian (section) |
| `zima-hosting/situs/tamanmarina/dasbor.css` | Seluruh gaya, termasuk aturan visibilitas per peran |
| `zima-hosting/situs/tamanmarina/dasbor.js` | Sidebar, pencarian, grafik, sakelar peran demo, sensor, UMKM |
| `zima-hosting/situs/tamanmarina/pengguna.js` | Modul akun: sesi, Akun Saya, kelola pengguna, audit |
| `zima-hosting/situs/tamanmarina/pengaturan.js` | Modul hub Pengaturan Sistem: 4 tab (Umum/Pengguna & Role/Pembayaran/Akuntansi), probe status layanan, master iuran & ambang, pengaturan lain (tambah/ubah/hapus), matriks peran |
| `zima-hosting/situs/tamanmarina/masuk.html` + `masuk.css` + `masuk.js` | Halaman `/masuk` (login) |
| `zima-hosting/situs/tamanmarina/hero.svg` | Gambar hero lokal (pengganti foto Unsplash) |
| `zima-hosting/auth/{server,penyimpanan,izin}.mjs` | Backend akun (API, scrypt+sesi+audit, matriks peran, pengaturan, probe sistem) |
| `zima-hosting/auth/Dockerfile` + `mula.sh` | Image `tm-auth` (node:22-alpine, tanpa dependensi); entrypoint `chown` lalu `exec su-exec node` |
| `zima-hosting/docker-compose.yml` | Service `caddy`, `cloudflared`, dan `tm-auth` |
| `zima-hosting/Caddyfile` | Blok host tamanmarina: CSP ketat, `/api/*` → tm-auth, `/sensor/*`, `file_server` |
| `zima-hosting/terbitkan-tamanmarina.ps1` | **Satu-satunya jalur terbit** yang terbukti (ttyd → path LIVE) |
| `zima-hosting/cadangkan-tamanmarina.ps1` | Membuat titik pulih: snapshot dari keadaan repo **+ entri buku** |
| `zima-hosting/kembalikan-tamanmarina.ps1` | Rollback: memulihkan **seluruh** berkas dari snapshot lalu menerbitkan ulang |
| `zima-hosting/buku-catatan.ps1` | Penulis entri buku (di-dot-source oleh ketiga skrip di atas) |
| `zima-hosting/BUKU-PERUBAHAN.md` | **Buku perubahan & rollback** — dibaca pertama sebelum mengubah apa pun |
| `zima-hosting/cadangan-tamanmarina/<nama>/` | Snapshot siap-rollback + `CATATAN-CADANGAN.md` (di luar web root) |
| `zima-hosting/CATATAN-KENDALA.md` | Jurnal kendala; entri 14 & 15 soal dasbor ini |

Path LIVE di host (mount `web-router`, jangan salah tulis):

```
/DATA/AppData/zima-hosting/Caddyfile
/DATA/AppData/zima-hosting/situs/tamanmarina/{index.html,dasbor.css,dasbor.js,pengguna.js,pengaturan.js,masuk.html,masuk.css,masuk.js,hero.svg}
/DATA/AppData/zima-hosting/auth/{Dockerfile,mula.sh,izin.mjs,penyimpanan.mjs,server.mjs}
```

---

## 2. Aturan wajib (melanggar = tampilan rusak senyap)

1. **Tidak boleh ada skrip inline.** CSP blok ini `script-src 'self'`; skrip
   inline diblokir **tanpa galat server** (halaman tetap 200). Semua JavaScript
   harus di `dasbor.js`.
2. **Gaya inline boleh** (`style-src 'unsafe-inline'`), mis. tinggi batang grafik.
3. **Gambar eksternal tidak akan termuat** (`img-src 'self' data:`). Pakai berkas
   lokal atau data URI.
4. **Bump versi aset setiap mengubah CSS/JS.** Cloudflare meng-cache aset statis;
   tautan di `index.html` memakai `?v=YYYYMMDD`. Setiap perubahan CSS/JS **wajib**
   menaikkan nilai ini, jika tidak pengunjung menerima salinan lama.
5. **Semua alamat situs di Caddyfile wajib berawalan `http://`** (tunnel
   menyambung ke port 80; tanpa itu blok jatuh ke fallback 404).
6. **Akhiran baris LF** untuk semua berkas di atas.
7. **CSP hanya di blok statis ini**, jangan dijadikan global (UI ZimaOS rusak).
8. **Jangan menyentuh layanan `clusternet.my.id`** — hanya blok tamanmarina dan
   `situs/tamanmarina/` yang boleh berubah.
9. **Semua fetch pengubah ke `/api/*` wajib mengirim header**
   `X-Diminta-Dengan: dasbor` — tanpa itu server menolak 403 (penangkal CSRF;
   formulir lintas situs tidak bisa menambah header khusus). Semua berkas JS
   modul akun (`masuk.js`, `pengguna.js`) sudah melakukannya; ikuti polanya.
10. **Peran & izin diputuskan server** (`/api/saya`), bukan oleh JS. Sakelar
    peran di sidebar hanyalah demo tanpa sesi; begitu ada sesi, `pengguna.js`
    menyembunyikannya dan `data-peran` body diambil dari akun yang masuk.

Jalankan `node validasi-hosting.mjs` setelah mengedit; harus
**83 lolos / 0 gagal / 0 peringatan** (exit 0).

---

## 3. Struktur halaman & ID bagian

Menu sidebar adalah tautan anchor ke `id` bagian di halaman yang sama:

`#beranda` · `#profil` · `#datawarga` · `#informasi` · `#kegiatan` ·
`#pengaduan` · `#fasilitas` · `#iuran` · `#laporan` · `#dokumen` · `#forum` ·
`#umkm` · `#kontak` · `#pengaturan`

Ada pula section yang bukan menu sidebar, tapi dituju tautan/cabang program:
`#lingkungan` (kartu sensor), `#akun` (Akun Saya, tujuan redirect setelah masuk),
`#pengguna` dan `#audit` (tabel kelola pengguna & audit log; keduanya
`hidden` di markup dan dibuka `pengguna.js` bila izinnya ada).

Di dalam `#pengaturan` ada bilah tab (`#tmTabNav`) dan empat panel
(`.tm-tab-panel` dengan `data-tab`): `#tmPanelUmum`, `#tmPanelPengguna`,
`#tmPanelPembayaran`, `#tmPanelAkuntansi`. **Semua panel wajib berada di dalam
`<section id="pengaturan">`** — kalau satu `</div>` saja salah tempat, parser
HTML memindahkan panel ke luar `main.content` (tampak di dasar `<body>`, gaya
rusak). Selalu hitung ulang keseimbangan `<div>`/`</div>` setelah menyunting
blok ini.

Bila menambah menu baru, tambahkan **dua** hal: `<a href="#id">` di `<nav>` dan
`<section id="id">`. Ada pemeriksa cepat (lihat bagian 6) untuk memastikan tidak
ada anchor tanpa target.

### Penanda peran

- Setiap menu atau section yang tidak untuk semua peran diberi
  `data-peran="warga pengurus admin"` (spasi = daftar peran yang boleh melihat).
- Peran aktif disimpan di `<body data-peran="…">` dan diubah oleh `dasbor.js`.
- Penyembunyian dilakukan **CSS** (`body[data-peran=…] [data-peran]:not([data-peran~=…])`),
  jadi tanpa JavaScript pun tampilan default (Warga) tetap benar.
- Angka kartu statistik yang beda per peran memakai `data-teks='{"warga":"…",…}'`.

---

## 4. Sensor lingkungan (`/sensor/*`)

Kartu Info Lingkungan mengambil `GET /sensor/api/data` dari **origin yang sama**.

```caddyfile
handle_path /sensor/* {
    reverse_proxy 192.168.20.27:88
}
```

`handle_path` menanggalkan awalan `/sensor`, sehingga `/sensor/api/data` menjadi
`/api/data` di perangkat ESP32. Kenapa harus lewat proxy, bukan langsung:

- Halaman HTTPS memanggil sensor HTTP → **diblokir konten campuran**.
- CSP `default-src 'self'` juga mengikat `connect-src` → host lain ditolak.

Dengan proxy same-origin, CSP tetap ketat dan tidak ada konten campuran. Data ini
sudah publik di `udara.clusternet.my.id` (perangkat yang sama), jadi tidak
menambah permukaan serangan. Bila sensor mati, kartu menampilkan data contoh dan
memberi tahu bahwa sensor tidak terjangkau. Rincian: `CATATAN-KENDALA.md` entri 15.

---

## 4b. Modul akun (`/api/*`, container `tm-auth`)

Backend manajemen pengguna — tanpa dependensi npm, hanya modul bawaan Node.
Container `tm-auth` TIDAK menerbitkan port; hanya Caddy yang menghubunginya
lewat network yang sama:

```caddyfile
handle /api/* {
    reverse_proxy tm-auth:3000
}
```

Same-origin (domain utama), jadi CSP `connect-src 'self'` tetap utuh.

**Peran & level** (`auth/izin.mjs`, kumulatif):

| Peran | Level | Kebutuhan |
|---|---|---|
| Warga | 1 | dasbor pribadi, profil, iuran sendiri, pengaduan, forum, UMKM, dokumen |
| Pengurus | 2 | + data warga, verifikasi iuran, laporan, pengumuman, kelola UMKM, **buat & kelola akun warga** |
| Admin | 3 | + kelola semua pengguna, ubah peran, hapus akun, `pengaturan.kelola`, `sistem.kelola`, audit log |

Pengurus hanya boleh mengatur akun **warga**; ubah peran & hapus akun hanya
admin; admin aktif terakhir tak bisa diturunkan/dinonaktifkan/dihapus; tak bisa
menghapus akun sendiri.

**API**: `GET /api/health`, `GET /api/peran`, `GET /api/saya`,
`POST /api/masuk`, `POST /api/keluar`, `POST /api/sandi` (ganti sandi sendiri),
`GET|POST /api/pengguna`, `PATCH|DELETE /api/pengguna/:id`,
`POST /api/pengguna/:id/sandi` (reset), `GET /api/audit?batas=`,
`GET|PUT /api/pengaturan` (izin `pengaturan.kelola`; berisi `iuran`,
`ambang`, dan `lain`), `GET /api/sistem?segar=1` (izin `sistem.kelola`).

**Keamanan**: sandi scrypt + garam; sesi token acak 256-bit di memori (12 jam,
restart container = semua orang keluar); cookie `tm_sesi` HttpOnly SameSite=Lax;
rate limit login 8 gagal/15 menit; body maks 32 KB; audit log maks 500 entri di
`/data/audit.json`; tulis atomik (tmp+rename, mode 0600).

**Data** di volume `tm-auth_data` (`/data`): `pengguna.json`, `audit.json`,
`pengaturan.json` (master iuran & ambang), dan `AWAL.txt` — sandi acak admin
pertama, ditulis **sekali** saat volume masih kosong. Setelah masuk pertama &
ganti sandi: `sudo docker exec tm-auth rm /data/AWAL.txt`.

**Uji**: harness 57 cek di `.uji-tmp/` — jalankan server uji
(`cd zima-hosting/auth && DATA_DIR=<folder salinan> PORT=8799 node server.mjs`)
lalu `bash .uji-tmp/uji.sh` dari akar repo; harapkan **57/57** (bagian 12 menguji
CRUD iuran/ambang/pengaturan lain, permintaan rusak → 400, 13 layanan pada
`/api/sistem`, dan warga → 403).

---

## 4c. Hub Pengaturan Sistem (`#pengaturan`, admin)

Section `#pengaturan` (`data-peran="admin"`) bukan lagi halaman contoh: seluruh
isinya datang dari server. Dipegang `pengaturan.js`, yang **hanya mulai** setelah
event `tm-sesi` dari `pengguna.js` membawa izin `pengaturan.kelola`.

- **Status Seluruh Sistem** — `GET /api/sistem` mem-probe **4 layanan hosting
  tamanmarina** (Caddy, tm-auth, dasbor, sensor) secara paralel dari dalam
  container `tm-auth` (butuh `sistem.kelola`). Daftar 9 layanan `clusternet.*`
sengaja dihapus atas permintaan pemilik (dianggap mengganggu). Hasil
  di-cache **15 detik**; tombol "↻ Segarkan Status" mengirim `?segar=1` untuk
  memaksa probe ulang. Respons apa pun (200/302/403) = hidup; timeout 5 detik /
galat jaringan = mati; latensi ≤ 2,5 detik = `ok`, di atasnya = `lambat`.
  Layanan didaftar **satu kali** di `SISTEM` (`auth/server.mjs`); menambah layanan
  = tambah satu baris di sana (dan blok host-nya di Caddyfile). Probe lokal Caddy
  memakai `Host: tamanmarina.my.id`; backend mem-probe dirinya sendiri lewat
  `http://127.0.0.1:${PORT}/api/health`.
- **Master Jenis Iuran**, **Ambang Approval**, dan **Pengaturan Lain** — dibaca
  dari `GET /api/pengaturan` dan disimpan dengan `PUT /api/pengaturan`. Server
  memvalidasi ketat: maks 30 jenis iuran / 10 ambang / 30 pengaturan lain,
  nominal bilangan bulat 0–1.000.000.000, nama jenis ≤ 80 karakter, pengesahan
  ≤ 120 karakter, nama pengaturan lain ≤ 80 karakter, nilainya ≤ 300 karakter;
  pesan galat menyebut nomor baris (`Baris iuran N: …`). Tersimpan atomik di
  `/data/pengaturan.json`; setiap perubahan masuk Audit Log sebagai
  `pengaturan.ubah`. Nilai bawaan (`PENGATURAN_BAWAAN`) = isi statis lama,
  sedangkan `lain` bawaan kosong.
- **Tambah / Ubah / Hapus dari UI** — setiap baris punya dua mode: **lihat**
  (teks + tombol `Ubah`/`Hapus`) dan **ubah** (input + `Selesai`/`Batal`).
  `+ Tambah …` membuat baris baru yang langsung berada di mode ubah; `Hapus`
  melepas baris dari tampilan dan `Batal` mengembalikannya tanpa menyentuh
  entri yang sudah tersimpan. Baris baru yang dibiarkan seluruhnya kosong
  dibuang saat disimpan (setara Batal), dan catatan "Belum ada …" muncul/lepas
  otomatis mengikuti isi daftar. Perubahan apa pun — termasuk penghapusan —
  **baru mengikat setelah tombol `Simpan Pengaturan` ditekan**; tombol
  `Batalkan Perubahan` memuat ulang seluruh isi dari server.
- **Peran & Hak Akses** — dari `GET /api/peran`; matriks nyata, bukan teks statis.
- **Info Backend** — ringkasan dari `GET /api/health`.

### Tab di dalam hub

Isi hub dipecah menjadi **empat tab** (`#tmTabNav`). Perpindahan tab ditangani
`pasangTab()`/`tabTampilkan()` di `pengaturan.js` (bukan `dasbor.js`), jadi hanya
aktif untuk admin dan tidak ada dua penangan yang saling menimpa. Tab selain
"umum" memuat datanya **saat pertama dibuka** (malas) lalu di-cache di layar:

| Tab | Sumber data |
|---|---|
| **Umum** | `GET /api/pengaturan` (iuran/ambang/lain), `GET /api/peran`, `GET /api/sistem`, `GET /api/health` |
| **Pengguna & Role** | `GET /api/pengguna` + `GET /api/peran` (data NYATA, bukan salinan berkas) |
| **Sistem Pembayaran** | `GET /api/pembayaran` → `/data/pembayaran.json` (`rekening` + `status`) |
| **Sistem Akuntansi** | `GET /api/akuntansi` → `/data/akuntansi.json` (`coa` + `jurnal` + `kas`) |

Dua tab terakhir semula membaca `payments.json`/`accounting.json` di web root —
**terbaca publik tanpa login**. Kini datanya pindah ke volume `/data` (di luar web
root) dan disajikan lewat endpoint ber-izin `pengaturan.kelola` (401 tanpa sesi,
403 untuk warga). Tab hanya menampilkan (baca-saja); tidak ada endpoint ubah.
Bentuk data sama seperti JSON lama, jadi isi `/data/pembayaran.json` dan
`/data/akuntansi.json` bisa disalin dari berkas lama bila perlu.

Semua DOM dibangun lewat helper `esc()`; sebagian tabel memakai `innerHTML`,
tetapi **setiap nilai yang berasal dari server/berkas di-escape** lebih dulu, jadi
CSP ketat dan aturan 1 tetap aman. Setiap fetch pengubah tetap mengirim
`X-Diminta-Dengan: dasbor`.

---

## 5. Mengubah & menerbitkan

```bash
# 0. SEBELUM mengubah apa pun: titik pulih + catatannya (snapshot + entri buku)
pwsh -NoProfile -File ./zima-hosting/cadangkan-tamanmarina.ps1 \
  -Nama 2026-10-07-sebelum-ubah-X -Catatan "<apa yang akan diubah>"

# 1. Edit berkas di zima-hosting/situs/tamanmarina/
# 2. (bila CSS/JS berubah) naikkan ?v= di index.html
# 3. validasi offline
node validasi-hosting.mjs

# 4. terbitkan (mengunggah Caddyfile + 9 aset + sumber tm-auth, build &
#    jalankan container tm-auth, restart web-router, verifikasi)
#    -Catatan mengisi entri buku; tanpanya entri tetap ditulis sebagai
#    "Terbit rutin" supaya jejaknya tidak pernah hilang.
MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/terbitkan-tamanmarina.ps1 -Sandi '<sandi ZimaOS>' -Catatan '<ringkasan perubahan>'
```

**Kebiasaan wajib: setiap penambahan program meninggalkan dua jejak.**
Sebuah titik pulih (snapshot di `cadangan-tamanmarina/`) dan satu entri di
`BUKU-PERUBAHAN.md` yang menyebut berkas, bukti uji, dan perintah rollback
persisnya. Ketiganya ditulis otomatis: `cadangkan-*.ps1` mencatat entri
"Cadangan", `terbitkan-*.ps1` entri "Terbit" (menunjuk titik pulih terbaru),
dan `kembalikan-*.ps1` entri "Kembali". Buku itulah berkas pertama yang
dibaca orang lain yang perlu memutar balik sebuah perubahan.

Skrip terbit otomatis membuat cadangan `*.bak-<tanggaljam>` di host sebelum
menimpa, mem-build image `tm-auth:22` dan menjalankan ulang container-nya
(network web-router dideteksi otomatis, volume `tm-auth_data` dipertahankan),
lalu memverifikasi dari luar: halaman 200 + penanda bagian baru (termasuk
`Status Seluruh Sistem` & `pengaturan.js`), setiap aset 200 (dengan
cache-buster), `/api/health` 200, `/masuk` 200, `/sensor/api/data` 200, dan
`clusternet.my.id` + `udara` tetap 200 (bukti tidak ada regresi).

**Jangan pakai panel `zima-deployer` (:8791)** — tombol "Terapkan ke ZimaOS" itu
tidak menulis ke Caddyfile LIVE (entri lama di `CATATAN-KENDALA.md`).

---

## 6. Verifikasi cepat

```bash
# anchor punya target?
node -e "const fs=require('fs');const h=fs.readFileSync('zima-hosting/situs/tamanmarina/index.html','utf8');const ids=new Set([...h.matchAll(/id=\"([^\"]+)\"/g)].map(m=>m[1]));const miss=[...new Set([...h.matchAll(/href=\"#([^\"]+)\"/g)].map(m=>m[1]))].filter(x=>!ids.has(x));console.log(miss.length?'TANPA TARGET: '+miss:'SEMUA ANCHOR OK')"

# sintaks JS & CSS/JS live
node --check zima-hosting/situs/tamanmarina/dasbor.js
node --check zima-hosting/situs/tamanmarina/pengguna.js
node --check zima-hosting/situs/tamanmarina/pengaturan.js
node --check zima-hosting/situs/tamanmarina/masuk.js
node --check zima-hosting/auth/server.mjs

# sensor + API akun + aset dari luar
curl -s -o /dev/null -w '%{http_code}\n' https://tamanmarina.my.id/sensor/api/data
curl -s https://tamanmarina.my.id/api/health
curl -s -o /dev/null -w '%{http_code}\n' https://tamanmarina.my.id/masuk
curl -s -o /dev/null -w '%{http_code} %{size_download}\n' "https://tamanmarina.my.id/dasbor.css?v=<versi>"

# rute hub pengaturan ada & terlindungi (tanpa cookie harus 401)
curl -s -o /dev/null -w '%{http_code}\n' https://tamanmarina.my.id/api/pengaturan
curl -s -o /dev/null -w '%{http_code}\n' https://tamanmarina.my.id/api/sistem
```

Di browser, periksa Console: hanya **satu** galat yang wajar, yaitu beacon
`static.cloudflareinsights.com` yang diblokir CSP. Galat lain = ada masalah.

---

## 7. Rollback

Tiga lapis, dari yang paling cepat:

1. **Cadangan otomatis di host** (dibuat setiap penerbitan). Kembalikan satu
   berkas lalu restart:
   ```
   sudo cp -a .../situs/tamanmarina/index.html.bak-<tanggaljam> .../index.html
   sudo docker restart web-router
   ```

2. **Snapshot di repo** (keadaan baik yang tersimpan) — daftar lengkap +
   perintah rollback tiap titik ada di **`BUKU-PERUBAHAN.md`**:
   ```
   zima-hosting/cadangan-tamanmarina/2026-10-05/                        (pra-modul akun)
   zima-hosting/cadangan-tamanmarina/2026-10-05-live/                  (kondisi live sebelum modul akun)
   zima-hosting/cadangan-tamanmarina/2026-10-05-sebelum-akun/          (sebelum modul akun)
   zima-hosting/cadangan-tamanmarina/2026-10-05-sebelum-pengaturan/    (sebelum hub Pengaturan; juga titik pulih pra-CRUD)
   zima-hosting/cadangan-tamanmarina/2026-10-06-sesudah-crud-pengaturan/ (setelah CRUD Pengaturan terbit)
   ```
   Rollback memulihkan **14 berkas**: 9 aset situs + 5 berkas `auth/`
   (Caddyfile hanya bila `-DenganCaddyfile`). Snapshot lama yang belum punya
   berkas baru tetap aman: berkas yang tidak ada di snapshot dilewati dengan
   peringatan, bukan menggagalkan rollback. Keadaan sebelum rollback selalu
   diselamatkan lebih dulu ke `cadangan-tamanmarina/pra-kembali-<stamp>/`,
   jadi rollback pun bisa dibatalkan.
   Untuk mematikan fitur akun tanpa menyentuh halaman: hapus blok
   `handle /api/*` di Caddyfile → `/api/*` kembali 404, dasbor pun otomatis
   kembali ke mode demo (tanpa sesi). Container bisa dihentikan:
   `sudo docker rm -f tm-auth` (data di volume tetap aman).
   Pulihkan + terbitkan ulang dalam satu perintah:
   ```
   MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-05 -Sandi '<sandi>'
   ```

3. **Membuat titik pulih baru** sebelum perubahan besar — satu perintah,
   menghasilkan snapshot **dan** entri di `BUKU-PERUBAHAN.md`:
   ```
   pwsh -NoProfile -File ./zima-hosting/cadangkan-tamanmarina.ps1 -Nama <label> -Catatan "<apa yang akan diubah>"
   ```
   (tanpa `-Nama` memakai tanggal hari ini; **selalu isi `-Catatan`**, karena
   itulah yang membuat titik pulih ini berguna saat dibaca nanti).

---

## 8. Jebakan yang sudah teruji

- **Skrip inline diblokir CSP tanpa galat server** — halaman tetap 200. Selalu
  taruh JS di `dasbor.js` (entri 14).
- **Cloudflare menyajikan CSS/JS basi dari cache.** Saat pertama kali memperbarui
  halaman, origin sudah baru tetapi CDN masih melayani ukuran lama. Solusinya:
  tautan aset berversi `?v=` (entri 15). Naikkan setiap kali CSS/JS berubah.
- **Jangan memeriksa aset tanpa cache-buster** — `curl .../dasbor.css` bisa
  membaca salinan lama dan "lolos" padahal belum terganti.
- **Urutan pemanggilan `zima-shell.mjs`**: semua `--upload` ditempatkan setelah
  perintah biasa, jadi mkdir / unggah / restart harus jadi tiga pemanggilan
  terpisah. Skrip terbit sudah menangani ini.
- **SSH 22 tertutup**; satu-satunya jalur ke host adalah ttyd (`:7681/ws`).
- **Volume `tm-auth_data` milik root, proses jalan sebagai `node`.** Tanpa
  entrypoint, tulis `/data` gagal. `mula.sh` melakukan `chown` volume lalu
  `exec su-exec node node server.mjs`; jangan hapus baris ini saat mengubah
  Dockerfile.
- **Jalankan `sudo` hanya lewat wrapper pwsh** (`zima-hosting/zima-shell.mjs`),
  bukan perintah host langsung. Build image manual di host butuh
  `sudo env DOCKER_CONFIG=/DATA/AppData/.docker docker build …` karena root FS
  read-only; skrip terbit sudah melakukannya.
- **Uji `/api/sistem` menghormati cache 15 detik.** Karena itu segarkan dengan
  `?segar=1`; tanpa itu perubahan status layanan baru terlihat setelah cache
  kedaluwarsa.

---

## 9. Checklist sebelum menerbitkan

- [ ] Tidak ada `<script>` inline di `index.html`.
- [ ] Tidak ada sumber `http://` atau gambar eksternal di halaman.
- [ ] Bila CSS/JS berubah: `?v=` di `index.html` sudah dinaikkan.
- [ ] Semua anchor `#…` punya section ber-`id` yang cocok.
- [ ] `node validasi-hosting.mjs` → 83/0/0.
- [ ] Bila berkas JS berubah: `node --check` pada tiap berkas lolos.
- [ ] Bila backend akun berubah: harness `.uji-tmp/uji.sh` → 57/57.
- [ ] **Titik pulih dibuat** sebelum mengubah berkas (`cadangkan-tamanmarina.ps1 -Nama … -Catatan …`).
- [ ] Entri di `BUKU-PERUBAHAN.md` memuat berkas, bukti uji, dan perintah rollback.
- [ ] Bila menambah berkas baru: daftar di `cadangkan-`, `terbitkan-`, dan `kembalikan-tamanmarina.ps1` diperbarui ketiganya.
- [ ] Bila `pengaturan.js`/`server.mjs` berubah: `?v=` `pengaturan.js` di
      `index.html` ikut dinaikkan.
- [ ] Snapshot cadangan dibuat (`cadangkan-tamanmarina.ps1`) untuk perubahan besar.
- [ ] Setelah terbit: cek Console (hanya galat beacon), `/sensor/api/data` 200,
      `/api/health` 200, `/masuk` 200, dan `clusternet.my.id` tetap 200.
