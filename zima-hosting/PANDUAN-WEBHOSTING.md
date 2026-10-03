# Web Hosting di ZimaOS untuk clusternet.my.id (tanpa port forwarding)

Tujuan: `clusternet.my.id` dan **semua** layanan di ZimaOS bisa diakses dari
internet lewat nama domain, tanpa satu pun port forwarding di router.

Isi folder ini:

| Berkas | Fungsi |
|---|---|
| `docker-compose.yml` | Dua container: `cf-tunnel` (cloudflared) + `web-router` (Caddy) |
| `Caddyfile` | Peta nama domain → layanan; di sinilah aplikasi baru ditambahkan |
| `situs/index.html` | Halaman utama `clusternet.my.id` (kartu digambar dari manifest) |
| `situs/dasbor.js` | Kode yang menggambar kartu layanan dari `situs/layanan.json` |
| `situs/layanan.json` | Daftar kartu dasbor; dihasilkan panel, dikirim `zima-deployer` |
| `.env.example` | Contoh penempatan token tunnel (salin jadi `.env`) |
| `RESET-ADGUARD-HOME.md` | Cara memulihkan/mengganti password AdGuard Home (`files.*`) bila lupa |
| `validasi-hosting.mjs` | Pemeriksa konsistensi (di folder induk): memastikan compose, Caddyfile, `.env`, dan panduan ini masih saling cocok |
| `validasi-hosting.mjs --uji` | Uji diri pemeriksa: menyuntikkan kerusakan sengaja ke salinan sementara, lalu menuntut setiap penjaga bereaksi |

## Mengapa ini bisa tanpa port forwarding

Ada dua arah koneksi yang berbeda:

| Cara lama (port forwarding) | Cara ini (Cloudflare Tunnel) |
|---|---|
| Internet **masuk** ke router → NAT → server | Server **keluar** ke Cloudflare → tunnel |
| Butuh IP publik + 1 port per layanan | Satu koneksi keluar, tak terbatas layanan |
| TLS harus diurus sendiri per port | TLS otomatis di sisi Cloudflare |
| Port tetap terbuka → dipindai orang | Tidak ada port masuk sama sekali |

Karena cloudflared membuat koneksi **keluar** (outbound) ke Cloudflare, router
tidak perlu tahu apa pun. Menutup semua port masuk justru bagian dari
konfigurasinya.

### Pengecualian yang disengaja: satu port masuk sebagai cadangan

Aturan di atas berlaku untuk semua layanan, **kecuali satu**: port **3001**
(Uptime Kuma) sengaja tetap dibiarkan diteruskan router. Alasannya: pemantauan
adalah justru hal yang paling ingin tetap bisa dibuka ketika tunnel, DNS, atau
Cloudflare sedang bermasalah - saat itulah halaman status paling dibutuhkan.

| Jalur | Alamat | Sifat |
|---|---|---|
| Utama | `https://kuma.clusternet.my.id` | lewat tunnel, TLS dari Cloudflare, ikut terlindungi Access |
| Cadangan | `http://<IP-WAN>:3001` | langsung ke container, HTTP polos, tidak lewat Cloudflare |

Keduanya melayani **container yang sama**, jadi monitor, status page, dan
sesi login selalu sinkron - tidak ada data yang perlu disalin. Yang perlu
sadar: jalur cadangan tidak terenkripsi (sandi login dikirim sebagai HTTP
polos) dan tidak tersaring Access, jadi sebaiknya sandi Uptime Kuma memakai
kata sandi yang kuat dan berbeda dari layanan lain. Bila kelak jalur cadangan
tidak diperlukan lagi, cukup hapus terusan port 3001 di router dan
`kuma.clusternet.my.id` tetap bekerja tanpa perubahan apa pun.

### Alamat halaman status Uptime Kuma

| Tujuan | Alamat |
|---|---|
| Halaman status (untuk dibagikan) | `https://kuma.clusternet.my.id/status/mesh` |
| Alamat pendek | `https://kuma.clusternet.my.id/status` -> dialihkan (302) ke alamat di atas |
| Umpan RSS | `https://kuma.clusternet.my.id/status/mesh/rss` |
| Panel admin | `https://kuma.clusternet.my.id/dashboard` |

Uptime Kuma menjawab 404 untuk `/status` tanpa slug, jadi alamat pendek itu
dibuat sebagai **pengalihan di Caddy** (`redir`, dijalankan sebelum
`reverse_proxy`) - bukan dengan mengganti slug halaman. Konsekuensinya perlu
diingat: mengganti slug halaman cukup dilakukan di UI Uptime Kuma, tetapi
dua baris `redir` di `Caddyfile` **harus ikut disesuaikan**, kalau tidak
alamat pendeknya menunjuk ke halaman yang sudah tidak ada.

Yang mudah terlewat: alamat pendek itu **hanya berlaku di jalur utama**. Jalur
cadangan `http://<IP-WAN>:3001` masuk **langsung ke container** dan melewati
Caddy, jadi di sana `/status` tetap dijawab 404 oleh Uptime Kuma - yang bekerja
hanya `/status/mesh`. Ini berlaku umum untuk semua yang dipasang di lapisan
Caddy (pengalihan, header keamanan, HSTS, CSP, kompresi): **tidak satu pun
berlaku di jalur cadangan**, karena jalur itu memang sengaja dibuat tidak
bergantung pada Caddy dan Cloudflare.

### Monitor baru otomatis masuk ke halaman status

Uptime Kuma **tidak** punya fitur "tambahkan monitor baru ke halaman status
secara otomatis" - permintaan itu masih berupa feature request yang belum
diimplementasikan (louislam/uptime-kuma#2810). Tanpa penanganan khusus, setiap
monitor baru harus dipasangkan manual, dan yang terlewat akan tampak "hilang"
padahal ada (persis kasus `mqtt2.meshnode.id`).

Di server ini hal tersebut ditangani oleh dua berkas di
`/DATA/AppData/zima-hosting/`:

| Berkas | Fungsi |
|---|---|
| `sinkron-status-kuma.sh` | Memasukkan semua monitor **aktif** yang belum ada ke grup `MeshNode` pada halaman `mesh`. Idempoten; tidak mengubah urutan yang sudah ada. |
| `pasang-sinkron-kuma.sh` | Memasang skrip di atas sebagai systemd timer tiap 5 menit (idempoten, aman dijalankan ulang). |

ZimaOS memakai systemd tetapi **tidak memasang cron/crond**, jadi penjadwalan
memakai `sinkron-status-kuma.timer`, bukan crontab.

```bash
# pasang atau pasang ulang (mis. setelah pembaruan ZimaOS)
sudo sh /DATA/AppData/zima-hosting/pasang-sinkron-kuma.sh

# jalankan sekali tanpa menunggu jadwal
sudo systemctl start sinkron-status-kuma.service

# lihat kapan jalan berikutnya
systemctl list-timers sinkron-status-kuma.timer

# lihat catatan penambahan
tail -n 20 /DATA/AppData/zima-hosting/sinkron-status-kuma.log

# copot
sudo systemctl disable --now sinkron-status-kuma.timer
sudo rm /etc/systemd/system/sinkron-status-kuma.{service,timer}
sudo systemctl daemon-reload
```

Perilaku yang bisa diatur lewat variabel lingkungan (lihat kepala
`sinkron-status-kuma.sh`): `KUMA_HALAMAN` (slug halaman), `KUMA_GRUP` (nama
grup), dan `KUMA_SERTAKAN_GRUP=1` bila monitor bertipe *group* juga ingin
ikut dimasukkan (bawaannya dilewati, karena grup bukan layanan).

Dua catatan penting:

- Skrip ini menulis langsung ke database Uptime Kuma (`monitor_group`). Kalau
  kelak Uptime Kuma mengubah skema tabelnya, skrip perlu ditinjau ulang.
- Unit systemd tinggal di `/etc/systemd/system`. Perubahan ada di dalam berkas
  skrip di `/DATA` yang persisten, tetapi **pendaftaran timer bisa hilang saat
  ZimaOS diperbarui** - cukup jalankan `pasang-sinkron-kuma.sh` lagi.

## Kondisi awal yang sudah terverifikasi

```
DNS clusternet.my.id   -> di Cloudflare (indie/agustin.ns.cloudflare.com)
A clusternet.my.id     -> 103.105.79.7   (DNS-only, proxy Cloudflare BELUM aktif)
A www                  -> 103.105.79.7
A mail                 -> 103.105.79.7
MX                     -> clusternet.my.id (port 25 tertutup, jadi mail belum jalan)
Wildcard subdomain     -> belum ada (NXDOMAIN)
Port 443 / 80          -> tertutup dari internet (Cloudflare proxy belum aktif)
Port terbuka ke publik -> 22, 8080, 8280, 8728
```

Artinya: separuh pekerjaan sudah beres (DNS sudah di Cloudflare). Tinggal
memasang tunnel dan memindahkan lalu lintas ke sana.

## Arsitektur target

```
                        Internet
                            |
              HTTPS (sertifikat gratis Cloudflare)
                            |
                     CLOUDFLARE EDGE
        DNS: clusternet.my.id / www / *.clusternet.my.id
             (CNAME -> <id-tunnel>.cfargotunnel.com)
                            |
        ====== koneksi KELUAR (tanpa port forwarding) ======
                            |
              ZIMAOS - container cloudflared
                            |
                   http://caddy:80  (internal)
                            |
                     CADDY (router nama host)
        +-------------------+--------------------+------------------+
        |                   |                    |                  |
  clusternet.my.id     zima.*               files.*         (layanan baru)
     ./situs        ZimaOS UI :8280      aplikasi :8080      cukup 1 blok
```

Kunci desainnya: **tunnel hanya menunjuk ke satu alamat (Caddy)**, sedangkan
pembagian layanan dilakukan oleh Caddy berdasarkan nama host. Menambah aplikasi
baru nanti tidak perlu mengubah DNS, tunnel, atau router.

## Yang perlu disiapkan

1. Akses akun Cloudflare yang mengelola zona `clusternet.my.id`.
2. Akses ke ZimaOS (admin UI atau SSH).
3. Berkas di folder ini: `docker-compose.yml`, `Caddyfile`, folder `situs/`.

> Yang mau cara cepat: langkah Cloudflare di dokumen ini diringkas sebagai
> checklist centang di **CHECKLIST-CLOUDFLARE.md** (folder ini) — bisa dicetak
> dan dicentang sambil dikerjakan.

## Langkah 0 - Periksa dulu berkasnya (opsional, 1 detik)

Kalau Anda mengubah `Caddyfile` atau `docker-compose.yml`, jalankan pemeriksa
ini sebelum memasang. Ia menangkap hal yang paling sering luput: port host yang
bentrok dengan ZimaOS, nama layanan yang salah ketik, mount folder yang tidak
ada, dan variabel `.env` yang belum dibuat. Tanpa Docker, tanpa jaringan.

```bash
node validasi-hosting.mjs        # dari akar repo; kode keluar 1 = ada yang GAGAL
node validasi-hosting.mjs --uji  # membuktikan pemeriksanya sendiri masih andal
```

## Langkah 1 - Buat tunnel di Cloudflare

1. Buka <https://one.dash.cloudflare.com> → **Networks → Tunnels**.
2. **Create a tunnel** → pilih **Cloudflared** → beri nama, mis. `zimaos`.
3. Pilih lingkungan **Docker**, lalu **salin token** yang muncul (rangkaian
   panjang yang diawali `eyJ...`). Token ini adalah kunci masuk server Anda —
   jangan ditempel ke chat, jangan di-commit.
4. Di ZimaOS, simpan token di `zima-hosting/.env`:

   ```
   TUNNEL_TOKEN=eyJhIjoi...(tempelkan)
   ```

   (`.env` sudah masuk `.gitignore` supaya tidak ikut ter-commit.)

## Langkah 2 - Pasang stack di ZimaOS

**Cara A - App Store (tanpa SSH):**
App Store → **Install a customized app** → tempelkan isi
`zima-hosting/docker-compose.yml`. Pastikan berkas `Caddyfile` dan folder
`situs/` sudah ada di folder aplikasi tersebut.

**Cara B - SSH ke ZimaOS:**

```bash
cd /DATA/AppData/zima-hosting     # folder pilihan Anda
docker compose up -d
docker compose logs -f cloudflared   # tunggu tulisan "Registered tunnel connection"
```

Hasil yang diharapkan: dua container jalan (`web-router`, `cf-tunnel`).
Yang perlu dicek di log cloudflared: koneksi tercatat **4 kali** dari lokasi
berbeda (edge Cloudflare) dan tidak ada error.

## Langkah 3 - Daftarkan nama domain ke tunnel

Di halaman tunnel → tab **Public Hostname** → **Add a public hostname**, isi:

| Subdomain | Domain | Path | Service |
|---|---|---|---|
| *(kosong)* | clusternet.my.id | - | `http://caddy:80` |
| `www` | clusternet.my.id | - | `http://caddy:80` |
| `*` | clusternet.my.id | - | `http://caddy:80` |

Tiga baris itu sudah cukup untuk **semua** subdomain ke depannya, dan ketiganya
sengaja diarahkan ke service yang **sama** (`http://caddy:80`) — Caddy yang
memutuskan layanan mana yang dilayani, berdasarkan nama host yang diminta
pengunjung (baris `www` = `www.clusternet.my.id`). Wildcard
hanya berlaku **satu tingkat**: `adguard.clusternet.my.id` cocok, tetapi
`a.b.clusternet.my.id` tidak (butuh sertifikat tambahan).

Cloudflare akan membuat sendiri record DNS `CNAME` ke
`<id-tunnel>.cfargotunnel.com` dengan proxy aktif (ikon awan oranye). Record A
lama yang menunjuk `103.105.79.7` pada nama yang sama akan tertimpa — itu
memang yang diinginkan.

## Langkah 4 - Tambahkan layanan

Cukup tambah satu blok di `zima-hosting/Caddyfile`, lalu:

```bash
docker compose restart caddy
```

Contoh isi `Caddyfile` setelah disesuaikan:

| Domain | Diteruskan ke | Catatan |
|---|---|---|
| `clusternet.my.id`, `www.clusternet.my.id` | folder `./situs` | situs utama |
| `zima.clusternet.my.id` | `192.168.145.252:8280` | UI ZimaOS (wajib pakai Access) |
| `adguard.clusternet.my.id` | `192.168.145.252:8080` | AdGuard Home, pemblokir iklan DNS (dulu `files.`) |
| `immich.clusternet.my.id` | `192.168.145.252:2283` | Immich 3.1.0, galeri foto (wajib pakai Access) |
| `grafana.clusternet.my.id` | `192.168.145.252:3003` | Grafana, dasbor (wajib pakai Access) |
| `kuma.clusternet.my.id` | `192.168.145.252:3001` | Uptime Kuma, pemantauan + halaman status publik (`/status/...`); panel admin `/dashboard` sebaiknya di balik Access. Port 3001 sengaja tetap diteruskan router sebagai jalur cadangan |
| `billing.clusternet.my.id` | `192.168.145.252:8082` | aplikasi billing PHP "Masuk - CLUSTERNET" (wajib pakai Access; dulu `portal.`) |
| `udara.clusternet.my.id`, `aqi.clusternet.my.id` | `192.168.20.13:88` | Air Quality Monitor ESP32 (Cluster Taman Marina). Perangkat ini **bukan** host ZimaOS, jadi targetnya ditulis sebagai IP LAN langsung, bukan `192.168.145.252`. Halamannya publik (data lingkungan), jadi **tidak** dipasang Cloudflare Access |
| `meshid.clusternet.my.id` | `192.168.20.36:9208` | Monitor node Meshtastic (gateway, node RF langsung, node MQTT). Exporter-nya systemd di host ZimaOS (`meshtastic-exporter.service`), jadi **hidup 24/7**; alamat LAN host dipakai langsung alih-alih akhiran container. Halamannya **publik tanpa Cloudflare Access** (keputusan pemilik, sama seperti `udara`) — sadarilah isinya memuat koordinat GPS node |
| `*.clusternet.my.id` | balasan 404 | subdomain tak dikenal |

> Monitor node Meshtastic (`meshid.clusternet.my.id`) punya catatan perawatan
> tersendiri di **`CATATAN-MESHNODEID.md`** (akar repo): peta alamat, perintah
> periksa, cara menerapkan rute + uji seluruh rute, dan kendala yang pernah
> terjadi (termasuk kenapa `zima-deployer` yang terpasang belum bisa menulis
> kartu dasbor).

### Notifikasi (ntfy)

Notifikasi MikroTik, Uptime Kuma, dan skrip server **tidak** memakai server
sendiri. Kanal yang dipakai adalah **layanan ntfy publik**:

| Keperluan | Server | Topik |
|---|---|---|
| Router MikroTik | `https://ntfy.adminforge.de` (utama), cadangan `https://ntfy.sh`, lalu ntfy lokal LAN | `rt-7k2m9dx4q8wf` |
| Uptime Kuma | `https://ntfy.adminforge.de` | `kuma-7m3xq9dt2v` |
| Sensor udara | `https://ntfy.adminforge.de` (utama), cadangan `https://ntfy.sh`, lalu LAN | `udara-xu64dtfks2ei` |

Detail tiap kanal ada di `PANDUAN-KUMA-NTFY.md` (Kuma), `mikrotik-ntfy/README.md`
(MikroTik), dan `udara/README.md` (sensor udara). Tidak ada subdomain ntfy yang
perlu dipetakan di Caddyfile.

> **Pernah ada** opsi menjalankan ntfy self-hosted di stack ini
> (`ntfy.clusternet.my.id`). Opsi itu **dicopot 27 Sep 2026** — lihat
> `CATATAN-KENDALA.md` entri 13. Server ntfy sendiri kini tidak dijalankan.

### Hasil pemindaian layanan (per 22 Sep 2026)

Yang **hidup** di host ZimaOS saat dipindai, dan keputusannya:

| Port | Isi | Dipetakan ke |
|---|---|---|
| 2283 | Immich 3.1.0 | `immich.clusternet.my.id`, di balik Access |
| 2284 | Immich yang sama (ETag identik) | tidak dipetakan - duplikat dari 2283 |
| 3001 | Uptime Kuma (pemantauan + halaman status) | `kuma.clusternet.my.id`; panel admin di balik Access. Ini satu-satunya port yang sengaja **tetap** diteruskan (cadangan bila tunnel mati) |
| 3003 | Grafana | `grafana.clusternet.my.id`, di balik Access |
| 4096 | HTTP Basic "Secure Area", identitas belum jelas | tidak dipetakan sampai jelas |
| 4403 | bukan HTTP (TCP) | tidak bisa diberi nama domain |
| 7681, 7682 | terminal web (ttyd) | **jangan dipetakan publik** - pakai ZeroTier/Access |
| 8007 | bukan HTTP (TCP) | tidak bisa diberi nama domain |
| 8080 | AdGuard Home (UI pemblokir DNS) | `adguard.clusternet.my.id` (dulu `files.`) |
| 8082 | Apache 2.4.68 + PHP 8.2, "Masuk - CLUSTERNET" | `billing.clusternet.my.id`, di balik Access (dulu `portal.`) |
| 8111 | UI ZimaOS (dilayani Caddy internal) | tidak perlu - sudah lewat 8280 |
| 8280 | Gerbang/UI ZimaOS | `zima.clusternet.my.id`, di balik Access |
| 8286 | bukan HTTP (TCP) | tidak bisa diberi nama domain |

Port di atas **hanya hidup di LAN** dan tidak perlu port forwarding: nama
hostname-nya sudah tercakup wildcard `*.clusternet.my.id` yang didaftarkan ke
tunnel, jadi menambah layanan **tidak** mengubah DNS maupun tunnel.

Cara memindai ulang saat Anda memasang aplikasi baru, atau bila IP/port
berubah:

```powershell
powershell -ExecutionPolicy Bypass -File .\pindai-layanan.ps1
```

Skrip itu mencetak blok Caddyfile siap tempel untuk setiap layanan yang
ditemukan, beserta usulan namanya. Untuk mengubah pemetaan tanpa mengedit
berkas secara manual, buka panel visual: `zima-hosting/panel-kelola.html`
(klik dua kali, berjalan di browser, tanpa server).

Kalau lebih suka alamat `http://` yang **tetap** (tidak berubah tiap sesi),
jalankan peluncurnya dari akar repo — ia menyalakan server statis kecil untuk
folder `zima-hosting/` pada port tetap lalu membuka browsernya:

```bash
node buka-panel.mjs        # http://127.0.0.1:8788/panel-kelola.html
```

Hentikan dengan `Ctrl+C`. Port dapat diganti lewat `PANEL_PORT`, dan
`--tanpa-buka` hanya menyalakan server tanpa membuka browser.

> **Jangan simpan tautan `http://127.0.0.1:<port>/...` dari fitur preview
> editor.** Port itu dibuat acak tiap sesi, jadi tautannya cepat basi. Pakai
> `buka-panel.mjs` (port tetap 8788) atau buka berkasnya langsung lewat
> `file://`. `127.0.0.1` juga menunjuk ke **PC Anda**, bukan ke ZimaOS.

## Dasbor utama dan tautan balik

`clusternet.my.id` dipakai sebagai **dasbor**: seluruh layanan ZimaOS muncul di
sana sebagai kartu, dan tiap kartu terbuka di **tab baru**
(`target="_blank" rel="noopener noreferrer"`) sehingga tab dasbor tidak pernah
tertelan oleh layanan yang dibuka. Itu jalan pulang yang paling andal.

Untuk layanan yang berkasnya memang bisa disunting, tautan pulang juga dipasang
di dalam aplikasinya:

| Layanan | Tempat tautan | Cara memasang ulang |
|---|---|---|
| Grafana | daftar `links` tiap dasbor (tampil di bar atas) | `node zima-hosting/tautan-balik-grafana.mjs` |
| Billing (PHPNuxBill) | `ui/ui_custom/customer/footer-public.tpl` di `/DATA/AppData/billing/app` | sisipkan `<a href="https://clusternet.my.id">ClusterNet</a>` di blok `auth-footer` |

Tiga layanan **tidak bisa** disisipi tautan karena antarmukanya sudah ter-*embed*
di dalam aplikasi, bukan berkas HTML terpisah: **AdGuard Home** (UI menyatu di
dalam biner `AdGuardHome` - tidak ada folder `build/static`), **Immich**, dan
**UI ZimaOS** (keduanya SPA ter-*build*). Untuk ketiganya, tab dasbor yang tetap
terbuka adalah satu-satunya jalan pulang.

Mengembalikan berkas billing ke keadaan semula:

```bash
sudo cp -a /DATA/AppData/billing/app/ui/ui_custom/customer/footer-public.tpl.bak-* \
           /DATA/AppData/billing/app/ui/ui_custom/customer/footer-public.tpl
```

Berkas `.bak-*` dibuat tepat sebelum perubahan, jadi salinan itu berisi templat
asli (Smarty menyusun ulang cache-nya sendiri setelah berkas berubah - tidak
perlu menghapus `ui/compiled`).

### Menambah subdomain = otomatis muncul di dasbor

Dulu daftar kartu ditulis tangan di `situs/index.html`, sehingga setiap
subdomain baru harus ditambahkan **dua kali** (Caddyfile dan HTML) dan yang
terlewat akan tampak "hilang" padahal layanannya hidup. Sekarang kartu digambar
oleh `situs/dasbor.js` dari `situs/layanan.json`:

| Berkas | Dibuat oleh | Isinya |
|---|---|---|
| `Caddyfile` | panel / tangan | rute nama domain |
| `situs/layanan.json` | panel (otomatis) | kartu yang tampil di dasbor |
| `situs/dasbor.js` | repo (jarang berubah) | kode perender kartu |

Di panel, tab **Dasbor** mengatur kartu mana yang dipajang. Ini sengaja dipisah
dari tombol **Matikan/Nyalakan** di tab **Layanan**, karena keduanya berbeda:

| Yang diatur | Tempatnya | Akibatnya |
|---|---|---|
| aktif | tab Layanan (Matikan/Nyalakan) | subdomain punya rute di Caddyfile dan bisa dibuka |
| dasbor | tab Dasbor (centang) | kartunya dipajang di halaman utama |

Menyembunyikan kartu **tidak** mematikan layanan: rutenya tetap ada dan
alamatnya tetap bisa dibuka - ia hanya tidak ditampilkan di halaman utama.
Sebaliknya, baris nonaktif tidak bisa dipajang, dan panel menandainya.

Menekan **Terapkan ke ZimaOS** mengirim keduanya: Caddyfile dipasang lebih dulu,
`layanan.json` ditulis **setelah** router terbukti sehat - jadi kartu tidak pernah
muncul mendahului rutenya.

Dua syarat di sisi ZimaOS:

1. **Deployer perlu mount tulis ke folder situs.** Tambahkan pada layanan
   `zima-deployer` (bukan pada `caddy`):

   ```yaml
   zima-deployer:
     volumes:
       - /var/run/docker.sock:/var/run/docker.sock
       - ./Caddyfile:/data/Caddyfile
       - ./situs:/data/situs          # <- baris baru
     environment:
       - DEPLOY_TOKEN=${DEPLOY_TOKEN}
       - SITUS_TARGET=/data/situs/layanan.json   # bawaan, boleh dihilangkan
   ```

   Tombol **Cek koneksi** di panel melaporkan apakah folder itu bisa ditulis.
   Bila belum, panel tetap aman dipakai - ia hanya memperingatkan bahwa kartu
   dasbor tidak akan diperbarui.

2. **Kirim berkasnya sekali** dengan skrip yang sudah ada. SSH port 22 di ZimaOS
   tertutup, jadi jalurnya lewat ttyd (alat yang sama dengan `zima-shell.mjs`):

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\zima-hosting\terbitkan-dasbor.ps1
   ```

   Skrip itu mengirim `index.html`, `dasbor.js`, dan `layanan.json` sekaligus -
   tiap berkas dicadangkan lebih dulu sebagai `.bak-TANGGALJAM` - lalu memeriksa
   bahwa `https://clusternet.my.id/layanan.json` benar-benar dilayani dan halaman
   utamanya sudah memuat `dasbor.js`. Tidak ada restart yang diperlukan: Caddy
   membaca berkas situs langsung dari folder yang di-mount.

   Bila Anda sudah mengubah centang di tab **Dasbor**, unduh manifest hasil panel
   (tab **Hasil Caddyfile** -> kartu *Manifest dasbor* -> **Unduh sebagai
   layanan.json**) lalu berikan lewat `-Manifest`. Tanpa itu, skrip memasang
   susunan bawaan dan centang lama Anda tidak terbawa.

Dua hal yang mudah salah:

- Jangan menaruh logika kartu kembali ke `index.html`: CSP situs ini memakai
  `script-src 'self'`, jadi skrip sebaris akan diblokir browser. Karena itu
  perendernya sengaja berupa berkas `dasbor.js` terpisah.
- `layanan.json` diambil dengan `cache: no-store`, sedangkan `dasbor.js` boleh
  di-cache. Kalau suatu saat kartu tidak ikut berubah, curigai dulu manifestnya
  belum tersalin - bukan browsernya.

## Langkah 5 - Lindungi panel admin dengan Cloudflare Access

UI ZimaOS hanya punya satu password; jangan digantung terbuka di internet.

1. Zero Trust → **Access → Applications → Add an application → Self-hosted**.
2. Domain: `zima.clusternet.my.id` (ulangi untuk panel admin lain).
   (Beda dengan `meshid`, yang isinya hanya baca dan memang dibiarkan publik.)
3. Policy: **Allow** → **Emails** → masukkan email Anda sendiri.
4. Simpan. Sejak itu, siapa pun yang membuka subdomain tersebut harus
   melewati login email (OTP) Cloudflare dulu — server tidak pernah tersentuh
   kalau tidak lolos.

Layanan lain yang sudah punya login sendiri (Nextcloud, Immich, dll.) boleh
dibiarkan publik, tetapi tetap boleh ditambahkan Access bila ingin lebih ketat.

## Langkah 6 - Akses dari LAN tetap enak dipakai

Supaya nama domain yang sama berfungsi di dalam rumah tanpa lewat internet:

- Di DNS internal (server DNS lokal `192.168.20.36` atau router), tambahkan
  wildcard `*.clusternet.my.id` → `192.168.145.252`.
- Caddy sudah dipetakan di host port **8089**, jadi dari LAN:
  `http://adguard.clusternet.my.id:8089` (atau arahkan port 80 router ke sana
  bila tidak bentrok dengan gateway ZimaOS yang memakai port 80 host).

Alternatif paling rapi untuk akses luar tanpa membuka apa pun: **ZeroTier**
(sudah terpasang di jaringan ini) atau Tailscale — hubungkan perangkat ke
jaringan privat itu dan pakai IP privatnya.

## Langkah 7 - Bersihkan jalur lama (penting)

Setelah domain terbukti jalan lewat tunnel:

1. **Hapus port forwarding** di RouterOS/MikroTik untuk 8280, 8080, 22, dan 8728.
2. **Batasi API MikroTik** — lihat `REKOMENDASI-OPTIMASI-SERVER.md` §1:
   `/ip service set api address=192.168.20.0/24,192.168.145.0/24`
3. **Hapus portproxy lama di PC ini** (14 aturan, sebagian sudah mati):

   ```powershell
   netsh interface portproxy show all
   # contoh hapus:
   # netsh interface portproxy delete v4tov4 listenport=8880 listenaddress=0.0.0.0
   ```
4. **Kalau nanti mau pasang email**, pindahkan MX dari `clusternet.my.id` ke
   `mail.clusternet.my.id` dan biarkan nama itu DNS-only (tidak diproksi) —
   record yang diproksi Cloudflare tidak bisa menerima SMTP.

## Verifikasi

Dari PC ini (satu perintah, sekaligus menjalankan audit keamanan):

```powershell
powershell -ExecutionPolicy Bypass -File .\cek-semua.ps1
```

Khusus domain saja:

```powershell
powershell -ExecutionPolicy Bypass -File .\cek-domain.ps1
```

Yang diharapkan setelah selesai:

| Indikator | Sebelum | Sesudah |
|---|---|---|
| `Server:` pada respons HTTPS | kosong / Caddy | **cloudflare** |
| `cf-ray:` | tidak ada | ada |
| HTTPS di `clusternet.my.id` | gagal (443 tertutup) | 200/301 dengan sertifikat valid |
| Subdomain acak | NXDOMAIN | 404 dari Caddy |
| Port publik 8280/8080/22/8728 | terbuka | tertutup |

Bila `Server:` masih `Caddy` atau `Via: ZimaOS-Gateway`, berarti trafik masih
lewat jalur langsung ke IP publik — periksa ulang proxy DNS (harus awan
oranye) dan apakah cloudflared benar-benar tersambung.

## Kalau ada masalah

| Gejala | Penyebab yang paling sering |
|---|---|
| cloudflared restart terus | token salah/terpotong saat salin |
| `502 Bad Gateway` di browser | nama service di Caddyfile salah atau container tujuan mati; cek `docker compose logs caddy` |
| Halaman ZimaOS tampil tapi terminal/websocket mati | UI ZimaOS tidak suka hostname lain; akses admin via ZeroTier/Tailscale saja dan cukup ekspos aplikasi |
| `1033` / DNS tidak berubah | record lama masih DNS-only; hapus record A `103.105.79.7` pada nama itu |
| Situs besar/video terasa dibatasi | Cloudflare gratis bukan CDN media; untuk berkas besar pakai subdomain DNS-only atau layanan lain |

## Rollback

1. Hentikan stack: `docker compose down` (di ZimaOS).
2. Hapus record `CNAME` ke `cfargotunnel.com` dan kembalikan record `A` ke
   `103.105.79.7` untuk nama yang perlu langsung.
3. Nyalakan kembali port forwarding yang diperlukan.

Urutkan sebaliknya dari pemasangan supaya tidak ada periode domain mati.
