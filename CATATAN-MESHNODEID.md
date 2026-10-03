# CATATAN MESH ID — peta perawatan

Catatan ini dibuat **28 Sep 2026** untuk memudahkan perbaikan ke depan. Isinya
peta alamat, perintah periksa, cara mengubah, kendala yang **sudah pernah**
terjadi beserta penyebabnya, dan daftar yang belum selesai. Gaya penulisannya
sengaja **gejala → sebab → solusi → bukti**, supaya kalau muncul lagi tinggal
ikut langkahnya.

Kode programnya sendiri ada di `meshtastic-monitor/` (lihat `README.md` di
folder itu untuk penjelasan fitur). Berkas ini fokus pada **penyebaran,
alamat, dan perawatan**.

---

## 1. Ringkasan satu menit

**Mesh ID** = halaman data node Meshtastic (gateway, node RF yang tersambung
langsung, dan node lewat MQTT) + metrik Prometheus. Sejak 28 Sep 2026 exporter
**tidak lagi** berjalan di mesin kerja Windows, melainkan sebagai **systemd di
host ZimaOS** supaya hidup 24/7.

```
gateway Meshtastic            host ZimaOS (192.168.20.36)                    internet
192.168.20.31:4403  ──TCP──▶  meshtastic-exporter.service  ──▶ Caddy (web-router)
                                     port 9208                    │
                                     └─ meshtastic-notif.service   │  Host: meshid.clusternet.my.id
                                        └─ ntfy (HP)               ▼
                                                           Cloudflare Tunnel (cf-tunnel)
                                                                   │
                                                     https://meshid.clusternet.my.id
```

| Hal | Nilai |
| --- | --- |
| Alamat publik | **`https://meshid.clusternet.my.id`** |
| Alamat LAN | `http://192.168.20.36:9208/` |
| Di host itu sendiri | `http://127.0.0.1:9208/` |
| Port / layanan | 9208 (exporter), 8089 (Caddy LAN), 7681 (ttyd/terminal), 8791 (deployer) |
| Perlindungan | **publik, tanpa Cloudflare Access** (keputusan pemilik) |
| Isi halaman | nama node, status, baterai/tegangan, SNR/hop, **koordinat GPS** |

> Karena halaman ini publik dan memuat koordinat GPS node, jangan pernah
> menambahkan data sensitif (sandi, kunci API) ke dalam halaman atau
> `/data.json`. Bila suatu saat ingin ditutup, cara termudah: pasang
> **Cloudflare Access** untuk hostname `meshid.clusternet.my.id` di Zero Trust
> (tidak ada perubahan Caddyfile yang diperlukan).

---

## 2. Peta cepat: komponen, tempat, berkas

| Komponen | Tempat | Berkas / unit |
| --- | --- | --- |
| Exporter (halaman + `/metrics` + `/data.json`) | host ZimaOS | `/DATA/AppData/meshtastic-monitor/`, unit `meshtastic-exporter.service` |
| Notifier ntfy | host ZimaOS | unit `meshtastic-notif.service`, keadaan di `notif-meshtastic-state.json` |
| Router nama domain | container `web-router` (Caddy) | `/DATA/AppData/zima-hosting/Caddyfile` |
| Terowongan Cloudflare | container `cf-tunnel` | token di `.env` stack hosting |
| Jembatan panel → host | container `zima-deployer` | `http://192.168.20.36:8791` (butuh token) |
| Halaman dasbor + kartu | host ZimaOS | `/DATA/AppData/zima-hosting/situs/{index.html,dasbor.js,layanan.json}` |
| Sumber di repo ini | `meshtastic-monitor/` dan `zima-hosting/` | — |
| Timer reset NodeDB | **tidak dipasang** (sengaja) | `meshtastic-reset.{service,timer}` ada di repo, tidak diaktifkan |

Layanan **MikroTik, sensor udara (udara/aqi), Grafana, Kuma, billing** tidak
terpengaruh oleh catatan ini; semuanya punya dokumen sendiri.

---

## 3. Perintah perawatan (yang paling sering dibutuhkan)

### 3.1 Dari host ZimaOS

Lewat terminal web `http://192.168.20.36:7681`, atau lewat skrip repo:

```bash
# status kedua layanan
systemctl status meshtastic-exporter meshtastic-notif --no-pager

# log (modul logging Python menulis ke stderr -> journal)
sudo journalctl -u meshtastic-exporter -n 50 --no-pager
sudo journalctl -u meshtastic-notif  -n 50 --no-pager

# restart setelah mengubah kode
sudo systemctl restart meshtastic-exporter meshtastic-notif

# periksa langsung di host
curl -s http://127.0.0.1:9208/metrics | grep meshtastic_exporter_up

# kode terbaru dikirim ulang + dipasang (dari akar repo, Git Bash)
ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/pasang-ke-zima.sh
```

Tanpa membuka browser, perintah bisa dijalankan dari sini:

```bash
ZIMA_PASS='sandi' MSYS_NO_PATHCONV=1 node zima-hosting/zima-shell.mjs \
  "sudo journalctl -u meshtastic-notif -n 40 --no-pager"
```

> Jebakan: bila muncul `[ws error]` + `websocket error`, ttyd menolak sesi
> WebSocket baru (HTTP-nya tetap 200). Biasanya sesi sebelumnya belum lepas:
> tunggu sebentar, tutup tab `192.168.20.36:7681`, lalu coba lagi. Ini pernah
> terjadi 28 Sep 2026 setelah 2-3 sesi berturut-turut.

### 3.2 Dari mesin Windows / PC mana pun di LAN

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://meshid.clusternet.my.id/     # harap 200
curl -s https://meshid.clusternet.my.id/metrics | grep meshtastic_exporter_up  # harap 1.0
node validasi-hosting.mjs            # harap "Lolos 80 | GAGAL 0"
node validasi-hosting.mjs --uji      # uji diri validator, harap 18/18
```

---

## 4. Cara mengubah rute (subdomain)

Alur resminya: **ubah Caddyfile di repo → validasi → terapkan ke ZimaOS**.

1. Sunting `zima-hosting/Caddyfile` (blok `http://meshid.clusternet.my.id`).
   Setiap blok situs wajib `import http-umum` dan **berawalan `http://`**
   (TLS ditangani Cloudflare; cloudflared menyambung ke Caddy lewat port 80).
2. `node validasi-hosting.mjs` — validator menuntut setiap hostname di
   Caddyfile juga disebut di `zima-hosting/PANDUAN-WEBHOSTING.md`, dan setiap
   IP internal dijelaskan di panduan itu.
3. Terapkan lewat deployer (memvalidasi dengan `caddy validate`, me-restart
   `web-router`, dan **memulihkan sendiri** berkas lama bila Caddy gagal hidup):

```bash
node -e 'const fs=require("fs");
const t=fs.readFileSync("zima-hosting/.env.deploy-token","utf8").replace(/^DEPLOY_TOKEN=/,"").trim();
const c=fs.readFileSync("zima-hosting/Caddyfile","utf8");
fetch("http://192.168.20.36:8791/deploy",{method:"POST",
  headers:{Authorization:"Bearer "+t,"Content-Type":"application/json"},
  body:JSON.stringify({caddyfile:c})})
 .then(async r=>console.log(r.status, JSON.stringify(await r.json())))'
```

Cara setara tanpa terminal: buka `zima-hosting/panel-kelola.html` (atau
`node buka-panel.mjs` → `http://127.0.0.1:8788/panel-kelola.html`) lalu tekan
**Terapkan ke ZimaOS**.

Setelah setiap deploy, **uji semua rute** (bukan hanya yang baru) karena
deployer mengganti Caddyfile secara utuh:

```bash
for h in clusternet.my.id www.clusternet.my.id zima.clusternet.my.id \
         adguard.clusternet.my.id immich.clusternet.my.id grafana.clusternet.my.id \
         kuma.clusternet.my.id billing.clusternet.my.id udara.clusternet.my.id \
         aqi.clusternet.my.id meshid.clusternet.my.id \
         tes-acak123.clusternet.my.id; do
  printf "%-30s " "$h"
  curl -s -m 6 -o /dev/null -w "%{http_code}\n" -H "Host: $h" http://192.168.20.36:8089/
done
```

Hasil yang benar (28 Sep 2026): `clusternet/www/zima/immich/billing/udara/aqi/
meshid` = **200**, `adguard/grafana/kuma` = **302** (punya login sendiri),
`tes-acak123` = **404** dari wildcard.

Hasil diperiksa ulang **3 Okt 2026** setelah rute `meshbot` ditambahkan: semua
angka di atas **tetap sama** (tidak ada yang tergeser), dan `meshbot` = **502**
— artinya rutenya benar tetapi belum ada yang mendengarkan di `:9209` (lihat
§5.14). 502 bukan kegagalan; ia justru bukti `reverse_proxy` menunjuk tujuan
yang benar.

> **Pembaruan 3 Okt 2026 (sore):** rute `meshbot` lalu **dicabut kembali**
> bersama seluruh pemasangan bot (lihat **§5.15**), jadi daftar loop di atas
> kembali seperti semula. `meshbot.clusternet.my.id` kini dijawab **404**
> oleh wildcard, dan `meshid` tetap 200.

Cadangan otomatis yang tersedia kalau ada yang salah:

| Berkas | Cadangan |
| --- | --- |
| Caddyfile | `/data/.Caddyfile.bak` di dalam container `zima-deployer` (salinan sebelum setiap deploy) |
| `situs/*` | `*.bak-TANGGALJAM` di folder yang sama di host |
| Dokumen/kode | repo ini (tidak ada commit otomatis) |

### 4.1 Kartu dasbor

Kartu "Mesh ID" berada di `zima-hosting/situs/layanan.json` (8 kartu).
Menerbitkannya:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File zima-hosting/terbitkan-dasbor.ps1 -Sandi <sandi-ZimaOS>
```

> Catatan penting: **build `zima-deployer` yang terpasang (28 Sep 2026) lebih
> tua dari `deployer.js` di repo** — pada `GET /ping` ia tidak mengembalikan
> medan `dasbor`, dan pada `POST /deploy` ia mengabaikan medan `layanan`.
> Artinya menekan **Terapkan** di panel **tidak** memperbarui kartu dasbor;
> pakai `terbitkan-dasbor.ps1` di atas. Kalau suatu saat deployer diperbarui,
> kedua jalur itu setara.

---

## 5. Kendala yang sudah pernah terjadi

### 5.1 Notifier hidup tetapi tidak pernah melapor, dan mengulang alarm

**Gejala.** `notif.err.log` (Windows) atau `journalctl -u meshtastic-notif`
penuh baris sama berulang tiap interval:

```
putaran gagal: 'charmap' codec can't encode character '\U0001f6dc' ...
```

Di sisi HP: pesan **sama** datang berulang tiap ~60 detik (pernah sampai
menimbulkan `429 Too Many Requests` dari `ntfy.adminforge.de`).

**Sebab.** `main()` notifier tidak memaksa UTF-8 pada `sys.stdout/stderr`. Saat
keluaran dialihkan ke berkas, Python memakai encoding lokal (cp1252 di Windows);
`print()` atas judul ber-emoji melempar `UnicodeEncodeError`. Urutannya yang
berbahaya: pencetakan terjadi **sesudah** percobaan kirim tetapi **sebelum**
keadaan disimpan, jadi tiap putaran mati di titik yang sama, alarm yang sama
diulang terus.

**Solusi.** `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`
di awal `main()` (sudah ada di kode sekarang).

**Bukti.** `notif.err.log` = 0 byte; `notif.log` maju normal
(`tidak ada perubahan status (N node dipantau)`).

**Aturan umum yang berlaku selamanya:** bila **semua** kanal gagal, notifier
sengaja mengembalikan keadaan node ke sebelumnya supaya dicoba lagi. Karena itu
kanal yang mati (mis. ntfy lokal) **tidak** mematikan alarm, tetapi kegagalan
yang **sistematis** akan terlihat sebagai alarm berulang. Munculnya pesan kembar
= ada yang salah pada pengiriman, bukan pada deteksi.

### 5.2 `hentikan-layanan.bat` tampak berhasil, layanan tetap jalan (Windows)

**Gejala.** Skrip menulis "Selesai", tetapi port 9208 masih LISTENING.

**Sebab.** `venv\Scripts\python.exe` di mesin itu adalah **peluncur venv**: ia
menjalankan interpreter dasar (`C:\Espressif\tools\python\python.exe`) sebagai
**proses anak** dengan argumen sama. Command line anaknya tidak memuat kata
`meshtastic-monitor`, sehingga saringan lama hanya mematikan peluncurnya —
sedangkan anaknya justru pemegang port.

**Solusi.** Saring berdasarkan **nama skrip** (`exporter-meshtastic\.py` /
`notif-meshtastic\.py`) sebagai nama berkas utuh, sehingga peluncur **dan**
anaknya termatikan sementara `uji-notif-meshtastic.py` tidak ikut.

**Bukti.** Setelah dijalankan: tidak ada `python.exe` yang cocok, port bebas.

### 5.3 `pasang-ke-zima.sh` gagal dua kali sebelum berhasil

**Gejala 1.** Skrip berhenti tanpa pesan jelas (`SHELL_JS: unbound variable`).

**Sebab 1.** Variabel `SHELL_JS` dipakai untuk memanggil `zima-shell.mjs`
tetapi tidak pernah diisi, sementara skrip memakai `set -u`.

**Solusi 1.** Diberi bawaan `SHELL_JS=${SHELL_JS:-$AKAR/zima-hosting/zima-shell.mjs}`.

**Gejala 2.**

```
Error: Cannot find module 'C:\c\temp\mikrotik_monitor\zima-hosting\zima-shell.mjs'
```

**Sebab 2.** Git Bash memberi jalur gaya MSYS (`/c/temp/...`) kepada `node.exe`
yang tidak mengenalnya; konversi otomatis dimatikan justru oleh
`MSYS_NO_PATHCONV=1` — yang memang wajib, supaya jalur tujuan `/DATA/...` tidak
berubah menjadi `C:/...`.

**Solusi 2.** Fungsi `ke_node()` yang memakai `cygpath -m` untuk jalur yang
diserahkan ke Node (dan meneruskan apa adanya di Linux/macOS).

**Bukti.** Pemasangan berhasil: 32 entri terkirim, venv + dependensi terpasang,
kedua unit systemd `enabled` dan `active (running)`.

### 5.4 Rute baru sempat menjawab 502

**Gejala.** `meshid.clusternet.my.id` menjawab **502** sesaat setelah Caddyfile
diterapkan.

**Sebab.** Blok rutenya sudah hidup, tetapi belum ada yang mendengarkan di
`192.168.20.36:9208` (exporter belum dipasang di host).

**Arti sebenarnya:** 502 justru **bukti rute sudah benar** — Caddy mencoba
meneruskan ke tujuan. Setelah exporter dipasang, jawabannya berubah menjadi 200.

### 5.5 Catatan alamat `192.168.145.252` vs `192.168.20.36`

`zima-hosting/Caddyfile` masih memakai `192.168.145.252` untuk layanan ZimaOS
(UI ZimaOS, AdGuard, Immich, Grafana, Kuma, billing), sedangkan dokumentasi
lapangan memakai `192.168.20.36`. Pada 28 Sep 2026 rute-rute itu **terbukti
masih hidup** lewat deploy dari repo, jadi nilainya benar **untuk container
Caddy**; dari mesin Windows, `192.168.145.252:3003` tidak menjawab sementara
`192.168.20.36:3003` menjawab. Untuk blok baru, alamat LAN `192.168.20.36`
dipakai langsung supaya bisa diuji dari LAN. Bila kelak salah satu rute ZimaOS
mati setelah deploy, tersangka pertama adalah perbedaan dua alamat ini —
gantilah blok itu ke `192.168.20.36` dan terapkan ulang.

### 5.6 Penerapan tampak berhasil, tetapi halaman & metrik tetap versi lama

Terjadi 28 Sep 2026 saat memasang pembaruan halaman exporter. **Gejala:**
`pasang-ke-zima.sh` selesai tanpa keluhan dan berkas di host sudah baru, tetapi
halaman `https://meshid.clusternet.my.id/` dan `/metrics` masih kode lama.

**Sebab.** `pasang-layanan.sh` memakai `systemctl enable --now`, yang hanya
menyalakan unit yang **belum** berjalan. Pada unit yang sudah aktif perintah itu
no-op, jadi proses lama (dengan kode lama di memori) tetap memegang port 9208.
Bukti: `systemctl show meshtastic-exporter -p ActiveEnterTimestamp` menunjukkan
jam jauh sebelum waktu penerapan.

**Solusi permanen** (sudah dipasang di `pasang-layanan.sh`): setelah `enable`,
selalu `systemctl restart`. Untuk memeriksa tanpa menerapkan ulang:

```bash
systemctl show meshtastic-exporter -p MainPID -p ActiveEnterTimestamp
```

Jamnya harus **sama dengan waktu penerapan terakhir**. Bila tidak, paksa:

```bash
sudo systemctl restart meshtastic-exporter meshtastic-notif
```

**Catatan kedua.** `pasang-ke-zima.sh` bisa melaporkan
`*** GAGAL: timeout ... penanda __DONE_4__ ***` pada langkah uji jalur admin
walau pemasangan sudah selesai — periksa `systemctl status` dan `/metrics`
dulu, jangan langsung mengulang.

### 5.7 Halaman hidup tetapi KOSONG ("hidup tetapi buta")

Terjadi 28 Sep 2026 sore. **Gejala:** `https://meshid.clusternet.my.id/`
memuat kerangka halaman (9.378 byte) tanpa satu pun baris node, `/data.json`
melaporkan `jumlah_node: 0` dan `kesehatan_gateway` `null`, tetapi
`meshtastic_exporter_up` tetap **1** sehingga tidak ada alert yang berbunyi.
Uptime di halaman juga tampak membeku.

**Tiga sebab yang menumpuk, semuanya sudah diperbaiki:**

1. **Versi terpasang tertinggal.** `md5sum` + `grep` di
   `/DATA/AppData/meshtastic-monitor/` membuktikan berkas di host **tidak
   memuat penjaga koneksi sama sekali** (44256 byte, 18:19) sementara berkas
   lokal sudah memuatnya (46652 byte, 18:40). Penerapan terakhir mendahului
   penyuntingan terakhir. **Selalu bandingkan `md5sum` host vs lokal** — jangan
   percaya "pasang selesai" saja.
2. **Penjaga mati bila pembacaan pertama kosong.** Socket mati pukul 18:22
   (`Unexpected OSError, terminating meshtastic reader`) sebelum satu pun
   pembacaan berisi; penanda "pernah ada isi" tak pernah menyala, jadi loop
   diam mengumpulkan 0 node tiap 30 detik **tanpa baris WARNING** (terbukti:
   `journalctl` 3 jam → 0 kali "tidak ada data dari gateway").
3. **Dua exporter berebut satu radio.** Salinan di mesin Windows dan di ZimaOS
   sama-sama ke `192.168.20.31:4403`; API node Meshtastic melayani **satu klien
   saja**, jadi tiap sambungan baru memutus yang lain (interval ~10 menit,
   seirama heartbeat pustaka).

**Solusi.** `mulai-ulang-zima.sh` (baru) untuk memulihkan tanpa mengunggah
berkas, plus penjaga yang diperkuat di `exporter-meshtastic.py`: penjaga
menyala dari isi handshake, tenggat `MESH_BUTA_TUNGGU` (120 detik), dan `up`
serta `meshtastic_cuplikan_umur_seconds` yang dihitung dari umur data saat
scrape — jadi alert tetap berbunyi walau loop pengumpulnya sendiri tersangkut.

```bash
ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/mulai-ulang-zima.sh
```

---

### 5.8 Saringan node ikut terbuang saat halaman menyegar

**Permintaan pemilik halaman:** saringan node harus bisa dipakai **tepat di atas
tabel NODE LEWAT MQTT (INTERNET)** — tabel terpanjang di halaman (ratusan node)
— dan katanya **tetap tersimpan** saat halaman menyegar sendiri tiap 5 detik.

**Keadaan sebelumnya.** Kotak saring hanya **satu**, duduk di atas ketiga tabel,
jadi untuk menyaring tabel MQTT orang harus menggulir jauh ke atas dulu. Kata
saringannya pun hanya disimpan di `#hash` alamat. Hash biasanya memang selamat
melewati penyegaran `<meta http-equiv="refresh">`, tetapi ia satu-satunya
salinan: begitu alamat dibuka dari tautan bersih atau diketik ulang, saringan
hilang tanpa jejak.

**Sekarang.** Ada **dua** kotak (`id="saring"` dan `id="saring-mqtt"`, keduanya
bertanda `data-saring`) yang berbagi satu kata saringan — mengetik di salah
satunya mengisi yang lain dan menyembunyikan baris di ketiga tabel sekaligus.
Kata saringannya disimpan di **tiga** tempat berlapis: `localStorage`
(`meshid-saring-1`, inilah yang membuatnya tidak hilang saat menyegar, dan
tidak bergantung pada peramban yang mempertahankan hash), `#hash` untuk tautan
yang bisa dibagikan (menang atas `localStorage`, supaya tautan kiriman orang
lain tidak ketimpa saringan lama penerima), dan `sessionStorage`
(`meshid-saring-fokus`) untuk mengembalikan fokus ke **kotak yang terakhir
dipakai**, bukan selalu kotak paling atas.

**Catatan pilihan.** Ini diuji dulu di peramban sungguhan, bukan hanya dari
hasil render: kotak kedua memang duduk **di atas** tabel MQTT-nya
(`getBoundingClientRect` kotak ≤ atas tabel), mengetik `!da5a16f8` menyisakan
1 dari 115 baris di kedua kotak sekaligus, dan sesudah satu siklus penyegaran
sendiri (`performance.timeOrigin` berubah) nilai, fokus, dan hasil saringannya
utuh kembali. Jejak uji di kode: `uji-halaman-meshtastic.py` bagian **10** —
sekarang **87 lulus / 0 gagal**. Saringan menempel di peramban, jadi perlu
**Ctrl+F5** sekali di tab yang sudah lama terbuka sebelum menilai hasilnya.

---

### 5.9 Menghapus node yang lama tidak aktif (tanpa mengosongkan seluruh daftar)

**Permintaan pemilik halaman:** "buat program otomatis node yang selama 5 hari
tidak aktif dihapus". Cara lama (`reset-node.py`) terlalu kasar - ia
mengosongkan **seluruh** NodeDB, termasuk node RF sendiri, dan menghapus semua
tanda Favorite.

**Jawaban:** `bersih-node.py` (baru). Ia membaca `lastHeard` tiap entri NodeDB,
memilih yang umurnya melewati ambang (bawaan **5 hari**), lalu mengirim
`remove_by_nodenum` satu per satu lewat jalur admin - satu perintah per node,
dengan jeda 1 detik. Setelah itu ia **menutup sambungan, menyambung ulang, dan
membaca ulang NodeDB** untuk membuktikan berapa yang benar-benar hilang; laporan
"berhasil" tidak berdasarkan asumsi. Hasilnya juga ditulis ke
`bersih-terakhir.json` dan dikirim ke ntfy.

**Pelindung bawaan** (masing-masing punya alasan yang sudah terbukti di
perangkat ini): gateway sendiri selalu aman; node **Favorite** dilewati; node
**jalur radio** dilewati (ROUTER bisa hanya memancar beberapa kali sehari -
umur panjang bukan berarti mati); node **tanpa `lastHeard`** dilewati (umur yang
tidak diketahui tidak boleh dibaca sebagai "lama"); ada `--batas 200` sebagai
jaring pengaman. Masing-masing bisa dibuka dengan `--termasuk-favorit` /
`--termasuk-radio`, dan `--kecuali !id` untuk mengunci node tertentu.

**Hasil ukur di gateway 28 Sep 2026** (115 entri: 9 jalur radio + 106 MQTT):

| Ambang | Lewat ambang | Isinya |
| --- | --- | --- |
| > 5 hari | 1 | 1 radio + Favorite - **dilindungi**, jadi nol yang dihapus |
| > 12 jam | 12 | 11 MQTT |
| > 6 jam | 26 | 25 MQTT |
| > 1 jam | 58 | 57 MQTT |

Median umur seluruh node hanya **4.358 detik** dan yang terlama 130 jam. Jadi
ambang 5 hari **aman tetapi hampir tidak pernah menyala**: node MQTT yang masih
hidup terus memperbarui waktunya. Untuk benar-benar mengosongkan daftar, ambang
1-6 jam yang bekerja - dan sesudah itu keran tetap harus ditutup dengan
`mqtt-downlink.py`, sebab selama downlink hidup node-node itu masuk kembali.

**Penjadwalan:** `meshtastic-bersih.timer` (harian 03:30, `Persistent=true`,
`--jeda-min-jam 20`), dipasang hanya bila diminta: `MESH_PASANG_BERSIH=1 sudo sh
pasang-layanan.sh`. Bawaannya **tidak** dipasang - sama semangatnya dengan timer
reset, karena ini tetap mengubah isi perangkat secara otomatis.

**Uji:** `uji-bersih-node.py` - **61 lulus / 0 gagal**, seluruhnya dengan
gateway palsu (tanpa jaringan, tanpa radio). Uji itu menahan tiap batas yang
mudah salah: tepat 5 hari masih AKTIF, lewat 1 detik sudah kandidat,
`lastHeard` 0/negatif dianggap tanpa waktu, `--batas` memotong lalu melaporkan
sisanya, `--jeda-min-jam` benar-benar menghentikan jalan kedua, dan mode
periksa terbukti **tidak** mengirim satu pun perintah hapus.

---

### 5.10 Meter sinyal per node di halaman Mesh ID

**Permintaan pemilik halaman:** memakai acuan resmi Meshtastic
([Apple](https://meshtastic.org/docs/software/apple/user/signal-meter/) &
[Android](https://meshtastic.org/docs/software/android/user/signal-meter/))
untuk menampilkan meter sinyal pada **setiap node** di halaman meshid.

**Inti acuannya:** meter Meshtastic bukan meter "keras-lemah" seperti ponsel,
melainkan meter **keterbacaan**. Yang dihitung jarak **SNR** paket terakhir dari
**lantai demodulasi** preset radio yang sedang dipakai — karena itu SNR negatif
itu normal (LoRa bisa mendengar di bawah derau), dan SNR yang sama bisa bernilai
berbeda antar-preset. RSSI sengaja tidak dipakai untuk rating per node.

**Angka lantainya tidak dikarang.** Tabel yang dipakai halaman disalin dari tabel
lintas-platform aplikasi Android & Apple (`ChannelOption.kt` dan
`ModemPresetSnrLimitTests.swift`), lengkap dengan koreksinya: lantai **LONG_SLOW
= -20 dB (SF12)**, bukan -7,5 dB — nilai yang pernah salah tertempel di kedua
aplikasi (issue #2041/#5446) sampai tautan LongSlow yang sehat dinilai buruk.
Ambang tingkatnya juga dari sana: `>0` dB di atas lantai = Baik, sampai −5,5 dB =
Cukup, sampai −7,5 dB = Buruk, lebih dalam = Nihil. Uji `uji-halaman-meshtastic.py`
bagian 11 mengunci angka-angka ini supaya tidak berubah diam-diam.

**Yang sekarang tampil:** kolom **Sinyal (SNR)** berisi tiga batang berwarna +
kata mutunya + angka SNR mentahnya. Preset gateway dibaca dari perangkat saat
exporter menyambung (`localNode.localConfig.lora`) dan ditulis terbuka di kepala
halaman serta legenda (`LONG_FAST -> lantai -17.5 dB`); untuk setelan **kustom**
lantai ditaksir dari spread factor/bandwidth dan ditandai `kustom`. Bila
setelannya belum terbaca, halaman menulis `tidak terbaca` dan menandai
lantainya sebagai **asumsi** — bukan menampilkan angka yang seolah-olah pasti.

**Dua keputusan yang sengaja diambil:** (1) node **jalur MQTT tidak diberi
meter** — gateway tidak pernah mendengarnya lewat udara, SNR yang tersimpan
datang dari radio orang lain, jadi menampilkannya sebagai "sinyal Anda" akan
menyesatkan; selnya berisi `– lewat internet`. (2) node tanpa SNR tetap `-`,
bukan "Nihil" — tidak ada data bukan berarti sinyalnya buruk.

**Hitungan di gateway 28 Sep 2026** (preset `LONG_FAST`, SF11/250 kHz, lantai
-17.5 dB): dari 115 node, 3 node jalur radio **semuanya Baik** (SNR 5.0 / 6.25 /
6.5 dB), 6 node `-` (jalur radio tanpa SNR), dan 106 node MQTT berisi
`– lewat internet`. Jadi meter ini belum "berbunyi" apa-apa — memang: tautan
lokal kita masih nyaman di atas lantai. Nilainya baru muncul saat sebuah tautan
mendekati lantai (mis. SNR ≈ −25 dB akan terbaca Nihil).

**Uji & sebaran:** `uji-halaman-meshtastic.py` naik dari 87 → **136 lulus / 0
gagal** (bagian 11 memeriksa tabel preset, batas tiap tingkat, meter per node di
halaman, dan `mutu_sinyal` + `lantai_snr` di `/data.json`).

### 5.11 Notifikasi: kontak radio langsung, gateway mati, node putus

**Permintaan pemilik halaman (tiga kabar):**

1. node LoRa yang **terdeteksi langsung di gateway dan SNR-nya terbaca** →
   notifikasi berisi **id node + kualitas sinyal**;
2. notifikasi bila **gateway mati**;
3. notifikasi bila **node yang tersambung ke gateway menjadi offline**
   (sudah ada; kini isinya ikut menyebut kualitas sinyal terakhir).

**Pembeda yang dipakai untuk "terdeteksi langsung":** SNR hanya terisi bila
**radio gateway sendiri** yang menerima paket node itu. Jadi syaratnya jalur
`lora` **dan** `snr` numerik — bukan sekadar nama node muncul di daftar. Node
yang paketnya menumpang internet (MQTT) memang ada di database gateway, tetapi
tidak pernah didengar lewat udara, sehingga tidak boleh dikabarkan seolah-olah
tautan RF-nya hidup.

**Cacat nyata yang ditemukan uji.** Saat fitur kontak radio pertama dipasang,
`uji-notif-meshtastic.py` melaporkan 7 kegagalan pada uji deteksi yang tadinya
hijau — bukan karena fitur barunya, melainkan karena loop "node hilang dari
daftar" di `deteksi()` **menimpa catatan node yang masih ada** dengan catatan
lama. Akibatnya status per node tidak pernah maju: node yang sudah offline
dilaporkan offline **terus tiap putaran**, dan pemulihannya tidak pernah
terdeteksi. Perbaikannya: node yang ada di `hadir` dilewati (`continue`), dan
hanya node di luar lingkup pantauan yang catatannya ditahan utuh. Pelajaran yang
masuk README: **jalankan `uji-notif-meshtastic.py` sebelum menerapkan
perubahan apa pun pada notifier.**

**Gateway mati diperiksa dari sisi notifier**, bukan dari halaman: saat gateway
tidak terbaca, halaman web justru sedang tidak bisa memberi tahu siapa pun. Tiga
sebab dibedakan, semuanya nyata di perangkat ini:

| Sebab | Tanda | Pesan berisi |
| --- | --- | --- |
| exporter tidak menjawab | pembacaan gagal | `exporter tidak menjawab (…)` |
| data exporter basi | `umur_data_seconds` > `NOTIF_BASI_GW` | `sudah basi … loop pengumpul tersangkut` |
| gateway "hidup tetapi buta" | `jumlah_node` 0 **dan** `firmware` kosong | `exporter hidup tetapi buta` |

Kabar mati berprioritas **`max`** (satu-satunya) dan hanya dikirim setelah
**2 putaran gagal berturut-turut** (`NOTIF_ABSEN_GW`), supaya exporter yang baru
**restart saat penerapan kode** tidak menjadi alarm palsu. Terbukti pada
penerapan kali ini: penerapan mengulang `meshtastic-exporter.service`, notifier
tumbuh hidup 1 putaran tanpa exporter, lalu pulih sendiri
(`gagal: 0`, `mati: false`, 3 node dipantau) tanpa satu pun alarm palsu.

**Exporter mati tidak membuat notifier lupa.** Ketika `/data.json` gagal dibaca,
tidak ada penilaian per node yang dibuat dan catatan lama dibiarkan **utuh**.
Sebelum perubahan ini, kelaparan data justru mematikan notifier di tengah putaran
(jejak `putaran gagal: … Connection refused` berulang di jurnal), sehingga tidak
ada satu pun kabar — termasuk kabar bahwa gateway mati.

**Lantai sinyal mengikuti preset gateway.** `/data.json` tidak mengirim
`lantai_snr` per node, hanya sekali di `kesehatan_gateway`. Karena itu `deteksi()`
membacanya dari sana; bila tidak ada, lantai bawaan dipakai. Tanpa ini, teks
notifikasi akan tetap menyebut `-17.5 dB` (LONG_FAST) sekalipun preset gateway
diganti — angka yang benar-benar menyesatkan pada preset lain.

**Jeda `NOTIF_JEDA_KONTAK` (6 jam).** `via` mengikuti paket **terakhir**, jadi
node di antara dua jalur bisa bergantian radio ↔ MQTT. Tanpa jeda, tiap
pergantian menjadi notifikasi. Kabar "kontak kembali" untuk node yang sama baru
boleh diulang setelah jeda ini.

**DUA TOPIK, satu server.** Ketiga kabar di atas terjadi jarang (beberapa kali
sepekan), sedangkan kabar rutin lainnya (baterai, SNR, hop, saran Favorite) bisa
beberapa kali sehari. Karena itu Mesh ID memakai **dua topik** supaya di ponsel
keduanya bisa diberi nada dering dan aturan "jangan ganggu" yang berbeda:

| Keperluan | Topik | Isi |
| --- | --- | --- |
| Kabar **penting** | `mesh-penting-2kevnee56c4` | gateway mati/pulih, node LoRa terdeteksi & kontak kembali, node offline/pulih |
| Kabar **rutin** | `mesh-6h4v8p2rxq` | baterai, SNR lemah, hop bertambah, node hilang dari database, gateway reboot, DB penuh, saran Favorite |

Kabar **pemulihan** dari ketiga hal penting itu ikut ke topik penting juga,
supaya topik itu tidak pernah berbunyi tanpa kabar sembuhnya. Penandanya
dibawa **di dalam** pesannya (`penting: True`), bukan disimpulkan dari judulnya —
supaya menyunting kalimat tidak diam-diam memindahkan kabar penting ke luar
topiknya. Uji 2c mengunci pemisahan ini, termasuk jalan kembalinya
(`NTFY_TOPIK_PENTING=` kosong = satu topik lagi).

**Alarm palsu kedua yang ditangkap uji.** Payload exporter yang belum lengkap
(tanpa kunci `jumlah_node`, mis. tepat setelah exporter dimulai) dulu disimpulkan
sebagai "gateway hidup tetapi buta" — persis alarm yang paling menakutkan untuk
dikeluarkan secara keliru. Syaratnya sekarang "`jumlah_node` **ada** dan bernilai
0"; ketiadaan kunci bukan bukti apa-apa, dan kegagalan membaca gateway sudah
tertangkap dua jalur lain (exporter tidak menjawab, data basi).

**Keadaan setelah dipasang** (28 Sep 2026, 22:15 WIB):

- `meshtastic-notif.service` **active**, deskripsi ikut diperbarui, memakai kode
  baru (`[exporter tidak terbaca] …` muncul di jurnal saat exporter belum siap);
- tangkapan uji: **51 lulus / 0 gagal** (mode kirim: ketiga jenis kabar plus
  satu kabar rutin benar-benar tiba di topik yang tepat) dan **45 lulus / 0
gagal** (`--kering`);
- satu notifikasi nyata benar-benar tiba di topik rutin dan dibaca kembali:
  `Node LoRa terdeteksi: [B38]MTL|CBT|MOB-01` dengan isi `ID node : !02ee76d0`
  dan `Kualitas sinyal: Baik (SNR 6.2 dB; lantai preset -17.5 dB)`;
- topik penting `mesh-penting-2kevnee56c4` **dibuat dan terbukti bisa ditulisi &
  dibaca kembali** (uji 3b), jadi langganan di ponsel aman ditambahkan.

### 5.12 Artefak runtime ikut terkirim saat penerapan → alarm palsu

**Gejala.** Dua kali dalam 30 menit masuk kabar
`Gateway Meshtastic baru saja reboot` yang mengaku `reboot_count` gateway
bertambah 8 (46 → 54). Padahal **uptime gateway naik terus** (2 jam 44 menit →
3 jam 14 menit) — tidak ada jeda power, tidak ada reboot. Yang mencurigakan:
keduanya mengaku "bertambah 8", artinya titik acuan yang dibaca notifier selalu
kembali ke 46.

**Sebab.** `meshtastic-monitor/notif-meshtastic-state.json` ada di mesin Windows
juga (sisa percobaan lama, terakhir 19:12, isinya `reboot_count: 46` dan
`node: {}`), dan `tar` di `pasang-ke-zima.sh` **tidak mengeluarkannya** dari
paket. Jadi setiap penerapan menimpa catatan notifier di host dengan catatan
lama dari mesin ini. Akibatnya bukan hanya reboot: daftar node yang kosong juga
membuat node yang sudah offline dilaporkan offline lagi, dan
`favorit_dilaporkan` yang lama membuat saran Favorite terulang.

Yang membuat jebakan ini sulit dilihat: `.gitignore` sudah mengabaikan berkas
state, tetapi `tar` tidak membaca `.gitignore` — daftar `--exclude` di skrip
penerapan adalah daftar yang berlaku, dan berkas yang dilewatkan dari DAFTAR itu
tidak pernah mengeluh. Ditambah lagi `notif-meshtastic-state.json` sudah masuk
`.gitignore` sehingga tampak "sudah aman".

**Perbaikan.** `--exclude='*state.json'` dan `--exclude='*.log'` ditambahkan ke
daftar paket, dan sesudah paket jadi isinya **DIPERIKSA** - kalau masih ada
artefak runtime, penerapan dihentikan (`exit 1`) dengan menyebut berkas mana yang
bermasalah, bukan sekadar memperingatkan. State dan log juga tidak lagi ikut
menimpa berkas lama di host (terbukti: `exporter.err.log`, `notif.log`, dan
`bot-meshtastic-state.json` di host masih bertanggal penerapan yang lama,
sementara `notif-meshtastic-state.json` baru ditulis oleh layanan sendiri).

**Verifikasi.** Setelah penerapan berikutnya, `reboot_count` yang tercatat di
state host = **54** (sama dengan gateway), dan tidak ada lagi kabar reboot palsu
sesudahnya.

### 5.13 Monitoring Mesh ID masuk ke Grafana yang sudah ada

**Permintaan pemilik halaman.** "Buatkan monitoring grafananya" — ingin metrik
Mesh ID (`meshtastic_*`) tampil di Grafana ZimaOS, bukan hanya angka di halaman
web. Semua akses host memakai user ZimaOS `hendra`.

**Keputusan: menumpang Prometheus/Grafana yang sudah hidup, bukan memasang yang
baru.** Host sudah menjalankan app `mikrotik-monitor` (Prometheus 0.0.0.0:9090,
container `mikrotik-prometheus`) dan `grafana` (0.0.0.0:3003) untuk memantau
router. Memasang Prometheus kedua berarti dua basis waktu, dua dasbor, dan dua
tempat yang bisa rusak diam-diam. Jadi yang ditambahkan hanya **satu job scrape**.

**Tiga berkas host yang disentuh** (cadangan `.bak-2026-09-28-2312` untuk dua
yang pertama):

| Berkas | Perubahan |
| --- | --- |
| `/DATA/AppData/mikrotik-monitor/prometheus.yml` | job `meshtastic` (`targets: ["host.docker.internal:9208"]`, `scrape_interval: 30s`) + `rule_files: [/etc/prometheus/alert-meshtastic.yml]` |
| `/DATA/AppData/mikrotik-monitor/alert-meshtastic.yml` | **baru**: 13 aturan (salinan dari repo) |
| `/var/lib/casaos/apps/mikrotik-monitor/docker-compose.yml` | `extra_hosts: [host.docker.internal:host-gateway]` + volume ketiga yang me-mount berkas aturan read-only |

**Kenapa `host.docker.internal` dan bukan alamat docker.** Exporter Mesh ID
mendengarkan di **host** (`0.0.0.0:9208`), bukan di dalam jaringan container.
Tiga alamat terbukti tembus dari dalam container: `172.17.0.1` (docker0),
`172.21.0.1` (gateway `mikrotik-monitor_default`), dan IP LAN host
`192.168.20.36`. Yang dipilih `host.docker.internal` karena **tidak terikat pada
nama jaringan** — kalau app compose suatu saat dibuat ulang dengan nama lain,
gateway `172.21.0.1` bisa berubah, sedangkan `extra_hosts: host-gateway` selalu
menunjuk IP host.

**Jebakan nyata: `rule_files` dan volume-nya harus dipasang bersama.** Bila
`rule_files:` ditambahkan ke `prometheus.yml` tetapi berkasnya tidak di-mount,
Docker membuat **direktori kosong** di jalur itu (`create_host_path`), dan
Prometheus **gagal start**. Karena itu volume ketiga ditulis eksplisit dengan
`create_host_path: false` supaya salah pasang langsung berisik, bukan diam-diam
membuat folder. Sesudah itu `promtool check config` → SUCCESS dan
`promtool check rules` → **13 rules found**.

**Satu aturan baru yang menutup lubang lama.** `MeshtasticExporterDown`
bersandar pada `meshtastic_exporter_up`, tetapi metrik itu **hanya dipancarkan
bila `MESH_BASI_MAKS` ≠ 0** (bawaan `max(3×interval, 90)`), sehingga bisa absen
tepat setelah exporter restart — dan sebuah aturan `absent()` yang salah tulis
justru akan berbunyi palsu. Karena itu ditambahkan
**`MeshtasticDataStale`** (`meshtastic_cuplikan_umur_seconds > 300`, `for: 5m`,
severity critical), yang tidak bergantung pada metrik mana pun yang bisa hilang:
umur cuplikan hanya tumbuh bila loop pengumpul benar-benar tersangkut.

**Menerbitkan dasbor lewat API, bukan impor manual.** Impor manual lewat web
Grafana sulit diulang dan tidak bisa diperiksa otomatis, jadi dibuat
`terbitkan-dasbor-grafana.py`: mengganti `${DS_PROMETHEUS}` secara **struktural**
(46 tempat, bukan ganti-teks di seluruh berkas), **membaca ulang** dasbor yang
tersimpan untuk mengambil `version`/`id` (menghindari HTTP 412 "version
mismatch"), lalu menerbitkan dengan `overwrite: true`. Setelah itu berkas dibaca
kembali dan skrip **`exit 1` bila masih ada `${DS_PROMETHEUS}`** (sisa = 0).
Opsi `--periksa` menjalankan tiap kueri panel **lewat datasource Grafana**, jadi
"panel kosong" ketahuan sebelum dilihat mata.

**Hasil live (28 Sep 2026, 23:15 WIB; diperiksa ulang beberapa saat kemudian).**
Job `meshtastic` **up**; 13 aturan `inactive/ok`; **1.418 → 1.449 seri** pada job
meshtastic (jumlahnya tumbuh mengikuti NodeDB); `sum(meshtastic_node_online)`
≈ 81–82 (selalu bergerak, wajar); `cuplikan_umur_seconds` ≈ 8,4 s; semua target
MikroTik lama tetap `up`.
Dasbor **uid `meshtastic-node`** (23 panel) tersedia di
`https://grafana.clusternet.my.id/d/meshtastic-node`; `--periksa` melaporkan
**18 panel berisi kueri, semua OK, 0 kosong** (Total node 1 seri, SNR 3 seri,
Suhu 5, Tekanan 4, dst). Penerbitan kedua kali **idempoten** (tetap versi 1).

Datasource yang dipakai adalah **`Prometheus`** (uid `prom-mikrotik` →
`http://172.17.0.1:9090`) — sama dengan dasbor MikroTik, jadi tidak ada
datasource baru yang perlu dirawat. Kredensial Grafana (`admin`) **tidak
disimpan di repo**; alat yang membutuhkannya (mis. `tautan-balik-grafana.mjs`)
membacanya dari luar repo, dan skrip penerbit menerimanya lewat env
`GRAFANA_USER`/`GRAFANA_PASS`.

> Catatan operasional: **port Prometheus (9090) dan API Grafana (3003) tidak
> terjangkau langsung dari subnet lain** (mis. mesin Windows), meski dipublikasikan
> host. Jadi `terbitkan-dasbor-grafana.py` dijalankan **di dalam host**
> (`192.168.20.36`) lewat `zima-shell.mjs`; dari Windows, `--kering` akan gagal di
> bagian datasource/panel. Antarmuka web Grafana sendiri dibuka lewat
> `grafana.clusternet.my.id` (Cloudflare Tunnel + Access), bukan langsung ke 3003.

**Posisi gulir & nama node di peta (1 Okt 2026, 20:35 WIB).** Tiga
gejala diperbaiki sekaligus lewat `pasang-perbaikan-layar.sh`
(unggah `exporter-meshtastic.py`, `lacak_halaman.py`, `lacak_node.py`
ke `/DATA/AppData/meshtastic-monitor`, cadangan `*.sebelum-layar-<stempel>`):

1. **Halaman Monitoring melompat ke atas tiap 5 s** (refresh meta).
   Sebab: muat ulang selalu mulai dari puncak. Solusi: `SKRIP_LAYAR`
   mencatat `window.scrollY` + posisi tiap kotak `.gulir` ke
   `sessionStorage` (kunci per `location.pathname`, debounce 120 ms,
   `history.scrollRestoration='manual'`, dipulihkan saat DOMContentLoaded
   dan lagi setelah `load`).
2. **Peta "kembali ke posisi awal"** (zoom 3, seluruh dunia). Sebab:
   sisa bit NodeDB (`0.0016384`) dan nilai di luar rentang bumi lolos
   ke `fitBounds`. Solusi: `posisi_bersih()` di `lacak_node.py`
   menyaring kosong/`NaN`/luar rentang/sisa bit di sekitar (0,0) —
   dipakai penyimpan riwayat **dan** peta, sehingga satu titik sampah
   tidak bisa merusak tampilan lagi.
3. **Nama node hanya bisa dibaca setelah mengklik marker.** Solusi:
   `bindTooltip` permanen (`label-node`, `interactive:false` supaya
   tidak menghalangi klik), label naik saat disorot (`label-naik`),
   dan saklar "nama node" di legenda (`peta-tanpa-nama`, ingat per
   tab lewat `sessionStorage`). Popup kini juga memuat telemetri
   perangkat (Suhu °C, Kelembapan % RH, Tekanan hPa, Kanal %, Udara
   TX %) — baris hanya muncul bila node benar-benar mengirim angka
   itu. Satuan ditulis sebagai karakter sungguhan, bukan entitas HTML,
   karena nilai popup di-escape sekali lagi.

Bukti: `uji-layar-lokal.py` → **SEMUA LULUS** (4 node sah dipetakan,
4 titik sampah tersaring, label + saklar + telemetri ada di HTML);
`node --check` lulus untuk ketiga skrip; live: `/peta` menampilkan
**97 label nama** (mis. `[B-68]MTL|CBT|ROUTER`), saklar berfungsi
(dicoba nyala/mati di peramban), popup gateway memuat `Kanal =
13.2%`, `Udara TX = 6.8%`, `Uptime = 3j 5m`. Rollback: salin kembali
`*.sebelum-layar-20261001-203513` lalu `sudo systemctl restart
meshtastic-exporter`.

**Nama node di peta Tracking (1 Okt 2026, 20:52 WIB).** Halaman
detail `/lacak/<id>` (peta riwayat + playback) kini menampilkan nama
node di dua tempat, sehingga halaman tetap jelas milik node mana
meski dibuka dari tautan/bookmark:

1. **Balon di atas marker posisi** (tooltip permanen, kelas
   `balon`): baris pertama nama node (`b-nama`), lalu waktu dan
   kecepatan. Sebelumnya balon hanya menampilkan waktu + kecepatan.
2. **Popup titik singgah**: diawali identitas node (`pop-judul` =
   nama, `pop-id` = ID node), baru label waktu + koordinat. Sebelumnya
   popup hanya berisi label waktu.

Sebab: `JS_LACAK` menyusun balon dan popup tanpa memakai
`DATA.nama`. Solusi: `const NAMA_NODE = escHtml(DATA.nama ||
DATA.node_id)` di awal skrip, lalu disisipkan ke
`marker.setTooltipContent(...)` (balon) dan `bindPopup(...)` (titik
singgah). **Nama node berasal dari perangkat (tak tepercaya)** —
wajib lewat `escHtml` sebelum masuk HTML; label waktu berasal dari
server (aman). Daftar `/lacak` sendiri sudah menampilkan nama
(kolom "Nama & Perangkat") sejak awal, jadi tidak diubah.

Bukti: `node --check` lulus; `uji-layar-lokal.py` → **SEMUA LULUS**
(cek baru untuk `/lacak/<id>`: balon berisi nama, popup diawali
nama + ID); live: `/lacak/!06f64024` balon memuat *"Reza Nursaid ·
01 Okt, 20.54 · 29.2 km/j"* dan popup titik singgah diawali
*"Reza Nursaid / !06f64024"*. Deploy lewat `pasang-perbaikan-layar.sh`
(layanan `active`). Rollback: salin kembali
`*.sebelum-layar-20261001-205221` lalu `sudo systemctl restart
meshtastic-exporter`.

**Garis rute rapi untuk riwayat lama (1 Okt 2026, 23:15 WIB).**
Tracking node n14b (`!0ec92128`) dan n15b (`!8f4b7a80`) masih
memuat lompatan ~12.493 km karena rutenya mengandung **sisa bit**
`[0.026214, 0.026214]` dan `[0.001638, 0.001638]` (dekat "Null
Island") — garis menyebrang peta dan `bounds` ikut rusak. Akar
sebab: `posisi_bersih()` hanya dipakai **saat menulis**
(`catat_snapshot`), sementara jalur baca `Penyimpan.titik()` hanya
menyaring `lat/lon is None`, sehingga baris yang tersimpan **sebelum
perbaikan 28 Sep** lolos mentah ke `paket_node` → `susun_lacak` →
`DATA.route`. Solusi: `posisi_bersih()` kini juga dipakai di jalur
baca — di `Penyimpan.titik()` (satu-satunya jalur keluar SQLite,
jadi route/stops/legs/bounds/stats semuanya bersih) dan di
`susun_lacak()` (pertahanan kedua bila pemanggil menyerahkan titik
mentah). Penyaringan ini idempotent, jadi titik yang sudah bersih
tidak berubah. **Lompatan jauh sengaja tidak disaring**: lompatan
39 km n15b adalah data perangkat antara dua koordinat nyata Jawa
Timur (Probolinggo ↔ Pasuruan); menyaring berdasarkan kecepatan
berisiko menghapus perjalanan nyata (mis. Reza Nursaid 7,7 km dalam
9 menit ≈ 52 km/j).

Bukti: `uji-layar-lokal.py` diperluas — menyuntik 7 baris "lama"
langsung ke SQLite (3 titik sah diselipi 2 sisa bit untuk `!c483e00a`;
2 titik Jakarta→Padang ≈922 km untuk `!0f1e2d3c`) → **SEMUA LULUS**
(rute 3 titik tanpa Null Island, bounds utuh, kaki < 200 m; lompatan
922 km tetap utuh). `py_compile` lulus; `uji-halaman-meshtastic.py`
187/187; `uji-bersih-node.py` 61/61. Live: `/lacak/!0ec92128.json`
19 titik, **0 titik Null Island**, lompatan maks 0 m (node diam);
`/lacak/!8f4b7a80.json` 37 titik, **0 Null Island**, bounds
`[[-8.179, 112.579], [-7.827, 112.617]]` — tidak ada lagi segmen
12.493 km. Deploy lewat `pasang-perbaikan-layar.sh` (impor OK,
layanan `active`). Rollback: salin kembali
`*.sebelum-layar-20261001-231546` lalu `sudo systemctl restart
meshtastic-exporter`.

---

### 5.14 `meshbot.clusternet.my.id` — dasbor bot di host yang sama (3 Okt 2026)

> **SEKARANG SUDAH DICABUT** — seluruh isi seksi ini adalah catatan riwayat.
> Rute, kartu dasbor, unit systemd, drop-in, dan kode bot dihapus pada hari yang
> sama; lihat **§5.15** untuk urutan rollback dan hasil verifikasinya.

**Permintaan:** memasang subdomain `meshbot.clusternet.my.id` untuk dasbor
`bot-meshtastic.py` (port 9209), berdampingan dengan `meshid` (exporter, 9208).

**Dua hal yang ditemukan sebelum menyentuh apa pun, keduanya menentukan
keputusan:**

1. **Port 9209 tidak mendengar apa pun** di host. Unit `meshtastic-bot.service`
hanya
   dipasang bila `MESH_PASANG_BOT=1`, dan pada 3 Okt 2026 unit itu memang belum
   terpasang — jadi menambah rute saja akan menghasilkan 502.
2. **Gateway Meshtastic hanya melayani SATU klien TCP**, dan klien itu sudah
   dipegang exporter. Bila bot ikut menyambung `192.168.20.31:4403`, keduanya
   saling mengusir — persis kegagalan senyap di §5.7 ("dua exporter berebut satu
   radio").

**Keputusan pemilik:** bot dijalankan **tanpa radio / mode MQTT**, dan subdomain
dilindungi **Cloudflare Access** (berbeda dengan `meshid` yang memang publik).
Keduanya tepat: tanpa radio tidak berebut klien, dan halaman bot memuat token
kendali yang bisa membungkam bot atau mengubah balasan yang naik ke udara.

**Yang diubah di repo:**

| Berkas | Perubahan |
| --- | --- |
| `bot-meshtastic.py` | dua lingkungan baru: `BOT_TANPA_RADIO` (sama dengan `--tanpa-radio`, supaya unit systemd tidak perlu mengubah `ExecStart`) dan `BOT_KENDALI_HOST` (daftar nama domain yang boleh memakai tombol/form). `_host_lokal()` kini menerima daftar izin — tanpa daftar, penjaga anti-DNS-rebinding tidak berubah sama sekali |
| `meshtastic-bot.service` | dokumentasi dua lingkungan baru (dalam komentar) |
| `pasang-layanan.sh` | fungsi `pasang_dropin_bot()` menulis drop-in `meshtastic-bot.service.d/mqtt.conf` — terpisah dari unit supaya tidak tertimpa penerapan kode berikutnya. Tiga keadaan seperti timer: `1` pasang, `0` cabut, tidak disebut = biarkan |
| `pasang-ke-zima.sh` | meneruskan `MESH_BOT_TANPA_RADIO`, `MESH_BOT_KENDALI_HOST`, `MESH_MQTT_HOST/PORT/ROOT` ke host (`sudo` mereset lingkungan, jadi harus lewat `sudo env`) |
| `zima-hosting/Caddyfile` | blok `http://meshbot.clusternet.my.id` → `192.168.20.36:9209` |
| `zima-hosting/situs/layanan.json`, `panel-kelola.html` | kartu **Meshbot** + entri panel (tanpa ini panel akan menghasilkan Caddyfile tanpa rute `meshbot`) |
| `zima-hosting/PANDUAN-WEBHOSTING.md` | baris tabel layanan + `meshbot` ditambahkan ke daftar Cloudflare Access |
| `README.md` | tabel dua lingkungan baru + bagian pemasangan `meshbot` |
| `uji-bot-meshtastic.py` | bagian **12c** (13 pemeriksaan): bawaan aman, daftar izin menolak subdomain & akhiran yang menempel, tanpa daftar penjaga lama tetap berlaku, POST HTTP betulan diterima hanya untuk nama yang diizinkan, `BOT_TANPA_RADIO` dibaca saat modul dimuat |

**Alur pemasangan (belum dijalankan pada 3 Okt 2026 — membutuhkan sandi
akun ZimaOS):**

```bash
MESH_PASANG_BOT=1 \
MESH_BOT_TANPA_RADIO=1 \
MESH_BOT_KENDALI_HOST=meshbot.clusternet.my.id \
ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/pasang-ke-zima.sh
```

**Sudah dijalankan dan terbukti (3 Okt 2026):**

- `node validasi-hosting.mjs` → **82 lolos, 0 gagal** (naik dari 80: hostname
  `meshbot` wajib disebut di panduan, dan kartu `layanan.json` wajib punya rute).
- Caddyfile dikirim lewat deployer `:8791` → `HTTP 200 … web-router sudah
  restart dan sehat` (deployer menjalankan `caddy validate` dulu dan memulihkan
  sendiri bila gagal).
- Uji seluruh rute (13 hostname) → semua angka sama seperti sebelumnya;
  `meshbot` = **502** karena `:9209` masih kosong.
- `uji-bot-meshtastic.py` → **171 lulus, 0 gagal** (dari 158),
  `uji-simulasi-bot.py` 13/0, `uji-bot-tanpa-radio.py` 21/0,
  `uji-eksportir-simulasi.py` 14/0, `jalankan-dasbor-simulasi.py --uji-diri` 11/0.

**Sudah dijalankan (3 Okt 2026, sesi pemasangan):**

- `pasang-ke-zima.sh` dengan `MESH_PASANG_BOT=1 MESH_BOT_TANPA_RADIO=1` →
  unit `meshtastic-bot` **active** bersama `meshtastic-exporter` dan
  `meshtastic-notif`; drop-in memuat `BOT_TANPA_RADIO=1` dan
  `BOT_KENDALI_HOST=meshbot.clusternet.my.id`.
- Rute `meshbot` **502 → 200** (diuji lewat router `192.168.20.36:8089` DAN
  lewat `https://meshbot.clusternet.my.id`); `meshid` tetap 200.
- `/data.json` publik melaporkan `sumber = "tanpa radio (MQTT saja)"`,
  metrik `meshtastic_bot_tanpa_radio 1.0`.
- Kartu **Meshbot** diterbitkan lewat `terbitkan-dasbor.ps1` → manifest 9 kartu.

**Masalah yang ditemukan sesudahnya: broker menolak klien anonim.**
Gejala: log bot berulang `MQTT tersambung, langganan: msh/ID/2/json/#` lalu
`MQTT terputus` tiap beberapa detik; `mqtt.terhubung = false`; 0 pesan masuk.
Probe langsung ke `mqtt.meshnode.id:1883` **dan** `:8883` menghasilkan rc
`Not authorized` dari dua mesin berbeda — bukan jaringan, dan bukan duplikasi
`client_id` (id bot sudah `hostname+pid`). Penyebab: di mode `--tanpa-radio`
bot tidak pernah membaca modul MQTT gateway (di situlah username/password
tersimpan), jadi menyambung tanpa nama. Laporan "tersambung" yang berulang itu
sendiri adalah **bug**: paho memanggil `on_connect` walau CONNACK gagal, dan
callback tidak memeriksa rc.

**Perbaikan (3 Okt 2026):**

| Berkas | Perubahan |
| --- | --- |
| `bot-meshtastic.py` | `saat_mqtt_terhubung` memeriksa rc SEBELUM melaporkan "tersambung"; tanpa username dicetak petunjuk menjalankan skrip di bawah |
| `baca-mqtt-gateway.py` | **baru** — baca modul MQTT gateway (hanya baca, tidak pernah menulis konfigurasi node) lalu tulis drop-in `broker.conf` + `broker.env`. Memakai `EnvironmentFile=` (bukan `Environment=`) supaya `%` di dalam sandi tidak disalahartikan spesifier systemd; sandi berspasi/kutip dikutip & diescape; `--uji-diri` 11 pemeriksaan |
| `uji-bot-meshtastic.py` | bagian **16**: rc ditolak (gaya v2 `Not authorized`, gaya v1 int ≠ 0) tidak pernah menghasilkan "tersambung"/langganan; rc sukses tetap persis seperti biasa → **174 lulus, 0 gagal** |

Prosedur di host — **exporter dihentikan dulu** (gateway satu klien TCP):

```bash
sudo systemctl stop meshtastic-exporter
sudo /DATA/AppData/meshtastic-monitor/venv/bin/python \
  /DATA/AppData/meshtastic-monitor/baca-mqtt-gateway.py \
  --dropin /etc/systemd/system/meshtastic-bot.service.d
sudo systemctl daemon-reload && sudo systemctl restart meshtastic-bot
sudo systemctl start meshtastic-exporter
```

Berkas `broker.*` sengaja terpisah dari `mqtt.conf` (ditulis
`pasang-layanan.sh`) supaya pemasangan ulang tidak menghapus kredensial;
`pasang_dropin_bot … 0` (cabut mode tanpa radio) menghapus seluruh direktori
`drop-in`, termasuk berkas ini — pemasangan ulang perlu membacanya lagi.

**Sisa pekerjaan:**

1. Jalankan prosedur kredensial di atas, lalu pastikan
   `mqtt.terhubung = true` dan `mqtt.pesan_terakhir` terisi di
   `https://meshbot.clusternet.my.id/data.json`.
2. **Cloudflare Access** untuk `meshbot.clusternet.my.id` di Zero Trust →
   Access → Applications → Self-hosted → Allow (email Anda). Tanpa ini
   siapa pun yang membuka subdomain memperoleh token kendali.

**Rollback rute:** kembalikan `zima-hosting/Caddyfile` (hapus blok `meshbot`)
lalu kirim ulang lewat deployer; cadangan otomatis tersimpan di
`/data/.Caddyfile.bak` di dalam container `zima-deployer`. Rollback layanan:
`sudo systemctl disable --now meshtastic-bot`.

---

### 5.15 Rollback: seluruh bot dicabut (3 Okt 2026)

**Permintaan:** "hilangkan semua yang berkaitan dengan bot" — pencopotan penuh,
dari deploy di host sampai kode lokal; membatalkan §5.14 (termasuk percobaan
`--json-aktif` yang mentok di penolakan firmware).

**Yang dicabut di host ZimaOS:**

| Yang | Keadaan sesudah dicabut |
| --- | --- |
| `meshtastic-bot.service` | `disable --now`; file unit + drop-in `meshtastic-bot.service.d/` (`mqtt.conf`, `broker.conf`, `broker.env`) dihapus, lalu `daemon-reload` → `is-active = inactive`, `is-enabled = not-found` |
| Port 9209 | tertutup (`ss -ltn` tidak lagi menampilkannya) |
| Berkas bot di `/DATA/AppData/meshtastic-monitor/` | `bot-meshtastic.py` (+ `.bak-*`), `uji-bot-*`, `uji-simulasi-bot.py`, `jalankan-dasbor-simulasi.py`, `baca-mqtt-gateway.py`, `meshtastic-bot.service` dihapus; **state lama diarsipkan** ke `/DATA/AppData/cadangan-bot-2026-10-03.tar.gz` |
| Rute Caddy | blok `http://meshbot.clusternet.my.id` dihapus dari `zima-hosting/Caddyfile`, deploy ulang lewat deployer (200, `web-router` sehat) |
| Kartu dasbor | kartu Meshbot dihapus dari `layanan.json` lokal lalu diterbitkan ulang dengan `terbitkan-dasbor.ps1` → manifest **8 kartu** |

**Yang dicabut di repo:**

- Kode: `bot-meshtastic.py`, `uji-bot-meshtastic.py`, `uji-bot-tanpa-radio.py`,
  `uji-simulasi-bot.py`, `jalankan-dasbor-simulasi.py`, `baca-mqtt-gateway.py`,
  `meshtastic-bot.service`, `bot-meshtastic-state*.json`.
- `NodeSimulasi` **diselamatkan** ke modul baru `simulasi-node.py` supaya
  `uji-eksportir-simulasi.py` (halaman exporter :9208 tanpa hardware) tetap
  berfungsi; pemuatannya dipindah dari `uji-simulasi-bot.py`.
- `pasang-layanan.sh`: opsi `MESH_PASANG_BOT`, fungsi `pasang_dropin_bot()`,
  blok enable/restart/status/summary bot, dan pemeriksaan dependensi
  `paho-mqtt` dihapus. `pasang-ke-zima.sh`: penerusan
  `MESH_PASANG_BOT`/`MESH_BOT_*`/`MESH_MQTT_*` dan pengecualian artefak
  `*kontak.json`/`*kendali.json` dihapus.
- `alert-meshtastic.yml`: lima aturan `MeshtasticBot*` dihapus.
  `prometheus-contoh.yml`: job `meshtastic-bot` dihapus. `requirements.txt`:
  `paho-mqtt` dihapus (tak ada lagi yang memakainya).
- `zima-hosting`: entri panel `Meshtastic Bot`, baris tabel + daftar Cloudflare
  Access di `PANDUAN-WEBHOSTING.md`, kartu `Meshbot` di `layanan.json`.
- `meshtastic-monitor/README.md`: bab `## Bot: deteksi node LoRa + balas
  otomatis` (± 750 baris) dan bagian `Lapis ketiga: broker MQTT (bot)` dihapus;
  tersisa seksi `## Uji tanpa radio: node simulasi + penyuntik paket` yang hanya
  memuat jalur exporter.

**Verifikasi (3 Okt 2026):**

- Rute lewat router `192.168.20.36:8089`: `meshbot` = **404** (wildcard),
  `meshid` = **200**, rute lain persis seperti sebelumnya (adguard/grafana/kuma
  = 302, `tes-acak123` = 404). Catatan: `udara`/`aqi` = 502 karena perangkat
  ESP32 `192.168.20.13` sedang tidak terjangkau — di luar rollback ini.
- `https://clusternet.my.id/layanan.json` = **8 kartu**, tanpa Meshbot
  (cadangan `layanan.json.bak-*` ikut dibuat).
- `node validasi-hosting.mjs` = **Lolos 80 | GAGAL 0**;
  `uji-eksportir-simulasi.py` = **14 lulus, 0 gagal** dengan `simulasi-node.py`.

**Bila ingin memasang lagi:** ikuti riwayat §5.14 — tetapi berkasnya sudah
terhapus semua, dan `meshtastic-monitor/` tidak di-git, jadi salinannya harus
diambil dari riwayat kerja sebelum 3 Okt 2026.

---

## 6. Yang belum selesai / sengaja ditunda

| Hal | Keadaan | Kalau ingin dilanjutkan |
| --- | --- | --- |
| Prometheus/Grafana ZimaOS | **sudah** mengambil metrik Mesh ID (job `meshtastic`, dasbor uid `meshtastic-node`, 13 aturan) — lihat §5.13 | biarkan; bila ingin alarm dikirim ke ponsel, sambungkan Alertmanager atau Uptime Kuma ke topik ntfy |
| Alertmanager | **tidak dipasang** (aturan sudah berjalan, tetapi hanya terlihat di Prometheus/Grafana) | tambahkan container Alertmanager, arahkan `alerting:` Prometheus ke sana, sambungkan ke ntfy lewat webhook |
| Penandaan Favorite otomatis | penjaga Windows **dinonaktifkan**, jadi belum ada yang otomatis | buat systemd timer di ZimaOS yang menjalankan `favorite-node.py --ya`, pola sama dengan `udara/pasang-notif-udara.sh` |
| Timer reset NodeDB | **tidak dipasang** (sengaja: reset menghapus semua Favorite) | `MESH_PASANG_TIMER=1 sudo sh /DATA/AppData/meshtastic-monitor/pasang-layanan.sh` |
| Cloudflare Access | tidak dipakai (keputusan pemilik) | Zero Trust → Access → tambahkan hostname `meshid.clusternet.my.id` |
| ntfy cadangan LAN | `http://192.168.200.253:7200` **mati** (connection refused) | biarkan; jalur utama `ntfy.adminforge.de` sudah cukup |
| Uptime Kuma | monitor untuk `meshid.clusternet.my.id` belum ada | tambahkan HTTP monitor; monitor baru otomatis masuk halaman status lewat `sinkron-status-kuma.timer` |
| `zima-deployer` | build-nya lebih tua dari repo (tanpa dukungan `layanan`) | perbarui image deployer, lalu panel bisa menerbitkan kartu dasbor sendiri |

---

## 7. Keadaan perangkat pada 28 Sep 2026 (untuk pembanding)

| Hal | Nilai |
| --- | --- |
| Gateway | `192.168.20.31:4403`, `!8f4c1354` `[B-75]MTL|CBT|HOME`, SEEED_XIAO_S3, role CLIENT |
| Firmware | `2.7.15.567b8ea`, `reboot_count` 46 |
| Isi NodeDB | 116 entri (107 di antaranya jalur MQTT) — sempat 200 → 6 → naik lagi |
| Node jalur radio | 9, di antaranya **3 terbukti langsung** (SNR terisi: 5.0 / 6.25 / 6.5 dB) |
| Pemantauan gateway | `NOTIF_BASI_GW=180`, `NOTIF_ABSEN_GW=2` — tiga sebab mati dibedakan |
| Downlink MQTT kanal 0 | **hidup** (sengaja; ini gerbang masuk node internet) |
| Kanal ntfy | `https://ntfy.adminforge.de`; topik penting `mesh-penting-2kevnee56c4`, topik rutin `mesh-6h4v8p2rxq` |
| Verifikasi akhir | publik **200**, `meshtastic_exporter_up 1.0`, `validasi-hosting.mjs` **Lolos 80 | GAGAL 0** |
| Grafana | dasbor `meshtastic-node` (23 panel, 0 kosong), job `meshtastic` 1.418 seri, 13 aturan Prometheus |

Catatan lapangan dari hari itu: notifier sempat mengabarkan
`Node Meshtastic OFFLINE: [B-68]MTL|CBT|ROUTER` (00:54). Node ROUTER memang
jarang memancar; ambang offline 3 jam (`MESH_OFFLINE_SECS=10800`) sudah dipilih
untuk keperluan itu. Bila alarm ini sering muncul, perpanjang ambangnya
(lihat `catat-node.py` untuk kalibrasi).

---

## 8. Kalau ada masalah: gejala → periksa apa

| Gejala | Yang diperiksa lebih dulu |
| --- | --- |
| Halaman publik 502 | `systemctl status meshtastic-exporter` di host; `curl 127.0.0.1:9208/` di host |
| Halaman publik 404 "belum dipetakan" | blok `meshid` hilang/tergeser dari Caddyfile → `docker logs web-router`, terapkan ulang |
| Halaman publik 1033 / DNS | tunnel/DNS Cloudflare; `docker logs cf-tunnel`, cari "Registered tunnel connection" |
| Halaman terbuka tetapi datanya beku | koneksi ke gateway: `journalctl -u meshtastic-exporter` cari "koneksi ke node gagal" |
| Data segar tetapi tidak ada alarm | kanal ntfy (429 / jawaban server), lihat §5.1 |
| Alarm yang sama berulang | pengiriman gagal sistematis, lihat §5.1 |
| `zima-shell.mjs` → `[ws error]` | ttyd sibuk; tunggu & tutup sesi lama (§3.1) |
| Rute ZimaOS lain ikut mati setelah deploy | perbedaan alamat `192.168.145.252` vs `192.168.20.36`, lihat §5.5 |
| Panel Grafana Mesh ID kosong | datasource `prom-mikrotik` menunjuk `172.17.0.1:9090`; jalankan `terbitkan-dasbor-grafana.py --periksa` **di host** untuk tahu kueri mana yang hampa |
| Prometheus tidak mau start setelah menyunting `prometheus.yml` | `rule_files` ditulis tanpa volume mount → Docker membuat direktori kosong; periksa `docker logs mikrotik-prometheus` |
| Aturan Mesh ID tidak pernah berbunyi | job `meshtastic` benar-benar `up`? kalau exporter mati, aturan berbasis data tidak bisa menilai |

---

## 9. Rollback

**Mengembalikan exporter ke mesin Windows** (mis. host ZimaOS diperbaiki):

```bash
# di mesin Windows
cmd //c meshtastic-monitor/mulai-layanan.bat          # nyalakan lagi
powershell -Command "Enable-ScheduledTask -TaskName 'Meshtastic Monitor'"   # butuh administrator
```

Lalu ubah rute agar menunjuk mesin itu (ganti `192.168.20.36:9208` menjadi
`192.168.20.59:9208` di `zima-hosting/Caddyfile`), `node validasi-hosting.mjs`,
terapkan lewat deployer seperti §4, dan **matikan** layanan ZimaOS:

```bash
sudo systemctl disable --now meshtastic-exporter meshtastic-notif
```

Menjalankan keduanya sekaligus **tidak disarankan**: dua notifier = alarm
kembar ke topik ntfy yang sama, dan dua klien TCP ke gateway.

**Mencopot subdomain saja:** hapus blok `meshid` dari Caddyfile, terapkan
ulang; selebihnya tidak perlu diubah (DNS/tunnel tidak pernah disentuh).

---

## 10. Berkas yang berkaitan

| Berkas | Isi |
| --- | --- |
| `meshtastic-monitor/README.md` | penjelasan fitur, variabel lingkungan, catatan kendala kode |
| `meshtastic-monitor/pasang-ke-zima.sh` | kirim + pasang ke host ZimaOS (butuh `ZIMA_PASS`) |
| `meshtastic-monitor/mulai-ulang-zima.sh` | restart unit di host ZimaOS tanpa mengunggah berkas (butuh `ZIMA_PASS`) |
| `meshtastic-monitor/pasang-layanan.sh` | pemasang unit systemd di host |
| `meshtastic-monitor/pasang-perbaikan-layar.sh` | unggah `exporter-meshtastic.py` + `lacak_halaman.py` + `lacak_node.py` ke host (cadangan `*.sebelum-layar-<stempel>`), restart + verifikasi `active` |
| `meshtastic-monitor/uji-layar-lokal.py` | uji render lokal halaman Monitoring/peta/daftar/tracking (termasuk balon nama & popup titik singgah) |
| `meshtastic-monitor/siapkan-logo.ps1` | pangkas pinggiran transparan + kecilkan logo jadi `meshnodeid-256.png` & `meshnodeid-64.png` |
| `meshtastic-monitor/meshnodeid-256.png`, `meshnodeid-64.png` | logo kepala halaman & ikon tab, dilayani exporter di `/logo.png` dan `/favicon.png` |
| `meshtastic-monitor/notif-meshtastic.py` | notifier ntfy (node offline/pulih, baterai, sinyal, kontak radio, gateway mati) |
| `meshtastic-monitor/uji-notif-meshtastic.py` | uji ujung-ke-ujung jalur exporter → deteksi → ntfy (51 langkah; termasuk kirim nyata ketiga jenis kabar ke topiknya masing-masing) |
| `meshtastic-monitor/meshtastic-notif.service` | unit systemd notifier (kanal + ambang, termasuk kontak radio & pemantauan gateway, dan dua topik ntfy) |
| `meshtastic-monitor/dashboard-grafana.json` | definisi dasbor Grafana (23 panel, uid `meshtastic-node`, datasource `${DS_PROMETHEUS}`) |
| `meshtastic-monitor/terbitkan-dasbor-grafana.py` | menerbitkan dasbor lewat API Grafana + `--periksa` tiap kueri panel |
| `meshtastic-monitor/alert-meshtastic.yml` | 13 aturan Prometheus (`promtool check rules`), termasuk `MeshtasticDataStale` |
| `meshtastic-monitor/prometheus-contoh.yml` | contoh potongan job scrape + `rule_files` untuk pemasangan di mesin lain |
| `uji-semua-ntfy.py` | uji semua kanal ntfy sekaligus (kini termasuk kedua topik Mesh ID) |
| `meshtastic-monitor/uji-halaman-meshtastic.py` | uji render halaman & metrik dengan data tiruan (aman dijalankan saat layanan hidup) |
| `meshtastic-monitor/favorite-node.py` | menandai node RF sebagai Favorite (periksa-saja tanpa `--ya`) |
| `meshtastic-monitor/reset-node.py` | reset NodeDB (periksa-saja tanpa `--ya`) |
| `meshtastic-monitor/bersih-node.py` | hapus satu per satu node yang lama tidak terdengar (periksa-saja tanpa `--ya`) |
| `meshtastic-monitor/uji-bersih-node.py` | uji aturan pemilihan node lama dengan gateway palsu (tanpa jaringan) |
| `meshtastic-monitor/meshtastic-bersih.service`, `meshtastic-bersih.timer` | jadwal harian 03:30 (`MESH_PASANG_BERSIH=1` saat memasang) |
| `zima-hosting/Caddyfile` | sumber rute nama domain (termasuk blok `meshid`) |
| `zima-hosting/PANDUAN-WEBHOSTING.md` | cara kerja tunnel + Caddy, tabel subdomain |
| `zima-hosting/panel-kelola.html` | panel visual: sunting rute & terapkan ke ZimaOS |
| `validasi-hosting.mjs` | pemeriksa konsistensi repo (offline, tanpa Docker) |
| `CATATAN-STUDI-MESHTASTIC-GITHUB.md` | peta seluruh organisasi GitHub `meshtastic` + usulan yang menyentuh Mesh ID |
| `studi-meshtastic-github.mjs` | alat pemeta organisasi `meshtastic` (baca-saja, tanpa token untuk pemakaian singkat) |
| `CATATAN-MESHNODEID.md` | catatan ini |

> Sandi akun ZimaOS dan token deployer **tidak** disimpan di repo. Token deployer
> ada di `zima-hosting/.env.deploy-token` (ikut `.gitignore`).
