# Monitoring Node Meshtastic dengan Prometheus + Grafana

Exporter Prometheus untuk node Meshtastic lewat **API TCP** (port `4403`).
Satu koneksi ke satu node sudah cukup memantau **semua** node yang didengar
node itu — termasuk node `ROUTER` di atas tower yang MQTT-nya mati.

```
Node gateway (TCP 4403) --> exporter :9208 --> Prometheus --> Grafana
```

## Keadaan saat ini (snapshot 28 Sep 2026, gateway `192.168.20.31`)

Catatan lapangan supaya tidak perlu menebak dari nol. Verifikasi ulang dengan
`reset-node.py` (periksa-saja), `favorite-node.py` (periksa-saja),
`bersih-node.py` (periksa-saja), dan `mqtt-downlink.py` (periksa-saja).

| Hal | Keadaan |
| --- | --- |
| Tempat exporter | **host ZimaOS `192.168.20.36`** (systemd), sejak 28 Sep 2026 |
| Alamat publik | **`https://meshid.clusternet.my.id`** (lewat Cloudflare Tunnel) |
| Salinan di mesin kerja Windows | exporter **dinyalakan ulang 28 Sep 2026 19:13** sesudah kedapatan buta (lihat kendala #5); **notifier** lokal sengaja **tidak** dinyalakan agar tidak ada alarm kembar dengan ZimaOS |
| Isi NodeDB | **115 entri** (9 jalur radio + 106 MQTT, 13 Favorite); sempat turun ke 6 entri saat downlink dicabut |
| Timer bersih-bersih NodeDB harian | **TIDAK dipasang** (menunggu keputusan; lihat bagian `bersih-node.py`) |
| Node jalur radio langsung | 4 node RF + gateway sendiri, **semuanya Favorite** |
| Setelan radio gateway | `LONG_FAST` (SF11 / 250 kHz) → lantai demodulasi **-17.5 dB** untuk meter sinyal |
| Downlink MQTT kanal 0 (`LongFast`) | **HIDUP** (sengaja dihidupkan kembali) |
| Uplink MQTT kanal 0 | hidup (tidak pernah dimatikan) |
| Modul MQTT | hidup — `mqtt.meshnode.id`, root `msh/ID` |
| Timer reset 2 harian | **TIDAK dipasang** (sengaja, lihat di bawah) |

Dua pelajaran yang sudah terbukti pada perangkat ini:

1. **Downlink MQTT adalah gerbangnya.** Saat dicabut, isi NodeDB menyusut
   sendiri dari **200 → 6 entri** dalam hitungan menit, tanpa perlu reset.
   Saat dihidupkan lagi, jumlahnya **naik kembali perlahan** menuju ±200
   (naik 6 → 16 hanya dalam beberapa menit).
2. **Favorite adalah jaring pengamannya.** Selama node RF ditandai Favorite,
   mereka lebih terlindungi dari penggusuran meski daftar kembali penuh.

**Timer reset sengaja tidak dipasang.** Reset NodeDB menghapus semua tanda
Favorite, jadi menjadwalkannya berkala akan menghapus perlindungan node RF
berulang kali demi membersihkan daftar yang — selama downlink hidup — memang
akan terisi ulang. Bila suatu saat daftar benar-benar perlu dikosongkan,
lakukan manual sekali, lalu tandai ulang:

```bash
./venv/Scripts/python reset-node.py --ya
./venv/Scripts/python favorite-node.py --ya
```

Bila node RF baru terdaftar bertahap setelah reset, `favorite-node.py` punya
mode jaga yang menandainya begitu muncul:

```bash
./venv/Scripts/python favorite-node.py --ya --jaga 240 \
    --node !da5a16f8,!02ee76d0,!8f4c228c
```

## Kenapa jalur TCP, bukan MQTT?

- Port `4403` adalah API TCP bawaan node Meshtastic.
- Node tersebut menyimpan database semua node yang pernah ia dengar, jadi
  node router di tower ikut terpantau tanpa dia perlu MQTT/internet.
- Tidak bergantung broker publik, dan data tidak keluar jaringan Anda.

## Instalasi

```bash
cd meshtastic-monitor
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Menjalankan

```bash
MESH_HOST=192.168.20.31 ./venv/bin/python exporter-meshtastic.py
```

Buka tampilan web (semua data node + paket masuk):

```
http://<ip-mesin-exporter>:9208/          # halaman HTML, auto-refresh 5 detik
http://<ip-mesin-exporter>:9208/data.json # JSON lengkap
http://<ip-mesin-exporter>:9208/metrics   # metrik Prometheus
http://<ip-mesin-exporter>:9208/lacak/!c483e00a  # lacak satu node (peta + data)
```

Uji cepat lewat terminal:

```bash
curl -s http://localhost:9208/metrics | grep '^meshtastic_'
curl -s http://localhost:9208/data.json | head
```

Contoh tampilan (data contoh, bukan data asli) ada di `contoh-tampilan.html` —
buka berkas itu di peramban untuk melihat tampilan persisnya. Berkas itu
hasil `uji-halaman-meshtastic.py`, jadi selalu ikut halaman terbaru; tab
**Peta** di dalamnya baru terisi kalau dibuka dari exporter yang hidup
(butuh `/data.json`), sedangkan tab **Tabel** tampil apa adanya.

### Variabel lingkungan

| Variabel | Bawaan | Keterangan |
|---|---|---|
| `MESH_HOST` | `192.168.20.31` | Alamat node Meshtastic gateway |
| `MESH_HOST_CADANGAN` | (kosong) | Alamat gateway cadangan, boleh lebih dari satu dipisah koma. Dipakai otomatis oleh exporter bila gateway utama tak bisa dihubungi (lihat **Failover gateway**) |
| `MESH_DATA_CADANGAN` | (kosong) | URL `/data.json` cadangan untuk `notif-meshtastic.py`, boleh lebih dari satu dipisah koma. Dipakai otomatis bila sumber utama tak terbaca |
| `MESH_PORT` | `4403` | Port API TCP node |
| `MESH_EXPORTER_PORT` | `9208` | Port HTTP exporter |
| `MESH_LISTEN` | `0.0.0.0` | Alamat bind exporter |
| `MESH_INTERVAL` | `30` | Detik antar penyegaran data |
| `MESH_OFFLINE_SECS` | `10800` | Ambang "online" (detik) |
| `MESH_PAKET_BUFFER` | `200` | Banyak paket terakhir yang disimpan untuk umpan |
| `MESH_LOG` | `INFO` | Level log |

### Failover gateway

Kalau gateway utama tidak bisa dihubungi, alat tidak langsung menyerah: ia
mencoba alamat di `MESH_HOST_CADANGAN`, lalu **kembali mencoba yang utama** pada
putaran berikutnya. Begitu gateway utama pulih, alat kembali ke sana sendiri
tanpa perlu di-restart.

```sh
MESH_HOST=192.168.20.31 MESH_HOST_CADANGAN=192.168.20.32 ./venv/bin/python exporter-meshtastic.py
```

- Halaman web dan `/data.json` selalu menampilkan gateway yang **sedang dibaca**,
bukan yang dikonfigurasi — jadi sumber yang sedang dipakai tidak menyesatkan.
Header page memuat label **sumber** (`utama`/`cadangan`), dan `/data.json`
menambah kunci `gateway.cadangan`.
- Metrik `meshtastic_exporter_gateway_cadangan` bernilai `1` saat memakai
  cadangan. Aturan alert `MeshtasticGatewayCadangan` berbunyi setelah 5 menit,
  sebagai tanda gateway utama masih perlu diperiksa.
- Notifier `notif-meshtastic.py` tidak menyambung ke gateway; sumbernya adalah
`/data.json`. Karena itu padanannya `MESH_DATA_CADANGAN` (atau
`--data-cadangan`): bila URL utama tak terbaca, notifier bergilir ke URL
cadangan, dan kembali bila sumber utama pulih. Alarm "gateway mati" tetap
berbunyi hanya ketika **semua** sumber gagal — bukan saat cadangan menyelamatkan.
- Cadangan tidak menciptakan data: bila gateway utama mati **dan** tidak ada
cadangan yang menjangkau node lewat radio, tidak ada data baru dari jalur radio.

## Tampilan web: semua data yang masuk ke node

Judul halaman ini **Meshnode-ID Monitor**. Selain `/metrics`, exporter
menyajikan halaman HTML di akar (`/`) yang memisahkan node berdasarkan
**bukti dari perangkat**, bukan tebakan. Dua nilai yang dipakai:

- **`via`** — jalur **paket terakhir** yang dicatat gateway (`diri` / `lora` / `mqtt`);
- **`snr`** — hasil **pengukuran radio gateway sendiri** terhadap node itu.

SNR hanya terisi kalau gateway benar-benar menerima paket node itu lewat udara.
Jadi **SNR yang ada + hop 0 = bukti gateway tersambung LANGSUNG** ke node itu.
Tanpa SNR, kita tidak punya bukti apa pun soal koneksi langsung.

Setiap bagian punya **panah penanda** di depan judulnya: **&#9660;** (biru) berarti
sedang terbuka, **&#9654;** berarti tertutup dan bisa dibuka dengan sekali klik.
Penanda bawaan peramban disembunyikan lewat CSS supaya bentuknya seragam.

**Status buka/tutup diingat.** Halaman ini menyegar sendiri tiap 5 detik; tanpa
diingat, setiap penyegaran akan menutup lagi bagian yang baru saja Anda buka —
menjengkelkan saat sedang membaca tabel MQTT yang panjang. Karena itu status
buka tiap bagian (`details.bagian`, id `bagian-gateway` / `bagian-ragu` /
`bagian-mqtt`) disimpan di **`localStorage`** peramban (`meshid-buka-1`) dan
dipasang kembali setiap halaman dimuat. Simpanan itu menang atas keadaan bawaan
di HTML, jadi bagian yang Anda tinggalkan terbuka akan tetap terbuka; kalau
belum ada simpanan, bawaannya dipakai (hanya bagian pertama yang terbuka).
Status ini per peramban dan per alamat (HTTPS dan LAN dihitung terpisah), dan
hanya menyimpan status buka — bukan isi halaman.

Isi halaman, berurutan:

1. **GATEWAY & NODE YANG TERSAMBUNG LANGSUNG** (terbuka) — baris pertama adalah
   gateway itu sendiri, sisanya node yang **terbukti** tersambung langsung:
   gateway mengukur SNR-nya sendiri dan jaraknya **0 hop**. Node yang sudah
   ditandai Favorite diberi tanda bintang &#9733;.
2. **NODE JALUR RADIO TANPA BUKTI KONEKSI LANGSUNG** (tertutup) — bukan node
   MQTT, tetapi gateway **belum pernah mengukur SNR-nya** dan jaraknya belum
   diketahui. Bisa jadi terakhir terdengar lewat perantara, atau entri lamanya
   masih tersimpan. Begitu gateway menangkap paketnya lewat udara, node itu
   **pindah sendiri** ke tabel di atas.
3. **NODE LEWAT MQTT (INTERNET)** (tertutup) — node dari broker publik;
   **bukan** jaringan radio lokal Anda, dan inilah yang memenuhi daftar node
   gateway. Tanda **"pernah lewat radio"** berarti gateway **juga** pernah
   mendengarnya lewat udara — kemungkinan itu node lokal yang paket terakhirnya
   kebetulan datang dari internet.
4. **Data yang masuk ke node** — umpan paket terakhir: waktu, pengirim, tipe
   (`TELEMETRY_APP`, `POSITION_APP`, dll), SNR, RSSI, dan hop.

**Urutan baris.** Di tiap tabel, node yang **ONLINE** diletakkan lebih dulu
(paling baru terdengar di atas), lalu yang **OFFLINE** turun ke bawah. Node
gateway selalu paling atas karena ia memang tabelnya sendiri. Urutannya stabil
(pemutus seri `node_id`), jadi baris tidak melompat-lompat tiap halaman
menyegar sendiri.

**Data telemetri yang ditampilkan.** Kolom bertambah begitu perangkatnya
melaporkan, dan tetap `-` bila tidak:

| Kolom | Isinya |
| --- | --- |
| **Baterai / Daya** | baterai (+ lencana `charge`), tegangan sungguhan, dan **uptime perangkat** sebagai `up 26m 5s` |
| **Kanal**, **Air TX**, **Hop** | sama seperti sebelumnya, tetap diwarnai menurut ambang |
| **Sinyal (SNR)** | meter tiga batang + kata mutunya (Baik/Cukup/Buruk/Nihil) + angka SNR apa adanya — lihat bagian meter sinyal di bawah |
| **Suhu / RH / hPa** | suhu, lalu kelembapan (`65.0 % RH`) dan tekanan (`1010 hPa`) di baris kecil bila sensornya ada |
| **Lat / Lon / Alt** | koordinat, dengan **ketinggian** di baris kecil bila ada |

Angka-angka itu diambil apa adanya dari NodeDB gateway. Jadi `-` berarti
perangkat **tidak melaporkan**, bukan "nol"; untuk memastikannya lihat
`meshtastic_packets_received_total{portnum="TELEMETRY_APP"}` atau
`meshtastic_device_uptime_seconds` di `/metrics`.

### Meter sinyal per node (kolom "Sinyal (SNR)")

Kolom **Sinyal (SNR)** tidak lagi angka polos: tiap node jalur radio dapat
**meter tiga batang** dengan aturan yang sama seperti aplikasi resmi Meshtastic
([Apple](https://meshtastic.org/docs/software/apple/user/signal-meter/) &
[Android](https://meshtastic.org/docs/software/android/user/signal-meter/)).
Intinya meter itu mengukur **keterbacaan, bukan kuat-lemah**: yang dinilai
adalah jarak SNR paket terakhir dari **lantai demodulasi** preset radio yang
sedang dipakai gateway — bukan dari angka nol, dan bukan dari RSSI.

| Tampilan | Artinya | Syarat |
| --- | --- | --- |
| **Baik** (3 batang, hijau) | margin sehat | SNR **di atas** lantai |
| **Cukup** (2 batang, kuning) | masih terbaca, mulai mendekati lantai | lantai sampai 5,5 dB di bawahnya |
| **Buruk** (1 batang, oranye) | di ujung jangkauan / gangguan berat | 5,5–7,5 dB di bawah lantai |
| **Nihil** (0 batang, merah) | pesan tenggelam di derau | lebih dari 7,5 dB di bawah lantai |

Angka SNR mentahnya tetap dicetak di sebelah meter, jadi tidak ada informasi
yang hilang. Karena radio LoRa memang bisa mendengar **di bawah** lantai derau,
SNR negatif itu normal di Meshtastic — dan SNR yang sama bisa berarti "Baik" di
satu preset dan "Nihil" di preset lain, jadi membandingkan SNR antar-preset
tidak ada artinya.

**Lantainya dibaca dari gateway, bukan ditebak.** Preset LoRa gateway dibaca
saat exporter menyambung, dan angkanya ditulis terbuka di legenda halaman
(mis. `LONG_FAST -> lantai -17.5 dB`), begitu juga di kepala halaman. Bila
setelannya belum terbaca, halaman menulis `tidak terbaca` dan menandai lantai
bawaannya sebagai **asumsi**.

Tabel lantai per preset diambil apa adanya dari tabel lintas-platform yang
dipakai aplikasi Android & Apple (`ChannelOption.kt` /
`ModemPresetSnrLimitTests.swift`) — bukan disusun sendiri:

| Preset | Lantai | Preset | Lantai |
| --- | --- | --- | --- |
| SHORT_TURBO / SHORT_FAST | -7,5 dB | LONG_MODERATE | -17,5 dB |
| SHORT_SLOW | -10 dB | LONG_FAST | -17,5 dB |
| MEDIUM_FAST / LONG_TURBO | -12,5 dB | LONG_SLOW | -20 dB |
| MEDIUM_SLOW | -15 dB | (kustom) | ditaksir dari SF & bandwidth |

> Catatan dari sumbernya: lantai **LONG_SLOW adalah -20 dB** (SF12). Nilai
> -7,5 dB pernah salah tertempel di sana di kedua aplikasi (issue #2041 dan
> #5446), dan akibatnya tautan LongSlow yang sehat dinilai "Buruk". Tabel di
> atas sudah memakai angka yang dikoreksi.

Untuk setelan **kustom** (preset dimatikan) tidak ada nama preset yang bisa
ditabelkan: lantai ditaksir dari spread factor yang benar-benar dilaporkan
gateway (SF7 = -7,5 dB, turun 2,5 dB tiap kenaikan SF, +5 dB bila bandwidth
500 kHz), dan di halaman ditulis sebagai `kustom (SF 12 / 125 kHz)` supaya
tidak dibaca sebagai angka pasti.

**Node jalur MQTT sengaja TIDAK diberi meter.** Gateway tidak mendengarnya
lewat udara sama sekali; SNR yang tersimpan untuk node seperti itu datang dari
radio orang lain di internet, jadi menggambarnya sebagai "sinyal Anda" akan
menyesatkan. Selnya berisi `– lewat internet`. RSSI tidak ikut ke meter per
node karena NodeDB tidak menyimpannya — RSSI ada per **paket** di tabel "Data
yang masuk ke node".

Angka mutunya juga tersedia untuk dasbor/alert di `/data.json` sebagai
`mutu_sinyal` (0-3, `null` untuk node MQTT) di tiap node, plus `lantai_snr`,
`preset`, `spread_factor`, dan `bandwidth` di `kesehatan_gateway`.

Ada **dua kotak saring** yang berbagi satu kata saringan: satu di atas ketiga
tabel, satu lagi **tepat di atas tabel MQTT** — tabel terpanjang di halaman ini
(ratusan node), dan tempat saringan paling sering dipakai untuk mencari satu
node di tengah lautan node internet. Ketik nama atau ID (mis. `ROUTER`, `MOB`,
`!da5a16f8`) di kotak mana pun: baris yang tidak cocok disembunyikan di ketiga
tabel sekaligus, dan kotak yang lain ikut terisi. Tempat penunjuk di kotak MQTT
langsung menyebut jumlahnya, mis. `saring 106 node MQTT: nama atau ID`.

Kata saringnya **tetap tersimpan** saat halaman menyegar sendiri tiap 5 detik,
dan **fokus kotaknya juga dikembalikan** ke kotak yang terakhir dipakai — jadi
bisa langsung melanjutkan mengetik tanpa klik ulang. Ada tiga tempat
penyimpanan, sengaja berlapis:

| Tempat | Kunci | Gunanya |
| --- | --- | --- |
| `localStorage` | `meshid-saring-1` | bertahan walau alamat dibuka ulang dari awal; inilah yang membuat saringan tidak hilang saat menyegar |
| `#hash` alamat | — | tautan hasil saringan bisa dibagikan apa adanya; **menang** atas `localStorage` supaya tautan yang dikirim orang lain tidak ketimpa saringan lama penerima |
| `sessionStorage` | `meshid-saring-fokus` | kotak yang terakhir dipakai, agar fokus kembali ke kotak itu (bukan selalu kotak paling atas) |

Jumlah baris yang cocok ditampilkan di sebelah **kedua** kotak (`12 node
cocok`), dan saringan dikosongkan untuk menampilkan semuanya lagi.

Kartu di bagian atas menunjukkan angka yang paling sering dicari: **langsung ke
gateway**, **radio ada bukti SNR**, **radio belum ada bukti**, **lewat MQTT
(internet)**, dan **online**.

**Kerapian tabel.** Setiap tabel duduk di kotak yang bisa digulir **sendiri**
(`overflow:auto`) dengan nama kolom **lengket** di atas, jadi tabel yang lebih
lebar dari layar tidak lagi menyeret seluruh halaman ke kanan. Jumlah kolomnya
12, bukan 14: peran dan jenis perangkat pindah ke baris kecil di bawah nama,
dan tegangan pindah ke bawah angka baterai — datanya tetap ada, hanya tidak
lagi memakan kolom sendiri. Angka rata kanan dan tidak boleh terpotong dua
baris (`tabular-nums`), dan kolom **Via** kini berbentuk lencana berwarna:
<span>**LORA**</span> hijau, **MQTT** abu-abu, **DIRI** biru.

### Logo dan ikon tab

Logo di samping judul dan ikon pada tab peramban **tidak** disisipkan ke dalam
HTML, melainkan dilayani sebagai berkas terpisah di `/logo.png` dan
`/favicon.png` dengan header `Cache-Control: max-age=86400`. Alasannya: halaman
ini menyegar sendiri tiap 5 detik, jadi logo yang disisipkan (mis. base64) akan
terunduh ulang di setiap penyegaran dan halaman membengkak.

Berkasnya dibuat dari logo asli oleh `siapkan-logo.ps1`, yang lebih dulu
**memangkas pinggiran transparan** lalu mengecilkannya (tanpa pemangkasan itu,
logo dengan banyak ruang kosong tampil kecil walau berkasnya besar):

```powershell
cd meshtastic-monitor
powershell -NoProfile -File siapkan-logo.ps1
# atau menunjuk berkas lain:
powershell -NoProfile -File siapkan-logo.ps1 -Sumber D:\lain\logo.png
```

Menghasilkan `meshnodeid-256.png` (kepala halaman, ~76 KB) dan
`meshnodeid-64.png` (ikon tab, ~9 KB). **Keduanya harus ikut diunggah** bersama
`exporter-meshtastic.py`; bila tidak ada, exporter tetap hidup dan hanya menulis
peringatan di log — halaman tampil tanpa logo, bukan ikon gambar rusak.

### Warna ambang di kolom Kanal, Air TX, dan Hop

Tiga kolom diberi warna menurut **pedoman operasional yang sama dipakai dasbor
komunitas Meshtastic**, supaya angkanya bisa dibandingkan antarperkakas. Arahkan
kursor ke angkanya untuk melihat tingkatannya; ringkasannya juga ditampilkan di
halaman pada kotak **"Ambang yang dipakai halaman ini"**.

| Kolom | Hijau | Kuning | Oranye | Merah |
| --- | --- | --- | --- | --- |
| **Kanal** (utilisasi) | <25% sehat | 25–40% sedang, pengiriman mulai tertahan | 40–50% tinggi, pembaruan GPS dikurangi | >50% padat, kelebihan beban |
| **Air TX** (airtime) | <5% bagus | 5–8% wajar | — | >8% kelebihan, kurangi pancaran |
| **Hop** | 0 langsung | 1–2 dekat | 3–4 jauh | ≥5 sangat jauh |

Angka tepat di batas masuk ke tingkat berikutnya (mis. tepat 25% sudah dibaca
"sedang", 5% sudah "wajar"), karena pedoman menyebut "**mulai** 25%".

### Kolom Baterai dan Tegangan (arti tampilannya)

| Yang tampil | Artinya |
| --- | --- |
| **charge** | perangkat **tersambung listrik/USB**. Firmware memakai skala 0–101 dan kode **101 = powered**, bukan "baterai 101%" (lihat meshtastic/firmware#4158) |
| angka persen, mis. `78%` | perangkat benar-benar berjalan dengan baterai |
| `–` | perangkat **tidak melaporkan** nilai itu (di jaringan kita: 65 dari 117 node) |
| tegangan `–` | tegangan membulat ke nol (derau ADC saat tidak ada penginderaan baterai, mis. `-0.001 V`) — bukan kerusakan |

**Nilai mentah tidak diubah.** `meshtastic_device_battery_level_percent` tetap
melaporkan `101` untuk perangkat bertenaga listrik, dan tegangan tetap `-0.001`.
Jadi perhatikan saat menulis alert: `battery < 20` tidak akan pernah menyala
untuk node bertenaga listrik, dan juga tidak menyala untuk node yang **tidak
melaporkan** baterai sama sekali — pastikan dulu node itu memang mengirim
telemetri perangkat (lihat `meshtastic_packets_received_total{portnum="TELEMETRY_APP"}`).

> Tampilan ini **hanya memengaruhi halaman**, bukan isi metrik: nilai mentah di
> `/metrics` dan `/data.json` tetap apa adanya. Jadi alert Prometheus tetap
> memakai ambangnya sendiri (lihat `alert-meshtastic.yml`) dan tidak ikut berubah
> saat warna di halaman disesuaikan.

Halaman menyegar sendiri tiap 5 detik. Versi mesin dari data yang sama ada di
`/data.json` untuk dipakai skrip lain.

### Tab "Peta langsung" & halaman lacak `/lacak/<node_id>`

Selain tabel, halaman punya **dua tab**: **Tabel node** (bawaan, seperti
sebelumnya) dan **Peta langsung**. Peta memakai data yang sudah ada di
`/data.json`, jadi tidak ada sumber data baru yang perlu dirawat.

- **Satu penanda per node**, warnanya mengikuti status & jalur paket terakhir:
  **hijau** = online lewat radio, **biru** = node gateway sendiri, **abu-abu** =
  online lewat MQTT (internet), **merah** = offline. Node tanpa koordinat tidak
  dipetakan, dan jumlahnya ditulis di atas peta supaya tidak tampak "hilang".
- **Klik penanda** membuka popup berisi data node (status, jalur, terakhir
  terdengar, sinyal, hop, baterai, posisi, ketinggian, perangkat) plus dua
  tombol: **Tengahin ke peta** dan **Lacak node ini**.
- **Tautan lacak dibentuk otomatis** dari id node: `/lacak/<node_id>`
  (mis. `/lacak/!c483e00a`). Halaman itu fokus ke satu node: peta disorot ke
  node itu (penandanya lebih besar) dan panel datanya diisi dari `/data.json`,
  lengkap dengan tautan kembali ke monitor node.

Dua keputusan yang perlu diketahui:

1. **Penyegaran halaman dimatikan di tab Peta.** Halaman ini menyegar sendiri
   lewat `<meta http-equiv="refresh" content="5">`; di tab Peta meta itu justru
   membangun ulang peta tiap 5 detik sehingga posisi/zoom yang sedang dilihat
   hilang. Jadi di tab Peta meta itu dilepas dan peta menyegar datanya sendiri
   lewat `/data.json` tiap 5 detik. Tab yang dipakai diingat di `localStorage`
   (`meshid-tab-1`), jadi penyegaran tidak mengembalikannya ke Tabel; kembali
   ke tab Tabel memuat ulang halaman supaya penyegaran 5 detiknya hidup lagi.
2. **Peta butuh internet.** Pustaka peta (Leaflet) dan basemap (OpenStreetMap)
   diambil dari CDN dan **hanya saat tab Peta dibuka** - halaman tabel yang
   menyegar tiap 5 detik tidak ikut mengunduhnya. Tanpa internet peta tidak
   tampil (ada pesan di panelnya), tetapi tabel node tetap berfungsi.

Untuk node yang **tidak ada** di database gateway, `/lacak/<id>` dijawab
**404** beserta penjelasannya - bukan diam-diam menampilkan halaman lain -
supaya tautan yang rusak terlihat rusak. Karena id node datang dari alamat,
id itu selalu di-escape sebelum ditempel ke halaman.

### Alamat untuk membukanya

Sejak exporter pindah ke host ZimaOS (28 Sep 2026), alamat yang dipakai
sehari-hari adalah:

| Dari mana | Alamat |
| --- | --- |
| Dari internet / HP (juga dari LAN) | **`https://meshid.clusternet.my.id/`** |
| Di host ZimaOS sendiri | `http://127.0.0.1:9208/` |
| Perangkat lain di LAN (HP, laptop, Grafana) | `http://192.168.20.36:9208/` |
| Metrik Prometheus | `https://meshid.clusternet.my.id/metrics` |
| JSON lengkap | `https://meshid.clusternet.my.id/data.json` |
| Peta & lacak satu node | `https://meshid.clusternet.my.id/lacak/!c483e00a` |
| Logo kepala halaman | `https://meshid.clusternet.my.id/logo.png` |
| Ikon tab peramban | `https://meshid.clusternet.my.id/favicon.png` |

Catatan rute: Caddy di host ZimaOS meneruskan
`meshid.clusternet.my.id` → `192.168.20.36:9208` (blok di
`zima-hosting/Caddyfile`). Karena wildcard `*.clusternet.my.id` sudah
didaftarkan ke tunnel, **tidak ada** perubahan DNS atau tunnel yang diperlukan.
Halaman ini sengaja **publik tanpa Cloudflare Access** (keputusan pemilik) —
sadarilah isinya memuat koordinat GPS node. Detail rute, cara mengubah, dan
tempat pindahnya ada di `CATATAN-MESHNODEID.md` di akar repo.

### Hanya SATU program boleh menyambung ke radio pada satu waktu

API jaringan node Meshtastic (port **4403**) melayani **satu klien saja**.
Bila ada program kedua menyambung, sambungan yang pertama diputus oleh
firmware — dan program pertama itu (termasuk exporter kita) **tidak selalu
sadar** sambungannya sudah dicabut (lihat kendala #5). Jadi:

- **Jangan** menjalankan exporter di dua mesin sekaligus (mis. ZimaOS **dan**
  mesin Windows). Pilih satu pemegang radio; mesin lain sebaiknya membaca
  `/data.json` si pemegang, bukan menyambung sendiri ke `4403`.
- Perkakas sekali jalan (`lihat-data-node.py`, `traceroute-node.py`,
  `catat-node.py`, `reset-node.py`) **memutus** sambungan exporter selama
  ia berjalan, lalu exporter pulih sendiri di putaran berikutnya. Itu wajar:
  halaman akan tampak diam beberapa detik, bukan rusak.
- Bila gateway sendiri sering reboot (`meshtastic_gateway_reboot_count` naik,
  `uptime` kecil), sambungan juga terputus sesering itu — cek catu daya node.

### Bila masih dijalankan di mesin Windows (cara lama)

Exporter di mesin Windows mendengarkan di `0.0.0.0:9208`, jadi yang menentukan
bisa-tidaknya diakses dari perangkat lain adalah **firewall Windows**, bukan
programnya. Wi-Fi mesin ini berkategori **Public**, dan bawaan Windows menolak
koneksi masuk pada profil itu. Karena itu perlu satu aturan izin (sekali saja,
butuh administrator) — hanya berlaku untuk cara lama ini:

```powershell
netsh advfirewall firewall add rule name="Meshtastic Exporter 9208" ^
  dir=in action=allow protocol=TCP localport=9208 profile=any remoteip=LocalSubnet
```

`remoteip=LocalSubnet` membatasi izin **hanya untuk subnet lokal** — jadi port
ini tidak terbuka ke internet. Mencabut izin:

```powershell
netsh advfirewall firewall delete rule name="Meshtastic Exporter 9208"
```

> Prometheus/Grafana di host ZimaOS **wajib** bisa menjangkau port ini. Jadi bila
> Anda memindahkan exporter ke ZimaOS kelak, aturan ini tidak lagi diperlukan di
> mesin Windows.

## Menjaga node RF tetap terdaftar di gateway (PENTING)

Satu node Meshtastic menyimpan daftar semua node yang ia dengar, dan daftar itu
**punya batas**. Saat penuh, Meshtastic membuang node "terlama dan paling tidak
menarik". Pada kasus Anda daftarnya terisi 200 entri dengan 195 node internet,
sementara node RF Anda memancar jarang — jadi ada risiko nyata node router tower
**tergeser keluar** dari daftar, dan monitoring kehilangan objeknya tanpa error.

Tiga langkah pencegahan, dari yang paling murah:

1. **Tandai node RF Anda sebagai Favorite.** Lewat aplikasi Meshtastic (daftar
node → pilih node → tandai Favorite) atau lewat `favorite-node.py` di bawah.
Node favorit lebih terlindungi dari penggusuran. Notifier juga mengingatkan
sekali per node bila ada node LoRa yang belum ditandai.
2. **Kurangi masuknya node internet.** Matikan **downlink MQTT** di gateway
(biarkan uplink tetap hidup) supaya node tidak menarik seluruh mesh publik ke
dalam daftarnya — caranya otomatis lewat `mqtt-downlink.py` di bawah.
3. **Pantau tandanya.** Halaman web exporter dan `notif-meshtastic.py` sekarang
melaporkan: isi database (`meshtastic_gateway_nodedb_count`), node yang hilang
dari daftar, dan saran Favorite.

## Tandai Favorite otomatis (`favorite-node.py`)

Langkah perlindungan termurah, dan sebaiknya dikerjakan **sebelum** reset apa pun.

```bash
./venv/Scripts/python favorite-node.py                 # PERIKSA SAJA (bawaan)
./venv/Scripts/python favorite-node.py --ya            # tandai semua node RF
./venv/Scripts/python favorite-node.py --ya --node !da5a16f8,!02ee76d0
./venv/Scripts/python favorite-node.py --ya --lepas     # rollback
```

Lingkup bawaannya sengaja sempit: hanya node yang terdengar **langsung lewat
radio** dan **bukan** gateway sendiri. Ratusan node MQTT di daftar Anda **tidak**
ikut ditandai — menandainya justru menghabiskan slot yang sedang kita lindungi.

## Matikan downlink MQTT (`mqtt-downlink.py`) — akar masalahnya

Ini **penyembuh**. Kalau NodeDB Anda penuh oleh node internet, penyebabnya cuma
satu: gateway menarik paket dari broker MQTT publik, dan tiap pengirimnya ikut
tercatat sebagai node. Matikan arus masuk itu, dan daftar berhenti terisi sendiri.

Tombol yang dipakai (dibaca dari perangkat Anda, bukan dugaan):

| Setelan | Arti | Ada di |
| --- | --- | --- |
| `downlink_enabled` | paket dari MQTT diterima & diolah | `ChannelSettings` per kanal |
| `proxy_to_client_enabled` | node memakai internet **milik klien** (bukan meneruskan paket ke klien) | `MQTTConfig` |

> **Koreksi 28 Sep 2026.** Dokumentasi resmi Meshtastic menyebut Client Proxy
> sebagai *"let the device use the client's (e.g. your phone's) network
> connection"* — arahnya kebalikan dari yang semula tertulis di catatan ini.
> Untuk gateway yang internetnya dari WiFi sendiri, tombol ini harus **mati**.
> Uji lapangan: dengan proxy hidup, selama 2,5 menit **0 paket** MQTT sampai ke
> klien API, jadi tombol ini memang bukan jalur pembacaan pesan.

```bash
./venv/Scripts/python mqtt-downlink.py                 # PERIKSA SAJA (bawaan)
./venv/Scripts/python mqtt-downlink.py --ya            # matikan downlink
./venv/Scripts/python mqtt-downlink.py --ya --matikan-proxy
./venv/Scripts/python mqtt-downlink.py --ya --nyalakan  # rollback
```

Alat ini **hanya** mematikan downlink; **uplink tetap hidup**, jadi node Anda
masih melapor ke MQTT/map. `--kanal N` membatasi ke kanal tertentu. Menulis
setelan membuat gateway memuat ulang setelannya (biasanya disertai reboot
singkat), lalu kirim kabar ke ntfy.

**Cara memastikan berhasil:** buka `reset-node.py` atau halaman web exporter
beberapa jam kemudian. Bila isi NodeDB berhenti naik, downlink memang gerbangnya.

Pengamatan nyata pada gateway `192.168.20.31` (27 Sep 2026): setelah downlink
dimatikan, isi NodeDB **menyusut sendiri dari 200 menjadi 6 entri** dalam
hitungan menit tanpa perlu reset — entri jalur MQTT ikut hilang. Jadi reset
biasanya **tidak diperlukan**; ambang `--hanya-jika-penuh` pun menolaknya.

Cara mengembalikannya (bila kelak ingin arus MQTT masuk lagi):

```bash
./venv/Scripts/python mqtt-downlink.py                 # lihat keadaan sekarang
./venv/Scripts/python mqtt-downlink.py --ya --nyalakan  # hidupkan downlink lagi
```

Sadari konsekuensinya: begitu downlink hidup lagi, ratusan node internet akan
kembali memenuhi daftar dalam hitungan jam. Perlindungan Favorite untuk node RF
tetap berlaku, tetapi kuota daftar kembali terpakai.

## Bersih-bersih NodeDB (`bersih-node.py` + timer)

> **Ini pilihan utama sebelum `reset-node.py`.** Dipakai saat daftar node mulai
> penuh oleh node yang sudah lama tidak terdengar.

`bersih-node.py` meminta gateway **menghapus satu per satu** node yang sudah
lama tidak terdengar — jadi slot NodeDB kembali lega tanpa menyentuh node yang
masih hidup. Ini berbeda dari `reset-node.py`, yang mengosongkan **seluruh**
daftar (termasuk node RF Anda) dan menghapus semua tanda Favorite.

Patokan umurnya `lastHeard` dari NodeDB: waktu paket terakhir yang membuat node
itu tercatat, baik lewat radio maupun lewat MQTT. Ambangnya **5 hari** dan bisa
diubah (`--hari N` atau `MESH_HAPUS_HARI`).

```bash
# 1. selalu mulai dari periksa-saja (bawaan: tidak menghapus apa pun)
./venv/Scripts/python bersih-node.py

# 2. baru jalankan sungguhan bila jalur admin terbukti OK
./venv/Scripts/python bersih-node.py --ya

# ambang lain, atau ikut menghapus node jalur radio
./venv/Scripts/python bersih-node.py --hari 2
./venv/Scripts/python bersih-node.py --ya --hari 5 --termasuk-radio
```

**Pelindung yang menyala secara bawaan** — semuanya bisa dibuka dengan sadar:

| Yang dilindungi | Bawaan | Cara membukanya |
| --- | --- | --- |
| Gateway itu sendiri | selalu aman | — (tidak bisa dibuka) |
| Node **Favorite** | dilewati | `--termasuk-favorit` |
| Node **jalur radio** (bukan MQTT) | dilewati | `--termasuk-radio` |
| Node tanpa `lastHeard` | dilewati | — (umur tak diketahui ≠ lama) |
| Id tertentu (mis. node penting) | — | `--kecuali !da5a16f8,!02ee76d0` |
| Jumlah per sekali jalan | 200 | `--batas N` |

Alasan node **jalur radio** dilindungi: node `ROUTER` bisa hanya memancar
beberapa kali sehari, jadi gampang lewat beberapa hari padahal baik-baik saja.
Sasaran bawaannya adalah node jalur MQTT — justru itulah yang membanjiri daftar.

**Hasil pengukuran nyata** di gateway `192.168.20.31` (28 Sep 2026, 115 entri:
9 jalur radio + 106 MQTT):

| Ambang | Node yang melewati ambang | Di antaranya |
| --- | --- | --- |
| > 5 hari | 1 | 1 jalur radio, 1 Favorite — **dilindungi**, jadi 0 yang dihapus |
| > 12 jam | 12 | 11 MQTT, 1 radio, 3 Favorite |
| > 6 jam | 26 | 25 MQTT |
| > 3 jam | 38 | 37 MQTT |
| > 1 jam | 58 | 57 MQTT |

Artinya ambang 5 hari memang paling aman, tetapi efeknya kecil: node MQTT yang
masih hidup terus memperbarui waktunya. Kalau tujuan Anda benar-benar
**mengosongkan daftar**, yang bekerja adalah ambang yang lebih pendek
(1-6 jam) — dan sesudah itu keran tetap perlu ditutup dengan `mqtt-downlink.py`,
karena selama downlink hidup node-node itu akan masuk kembali.

**Cara alat ini membuktikan hasilnya.** Setelah menghapus, ia menutup sambungan,
menyambung ulang, lalu **membaca ulang NodeDB** dan melaporkan berapa yang
benar-benar hilang dan berapa yang masih tercatat — jadi laporan "berhasil"
tidak berdasarkan asumsi. Ia juga menulis penanda `bersih-terakhir.json`
(untuk pengaman `--jeda-min-jam`) dan mengirim ringkasan ke ntfy.

> Catat: alat ini memakai koneksi TCP ke gateway, dan API node Meshtastic hanya
> melayani **satu klien** — exporter akan tergeser sebentar lalu menyambung ulang
> sendiri (halaman pemantau bisa basi 1-2 menit). Sama seperti `reset-node.py`.

### Jadwalkan harian (systemd)

> **Tidak dipasang secara bawaan.** Pasang bila memang ingin berjalan sendiri.

`meshtastic-bersih.timer` menjalankan `meshtastic-bersih.service` **setiap hari
pukul 03:30** (setelah jadwal reset, bila itu juga dipasang), dengan
`RandomizedDelaySec=600` dan `Persistent=true`.

```bash
MESH_PASANG_BERSIH=1 sudo sh /DATA/AppData/meshtastic-monitor/pasang-layanan.sh

# lihat jadwal berikutnya & uji jalan sekarang
systemctl list-timers meshtastic-bersih.timer
sudo systemctl start meshtastic-bersih.service
journalctl -u meshtastic-bersih.service -n 40 --no-pager
```

Service memakai `--ya --jeda-min-jam 20 --jeda 1.0`: `--jeda-min-jam 20`
mencegahnya berjalan dua kali sehari akibat `Persistent` mengejar jadwal setelah
reboot, dan `--jeda 1.0` memberi napas firmware di antara perintah admin (satu
perintah per node). Ambangnya diatur lewat `Environment=MESH_HAPUS_HARI=5` di
dalam unit — tidak perlu menyunting skrip.

Seluruh aturan pemilihan di atas bisa diuji tanpa gateway sama sekali:

```bash
./venv/Scripts/python uji-bersih-node.py      # 61 uji, gateway palsu
```

## Reset NodeDB berkala (`reset-node.py` + timer)

> **Ini obat sementara, bukan penyembuh.** Selama **downlink MQTT** masih hidup,
ratusan node internet akan mengisi ulang daftar dalam hitungan jam. Reset hanya
membeli waktu. Penanganan yang benar tetap: matikan downlink MQTT, pakai broker
sendiri, atau channel privat.

`reset-node.py` memerintahkan gateway mengosongkan daftar node (NodeDB).
**Aman secara bawaan**: tanpa `--ya`, alat ini hanya membaca dan menguji jalur
admin (minta metadata), tidak mengubah apa pun.

```bash
# 1. selalu mulai dari periksa-saja (bawaan)
./venv/Scripts/python reset-node.py

# 2. baru jalankan sungguhan bila jalur admin terbukti OK
./venv/Scripts/python reset-node.py --ya --hanya-jika-penuh 190
```

Efek samping yang harus disadari sebelum menjadwalkannya:

- daftar node jadi **kosong**, termasuk node RF Anda — mereka terdaftar ulang
  saat terdengar lagi (node `ROUTER` bisa perlu beberapa jam);
- tanda **Favorite ikut hilang** bersama entri node, jadi tandai ulang setelah
  node muncul kembali;
- gateway memuat ulang daftarnya; ada jeda singkat saat belum mengenal node lain.
- penghitung `reboot_count` gateway akan naik pada tiap reset — jangan bingung
  bila `MeshtasticGatewayReboot` berbunyi setelah reset terjadwal.

`reset-node.py` menulis penanda `reset-terakhir.json` setiap kali benar-benar
reset. `notif-meshtastic.py` membacanya dan **menahan alarm "node hilang"**
selama jendela tenang (bawaan 1800 detik) supaya Anda tidak dibanjiri alarm palsu
akibat reset itu sendiri. Atur dengan `--jendela-notif DETIK` /
`NOTIF_JENDELA_RESET`, atau matikan dengan `--jendela-reset 0`.

### Jadwalkan tiap 2 hari malam hari (systemd)

> **Tidak dipasang secara bawaan.** Baca peringatan di bawah dahulu; memasang
> timer ini berarti menyetujui bahwa Favorite Anda akan terhapus tiap reset.

`meshtastic-reset.timer` menjalankan `meshtastic-reset.service` pada tanggal
ganjil pukul **02:30** (`OnCalendar=*-*-1/2 02:30:00`), dengan
`RandomizedDelaySec` dan `Persistent=true` (mengejar jadwal yang terlewat bila
mesin sempat mati).

```bash
sudo cp meshtastic-reset.service meshtastic-reset.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meshtastic-reset.timer

# lihat jadwal berikutnya & uji jalan sekarang
systemctl list-timers meshtastic-reset.timer
sudo systemctl start meshtastic-reset.service
```

Service memakai `--ya --hanya-jika-penuh 190 --jeda-min-jam 36 --jendela-notif
1800`:

- `--hanya-jika-penuh 190` — reset hanya bila daftar hampir penuh, jadi tidak
  mengosongkan daftar yang masih sehat;
- `--jeda-min-jam 36` — pengaman agar tidak dobel bila `Persistent` mengejar
  jadwal setelah restart;
- `--jendela-notif 1800` — masa tenang alarm "node hilang" pasca reset.

> Tanggal 31 → 1 menyeberang bulan jadi berselang 1 hari; tidak masalah karena
> `--jeda-min-jam 36` mencegah reset beruntun.

Tanpa systemd (mis. Windows Task Scheduler atau cron), cukup panggil perintah
yang sama dua hari sekali pada dini hari:

```
0 2 */2 * *  cd /opt/meshtastic-monitor && ./venv/bin/python reset-node.py --ya --hanya-jika-penuh 190 --jeda-min-jam 36
```

## Kalibrasi ambang offline (`catat-node.py`)

Node berperan `ROUTER` hanya memancarkan telemetry sendiri sekitar tiap 12 jam.
Bila `MESH_OFFLINE_SECS` lebih pendek dari irama alami node, Anda akan menerima
alert offline **palsu** setiap hari. Karena itu ukur dulu iramanya:

```bash
# rekam 24 jam (baca dari exporter yang sedang jalan)
python catat-node.py --durasi 24

# atau ambil sendiri dari node, tanpa exporter
./venv/Scripts/python catat-node.py --langsung --durasi 24

# lihat hasil kapan saja
python catat-node.py --laporan
```

Alat ini mencatat sampel tiap 60 detik, mencari kapan tiap node **mengirim paket
baru**, lalu melaporkan jeda terpendek/median/**terpanjang** dan
merekomendasikan `MESH_OFFLINE_SECS` sekitar **2× jeda terpanjang**. Contoh
keluaran untuk node yang memancar tiap 1–2 jam:

```
   !da5a16f8  -> MESH_OFFLINE_SECS >= 14400 (4j 0m)
```

Jalankan pencatatan ini **sebelum** mengaktifkan alert offline. Node `ROUTER`
bisa hanya memancar beberapa kali sehari, jadi butuh data 24 jam sebelum
angkanya bisa dipercaya.

## Pasang sebagai layanan

### Tercepat: jalankan di mesin Windows (`mulai-layanan.bat`)

Cara paling cepat menghidupkan pemantauan: jalankan di **mesin kerja yang sudah
satu LAN dengan gateway** — tanpa sandi, tanpa SSH, tanpa `venv` baru, karena
pustaka `meshtastic` sudah terpasang di `venv` folder ini.

**Klik dua kali `mulai-layanan.bat`** (atau `cmd //c mulai-layanan.bat`).
Hentikan dengan `hentikan-layanan.bat`.

Skrip itu **mematikan dulu** layanan yang masih jalan sebelum menyalakan yang
baru, lalu menyalakan tepat satu exporter dan satu notifier. Jadi aman ditekan
berulang kali — tidak ada layanan kembar. Setelah dijalankan, tampilan daftar
proses akan memperlihatkan **dua** `python.exe` per layanan:

```
venv\Scripts\python.exe -satu-tugas-...   -> peluncur venv (induk)
C:\Espressif\tools\python\python.exe ...  -> interpreter dasar (anak), PEMEGANG port 9208
```

Ini normal, bukan layanan ganda: `venv\Scripts\python.exe` di mesin ini adalah
**peluncur** yang menjalankan interpreter dasar dari `pyvenv.cfg` sebagai proses
anak dengan argumen yang sama. Rinciannya di catatan kendala nomor 4.

| Berkas | Isi |
| --- | --- |
| `exporter.err.log` | log exporter (modul `logging` Python menulis ke **stderr**) |
| `exporter.log` | keluaran biasa exporter (biasanya kosong) |
| `notif.log` | log notifier |
| `notif-meshtastic-state.json` | status terakhir yang dipakai notifier |

Berkas `.bat` ini sudah memuat setelan yang sama dengan unit systemd: gateway
`192.168.20.31:4403`, port exporter `9208`, `MESH_OFFLINE_SECS=10800`, cakupan
`NOTIF_LINGKUP=lora`, dan kanal ntfy yang sama.

> Keterbatasan yang harus disadari: proses ini **mati saat mesin dimatikan atau
> pengguna log out**. Untuk pemantauan 24/7, pindahkan ke host ZimaOS (di bawah)
> yang selalu hidup.

Uji cepat setelah dijalankan:

```bash
curl -s http://127.0.0.1:9208/metrics | grep meshtastic_exporter_up
curl -sI http://127.0.0.1:9208/logo.png | head -3      # gambar halaman
# atau buka di browser: http://127.0.0.1:9208/
```

### Otomatis penuh (`pasang-otomatis.ps1`)

Setelah bagian ini dipasang, **tidak ada lagi yang perlu diklik**:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File pasang-otomatis.ps1
# mencopot otomatisasi:
powershell -NoProfile -ExecutionPolicy Bypass -File pasang-otomatis.ps1 lepas
```

Skrip itu mendaftarkan satu tugas Task Scheduler bernama **`Meshtastic Monitor`**
yang menjalankan `pastikan-hidup.ps1` dengan dua pemicu — **saat log in** dan
**berkala tiap 10 menit**. Pendaftaran tugas butuh hak **administrator**
(sekali saja); menjalankannya tidak.

`pastikan-hidup.ps1` sendiri idempoten dan mengerjakan tiga hal:

1. menyalakan **exporter** bila belum jalan;
2. menyalakan **notifier** bila belum jalan;
3. menjalankan `favorite-node.py --ya` supaya **node radio langsung yang baru
   muncul langsung ditandai Favorite** — perlindungan tanpa disuruh.

Semua kejadiannya dicatat di `pastikan-hidup.log`. Contoh isi nyata:

```
2026-09-27 23:13:39 menyalakan exporter-meshtastic.py (sebelumnya tidak jalan)
2026-09-27 23:26:04 Favorite otomatis: !6394c14e  Joni Elpiji  -> Favorite
```

> **Yang sengaja TIDAK diotomatiskan: reset NodeDB.** Reset menghapus semua
tanda Favorite, jadi menjadwalkannya justru merusak perlindungan yang sedang
dibangun otomatisasi di atas. Kalau daftar benar-benar perlu dikosongkan,
lakukan manual sekali lalu biarkan penjaga menandai ulang.

Perintah berguna:

```powershell
Get-ScheduledTaskInfo -TaskName 'Meshtastic Monitor'   # hasil & jadwal berikut
Start-ScheduledTask -TaskName 'Meshtastic Monitor'     # paksa satu putaran

# menjalankan penjaga langsung dari terminal - WAJIB pakai -ExecutionPolicy Bypass,
# kalau tidak PowerShell menolak: "running scripts is disabled on this system"
powershell -NoProfile -ExecutionPolicy Bypass -File pastikan-hidup.ps1
```

Setelah penjaga menyalakan layanan, daftar proses akan memperlihatkan **dua**
`python.exe` per layanan (peluncur venv + interpreter dasarnya). Itu normal —
lihat catatan kendala nomor 4.

### ZimaOS — kirim dari Windows, lalu pasang di host

**Status: sudah terpasang dan inilah instalasi yang hidup** (28 Sep 2026).
`meshtastic-exporter.service` + `meshtastic-notif.service` berjalan di
`/DATA/AppData/meshtastic-monitor`, halaman webnya dipublikasikan sebagai
`https://meshid.clusternet.my.id`. Salinan di mesin Windows sudah dimatikan
(lihat `CATATAN-MESHNODEID.md` di akar repo untuk peta lengkap dan cara
perawatan).

Host ZimaOS dari LAN adalah **`192.168.20.36`** (bukan `192.168.200.253` — itu
antarmuka lain untuk pemantauan MikroTik). ZimaOS memakai systemd tetapi **tidak
memasang cron**, jadi penjadwalan lewat systemd timer adalah cara paling andal di
host itu.

**Langkah 1 — kirim + pasang, satu perintah dari akar repo (Git Bash):**

```bash
ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/pasang-ke-zima.sh
```

Skrip itu mengemas folder (tanpa `venv`/cache), mengunggahnya lewat
`zima-hosting/zima-shell.mjs` (jalur WebSocket ttyd yang sudah terbukti di repo
ini, tanpa perlu kunci SSH), mengekstrak ke `/DATA/AppData/meshtastic-monitor`,
lalu menjalankan pemasangnya. Sandi hanya lewat variabel lingkungan pada baris
perintah — **jangan** ditulis ke berkas atau repo.

> Jebakan yang sudah diketahui: Git Bash mengubah argumen berawalan `/` menjadi
> path Windows. Skripnya sudah menyetel `MSYS_NO_PATHCONV=1` untuk Anda; kalau
> memanggil `zima-shell.mjs` manual, setel sendiri dulu.

**Langkah 1b — hanya menyalakan ulang (tanpa mengunggah apa pun):**

```bash
ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/mulai-ulang-zima.sh
```

Dipakai saat halaman memuat kerangka halaman tetapi **tanpa node** — proses
lama masih memegang port 9208 dengan kode di memori, dan yang perlu diganti
hanyalah sambungannya ke radio. Skrip ini tidak menyentuh berkas apa pun, jadi
aman dijalankan juga saat folder lokal sedang setengah jadi. Unit lain bisa
diminta sebagai argumen, mis.
`... mulai-ulang-zima.sh meshtastic-notif.service`.

**Langkah 2 (bila ingin manual di host):**

```bash
sudo sh /DATA/AppData/meshtastic-monitor/pasang-layanan.sh
```

Skrip itu, idempoten (aman diulang):

1. merapikan berkas skrip (akhir baris Unix, izin eksekusi);
2. membuat `venv` + memasang `requirements.txt` bila belum ada;
3. menulis unit systemd dari template `.service`/`.timer` di folder itu,
   mengganti path `/opt/meshtastic-monitor` dengan folder nyatanya;
4. mengaktifkan **exporter** dan **notifier**;
5. menjalankan `reset-node.py` mode **periksa-saja** (tidak mengubah apa pun).

**Timer reset sengaja TIDAK diaktifkan**, dan bila pernah terpasang dari
pemasangan lama, skrip ini justru mematikannya. Alasannya sama seperti di bagian
Keadaan saat ini: reset menghapus Favorite, sedangkan daftar akan terisi ulang
selama downlink MQTT hidup. Untuk memasangnya secara sadar:

```bash
MESH_PASANG_TIMER=1 sudo sh /DATA/AppData/meshtastic-monitor/pasang-layanan.sh
```

Setelah itu uji paksa kapan saja: `sudo systemctl start meshtastic-reset.service`.
Cara mencopot ada di kepala berkas skripnya.

### Host Linux biasa

```bash
sudo useradd -r -s /usr/sbin/nologin meshtastic
sudo mkdir -p /opt/meshtastic-monitor
sudo cp -r ./* /opt/meshtastic-monitor/
sudo cp meshtastic-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meshtastic-exporter
```

Layanan lain (opsional): `meshtastic-notif.service` untuk notifikasi ntfy, dan
`meshtastic-reset.timer` untuk reset NodeDB terjadwal (lihat bagian Reset NodeDB
di atas).

> **Penerapan tidak boleh membawa catatan runtime.** `pasang-ke-zima.sh`
mengeluarkan `*state.json` dan `*.log` dari paket, lalu **memeriksa** isi paket:
bila artefak runtime masih ikut, penerapan dihentikan. Berkas state adalah
catatan milik **mesin yang menjalankan**, dan menimpanya dengan catatan dari
mesin lain memicu alarm palsu yang tampak sungguhan — mis. `reboot_count` yang
lebih lama membuat "Gateway baru saja reboot" berbunyi padahal uptime gateway
naik terus (lihat `CATATAN-MESHNODEID.md` §5.12). Mengabaikan berkas di
`.gitignore` tidak menolong di sini: `tar` tidak membaca `.gitignore`.

`meshtastic-notif.service` memuat setelan kanal dan ambang yang sama dengan
skripnya, termasuk `NOTIF_KONTAK_BARU=1` (id node + kualitas sinyal saat node
terdeteksi langsung oleh radio gateway), `NOTIF_JEDA_KONTAK=21600`, dan
pemantauan gateway `NOTIF_BASI_GW=180` / `NOTIF_ABSEN_GW=2`. Tanpa pemantauan itu,
notifikasi node dan halaman web sama-sama bisu saat gateway benar-benar mati.

## Prometheus

Tempel blok pada `prometheus-contoh.yml` ke `prometheus.yml` Anda. `targets`
harus menunjuk ke **mesin exporter**, bukan ke node Meshtastic.

Aturan alert ada di `alert-meshtastic.yml` (offline, exporter down, **data basi**,
baterai lemah, kanal padat). Rujuk lewat `rule_files`.

### Yang sudah terpasang di ZimaOS (28 Sep 2026)

Mesh ID kini ikut dipanen oleh Prometheus yang sudah ada di ZimaOS - bukan
Prometheus baru - sehingga riwayat node, router, dan gateway berada di satu
tempat. Berkasnya semua sudah ada di repo ini; di host hanya tiga berkas ini yang
berubah:

| Berkas di host | Isi |
|---|---|
| `/DATA/AppData/mikrotik-monitor/prometheus.yml` | tambah job `meshtastic` + `rule_files` |
| `/DATA/AppData/mikrotik-monitor/alert-meshtastic.yml` | 13 aturan alert Mesh ID |
| `/var/lib/casaos/apps/mikrotik-monitor/docker-compose.yml` | `extra_hosts: host-gateway` + mount berkas aturan |

```bash
# target Mesh ID UP?
python3 -c "import json,urllib.request as u;print([(t['labels']['job'],t['scrapeUrl'],t['health']) for t in json.load(u.urlopen('http://127.0.0.1:9090/api/v1/targets'))['data']['activeTargets'] if t['labels']['job']=='meshtastic'])"
# berapa seri yang masuk
python3 -c "import json,urllib.request as u;print(u.urlopen('http://127.0.0.1:9090/api/v1/query?query=count(%7Bjob%3D%22meshtastic%22%7D)').read()[:200])"
```

> **Alamat exporter dari dalam container.** Exporter berjalan di HOST (port
> 9208), sedangkan Prometheus ada di dalam container. Dipakai
> `host.docker.internal:9208` lewat `extra_hosts: host-gateway` karena itu paling
> tahan terhadap perubahan subnet docker. Bila suatu saat gagal, ketiganya ini
> sudah terbukti tembus dan bisa dipakai bergantian: `172.21.0.1` (gateway
> jaringan `mikrotik-monitor_default`), `172.17.0.1` (docker0), dan
> `192.168.20.36` (IP LAN host). Gejala alamat yang salah bukan kegagalan senyap:
> target job `meshtastic` DOWN dan alert `MeshtasticExporterDown` berbunyi.

> **`rule_files` dan volume mount harus berubah bersama.** Menyebut berkas aturan
> di `prometheus.yml` tanpa memasang volumenya membuat Prometheus **menolak
> start** (bukan mengabaikannya). Karena itu mount-nya memakai
> `create_host_path: false` supaya berkas yang hilang berhenti dengan alasan yang
> jelas. Sebelum membuat ulang container, periksa dulu dengan:
>
> ```bash
> docker run --rm -v /DATA/AppData/mikrotik-monitor:/etc/prometheus:ro \
>   --entrypoint /bin/promtool prom/prometheus check config /etc/prometheus/prometheus.yml
> ```

## Grafana

### Terbitkan lewat API (`terbitkan-dasbor-grafana.py`)

```bash
python terbitkan-dasbor-grafana.py                # terbitkan (idempoten)
python terbitkan-dasbor-grafana.py --periksa       # sekalian uji tiap panel
python terbitkan-dasbor-grafana.py --kering        # hanya melaporkan
```

Skrip ini membaca `dashboard-grafana.json` yang sengaja tetap **portabel**
(datasource-nya ditulis `${DS_PROMETHEUS}`), mencari datasource Prometheus di
Grafana, mengisi uid-nya ke seluruh panel, lalu menerbitkan sebagai uid
`meshtastic-node`. Datasource di ZimaOS: nama **`Prometheus`**, uid
**`prom-mikrotik`**.

**Mengapa lewat API, bukan impor manual.** Impor lewat antarmuka selalu meminta
pemilihan datasource, dan salah pilih menghasilkan dasbor yang **seluruh
panelnya kosong tanpa satu pun pesan galat** - kegagalan senyap yang paling lama
tidak disadari. `--periksa` menutup celah itu: ia menjalankan **setiap kueri
panel lewat datasource Grafana** (bukan langsung ke Prometheus, justru supaya
uid yang salah ikut terketuk) dan melaporkan panel mana yang masih kosong.

Hasil terakhir: **23 panel, 0 kosong** (18 panel berisi kueri).

### Impor manual (tanpa skrip)

1. Grafana → **Dashboards → New → Import**.
2. Unggah `dashboard-grafana.json` (atau tempel isinya).
3. Pilih datasource Prometheus saat diminta.

Isi dashboard (23 panel): ringkasan (total node, node online, status exporter,
paket/menit), **tabel semua data node**, baterai & tegangan, utilisasi kanal,
airtime TX, SNR, hop, umur sejak terdengar, riwayat online, suhu/kelembapan/
tekanan, **peta posisi**, dan **laju + total paket per node & tipe**.

> Catatan: tabel "Semua data node" menggabungkan beberapa query memakai
transformasi *Join by field* pada `node_id`. Bila nama kolom nilai berbeda di
versi Grafana Anda, sesuaikan lewat *Transform → Organize fields*.

### Contoh query panel

- **Baterai per node**: `meshtastic_device_battery_level_percent`
- **Status online**: `meshtastic_node_online` (Stat, mapping 1=ONLINE, 0=OFFLINE)
- **Umur sejak terdengar**: `meshtastic_node_last_heard_seconds`
- **Waktu terdengar terakhir (epoch)**: `meshtastic_node_last_heard_timestamp_seconds`
  — bentuk timestamp dari metrik di atas, untuk dasbor/alert yang memakai waktu,
  bukan umur (`time() - meshtastic_node_last_heard_timestamp_seconds`)
- **SNR**: `meshtastic_node_snr_db`
- **Hop**: `meshtastic_node_hops_away`
- **Utilisasi kanal**: `meshtastic_device_channel_utilization_percent`
- **Peta**: `meshtastic_node_latitude` / `meshtastic_node_longitude`
- **Laju paket masuk**: `sum by (node_id) (rate(meshtastic_packets_received_total[5m]))`
- **Tabel nama node**: `meshtastic_node_info` (label long_name/role/hw_model/**via**)
- **Hanya node jaringan RF sendiri**: `meshtastic_node_direct == 1`
  (dipakai juga untuk membatasi semua aturan alert, lihat `alert-meshtastic.yml`)
- **Kesehatan gateway**: `meshtastic_gateway_uptime_seconds`,
  `meshtastic_gateway_reboot_count` (pakai `changes(...[1h])`),
  `meshtastic_gateway_nodedb_count`, `meshtastic_gateway_nodes_lora`,
  `meshtastic_gateway_nodes_mqtt`
- **Umur data di halaman**: `meshtastic_cuplikan_umur_seconds` — umur data node
  terakhir yang dikumpulkan. Angka yang membesar terus berarti loop pengumpul
  tersangkut; karena di-scrape dari thread HTTP yang terpisah, `up` di bawah ini
  tetap ikut turun ke 0 setelah melewati `MESH_BASI_MAKS`.
- **Node favorit**: `meshtastic_node_favorite` (1 = ditandai Favorite)

## Periksa cepat tanpa Grafana

### `lihat-data-node.py` — daftar semua node, dan memisahkan jalurnya

Menarik sekali data live dari node dan mencetak tabel semua node beserta
kolom **Via** (LoRa / MQTT / DIRI) — berguna untuk menjawab "node saya
kelihatan tidak?" sebelum menyalakan Prometheus/Grafana, sekaligus melihat mana
yang **radio lokal** dan mana yang **internet**:

```bash
./venv/Scripts/python lihat-data-node.py          # semua, plus ringkasan
./venv/Scripts/python lihat-data-node.py --lora   # hanya jalur radio (lokal)
./venv/Scripts/python lihat-data-node.py --mqtt   # hanya jalur internet
./venv/Scripts/python lihat-data-node.py --json   # data mentah
MESH_HOST=192.168.20.31 ./venv/Scripts/python lihat-data-node.py
```

Setiap kali dijalankan, baris terakhirnya merangkum pemisahan itu - termasuk
**berapa yang terbukti** tersambung langsung ke gateway:

```
Total 71 node: 11 jalur radio (di antaranya 3 TERBUKTI tersambung langsung ke
  gateway lewat SNR), 59 MQTT (internet), 1 diri.
```

**Arti kolom Via**: nilainya dihitung dari **paket terakhir** yang dicatat
gateway untuk node itu.

| Via | Arti |
| --- | --- |
| `LoRa` | terakhir terdengar lewat radio — tapi lihat catatan bukti di bawah |
| `MQTT` | paket terakhirnya datang dari **broker internet**, bukan lewat radio |
| `DIRI` | node gateway itu sendiri |

> **`LoRa` belum berarti tersambung langsung.** Itu hanya berarti jalur terakhir
> bukan MQTT. Bukti koneksi **langsung** ada di kolom **SNR**: kalau SNR terisi
> (dan hop 0), gateway sendiri yang mengukur link radio itu. Bila SNR kosong,
> belum ada bukti apa pun — dan inilah yang dipisahkan di halaman web.
>
> Jebakan kedua: karena ini paket **terakhir**, node lokal yang kebetulan
> terakhir terdengar lewat MQTT akan tampil sebagai `MQTT`. Penandanya: bila
> node `MQTT` itu **masih menyimpan nilai SNR**, gateway pernah mendengarnya
> lewat udara — di halaman web ditandai **"pernah lewat radio"**.

### `traceroute-node.py` — lewat node apa paket sampai, dan sekuat apa

Menjawab pertanyaan yang tidak bisa dijawab daftar node: **jalur** dan
**kualitas tiap hop**, dua arah.

```bash
./venv/Scripts/python traceroute-node.py '!da5a16f8'      # satu tujuan
./venv/Scripts/python traceroute-node.py ROUTER           # cari dari nama
./venv/Scripts/python traceroute-node.py --semua          # semua node LoRa
./venv/Scripts/python traceroute-node.py '!da5a16f8' --mentah   # angka mentah
```

> **Catatan:** traceroute **memancarkan paket ke udara** (bukan sekadar membaca),
> jadi jangan jadikan panel Prometheus yang di-scrape terus-menerus. Pakai saat
> mendiagnosis saja.

Hasil pada jaringan ini (diambil langsung dari node):

| Tujuan | Jalur | SNR pergi | SNR balik |
|---|---|---|---|
| `!da5a16f8` router tower | langsung, 0 hop | **−15,8 dB** | **+7,0 dB** |
| `!02ee76d0` MOB-01 | — | tidak menjawab | — |
| `!8f4c228c` MOB-02 | — | tidak menjawab | — |

**Temuan: link gateway ↔ router tower ASIMETRIS.** Router mendengar gateway
hanya pada −15,8 dB (mendekati batas decode LoRa), sementara gateway mendengar
router dengan nyaman di +7,0 dB. Artinya arah **naik** (gateway → tower) yang
rapuh, bukan arah turun. Ini menjelaskan mengapa sebagian paket ke tower bisa
hilang walau daftar node tampak normal. Perbaikan yang masuk akal: antena/posisi
node gateway (dan ketinggian/arah antena), karena sisi tower sudah jelas kuat.

Nilai `snr_towards` dan `snr_back`-masing-masing berasal dari field protobuf
`RouteDiscovery` (SNR “towards the destination” dan arah balik), dibagi 4 sesuai
skala firmware.

## Notifikasi ntfy (offline / pulih / baterai / sinyal / gateway)

`notif-meshtastic.py` memantau `/data.json` dan mengirim notifikasi ke **ntfy**
hanya saat ada **perubahan status** (pola yang sama dengan `mikrotik-ntfy/`):

| Kejadian | Prioritas | Tag |
|---|---|---|
| node online → offline | high | `red_circle` |
| node offline → online | default | `green_circle` |
| **node LoRa terdeteksi LANGSUNG oleh radio gateway** (memuat id + kualitas sinyal) | default | `signal_strength` |
| **kontak radio node itu terukur kembali** (tadinya hanya lewat MQTT) | default | `signal_strength` |
| **gateway MATI / tidak terbaca** (tiga sebab, lihat bawah) | **max** | `red_circle` |
| **gateway terbaca kembali** | default | `green_circle` |
| baterai turun melewati ambang | high | `warning` |
| baterai normal kembali | default | `battery` |
| SNR link turun di bawah ambang | high | `signal_strength` |
| SNR link membaik (ambang + margin) | default | `signal_strength` |
| hop bertambah dari titik terbaik | high | `arrows_counterclockwise` |
| hop kembali ke titik terbaik | default | `arrows_counterclockwise` |
| node **hilang dari database gateway** | high | `warning` |
| node muncul kembali di database | default | `green_circle` |
| gateway baru saja reboot | high | `recycle` |
| database gateway hampir penuh | high | `warning` |
| node RF belum ditandai Favorite | default | `star` |

### Tiga kabar yang paling penting membaca keadaan gateway

**1. Node LoRa terdeteksi langsung (`NOTIF_KONTAK_BARU`).** SNR hanya terisi
bila **radio gateway sendiri** yang menerima paket node itu. Jadi SNR yang ada
+ jalur `lora` = bukti kontak radio, bukan paket yang menumpang internet
(MQTT). Notifikasinya memuat **id node**, nama, role, hop, baterai, dan
**kualitas sinyalnya** — memakai penilaian yang sama dengan halaman web
(Baik/Cukup/Buruk/Nihil + angka SNR dan lantai preset gateway). Node yang
tadinya hanya terdengar lewat MQTT lalu terukur radio juga dikabari
("kontak radio kembali").

Halaman web hanya bisa **ditengok**; notifikasi ini **mencari Anda** — dan
hanya inilah cara mengetahui node RF benar-benar memancar tanpa membuka
halaman.

Jalur (`via`) mengikuti paket **terakhir**, jadi node di antara dua jalur bisa
bergantian radio ↔ MQTT. Tanpa jeda, tiap pergantian menjadi satu notifikasi.
Karena itu kabar ulang untuk node yang sama dibatasi `NOTIF_JEDA_KONTAK`
(bawaan 6 jam). Matikan seluruh kabar ini dengan `--tanpa-kontak` /
`NOTIF_KONTAK_BARU=0`.

**2. Gateway MATI (`NOTIF_BASI_GW`, `NOTIF_ABSEN_GW`).** Diperiksa dari **sisi
notifier**, karena halaman web tidak bisa memberi tahu siapa pun saat dirinya
sendiri mati. Tiga sebab, semuanya pernah terjadi di perangkat ini:

| Sebab | Tanda di `/data.json` |
|---|---|
| exporter tidak menjawab | pembacaan gagal (`Connection refused`) |
| data exporter **basi** | `umur_data_seconds` > `NOTIF_BASI_GW` — exporter hidup, loop pengumpulnya tersangkut |
| gateway "hidup tetapi buta" | `jumlah_node` = 0 **dan** `firmware` kosong |

Selama salah satu sebab berlaku, pemantauan node **buta**: halaman kosong tanpa
satu pun alert. Notifikasi gateway mati berprioritas **`max`**. Setelah terbaca
kembali, dikirim kabar pemulihan lengkap dengan lama matinya.

Dua putaran gagal berturut-turut (`NOTIF_ABSEN_GW`) diperlukan sebelum
dilaporkan, supaya kegagalan sesaat — mis. exporter baru **restart** saat
penerapan kode, yang memang terjadi — tidak menjadi alarm palsu. Matikan
seluruh pemeriksaan ini dengan `--basi-gw off` / `NOTIF_BASI_GW=off`.

> **Exporter mati tidak membuat notifier lupa.** Saat `/data.json` gagal
dibaca, tidak ada penilaian per node yang dibuat dan catatan lama dibiarkan
**utuh**. Kalau tidak, setiap gangguan sebentar akan membuat notifier mengira
semua node pulih/hilang saat gateway kembali — satu banjir alarm palsu tepat
saat keadaannya paling sulit dibaca.

**3. Node yang tersambung ke gateway menjadi offline.** Ini kabar lama (offline
biasa), tetapi isinya kini ikut menyebut **kualitas sinyal terakhir** node dan
jarak hop-nya — supaya bisa dibedakan "node putus" dari "node pindah jauh dan
sinyalnya sekarat".

### Cakupan: hanya node yang terhubung LANGSUNG lewat LoRa

Satu node Meshtastic menyimpan **semua** node yang ia dengar — dan pada kasus
Anda, 107 dari 116 node datang lewat broker MQTT publik (mesh se-Indonesia).
Tanpa pembatasan, notifikasi akan berbunyi untuk node orang lain di Padang,
Malang, atau Muntilan yang tidak ada hubungannya dengan jaringan RF Anda.

Karena itu cakupan bawaan adalah **`lora`**: hanya node yang benar-benar
terdengar radio oleh gateway `192.168.20.31` — mis. node `ROUTER` di tower dan
node LoRa lain satu jaringan. Yang dilewati:

- node dengan `via` = `mqtt` (datang lewat internet),
- node gateway sendiri (`via` = `diri`) — kalau gateway mati, exporter-nya yang mati,
- node yang **belum pernah terdengar** (tanpa `last_heard_seconds`), karena
  statusnya tidak bisa dipastikan — ini mencegah alarm palsu untuk entri
  database yang tidak pernah punya kontak radio.

Atur dengan `--semua-node` (ikut pantau MQTT) atau `--node ID1,ID2` (batasi ke
daflar tertentu, paling ketat). Lingkungan: `NOTIF_LINGKUP`, `NOTIF_NODE`.

> **Switching cakupan tidak memicu alert retroaktif.** Saat sebuah node baru
> masuk cakupan, statusnya hanya dicatat sebagai baseline. Tambahkan
> `--lapor-awal` bila ingin langsung diberi tahu soal node yang sudah offline.

Sengaja memakai **kanal terpisah** dari router (`rt-...`) dan Uptime Kuma
(`kuma-...`) supaya gangguan antar-sistem tidak tercampur, dan di dalam Mesh ID
sendiri dipakai **dua topik**:

| Keperluan | Topik | Isi |
|---|---|---|
| Kabar **penting** | `mesh-penting-2kevnee56c4` | gateway mati/pulih, node LoRa terdeteksi langsung & kontak kembali, node offline/pulih |
| Kabar **rutin** | `mesh-6h4v8p2rxq` | baterai, SNR lemah, hop bertambah, node hilang dari database, gateway reboot, DB penuh, saran Favorite |

Server untuk keduanya `https://ntfy.adminforge.de`, dengan cadangan ntfy lokal
ZimaOS `http://192.168.200.253:7200` (LAN, tanpa internet).

**Mengapa dipisah dua topik.** Kabar penting terjadi jarang (beberapa kali
sepekan), sedangkan kabar rutin bisa beberapa kali sehari. Langganan terpisah
berarti di ponsel keduanya bisa diberi **nada dering dan aturan "jangan ganggu"
yang berbeda** — topik penting boleh menembus mode senyap, topik rutin tidak.
Kabar **pemulihan** dari ketiga hal penting itu ikut ke topik penting juga,
supaya topik itu tidak pernah berbunyi tanpa kabar sembuhnya.

Atur lewat `NTFY_TOPIK_PENTING` / `--topik-penting`. **Isi kosong berarti
kembali memakai satu topik saja** — jadi pemisahan ini bisa dicabut tanpa
menyunting kode:

```bash
NTFY_TOPIK_PENTING= python notif-meshtastic.py   # satu topik saja
```

Daftarkan server + topik di aplikasi ntfy ponsel Anda agar peringatan masuk;
untuk memastikan keduanya benar-benar hidup, jalankan
`python uji-semua-ntfy.py --hanya mesh` atau `python uji-notif-meshtastic.py`.
Skrip ini **tidak butuh Prometheus** — cukup exporter yang jalan.

```bash
python notif-meshtastic.py            # layanan jalan terus
python notif-meshtastic.py --sekali   # satu putaran (untuk cron/timer)
```

Opsi: `--data URL`, `--state BERKAS`, `--interval DET`, `--ambang-baterai N`
(0 = matikan), `--lapor-awal`, `--ambang-snr N` (bawaan `-7`; `off` = matikan),
`--margin-snr N` (bawaan `3`), `--hop-naik N` (bawaan `1`; `off` = matikan),
`--semua-node`, `--node ID1,ID2`, `--kecuali ID1,ID2`, `--absen N` (bawaan `2`),
`--db-ambang N` (bawaan `190`), `--tanpa-saran-favorit`, `--tanpa-kontak`,
`--jeda-kontak DET` (bawaan `21600`), `--basi-gw DETIK` (bawaan `180`;
`off` = matikan), `--absen-gw N` (bawaan `2`).
Lingkungan: `MESH_DATA`, `NTFY_SERVER`, `NTFY_TOPIK`, `NTFY_TOKEN`, `NTFY_LOKAL`,
`NOTIF_SNR_AMBANG`, `NOTIF_SNR_MARGIN`, `NOTIF_HOP_NAIK`, `NOTIF_LINGKUP`,
`NOTIF_NODE`, `NOTIF_KECUALI`, `NOTIF_ABSEN`, `NOTIF_DB_AMBANG`,
`NOTIF_SARAN_FAVORIT`, `NOTIF_KONTAK_BARU`, `NOTIF_JEDA_KONTAK`, `NOTIF_BASI_GW`,
`NOTIF_ABSEN_GW`, `NTFY_TOPIK_PENTING`.

**Lantai sinyal mengikuti preset gateway.** Penilaian SNR (Baik/Cukup/Buruk/
Nihil) selalu dihitung **relatif terhadap lantai demodulasi preset gateway**
(saat ini LONG_FAST → −17.5 dB), bukan dari kuat-lemah `RSSI`. Angka lantai
itu datang dari `kesehatan_gateway.lantai_snr` di `/data.json` — jadi bila
preset gateway kelak diubah, teks notifikasi ikut benar sendiri tanpa
penyuntingan. Penjelasan cara membacanya ada di bagian **Meter sinyal** di atas.

**Cara kerja alert kualitas link:**

- **SNR** — diukur gateway terhadap paket terakhir node itu, jadi ia menunjukkan
  kualitas link node ↔ gateway. Peringatan saat SNR < `--ambang-snr`; pemulihan
  baru dianggap sah saat SNR ≥ ambang + `--margin-snr`. Histeresis ini mencegah
  notifikasi bolak-balik saat SNR berayun di sekitar ambang.
- **Hop** — peringatan saat jumlah hop naik ≥ `--hop-naik` dari **titik
  terbaiknya** (hop terkecil yang pernah terlihat). Artinya node tak lagi bisa
  dicapai serapat biasanya — biasanya tanda node perantara ikut putus. Pulih
  saat hop kembali ke titik terbaik.

Keduanya hanya dievaluasi saat node sedang online; node offline sudah ditangani
notifikasi offline, jadi tidak ada pesan ganda.

Pasang sebagai layanan:

```bash
sudo cp meshtastic-notif.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meshtastic-notif
```

> **Kanal mati ≠ alert hilang.** Notifikasi yang gagal dikirim ke semua kanal
> tidak "menelan" perubahan status — catatannya dikembalikan sehingga dicoba
> lagi pada putaran berikutnya, sampai benar-benar terkirim.

### Uji ujung-ke-ujung (`uji-notif-meshtastic.py`)

Membuktikan: exporter terbaca, logika deteksi benar (offline/pulih/baterai/
SNR/hop, dan tidak mengulang saat status tetap), **tiga kabar baru** di atas
(kontak radio + kualitas sinyalnya, "kontak kembali", gateway mati karena tiga
sebab berbeda beserta pemulihannya, dan state yang tetap utuh saat exporter
mati), lalu pesan hasil deteksi **benar-benar tiba** di server ntfy (dibaca
kembali):

```bash
python uji-notif-meshtastic.py                    # 51 lulus / 0 gagal (mode kirim)
python uji-notif-meshtastic.py --kering           # 45 lulus / 0 gagal, tanpa kirim nyata
MESH_DATA=https://meshid.clusternet.my.id/data.json python uji-notif-meshtastic.py --kering
NTFY_SERVER=https://ntfy.sh python uji-notif-meshtastic.py --topik uji
```

- **LULUS** → jalur exporter → deteksi → ntfy terbukti hidup.
- **GAGAL** → ditampilkan langkah mana yang putus (sumber data, deteksi, atau
  pengiriman).

Bagian **3** adalah uji kirim yang sebenarnya: **ketiga jenis kabar** disusun
dari node yang benar-benar ada di `/data.json` saat itu (kontak radio langsung,
node yang tersambung gateway menjadi offline), diarahkan ke topiknya oleh fungsi
yang sama dengan layanan (`topik_untuk`), lalu **masing-masing dibaca kembali**
dari server ntfy dan dicocokkan lewat penanda unik. Hanya kabar **gateway mati**
yang disimulasikan — itu pun diberi label jelas di isi pesannya, karena gateway
yang sehat tentu tidak boleh dimatikan hanya demi uji. Bagian **3d** memastikan
kabar rutin tidak ikut pindah ke topik penting.

**Jalankan uji ini berkala, bukan hanya saat mengubah kode.** Dua di antaranya
menangkap masalah yang tidak terlihat dari halaman web: loop "node hilang" yang
menimpa catatan node yang masih ada, dan payload exporter yang belum lengkap
yang dikira "gateway mati".

Uji ini **wajib** dijalankan sebelum menerapkan perubahan pada
`notif-meshtastic.py`. Dua cacat nyata ditemukan di sini: (1) loop "node hilang
dari daftar" menimpa catatan node yang **masih ada**, sehingga status per node
tidak pernah maju dan setiap putaran melaporkan ulang kejadian yang sama (node
offline dilaporkan offline terus, pemulihan tidak pernah terdeteksi); (2)
payload exporter yang **belum lengkap** (tanpa kunci `jumlah_node`, mis. saat
baru dimulai) disimpulkan sebagai "gateway mati" — alarm palsu yang
menakutkan. Syaratnya kini "`jumlah_node` ada dan bernilai 0".

### Uji halaman & metrik (`uji-halaman-meshtastic.py`)

Menguji **render halaman dan metrik dengan data node tiruan**, jadi aman
dijalankan kapan saja — termasuk saat layanan produksi sedang hidup dan sedang
memegang koneksi ke gateway. Yang diperiksa: bagian penting halaman tetap ada,
pewarnaan ambang muncul di nilai yang tepat (termasuk tepat di batas angka),
dan metrik `meshtastic_node_last_heard_timestamp_seconds` sepadan dengan
metrik umur.

```bash
cd meshtastic-monitor
./venv/Scripts/python uji-halaman-meshtastic.py
```

Keluaran HTML-nya ditulis ke `.tmp-uji-halaman/tampilan.html` (di akar repo)
supaya bisa dibuka di peramban dan dilihat langsung tanpa mengganggu layanan.

## Uji tanpa radio: node simulasi + penyuntik paket

Halaman exporter bisa dibuktikan terisi **tanpa radio, tanpa airtime, dan tanpa
gateway**: satu berkas merangkai paket yang "seolah diterima dari udara", satu
berkas menyediakan node Meshtastic tiruan, dan exporter dijalankan apa adanya di
depannya.

```bash
./venv/Scripts/python suntik-paket.py --uji-diri               # 17 uji paket, tanpa jaringan
./venv/Scripts/python uji-eksportir-simulasi.py                # 14 uji halaman exporter :9208
```

`simulasi-node.py` menyalakan **node Meshtastic tiruan** yang berbicara
protokol PhoneAPI asli (bingkai `0x94 0xC3` + `ToRadio`/`FromRadio`, jabat tangan
`want_config_id` -> `my_info` -> `node_info` -> `moduleConfig` -> `channel` ->
`config_complete_id`). Node itu bisa disemai NodeDB yang masuk akal (gateway,
dua tower router, sensor, tracker - lengkap dengan peran, perangkat, baterai,
tegangan, SNR, hop, posisi), dan `suntik-paket.py` menyuntikkan skenario drive
test sebagai klien kedua.

`uji-eksportir-simulasi.py` menjawab satu pertanyaan: bisakah **halaman exporter
:9208** yang dipakai memantau jaringan sungguhan terisi tanpa satu pun radio?
Rantainya persis produksi, hanya radionya yang dipalsukan:
`exporter-meshtastic.py` dijalankan sebagai **proses terpisah** yang menunjuk ke
node itu lewat `MESH_HOST`/`MESH_PORT`, lalu uji ini membaca `/`, `/data.json`,
dan `/metrics` sungguhan lewat HTTP lalu memeriksa nama, SNR, hop, peran, preset
radio, dan **lantai SNR** yang dipakai meter sinyal.

Bagian **6** adalah **kontrol negatif**: rantai yang sama dijalankan **tanpa
semaian**. Halaman harus hanya berisi node gateway, dan nama tower semaian harus
**tidak ada**. Bila bagian itu tetap hijau, maka hijau di bagian utama tidak
membuktikan apa pun. Hasil: **14 lulus, 0 gagal**.

Penyuntiknya dipakai langsung untuk menyusun skenario:

```bash
./venv/Scripts/python suntik-paket.py --kering --teks ping   --node '!11112222:7.5:-92:0:MOB-UJI' --posisi '!11112222:-6.19:106.8:12'
./venv/Scripts/python suntik-paket.py --sapuan --langkah 0.05 --nama MOB-UJI
```

Bawaannya menuju `127.0.0.1:4404` (sengaja bukan 4403 milik gateway). Menyuntik
ke host bukan loopback **ditolak** kecuali diberi `--ya`, karena flag injeksi di
firmware berbunyi *"must never ship enabled"*. Opsi `--sapuan` mengumumkan
NodeInfo lebih dulu supaya node drive test tampil bernama, bukan sebagai
`!6d0b0001`.

Yang **tidak** dibuktikan uji ini, dan tetap perlu radio sungguhan: perilaku
udara (lantai derau, airtime nyata, tabrakan paket) dan apakah node fisik mau
menerima paket suntikan - itu bergantung pada build firmware yang punya
`SIMULATOR_APP`/`MESHTASTIC_ENABLE_FRAME_INJECTION`.

## Catatan penting

- **Node `ROUTER` hanya memancarkan telemetry sendiri ~tiap 12 jam.** Jadi
  baterai/utilisasi node tower akan jarang diperbarui. Node `CLIENT` jauh
  lebih rapat. Bila ingin telemetry router rapat, ubah role-nya menjadi
  `ROUTER_CLIENT` (tetap bekerja sebagai router tower).
- Node router harus **terdengar** oleh node gateway lewat LoRa. Jika node
  gateway MQTT-only tanpa radio, router tidak akan muncul.
- `MESH_OFFLINE_SECS` bawaan 3 jam agar node `ROUTER` yang jarang
  memancarkan nodeinfo tidak salah dianggap offline. Turunkan bila hanya
  memantau node `CLIENT`.
- Bila node router tidak muncul sama sekali, cek jarak/RF: gunakan fitur
  traceroute/daftar node di aplikasi Meshtastic untuk memastikannya terdengar.
- **Peran (role) node**: bila gateway `192.168.20.31` memang bertugas sebagai
  gerbang MQTT sekaligus jembatan ke router tower, `ROUTER_CLIENT` lebih tepat
  daripada `CLIENT`. Dan bila ingin telemetry router tower lebih rapat daripada
  ~12 jam, ubah node tower dari `ROUTER` menjadi `ROUTER_CLIENT` — tetap bekerja
  sebagai router, tetapi laporannya normal.
- **Reboot gateway**: node gateway melaporkan penghitung reboot. Bila angkanya
  terus naik untuk perangkat 24/7, itu tanda catu daya/panas/watchdog — notifier
  dan aturan alert `MeshtasticGatewayReboot` akan memberitahukannya.
- **Lingkungan Python**: `meshtastic-monitor/venv` sudah berisi dependensi dan
  diabaikan git. Untuk alat berbasis pustaka `meshtastic` (`lihat-data-node.py`,
  `catat-node.py --langsung`, exporter), pakai `./venv/Scripts/python`.
- `notif-meshtastic.py` memakai ambang offline yang sama dengan exporter
  (`MESH_OFFLINE_SECS`). Karena bawaan 3 jam, node `ROUTER` yang wajar jarang
  memancar tidak akan langsung dianggap offline.

## Catatan kendala yang pernah terjadi

Gaya **gejala → sebab → solusi → verifikasi**, supaya kalau muncul lagi tinggal
ikut langkahnya.

### 1. Notifikasi ntfy hilang diam-diam bila nama node memuat emoji

**Gejala.** `notif.err.log` penuh baris seperti:

```
[GAGAL] Node 🛜 MQTT-GateWay_GTP⛰️📡 HILANG dari database gateway ->
  server utama gagal ('latin-1' codec can't encode character '\U0001f6dc' ...) |
  server utama (percobaan ke-2) gagal (...) | ntfy lokal gagal (...)
```

Semua kanal dilaporkan gagal, jadi alarm untuk node itu **tidak pernah sampai** —
padahal node ber-emoji justru banyak di mesh ini.

**Sebab.** `_post()` sudah meng-encode **body** ke UTF-8, tetapi **header**
(`Title`) tidak. `http.client` menulis header sebagai latin-1, sehingga judul
ber-emoji melempar `UnicodeEncodeError`. Karena error itu turunan `ValueError`
yang ditangkap `kirim()`, akibatnya seluruh kanal dicoba-lalu-gagal sekaligus.

**Solusi.** `_aman_header()` di `notif-meshtastic.py`: nilai header non-ASCII
dikirim sebagai byte UTF-8, bukan dipaksa latin-1.

**Verifikasi.** Kirim judul ber-emoji lalu baca kembali dari server:

```
title = 'Uji emoji 🛜 MQTT-GateWay_GTP⛰️📡'   -> emoji selamat sampai tujuan
```

### 2. Uji E2E gagal palsu saat nama node memuat emoji

**Gejala.** `uji-notif-meshtastic.py` melaporkan
`tidak bisa membaca http://127.0.0.1:9208/data.json (charmap codec ...)`, padahal
baris sebelumnya justru "exporter menjawab: 70 node dipantau".

**Sebab.** Dua hal bertumpuk: (a) skrip tidak memaksa UTF-8 pada keluaran,
sehingga konsol Windows cp1252 tidak bisa mencetak nama ber-emoji; dan (b) blok
`try` yang terlalu luas ikut membungkus loop pencetakan, sehingga kegagalan
**menampilkan** dilaporkan sebagai kegagalan **membaca** — pesan yang
menyesatkan saat mencari masalah.

**Solusi.** Paksa `sys.stdout/stderr` ke UTF-8 (seperti skrip lain) dan
persempit `try` hanya ke pengambilan + penguraian data.

**Verifikasi.** `python uji-notif-meshtastic.py` → **20 lulus, 0 gagal**.

### 3. Notifier HIDUP tetapi tidak pernah melapor ("putaran gagal" berulang)

**Gejala.** `notif.err.log` hanya berisi baris yang sama terus-menerus, tanpa
henti, dan tidak ada alarm yang sampai ke ponsel:

```
putaran gagal: 'charmap' codec can't encode character '\U0001f6dc' ...
```

Daftar proses memperlihatkan notifier **berjalan**, jadi mudah disangka sehat.

**Sebab.** `main()` notifier tidak pernah memaksa UTF-8 pada `sys.stdout/stderr`.
Begitu keluarannya dialihkan ke berkas (`mulai-layanan.bat` memakai `>>`),
Python memakai encoding lokal (cp1252), dan `print()` atas judul ber-emoji
melempar `UnicodeEncodeError`. Urutannya penting: pencetakan terjadi **sesudah**
percobaan kirim tetapi **sebelum** keadaan disimpan, sehingga tiap putaran mati
di titik yang sama — keadaan tidak pernah maju, alarm yang sama diulang terus
(itulah asal "429 Too Many Requests" dari server ntfy), dan tidak ada satu pun
laporan yang tercatat.

**Solusi.** Paksa `sys.stdout/stderr` ke UTF-8 dengan `errors="replace"` di awal
`main()`, sama seperti skrip-skrip lain.

**Verifikasi.** `notif.err.log` tetap **0 byte** dan `notif.log` memperlihatkan
putaran maju normal:

```
tidak ada perubahan status (4 node dipantau)
tidak ada perubahan status (4 node dipantau)
```

### 4. `hentikan-layanan.bat` tampak berhasil, layanan tetap jalan

**Gejala.** Skrip menghentikan proses dan menulis "Selesai", tetapi port 9208
**masih LISTENING** dan halaman web tetap terbuka.

**Sebab.** `venv\Scripts\python.exe` di mesin ini bukan interpreter biasa,
melainkan **peluncur venv**: ia menjalankan interpreter dasar dari `pyvenv.cfg`
(`C:\Espressif\tools\python\python.exe`) sebagai **proses anak** dengan argumen
yang sama. Penyaringan lama mencari nama folder `meshtastic-monitor`, yang ada
pada command line peluncur tetapi **tidak ada** pada anaknya — sehingga hanya
peluncur yang mati, sedangkan anaknya (yang memegang socket) terus hidup.

**Solusi.** Saring berdasarkan **nama skrip** (`exporter-meshtastic\.py` /
`notif-meshtastic\.py`) sebagai nama berkas utuh, sehingga peluncur dan anaknya
ikut termatikan sementara `uji-notif-meshtastic.py` tidak ikut.

**Verifikasi.** Setelah `hentikan-layanan.bat`: `Get-CimInstance Win32_Process`
filter `python.exe` → **kosong**, dan `netstat` tidak lagi menampilkan 9208.

### 5. Exporter "hidup" tetapi buta (0 node selamanya, tanpa satu pun alert)

**Gejala.** Halaman web dan `/data.json` menampilkan **0 node** terus-menerus
(`kesehatan_gateway` berisi `null`, `firmware` tetap terbaca), tetapi
`meshtastic_exporter_up` bernilai **1** dan tidak ada alert yang berbunyi.
Ditemukan 28 Sep 2026 pada **kedua** salinan exporter sekaligus (ZimaOS dan
mesin Windows) — jadi halaman produksi `meshid.clusternet.my.id` tampak hidup
padahal kosong.

**Sebab.** Loop koneksi exporter hanya `time.sleep` antar-pembaruan dan tidak
pernah memeriksa apakah data benar-benar datang. Saat gateway memuat ulang
setelannya (mis. sesudah menulis setelan MQTT) atau reboot, socket lama mati
**tanpa memberi tahu pembaca**, dan pustaka `meshtastic` **tidak** membersihkan
penanda `isConnected`-nya saat socket putus. Akibatnya `kumpulkan()`
mengembalikan 0 node selamanya, dicatat sebagai `debug`, lalu diulang — dan
karena `up` tetap 1, aturan alert `MeshtasticExporterDown` pun diam.

**Solusi.** Dua penjaga di `sambung()` (`exporter-meshtastic.py`):

1. **handshake** — jangan mengaku "up" sebelum database node benar-benar
   terbaca (menunggu sampai `MESH_TUNGGU_AWAL` detik, bawaan 30);
2. **penjaga kebuntuan** — bila database kosong berturut-turut padahal
   sebelumnya ada isinya (`MESH_KOSONG_MAKS`, bawaan 3), turunkan penanda `up`
   dan keluar supaya `main()` menyambung ulang dengan jeda bertingkat.

**Verifikasi.** Tiga uji palsu (tanpa perangkat): handshake kosong → menolak
mengaku up; data berhenti setelah sempat ada → menyambung ulang; sambungan
sehat → tetap jalan. Bila menimpa lagi, halaman web akan menunjukkan `up=0`
dan alert `MeshtasticExporterDown` berbunyi ~5 menit kemudian.

**Kambuh 28 Sep 2026 sore — versi terpasang tertinggal.** Halaman produksi
(`https://meshid.clusternet.my.id/`) memuat kerangka halaman 9.378 byte tanpa
satu pun baris node, sementara `meshtastic_exporter_up` tetap **1**. Tiga sebab
menumpuk, semuanya sudah diperbaiki:

1. **Berkas di host lebih tua dari berkas lokal.** `md5sum`/`grep` menunjukkan
   berkas di `/DATA/AppData/meshtastic-monitor/` **tidak memuat penjaga sama
   sekali** (`pernah_ada`, `BAWAAN_TUNGGU_AWAL`) — perbaikan itu belum pernah
   terpasang, sebab penerapan terakhir (18:19) mendahului penyuntingan lokal
   (18:40). Pelajaran: setelah menyunting, **selalu** bandingkan `md5sum` host
   dan lokal, jangan hanya percaya "pasang selesai".
2. **Penjaga mati bila pembacaan PERTAMA sudah kosong.** Penjaga lama menunggu
   "pernah ada isinya" lebih dulu; di host ZimaOS socket mati pada 18:22 sebelum
   satu pun pembacaan berisi, sehingga penanda itu tak pernah menyala dan loop
   diam mengumpulkan 0 node tiap 30 detik **tanpa satu pun baris WARNING**.
   Sekarang isi handshake dipakai untuk menyalakan penjaga, dan ada tenggat
   `MESH_BUTA_TUNGGU` (bawaan 120 detik) supaya sambungan yang sejak awal kosong
   pun akhirnya disambung ulang.
3. **Dua exporter berebut satu radio.** Salinan di mesin Windows (proses dari
   00:56 dan 19:13) dan salinan di ZimaOS sama-sama menyambung ke
   `192.168.20.31:4403`; tiap sambungan baru memutus sambungan yang lain
   (lihat "Hanya SATU program boleh menyambung ke radio").

Ditambah satu jaring pengaman baru: `meshtastic_cuplikan_umur_seconds` dan
`up` yang dihitung dari **umur data** saat scrape (`MESH_BASI_MAKS`, bawaan
3× interval, minimal 90 detik). Karena scrape dilayani thread HTTP yang
**terpisah** dari loop pengumpul, alert `MeshtasticExporterDown` tetap berbunyi
walau loop-nya sendiri yang tersangkut.

**Cara memulihkan cepat** (satu perintah dari akar repo):

```bash
ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/mulai-ulang-zima.sh
```

yang setara dengan, di host ZimaOS:

```bash
sudo systemctl restart meshtastic-exporter
```

**Verifikasi 28 Sep 2026 19:40.** Halaman publik kembali memuat **114 node**
(65.168 byte, 124 baris tabel, umur data <20 detik), `up=1`, dan
`meshtastic_cuplikan_umur_seconds` muncul di `/metrics`. Uji
`uji-halaman-meshtastic.py`: **48 lulus / 0 gagal** (4 uji baru meniru socket
yang mati sesudah handshake, gelandangan tanpa isi, dan data basi).

### 5. Penerapan ke ZimaOS tampak berhasil, halaman tetap versi LAMA

**Gejala.** `pasang-ke-zima.sh` selesai tanpa keluhan, berkas di host sudah baru
(dibuktikan `md5sum`/`grep` di `/DATA/AppData/meshtastic-monitor/`), tetapi
halaman di `https://meshid.clusternet.my.id/` **dan** `http://192.168.20.36:9208/`
masih memperlihatkan kode lama — mis. metrik baru tidak muncul di `/metrics`.

**Sebab.** `pasang-layanan.sh` memakai **`systemctl enable --now`**, yang hanya
**menyalakan** unit yang belum berjalan. Pada unit yang sudah aktif, perintah itu
**tidak melakukan apa pun**, jadi proses lama (beserta kode lama yang sudah
dimuat ke memori) terus melayani port 9208. Buktinya terlihat di host:

```
Main PID: 2741779 (python)
Active: active (running) since Mon 2026-09-28 15:16:41 WIB; 2h 40min ago   <- masih proses lama
```

padahal penerapan baru terjadi sekitar pukul 17.5x.

**Solusi.** Setelah `enable`, **paksa restart**:

```bash
systemctl enable   meshtastic-exporter.service meshtastic-notif.service
systemctl restart  meshtastic-exporter.service meshtastic-notif.service
```

(`--now` tetap dipakai untuk **timer**, karena me-restart timer hanya akan
menggeser jadwalnya tanpa manfaat.)

**Verifikasi.** `systemctl show meshtastic-exporter -p MainPID
-p ActiveEnterTimestamp` → PID dan jam **berubah** ke waktu penerapan; lalu
`/metrics` memuat metrik baru dan halaman memuat kotak ambang. Sudah dicoba
28 Sep 2026: PID 2741779 (15:16) → **2843514 (17:58)**, halaman live memuat
"Ambang yang dipakai halaman ini" dan `meshtastic_node_last_heard_timestamp_seconds`.

> **Catatan kedua.** Pada penerapan yang sama, penanda `__DONE_4__` dari langkah
> terakhir (uji jalur admin) **tidak muncul** dalam batas tunggu 180 detik,
> sehingga skrip melaporkan `*** GAGAL: timeout ... ***` — padahal pemasangan
> **sudah selesai**. Jadi jangan panik: periksa `systemctl status` dan `/metrics`
> dulu sebelum mengulang penerapan. Bila perlu, jalankan ulang uji jalurnya
> terpisah:
>
> ```bash
> TTYD_URL='ws://192.168.20.36:7681/ws' ZIMA_PASS='...' \
>   node zima-hosting/zima-shell.mjs "sudo sh /DATA/AppData/meshtastic-monitor/pasang-layanan.sh"
> ```
