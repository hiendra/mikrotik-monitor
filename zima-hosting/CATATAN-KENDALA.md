# Catatan Kendala — Clusternet

Satu tempat untuk **gejala → sebab → solusi → verifikasi**, supaya kalau masalah
sama muncul lagi tinggal ikut langkahnya. Tambahkan entri baru di bagian bawah
setiap kali ada kendala baru.

> Jangan pernah menulis sandi/token di berkas ini. Tulis hanya **di mana**
> sandinya disimpan, bukan sandinya.

Peta cepat infrastruktur:

| Bagian | Alamat |
|---|---|
| Host ZimaOS (dari LAN) | `192.168.20.36` (juga dikenal sebagai `192.168.145.252` dari subnet lain) |
| Prometheus | `192.168.20.36:9090` (hanya LAN) |
| Grafana | `192.168.20.36:3003` / `https://grafana.clusternet.my.id` |
| ttyd (terminal ZimaOS) | `192.168.20.36:7681` → dipakai `zima-hosting/zima-shell.mjs` |
| Deployer (jembatan panel) | `192.168.20.36:8791` |
| Router dipantau | `192.168.20.1`, `192.168.200.253`, `192.168.200.1` (CCR1009, `bks.marina.garuda.net.id`, RouterOS 6.49.21) |
| Rantai data | RouterOS ──SNMP──▶ snmp_exporter (9116/9117) ──▶ Prometheus (9090) ──▶ Grafana |

---

## 0. Diagnosa cepat (satu perintah)

```bash
# a. Target mana yang UP / DOWN (dari host ZimaOS atau LAN)
curl -s "http://192.168.20.36:9090/api/v1/query?query=up" | tr ',' '\n' | grep -E 'instance|job'

# b. Alasan target gagal (context deadline exceeded = SNMP tidak menjawab)
curl -s "http://192.168.20.36:9090/api/v1/targets?state=any" | tr ',' '\n' | grep -E 'instance|lastError'

# c. Grafana hidup?
curl -s https://grafana.clusternet.my.id/api/health

# d. Datasource & dasbor
curl -s -u admin:SANDI "https://grafana.clusternet.my.id/api/datasources"
curl -s -u admin:SANDI "https://grafana.clusternet.my.id/api/search?type=dash-db"
```

Cara baca hasil: kalau target `up=0` dengan `context deadline exceeded`, berarti
exporter **tidak mendapat balasan SNMP** dari router → lanjut ke Entri 2.
Kalau semua target `up=1` tetapi grafik kosong → Entri 4.

---

## 1. Grafana kosong / "tidak menampilkan data MikroTik"

**Gejala.** Dasbor MikroTik kosong, datasource `prom-mikrotik` menunjuk
`http://172.17.0.1:9090` tetapi tidak ada isinya.

**Sebab.** Konfigurasi scrape dulu ditulis **dari dalam container** Prometheus
(`entrypoint: printf ... > /etc/prometheus/prometheus.yml`). Image
`prom/prometheus` berjalan sebagai user `nobody`, sedangkan `/etc/prometheus`
milik root → penulisan gagal → Prometheus **crash-loop**:

```
sh: line 0: can't create /etc/prometheus/prometheus.yml: Permission denied
```

**Solusi.** Pindahkan konfigurasi ke **host** dan mount read-only (bukan ditulis
container). Detail lengkap ada di `MIKROTIK-GRAFANA.md`.

Jangan pernah kembali ke pola `printf > /etc/prometheus/...`; pola itu memang
yang rusak dan muncul lagi tiap `prom/prometheus:latest` ditarik ulang.

---

## 2. Router 192.168.200.1 (CCR1009) tidak muncul di Grafana

**Gejala (27 Sep 2026).** Ketiga job — `mikrotik`, `mikrotik-ifs`,
`mikrotik-hr` untuk instance `192.168.200.1` — `up=0` dengan
`lastError: context deadline exceeded`. Router `.20.1` dan `.200.253` sehat.

**Sebab.** SNMP di router itu **aktif**, tetapi community bernama `public`
(yang dipakai snmp_exporter lewat auth `public_v2`) dibatasi
`addresses=103.105.79.0/24`. Permintaan dari host pemantau di `192.168.20.0/24`
**dibuang tanpa balasan**. Bukti di tabel koneksi router:
`192.168.200.253 → 192.168.200.1:161` dengan `repl-packets=0`; sedangkan dari
`103.105.79.74` ada balasan.

**Solusi (dari terminal RouterOS / API 8728).**

```routeros
# 1) Backup dulu
/system backup save name=sebelum-perbaikan-snmp

# 2) Izinkan alamat pemantau
/snmp community set [find name="public"] addresses=0.0.0.0/0

# 3) Verifikasi
/snmp community print
```

> **Jebakan.** Saat diuji, daftar alamat bertingkat tampak "tidak diterima"
> agent SNMP RouterOS 6.49. Sebab sebenarnya: **sumber paket di-SNAT menjadi
> `192.168.200.253`**, bukan `192.168.20.x` (lihat Entri 5). Jadi daftar alamat
> tetap boleh dipakai — masukkan **alamat NAT-nya**. `0.0.0.0/0` dipakai karena
> paling sederhana, sama seperti community `monitoring`/`zabbix`/`server`.

**Verifikasi.** Ketiga job `up=1`, `count({instance="192.168.200.1"})` ≈ 9.800 seri.

**Rollback.** `/snmp community set [find name="public"] addresses=103.105.79.0/24`

---

## 3. Cara masuk ke router / host (kalau perlu perbaikan langsung)

**Router `192.168.200.1`:**

- **API 8728 terbuka** — ini jalur yang dipakai untuk memperbaiki (login
  `admin` + sandi; sandi disimpan di luar repo).
- **SSH 22 TIDAK melayani** — TCP-nya menerima sambungan tetapi tidak pernah
  mengirim banner SSH, jadi `ssh`/paramiko gagal "Error reading SSH protocol
  banner". Jangan buang waktu di sini.
- WinBox `8269`, HTTP `8069` dibatasi ke `103.105.79.0/24`; `8291`/`80`/`443`
  dari LAN timeout.
- Kredensial router **berbeda dengan** kredensial ZimaOS.

**Host ZimaOS:**

- ttyd `192.168.20.36:7681` → `zima-hosting/zima-shell.mjs`
  (`ZIMA_PASS=... node zima-hosting/zima-shell.mjs "docker ps"`).
- Docker di ZimaOS butuh `sudo`.

---

## 4. Data sudah masuk tapi grafik tetap "kosong"

**Gejala.** Prometheus `up=1` dan metrik ada, tetapi garis di Grafana tidak
kelihatan.

**Sebab.** Dasbor memakai rentang bawaan **`now-6h`**, sedangkan data baru mulai
terkumpul beberapa menit sebelumnya → garis hanya mengisi ujung kanan
(< 5% lebar panel). Panel yang memakai `rate(...[5m])` / `irate(...)` juga butuh
**minimal 2 sampel** (interval scrape 30s) sebelum menggambar.

**Solusi.** Ubah rentang waktu panel ke **"Last 15 minutes"**, lalu refresh.
Tidak ada yang perlu diperbaiki di router/Prometheus.

---

## 5. Billing (PHPNuxBill) ↔ MikroTik 192.168.200.1

**Konteks.** Aplikasi billing = **PHPNuxBill** (Apache + PHP 8.2) di ZimaOS:
`192.168.20.36:8082` dari LAN, dipetakan Caddy `billing.clusternet.my.id` →
`192.168.145.252:8082`. Ia mengelola pelanggan PPPoE lewat **API RouterOS
(8728)** di `192.168.200.1`, login sebagai user `admin`.

**Temuan kunci: SNAT.** Trafik dari subnet `192.168.20.x` **di-SNAT** dan tiba di
router sebagai `192.168.200.253`. Karena itu, di log router koneksi billing
muncul sebagai `user admin logged in from 192.168.200.253 via api`, walaupun
aplikasinya berjalan di `192.168.20.36`. Bukti: login dari **PC mana pun** di
`192.168.20.x` juga tercatat sebagai `.200.253`.

> **Konsekuensi penting:** setiap aturan pembatas sumber di router harus memakai
> `192.168.200.253` / `192.168.200.0/24` — **bukan** `192.168.20.x`, karena
> alamat asli sudah ditulis ulang sebelum sampai ke router ini.

**Hasil verifikasi (27 Sep 2026).** Integrasi sehat:

| Uji | Hasil |
|---|---|
| Baca API | 88 PPPoE secret (0 disabled, 0 nama ganda), 68 aktif, 65 simple queue |
| Tulis API | uji `address-list add` → `remove` berhasil (`!done`) |
| Aktivitas | billing login API tiap ±30–60 detik |
| Profil PPP | 18 profil, dipakai normal (3Mb×47, 20Mb×14, …) |
| Anomali data | tidak ada sesi aktif tanpa secret / secret disabled yang online |

**Perbaikan.** Service `api` (8728) semula terbuka `0.0.0.0/0` (audit menandai
ini KRITIS). Dibatasi ke jaringan billing + jaringan ISP, menyamai `ssh`/`www`:

```routeros
/system backup save name=sebelum-batasi-api
/ip service set api address=103.105.79.0/24,192.168.200.0/24
/ip service print
```

**Verifikasi setelah perbaikan.** Login API dari LAN tetap berhasil dan billing
tetap terhubung (login API terus muncul di log router).

**Rollback.** `/ip service set api address=""`

**Pengawasan.** Pada 27 Sep 06:33 pernah terjadi operasi massal: **90 login API +
118 `ppp secret changed by admin` dalam ±1 menit** — dugaan aksi/sync massal dari
billing. Bila muncul lagi tanpa sebab jelas, periksa dari sisi aplikasi.

**Sisa pengamanan yang disarankan (belum dikerjakan):**

- Ganti user API billing dari `admin` (grup `full`) ke user khusus bergrup `write`.
- `winbox` (8269) juga masih `0.0.0.0/0` — pertimbangkan dibatasi seperti `ssh`.

## 6. Notifikasi router (ntfy) gagal terkirim

**Gejala.** Log router penuh `script,warning` → `ntfy: gagal mengirim notifikasi
(periksa DNS, rute, atau sertifikat CA router)`. Semua peringatan router (internet
down, heartbeat, backup, kesehatan) berhenti sampai di pengguna.

**Sebab.** Bukan DNS dan bukan MTU. Jalur keluar menuju `ntfy.sh`
(159.203.148.75 / DigitalOcean) tidak bisa diandalkan dari jaringan ini:
`:ping` ke IP itu menjawab, tapi TCP 80/443 timeout 10 detik — **baik dari router
maupun dari PC lain** (keduanya lewat IP publik yang sama). `tracert` mati di
backbone Telia (233–272 ms), sementara `tracert 1.1.1.1` sehat 9 ms.
Catatan: berkas repo pernah dialihkan ke `ntfy.adminforge.de` dengan alasan
"ntfy.sh sedang membatasi IP publik kita" — jadi ada dua kemungkinan yang tidak
saling eksklusif: jalur transit rusak, **atau** IP kita dibatasi di sisi ntfy.sh.
Karena tidak bisa dipastikan dari sisi kita, jangan bergantung pada satu kanal saja.

**Solusi (SUDAH DITERAPKAN 27 Sep 2026).** `ntfy-kirim` di router kini multi-kanal:
1) server utama → 2) ulangi server utama (jeda 3 detik) → 3) **ntfy lokal di ZimaOS
lewat LAN** (`http://192.168.200.253:7200` — tidak menyentuh internet sama sekali).
Hasilnya dicatat ke log. Salinan skrip lama: `mikrotik-ntfy/ntfy-kirim.sebelum-20260927.rsc`.

> Agar peringatan cadangan sampai ke ponsel, daftarkan server LAN
> `http://192.168.200.253:7200` dengan topik `router-9f3k7q2m4w` di aplikasi ntfy
> (lihat Entri 13: subdomain `ntfy.clusternet.my.id` sudah dilepas).

**Verifikasi.**
```routeros
/log print where message~"ntfy"
# dicari   : "ntfy: terkirim via ntfy lokal ZimaOS" / "... via server utama"
# dihindari: "ntfy: GAGAL di semua kanal"
```
Contoh hasil uji nyata:
```
[07:50:14] script,info   ntfy: terkirim via ntfy lokal ZimaOS
```

**Rollback.** Kembalikan isi skrip dari `mikrotik-ntfy/ntfy-kirim.sebelum-20260927.rsc`
atau dari backup router `sebelum-hardening-20260927.backup`.

## 7. Pesan notifikasi terkirim DUA KALI (selisih ~2 detik)

**Gejala.** Dua notifikasi sama dengan selisih 2 detik, mis.
`Time : 06:58:47` lalu `Time : 06:58:49`.

**Sebab.** Satu peristiwa memicu skrip dua kali. Pemicunya: **men-set ulang entri
Netwatch dari skrip akan merestart probe-nya**. Saat internet masih mati, probe yang
restart langsung gagal lagi → `down-script` jalan lagi ~2 detik kemudian.

**Solusi.** Jangan pernah menulis ke entri Netwatch dari skrip. Simpan status di skrip
penanda (`ntfy-down-time`, `ntfy-nw-terakhir`) karena global yang di-set `script run`
bisa hilang saat job selesai, lalu pasang anti-flood per arah (saat ini 15 detik).
Skrip `read,write,test` **bisa** baca/tulis properti `source` skrip penanda — sudah diuji.

**Verifikasi.** Kirim satu kali `netwatch-down`; pastikan hanya muncul satu notifikasi,
dan `ntfy-nw-terakhir` berubah isinya.

**Rollback.** Kembalikan isi skrip dari backup router.

## 8. MikroTik 192.168.200.1 — hasil inspeksi menyeluruh
Lihat `INSPEKSI-MIKROTIK-200-1.md` (profil perangkat, 12 temuan berprioritas,
perintah perbaikan siap tempel, dan riwayat perubahan).

## 9. Notifikasi Uptime Kuma tidak sampai ke iPhone

**Gejala.** Monitor di Uptime Kuma (`kuma.clusternet.my.id`) mati, tetapi tidak
ada notifikasi di ponsel. Notifikasi router tetap normal, jadi bukan soal
jaringan maupun server ntfy-nya.

**Sebab.** Uptime Kuma belum punya kanal notifikasi ke ntfy sama sekali;
satu-satunya yang terpasang hanya Discord. Di Kuma notifikasi tidak muncul
otomatis: ia harus (a) dibuat di Settings -> Notifications, lalu
(b) dicentang di tiap monitor. Karena itu monitor boleh down berkali-kali tanpa
ada kabar apa pun.

**Solusi (SUDAH DITERAPKAN 27 Sep 2026).** Tambahkan notifikasi **Ntfy** di
panel Kuma dengan topik **terpisah** dari topik router, supaya gangguan router
dan gangguan layanan tidak tercampur di layar kunci:

| Setelan | Nilai |
|---|---|
| Notification Type | `Ntfy` |
| Friendly Name | `ntfy Kuma (adminforge)` |
| Server URL | `https://ntfy.adminforge.de` (**tanpa** nama topik) |
| ntfy Topic | `kuma-7m3xq9dt2v` |
| Priority / Priority for DOWN-events | `3` / `5` |
| Default enabled + Apply on all existing monitors | dicentang |

Topik router tetap `rt-7k2m9dx4q8wf`. Langkah lengkap, termasuk memasang di
iPhone, ada di `PANDUAN-KUMA-NTFY.md`.

> **Jebakan 1.** **Server URL harus tanpa nama topik.** Menggabungkannya
> (`https://ntfy.adminforge.de/kuma-...`) membuat pengiriman gagal.
> **Jebakan 2.** Notifikasi dibuat tetapi lupa dicentang di monitor: Kuma tetap
> menampilkannya di daftar notifikasi, tetapi tidak pernah mengirim apa pun.
> **Jebakan 3.** Nama topik = sandi. Kalau bocor, pesan status layanan bisa
> dibaca siapa pun di server publik itu.

**Verifikasi.**

```bash
python zima-hosting/uji-kuma-ntfy.py
# dicari   : "[LULUS] ada pesan ASLI dari Kuma di topik ini"
#            "[LULUS] topik ntfy terbaca"
# dihindari: "[GAGAL] belum ada pesan asli dari Kuma dalam ... jam"
```

Cara lain: panel Kuma -> **Edit** notifikasi -> tombol **Test** -> harus muncul
**Sent Successfully.**

**Rollback.** Panel Kuma -> **Edit** -> hapus centang **Default enabled** dan
lepas centangnya di tiap monitor, atau hapus notifikasinya. Tidak ada berkas
di repo, skrip, maupun scheduler yang bergantung padanya.

**Catatan.** Dengan `ntfy.adminforge.de`, notifikasi iPhone baru muncul saat
aplikasi dibuka (bukan push instan), karena server itu tidak meneruskan ke push
Apple. Untuk push instan: pindah server ke `https://ntfy.sh`.

## 10. Grafana "Air Quality" kosong — sensor pindah alamat (`.27` → `.13`)

**Gejala (27 Sep 2026).** Dasbor "Air Quality - Cluster Taman Marina" kosong,
`air_up=0`, datasource `ESP32 Air Quality` (Infinity) gagal Health check.
Datasource dan exporter sama-sama menunjuk `192.168.20.27`.

**Sebab.** Sensor ESP32 sudah berpindah ke `192.168.20.13` — lease-nya statik
(MAC `F4:CF:A2:D9:C8:31`); tidak ada lease `.27`, ARP `.27` kosong, port `.27:88`
tertutup. Alamat lama tertinggal di **dua** tempat yang harus diperbaiki
bersama-sama:

1. Datasource **Infinity** Grafana `ESP32 Air Quality` (uid `bfyhierx49ypsd`).
2. Container **`air-bridge`** — skrip Python-nya disimpan sebagai **base64 inline**
di `entrypoint` pada `/var/lib/casaos/apps/air-quality/docker-compose.yml`
(bukan berkas `.py` terpisah).

**Solusi.**

- Grafana → datasource `ESP32 Air Quality` → ubah url ke `http://192.168.20.13:88`
  → **Save & test** (harus "Health check OK").
- Sunting compose: ganti `.27` → `.13`, cadangkan dulu
  (`cp docker-compose.yml docker-compose.yml.bak-air-<tgl>`), lalu
  `docker compose up -d`.

**Verifikasi.** `air_up=1`; semua metrik sensor muncul; dasbor terisi
(32.5 °C, 47.8 %, 20.0 °C, eCO2 400 ppm, TVOC 0, AQI 1).

**Rollback.** Kembalikan dari `docker-compose.yml.bak-air-*`; datasource cukup
diubah lagi lewat UI.

> **Ingat:** Infinity membaca sensor **langsung**, Prometheus lewat `air-bridge`.
> Mengubah alamat sensor berarti memperbaiki **keduanya**.

---

## 11. Notifikasi kualitas udara tidak sampai ke ponsel / pesan kembar

**Gejala.** Notifikasi sensor tidak muncul, atau muncul dua kali, atau API
menjawab `HTTP 400 invalid request: request body must be valid JSON`.

**Sebab & aturan (teruji 27 Sep 2026).**

1. **`priority` di badan JSON HARUS angka 1–5.** Mengirim `"priority":"high"`
ditolak HTTP 400 dan pesan **tidak terkirim sama sekali**. (Lewat **header**
HTTP, teks tetap boleh — karena itu skrip RouterOS memakai teks.)
2. **Pesan kembar** terjadi bila mengirim ke semua kanal sekaligus. Skrip
`udara/notif-udara.sh` **berhenti di kanal pertama yang berhasil**, jadi satu
kejadian = satu pesan.
3. **Server adminforge tidak meneruskan ke push Apple**, sedangkan `ntfy.sh`
meneruskan. Keputusan user (27 Sep 2026): **adminforge tetap kanal utama**
(memang terbukti sampai instan ke ponsel user), `ntfy.sh` didaftarkan sebagai
cadangan.
4. Topik = kata sandi; jangan pernah dicampur dengan topik router/Kuma.

**Solusi.** Skrip multi-kanal di `udara/notif-udara.sh`
(`adminforge` → `ntfy.sh` → LAN `192.168.200.253:7200`), dijalankan systemd
timer `notif-udara.timer` tiap 1 menit. Langganan app ntfy: tambahkan
**kedua** server dengan topik `udara-xu64dtfks2ei`. Langkah lengkap di
`udara/README.md`.

**Verifikasi.**

```bash
sudo sh /DATA/AppData/udara/notif-udara.sh uji
curl -s "https://ntfy.adminforge.de/udara-xu64dtfks2ei/json?poll=1&since=15m"
tail -n 20 /DATA/AppData/udara/notif-udara.log   # cari "ntfy terkirim via <server>"
```

**Rollback.** Tidak wajib; notifikasi murni aditif.

---

## 12. Berkas terpasang ke path salah saat unggah ke host ZimaOS

**Gejala.** Setelah `node zima-hosting/zima-shell.mjs --upload <lokal> /DATA/...`,
keluar `tee: 'C:/Espressif/tools/git/DATA/...': No such file or directory`.

**Sebab.** **MSYS/Git Bash mengubah argumen berawalan `/`** menjadi path Windows
sebelum diteruskan ke Node.

**Solusi.** Jalankan dengan konversi path dimatikan:

```bash
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
```

**Jebakan terkait.** Menghapus berkas sementara milik root di `/tmp` sebagai
user biasa **gagal diam-diam** (direktori sticky); `rm -f` tidak menghapus apa pun
— pakai `sudo rm -f`.

**Verifikasi.** Perintah unggah mencetak `TERPASANG: <tujuan yang benar>` dan
`md5sum` lokal = `md5sum` di host.

### Catatan terkait: tautan `http://127.0.0.1:<port>/...` cepat basi

**Gejala (27 Sep 2026).** `http://127.0.0.1:65505/panel-kelola.html` tidak bisa
dibuka, padahal sebelumnya sempat jalan.

**Sebab.** Bukan ZimaOS dan bukan repo. `127.0.0.1` menunjuk ke **PC sendiri**,
dan fitur *preview* editor menyalakan server di **port acak yang berganti tiap
sesi** (65505 → 53527). Bukti: `curl` ke port itu HTTP 000, `netstat` di PC
kosong untuk seluruh rentang `655xx`, `grep 65505` di repo nol hasil, dan `ss`
di host ZimaOS tidak menemukan port itu sama sekali.

**Solusi.** Jangan simpan tautan berport dari preview. Pakai salah satu:

- Buka berkasnya langsung: `file:///.../zima-hosting/panel-kelola.html`
  (panel ini statis, **tidak butuh server**).
- Alamat tetap: `node buka-panel.mjs` → `http://127.0.0.1:8788/panel-kelola.html`
  (ganti port dengan `PANEL_PORT`, `--tanpa-buka` untuk server saja).

---

## 13. ntfy self-hosted dilepas dari stack hosting (27 Sep 2026)

**Gejala.** `https://ntfy.clusternet.my.id` menjawab **404** dan tak ada satu
pun kanal notifikasi yang bergantung padanya; namun repo (Caddyfile, compose,
panel, panduan) masih mendeklarasikan server ntfy sendiri, seolah-olah ia hidup.

**Sebab.** Opsi ntfy self-hosted di stack `zima-hosting` memang tidak pernah
benar-benar berjalan: blok `ntfy` tidak pernah masuk ke Caddyfile LIVE, container
`ntfy` dari `docker-compose.yml` tidak ada di host, dan aplikasi ntfy yang pernah
ada (`big-bear-ntfy-app-1`, aplikasi CasaOS terpisah) sudah di-uninstall pemilik.
Sementara itu notifikasi nyata sudah pindah ke layanan ntfy publik
(`ntfy.adminforge.de` utama, `ntfy.sh` cadangan, LAN `192.168.200.253:7200`).
Jadi subdomain ini hanya menyisakan kebingungan, bukan fungsi.

**Solusi (SUDAH DITERAPKAN 27 Sep 2026).** Lepas seluruh opsi ntfy self-hosted:

- Hapus blok `http://ntfy.clusternet.my.id` dari `zima-hosting/Caddyfile`.
- Hapus service `ntfy` + volume `ntfy_data` dari `zima-hosting/docker-compose.yml`.
- Hapus entri `ntfy` dari `zima-hosting/panel-kelola.html`.
- Hapus seksi + baris ntfy dari `zima-hosting/PANDUAN-WEBHOSTING.md`.
- Hapus berkas `ntfy-pasang.sh`, `ntfy-uji.sh`, dan `PANDUAN-NTFY-IPHONE.md`.
- Layani notifikasi tetap lewat layanan publik di tabel `PANDUAN-KUMA-NTFY.md`,
  `mikrotik-ntfy/README.md`, dan `udara/README.md`.

**Verifikasi.**

```bash
node validasi-hosting.mjs        # diharapkan Lolos tanpa GAGAL
curl -sI https://ntfy.clusternet.my.id | head -1   # 404 (wildcard), memang diharapkan
```

Hasil pemeriksaan 27 Sep 2026: `node validasi-hosting.mjs` → **Lolos 77 | GAGAL 0**,
`--uji` → 18/18. Host ternyata **sudah** seragam dengan repo — md5
`/DATA/AppData/zima-hosting/Caddyfile` (`af337a55…`) dan `docker-compose.yml`
(`25e607be…`) sama persis, begitu pula seluruh `situs/`. Artinya blok/service ntfy
memang **hanya ada di repo**, tak pernah sampai ke host. Endpoint live:
`clusternet.my.id` **200**, `udara.clusternet.my.id` **200** (bukti Caddy sudah
memuat Caddyfile terkini), `kuma.clusternet.my.id` **302**, `ntfy.clusternet.my.id`
**404** (wildcard, sesuai harapan). Kontainer: `web-router`, `cf-tunnel`, dan
`zima-deployer` semuanya **Up**.

Bukti kanal notifikasi yang **tersisa** hidup: `python uji-semua-ntfy.py` →
**5/7 kanal LULUS** (semua kanal wajib). Dua kanal yang gagal adalah LAN lokal
`http://192.168.200.253:7200` untuk router & udara — wajar, karena ntfy lokal
itulah yang dilepas di entri ini.

**Rollback.** Kembalikan blok Caddyfile + service compose dari git, lalu
`docker compose up -d`. Tidak disarankan: notifikasi sudah stabil tanpa itu.

## 14. Templat entri baru

```markdown
## N. <Judul singkat>

**Gejala.** <apa yang terlihat, sertakan pesan galat apa adanya>

**Sebab.** <akar masalah + cara memastikan>

**Solusi.** <langkah + perintah siap tempel>

**Verifikasi.** <perintah/kriteria yang membuktikan sudah beres>

**Rollback.** <cara kembali bila salah>
```

---

## Berkas terkait

- `MIKROTIK-GRAFANA.md` — detail rantai SNMP → Prometheus → Grafana, termasuk "Kasus ketiga": menambahkan metrik **Mesh ID** ke Prometheus yang sama (job `meshtastic`, dasbor `meshtastic-node`, jebakan `rule_files` tanpa volume mount).
- `INSPEKSI-MIKROTIK-200-1.md` — laporan inspeksi MikroTik `192.168.200.1` (27 Sep 2026).
- `REKOMENDASI-OPTIMASI-SERVER.md` — temuan audit & prioritas perbaikan.
- `PANDUAN-WEBHOSTING.md` — pemasangan stack hosting.
- `PANDUAN-KUMA-NTFY.md` — notifikasi Uptime Kuma ke iPhone (topik ntfy terpisah).
- `uji-kuma-ntfy.py` — pemeriksa kanal Kuma → ntfy.
- `CATATAN-KERJA-2026-09-27.md` — jurnal kerja 27 Sep 2026 (kronologi, jejak berkas, jebakan).
- `CHECKLIST-CLOUDFLARE.md` — daftar periksa tunnel & Access.
