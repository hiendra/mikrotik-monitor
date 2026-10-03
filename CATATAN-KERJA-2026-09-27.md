# Catatan Kerja — 27 Sep 2026

Jurnal satu hari kerja: **apa yang diubah, di mana, kenapa, dan bagaimana
memastikannya**. Dibuat supaya kendala berikutnya bisa ditelusuri cepat tanpa
mengulang penemuan hari ini. Untuk pola gejala → sebab → solusi, lihat
`CATATAN-KENDALA.md` (entri 11–13 diisi dari hari ini).

> Tidak ada sandi/token di berkas ini. Hanya **di mana** disimpan.

---

## 0. Ringkasan

Hari ini fokusnya **sensor kualitas udara (ESP32)**: memperbaiki alamat yang
salah, menampilkannya di Grafana dan di portal web, lalu memasang
**notifikasi ntfy** agar gangguan sensor sampai ke ponsel.

Empat pekerjaan utama:

1. **Perbaikan alamat sensor `.27` → `.13`** di dua tempat (exporter Prometheus
   dan datasource Grafana Infinity). Sensor sudah lama berpindah IP sehingga
   Grafana kosong.
2. **Portal publik** `udara.clusternet.my.id` / `aqi.clusternet.my.id` +
   **kartu dasbor** "Kualitas Udara".
3. **Paket notifikasi ntfy** `udara/` + systemd timer tiap 1 menit.
4. **Uji nyata ke ponsel** dan penetapan **adminforge sebagai kanal utama**,
   lalu **pembakuan format pesan 2 baris**.

Status akhir: Grafana terisi, portal 200, notifikasi uji & notifikasi nyata
terkirim, validator repo **Lolos 79 | GAGAL 0 | PERINGATAN 0**.

---

## 1. Peta cepat

| Bagian | Nilai |
|---|---|
| Sensor Air Quality | `http://192.168.20.13:88` (endpoint data: `/api/data`) |
| Exporter (bridge) | container `air-bridge` (python:3-alpine), ditulis sebagai base64 inline di compose |
| Prometheus kualitas udara | container `air-prometheus`, host port **9091** |
| Grafana datasource (Prometheus) | `Prometheus Air Quality`, uid `bfyhlidmwu2gwa` → `http://172.17.0.1:9091` |
| Grafana datasource (langsung) | `ESP32 Air Quality` (Infinity), uid `bfyhierx49ypsd` → `http://192.168.20.13:88` |
| Dasbor | uid `air-quality-clusternet` — "Air Quality - Cluster Taman Marina", 11 panel |
| Portal sensor | `https://udara.clusternet.my.id` (alias `aqi.clusternet.my.id`) |
| Notifikasi | systemd timer `notif-udara.timer` tiap 1 menit, topik `udara-xu64dtfks2ei` |
| Kanal ntfy | `https://ntfy.adminforge.de` (utama) → `https://ntfy.sh` → `http://192.168.200.253:7200` (LAN) |
| Loceng di host | `/DATA/AppData/udara/` (skrip, `keadaan.env`, `notif-udara.log`) |

Topik ntfy lain yang sudah ada sebelumnya (jangan dicampur):
`rt-7k2m9dx4q8wf` (router), `kuma-7m3xq9dt2v` (Uptime Kuma).

---

## 2. Kronologi pekerjaan

### 2.1 Perbaikan alamat sensor `.27` → `.13`

**Masalah.** Datasource Grafana dan exporter sama-sama menunjuk
`192.168.20.27`, padahal lease statik sensor (MAC `F4:CF:A2:D9:C8:31`) sudah
dikunci ke **`.13`**. Tidak ada lease `.27`, ARP `.27` kosong, port `.27:88`
tertutup → Grafana kosong.

**Yang dikerjakan.**

- Datasource **Infinity** `ESP32 Air Quality`: url `.27` → `.13`,
  **Save & test → Health check OK**.
- Container **`air-bridge`**: skrip Python disimpan sebagai **base64 inline**
  di `entrypoint` pada `/var/lib/casaos/apps/air-quality/docker-compose.yml`.
  Variabel `ESP = "http://192.168.20.27:88/api/data"` diganti `.13`.
  Cadangan dibuat: `docker-compose.yml.bak-air-2026-09-27-2035`, lalu
  `docker compose up -d`.

**Verifikasi.** `air_up=1`, semua metrik sensor muncul, dasbor terisi
(32.5 °C, 47.8 %, 20.0 °C, eCO2 400 ppm, TVOC 0, AQI 1).

### 2.2 Portal subdomain + kartu dasbor

- Blok baru di **Caddyfile LIVE** `/DATA/AppData/zima-hosting/Caddyfile`
  (baris ~152–157, **sebelum** wildcard `*.clusternet.my.id`):

  ```caddy
  http://udara.clusternet.my.id, http://aqi.clusternet.my.id {
      import http-umum
      reverse_proxy 192.168.20.13:88
  }
  ```

  Cadangan: `Caddyfile.bak-udara-*`. `caddy validate` → Valid, lalu
  `docker restart web-router`.
- Verifikasi: LAN (Host header via port 8089) **dan** publik HTTPS → **200**,
  judul "Air Quality Monitor". Tidak ada regresi pada clusternet/grafana/kuma/
  zima/adguard/immich/billing.
- **Repo disamakan:** `zima-hosting/Caddyfile`,
  `zima-hosting/PANDUAN-WEBHOSTING.md` (baris tabel subdomain),
  `zima-hosting/panel-kelola.html` (entri "Air Quality Monitor (ESP32)",
  host `udara...`+`aqi...`, target `192.168.20.13:88`, access false).
- **Kartu dasbor** "Kualitas Udara": `zima-hosting/situs/layanan.json`
  ditambah entri (kini **7 kartu**), dan tiga berkas skema baru di-deploy ke
  live: `index.html`, `dasbor.js`, `layanan.json`.

Verifikasi kartu: `/` 200 memuat `dasbor.js`, `/dasbor.js` 200,
`/layanan.json` 200 berisi 7 kartu; pohon aksesibilitas menampilkan link
"Kualitas Udara AKTIF udara.clusternet.my.id".

### 2.3 Paket notifikasi ntfy sensor udara (`udara/`)

Berkas baru: `udara/notif-udara.sh`, `udara/pasang-notif-udara.sh`,
`udara/README.md` (+ 3 baris di `README.md` root).

Aturan notifikasi (hanya berbunyi saat ada **perubahan nyata**, bukan tiap menit):

| Kejadian | Judul | Prio · ikon |
|---|---|---|
| Tidak ada data > **300 s** | `Sensor kualitas udara MATI` | 4 · 🔴 |
| Data kembali | `Sensor kualitas udara PULIH` | 3 · 🟢 |
| AQI ≥ **3** dan makin naik | `Kualitas udara memburuk: AQI N (Status)` | 3 (4 bila AQI ≥ 4) · ⚠️ |
| AQI kembali < 3 | `Kualitas udara normal kembali: AQI N (Status)` | 3 · 🟢 |

Detail teknis penting:

- Pengiriman lewat **publikasi JSON** (`jq -n` + `curl -d`), topik jadi bagian
  URL sehingga tetap berfungsi sebagai "kata sandi". `priority` **wajib angka**.
- **Multi-kanal**: `for _s in $SERVERS` — **berhenti di kanal pertama yang
  berhasil**, jadi satu kejadian = satu pesan (tidak ada pesan kembar).
  Log mencatat `ntfy terkirim via <server>` / `ntfy gagal via <server>` /
  `ntfy GAGAL di semua kanal`.
- Keadaan disimpan di `/DATA/AppData/udara/keadaan.env`
  (`terakhir_sukses`, `mati_dilaporkan`) sehingga pesan sama tidak diulang.
- Log dirotasi ~1000 baris, dengan guard `-w` supaya aman dijalankan non-root
  (mis. untuk `status`).
- **Kenapa ambang 5 menit?** Sensor menyala ulang sporadis: dari
  `air_uptime_seconds`, terukur **2 restart dalam 42 menit** awal pengamatan
  (20:41:40 uptime 1794 s → 8 s; 20:58:40 969 s → 48 s), lalu stabil >20 menit.
  Ambang 5 menit melewati mati-singkat itu tapi tetap menangkap kerusakan nyata.

Pemasangan: systemd `notif-udara.service` + `notif-udara.timer`
(`OnCalendar=*:*:00`, `AccuracySec=5s`) — ZimaOS **tanpa cron**, jadi timer
systemd adalah penggantinya (preseden: `sinkron-status-kuma.timer`).
Skrip + keadaan di `/DATA/AppData/udara/`.

### 2.4 Uji ke ponsel & penetapan kanal utama

- Uji ke **adminforge** (kode `Z54FYM`) → HTTP 200, terbaca ulang. **Tidak**
  muncul di ntfy.sh. **User mengonfirmasi notifikasi muncul sendiri di ponsel.**
- Uji ke **ntfy.sh** (`SIJHAV`, `EAQXIH`) → 200 & terbaca; user mengonfirmasi
  `EAQXIH` muncul (langganan ntfy.sh ditambahkan user).
- **Keputusan user: adminforge tetap kanal utama** (sama dengan MikroTik/Kuma).
  `SERVERS` disetel `adminforge ntfy.sh LAN`, diunggah, dan uji 21:43:35
  terkirim ke **adminforge** dengan ntfy.sh **kosong** (tidak dobel).
- `https://ntfy.clusternet.my.id` masih **404** (blok ntfy belum ada di Caddyfile
  live) — tidak dipakai. Belakangan opsi ntfy self-hosted ini **dilepas**
  (lihat §2.7 dan `zima-hosting/CATATAN-KENDALA.md` entri 13).

### 2.5 Pembakuan format pesan 2 baris

Sebelumnya pesan AQI hanya satu baris angka. Diganti jadi **dua baris**:

```
Suhu 32.40 C, RH 47.32 %, eCO2 751 ppm, TVOC 249 ppb
Cluster Taman Marina - Metland Cibitung . dibaca 2026-09-27 21:51:30
```

Baris 2 diambil dari field `lokasi` dan `waktu` pada `/api/data`. Newline
ditulis apa adanya di dalam kutip ganda (aman karena pesan dikirim sebagai
argumen `jq --arg`, bukan lewat `printf`).

Verifikasi akhir: `sh -n` OK, render langsung dari data sensor benar,
**MD5 lokal = MD5 di host** (`5a43fa37f24e467874f48bdd36c285d8`), dan
**notifikasi nyata 21:50:02** (`Kualitas udara memburuk: AQI 3 (Sedang)`)
terkirim via adminforge sudah memakai format baru. `udara/README.md` diperbarui.

### 2.6 Aktivitas lain bertanggal 27 Sep (di luar alur sensor udara)

Agar jurnal satu hari ini lengkap, berikut pekerjaan lain yang juga tercatat
bertanggal 27 Sep 2026 — detailnya ada di `CATATAN-KENDALA.md`, tidak diulang
lagi di sini:

| Topik | Rujukan |
|---|---|
| Batasi service API MikroTik + audit billing ↔ MikroTik | entri 5 |
| Notifikasi router (ntfy) jadi multi-kanal (server utama → ulang → LAN) | entri 6 |
| Perbaiki notifikasi terkirim dua kali (Netwatch tidak boleh ditulis dari skrip) | entri 7 |
| Inspeksi menyeluruh MikroTik `192.168.200.1` | `INSPEKSI-MIKROTIK-200-1.md` |
| Notifikasi Uptime Kuma → ntfy (topik terpisah `kuma-7m3xq9dt2v`) | entri 9, `PANDUAN-KUMA-NTFY.md` |

### 2.7 Panel pengelola hosting: alamat tetap + satu ketidakcocokan diperbaiki

Dipicu pertanyaan "kenapa `http://127.0.0.1:65505/panel-kelola.html` tidak bisa
dibuka". Hasil pemeriksaan:

- **Tidak ada apa pun di port itu.** `curl` → HTTP 000 (ditolak), `netstat` di
  PC kosong untuk semua port `655xx`, dan `grep 65505` di seluruh repo → **nol
  hasil**. `ss` di host ZimaOS juga tidak menemukan `65505` maupun `53527`.
- Yang benar: `127.0.0.1` menunjuk ke **PC sendiri**, bukan ZimaOS. Fitur
  preview editor memakai **port acak yang berganti tiap sesi** (pagi ini
  65505, lalu 53527) — jadi tautan `http://127.0.0.1:<port>/...` selalu cepat
  basi. `panel-kelola.html` sendiri **tidak butuh server**: ia berkas statis
  mandiri dan bisa dibuka dengan klik dua kali (`file://`).
- **Perbaikan permanen:** ditambah `buka-panel.mjs` — server statis kecil untuk
  folder `zima-hosting/` pada **port tetap 8788**, lalu membuka browsernya.
  Tanpa admin, tanpa Docker. Sudah diuji: `/panel-kelola.html` 200,
  `/` → 302, berkas sah 200, berkas tak ada 404, dan percobaan keluar folder
  (`%2e%2e%2f`) ditolak **403**.
- **Ketidakcocokan yang ikut ditemukan & diperbaiki:** entri "Air Quality
  Monitor (ESP32)" di panel masih `dasbor: false`, padahal `situs/layanan.json`
  LIVE sudah memuat kartu "Kualitas Udara". Menekan **Terapkan ke ZimaOS** akan
  **menghapus kartu itu** (7 → 6). Sudah disetel `dasbor: true`; panel kini
  melaporkan "7 kartu di dasbor", cocok dengan yang live.

> **Tindak lanjut (SUDAH SELESAI).** Pertanyaan lanjutan pemilik: "apakah
> `ntfy.clusternet.my.id` perlu untuk menjalankan notifikasi?" — jawabannya
> **tidak**. Pemeriksaan ulang di host membuktikan seluruh rantainya sudah mati:
> Caddyfile LIVE memang tidak punya blok ntfy, container `ntfy` dari compose ini
> tidak ada, dan aplikasi ntfy CasaOS (`big-bear-ntfy-app-1`) sudah di-uninstall
> pemilik (`Exited`). Karena notifikasi nyata berjalan lewat layanan publik
> (`ntfy.adminforge.de` utama, `ntfy.sh` cadangan, LAN `192.168.200.253:7200`),
> seluruh opsi ntfy self-hosted **dicopot** dari repo (Caddyfile, compose, panel,
> panduan) beserta `ntfy-pasang.sh`, `ntfy-uji.sh`, dan `PANDUAN-NTFY-IPHONE.md`.
> Rinciannya di `zima-hosting/CATATAN-KENDALA.md` entri 13.

### 2.8 Penguji semua kanal ntfy (`uji-semua-ntfy.py`)

Permintaan pemilik: "buat test semua notif di ntfy". Dibuat skrip baru di akar
repo yang menguji **semua** kanal sekaligus dalam satu perintah: router MikroTik,
Uptime Kuma, dan sensor udara × server utama (`ntfy.adminforge.de`), cadangan
(`ntfy.sh`), dan LAN lokal (`192.168.200.253:7200`). Untuk tiap kanal skrip
membaca topik, menulis satu probe berlabel `UJI`, lalu membacanya kembali.

- Kanal "wajib" (adminforge) menentukan kode keluar; kanal cadangan/LAN hanya
  informasi, karena LAN memang hanya hidup di jaringan lokal.
- Opsi: `--json`, `--hanya KATA`, `--jam N`, `--tanpa-kirim`, `--semua-wajib`.
- Melengkapi penguji lama: `uji-ntfy.py` (lewat router nyata) dan
  `zima-hosting/uji-kuma-ntfy.py` (pesan asli dari Kuma).

**Hasil nyata 27 Sep 2026:** **5/7 LULUS** — semua kanal wajib lulus; yang gagal
adalah dua kanal LAN lokal, konsisten dengan lepasnya ntfy lokal (entri 13).

---

## 3. Jejak perubahan berkas

**Repo (semua belum di-commit — sesuai kebiasaan kerja):**

| Berkas | Perubahan |
|---|---|
| `udara/notif-udara.sh` | paket notifikasi (multi-kanal, format 2 baris) |
| `udara/pasang-notif-udara.sh` | pemasang systemd idempoten |
| `udara/README.md` | dokumentasi kanal, topik, uji, ambang, jebakan |
| `README.md` | +3 baris menunjuk paket `udara/` |
| `zima-hosting/Caddyfile` | blok `udara`/`aqi` |
| `zima-hosting/PANDUAN-WEBHOSTING.md` | baris tabel subdomain + cara membuka panel & peringatan port preview |
| `zima-hosting/panel-kelola.html` | entri "Air Quality Monitor (ESP32)" + `dasbor: false` → `true` (selaras dengan `layanan.json` live) |
| `zima-hosting/CHECKLIST-CLOUDFLARE.md` | catatan peluncur panel |
| `zima-hosting/situs/{index.html,dasbor.js,layanan.json}` | skema kartu + kartu "Kualitas Udara" |
| `buka-panel.mjs` | **baru** — peluncur panel pada alamat tetap `http://127.0.0.1:8788` |
| `CATATAN-KERJA-2026-09-27.md` | berkas ini |
| `zima-hosting/CATATAN-KENDALA.md` | entri 11–13 |

**Di host ZimaOS (bukan repo):**

| Lokasi | Isi |
|---|---|
| `/DATA/AppData/udara/` | `notif-udara.sh`, `pasang-notif-udara.sh`, `keadaan.env`, `notif-udara.log` (+ beberapa `*.bak-*`) |
| `/etc/systemd/system/notif-udara.{service,timer}` | timer tiap 1 menit |
| `/DATA/AppData/zima-hosting/Caddyfile` | blok `udara`/`aqi` (versi LIVE) |
| `/DATA/AppData/zima-hosting/situs/` | `index.html`, `dasbor.js`, `layanan.json` LIVE |
| `/var/lib/casaos/apps/air-quality/docker-compose.yml` | `ESP` → `.13` |

---

## 4. Jebakan yang terbukti hari ini (hemat waktu!)

1. **`priority` ntfy di badan JSON harus ANGKA 1–5.** Teks (`"high"`) → `HTTP
   400 invalid request: request body must be valid JSON`, pesan tidak terkirim.
   Lewat **header** HTTP teks tetap boleh (itu sebabnya skrip RouterOS pakai teks).
2. **MSYS/Git Bash mengubah argumen `/DATA/...` jadi `C:/...`.** Saat unggah
   lewat `zima-shell.mjs`, jalankan dengan
   `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'` — kalau tidak, berkas terpasang
   ke path Windows yang salah.
3. **`sudo rm` file milik root di `/tmp` gagal sebagai user biasa** (direktori
   sticky). `rm -f` **tidak** menghapus, hanya diam-diam ditolak → hapus dengan
   `sudo rm -f`.
4. **Bind mount Caddy memakai inode** → sunting Caddyfile/situs **di tempat**
   (`cat > file` / `tee`), jangan `mv` (mengganti inode → konten tidak berubah
   di container).
5. **Datasource Infinity vs Prometheus itu dua jalur berbeda.** Infinity membaca
   sensor langsung (`/api/data`); Prometheus lewat `air-bridge`. Perbaiki
   **keduanya** kalau alamat sensor berubah.
6. **Skrip bridge disimpan sebagai base64 inline** di `docker-compose.yml`.
   Jangan cari berkas `.py` terpisah — sunting base64-nya (atau regen), lalu
   `docker compose up -d`.

---

## 5. Cadangan & rollback

| Apa | Cadangan |
|---|---|
| Compose air-quality | `docker-compose.yml.bak-air-2026-09-27-2035` |
| Caddyfile LIVE | `Caddyfile.bak-udara-*` |
| index.html LIVE | `index.html.bak-2026-09-27-2100` |
| `notif-udara.sh` host | `notif-udara.sh.bak-2026-09-27-*` |
| Copot notifikasi | `sudo systemctl disable --now notif-udara.timer` lalu hapus unit-nya |

---

## 6. Cara cepat memeriksa kesehatan (perintah)

```bash
# Sensor hidup?
curl -s --max-time 8 http://192.168.20.13:88/api/data

# Notifikasi terakhir & kanal yang dipakai
tail -n 20 /DATA/AppData/udara/notif-udara.log
sudo sh /DATA/AppData/udara/notif-udara.sh status

# Timer jalan?
systemctl list-timers notif-udara.timer

# Pesan benar-benar tiba (bukan hanya terkirim)
curl -s "https://ntfy.adminforge.de/udara-xu64dtfks2ei/json?poll=1&since=15m"

# Portal & kartu dasbor
curl -sI https://udara.clusternet.my.id | head -1
node validasi-hosting.mjs      # dari repo: Lolos 79 | GAGAL 0
```

---

## 7. Sisa pekerjaan (belum dikerjakan)

- **Sebab restart sporadis sensor belum diketahui** (catu daya? WiFi? watchdog?).
  Kandidat: korelasikan `air_uptime_seconds` dengan RSSI/beban/waktu.
- **Bersihkan berkas sampah di host**: `/DATA/AppData/udara/*.bak-*`,
  `index.html.bak` bernama literal, `index_0.html`, `up.txt` di folder situs.
- ~~`https://ntfy.clusternet.my.id` masih 404~~ — **beres**: opsi ntfy
  self-hosted dicopot seluruhnya (lihat §2.7). Bila nanti mau push instan,
  pakai `https://ntfy.sh` yang sudah jadi kanal cadangan.
- **`192.168.145.252:7681` tidak melayani** (ttyd hanya di `192.168.20.36:7681`).
- Halaman status `air_quality` di dasbor belum diberi catatan apakah angka ENS160
  layak dipercaya. **Bukti hari ini:** eCO2/TVOC **tidak** mentok — pada 21:47
  terbaca eCO2 441 ppm, TVOC 42 ppb (400/0 memang wajar untuk udara luar bersih),
  jadi dugaan "ENS160 belum memanas" kemungkinan salah.

---

## 8. Berkas terkait

- `zima-hosting/CATATAN-KENDALA.md` — pola gejala → sebab → solusi (entri 11–13).
- `zima-hosting/MIKROTIK-GRAFANA.md` — rantai SNMP → Prometheus → Grafana.
- `zima-hosting/PANDUAN-WEBHOSTING.md` — pemasangan stack hosting & subdomain.
- `udara/README.md` — paket notifikasi sensor kualitas udara.
- `validasi-hosting.mjs` — validator offline konsistensi repo.
