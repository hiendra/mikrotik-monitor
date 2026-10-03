# CATATAN STUDI — organisasi GitHub `meshtastic`

Catatan ini dibuat **28 Sep 2026** setelah membaca seluruh organisasi
<https://github.com/meshtastic> (145 repo publik) lewat GitHub API, plus
dokumentasi resmi di <https://meshtastic.org/> dan README proyek komunitas
yang dirujuk dokumentasi itu.

Gaya penulisannya: **apa → untuk apa → apa artinya bagi kita**. Bagian 6–7
adalah bagian yang paling berguna untuk pekerjaan Mesh ID; bagian 1–5 adalah
peta umum supaya tidak perlu menelusuri ulang dari nol.

- **§6.8–6.9** membahas dua proyek komunitas di **luar** organisasi
  (`anthonybo/meshtastic-dashboard` dan
  `Piccolino1965/Meshtastic-Ultimate-Center-ACH`) yang perlu dibandingkan
  karena keduanya menggarap sisi yang mirip dengan Mesh ID.
- **§6.10** merangkum **situs dokumentasi resmi**
  (`meshtastic.org/docs/about/`, `/docs/faq/`, `/docs/legal/`,
  `/docs/community/software/`) — termasuk dua angka yang menyentuh langsung
  cara kita memantau: batas NodeDB dan aturan merek.

Alat untuk menyegarkan data ada di repo ini:

```bash
node studi-meshtastic-github.mjs                  # ringkasan organisasi + 145 repo
node studi-meshtastic-github.mjs --cari mqtt      # saring nama/keterangan
node studi-meshtastic-github.mjs --dalam python mqtt-converter api
                                                  # rilis terakhir + isi direktori akar
```

> Tanpa token, GitHub API hanya memberi ~60 permintaan/jam per IP. Setelah itu
> muncul `HTTP 403`; tunggu sejam atau jalankan dengan `GITHUB_TOKEN=xxx ...`.

---

## 1. Organisasi dalam angka

| Hal | Nilai |
| --- | --- |
| Nama / laman | Meshtastic — <https://meshtastic.org> |
| Kontak | `contact@meshtastic.org`, X/Twitter `@TheMeshtastic` |
| Berdiri | 29 Feb 2020 |
| Repo publik | **145** (92 tanpa kategori, 34 `firmware-dep`, 8 `client`, 6 `docs`, 3 `core`, 2 `sdk`) |
| Bahasa | C++ 36, C 33, tanpa bahasa 23, Python 13, TypeScript 11, Kotlin 8, Shell 4, C# 3, Swift 2, Go 2, sisanya satuan |
| Sudah diarsipkan | **9**: `js`, `Meshtastic-gui-installer`, `meshtastic_linkplanner`, `RadioLib`, `meshtastic-hub`, `geeksville-androidlib`, `arduino-esp32-archive`, `SX126x-Arduino`, `Repeater_old` |
| Repo terbesar | `firmware` 8.353★ · `meshtastic` (dokumentasi) 2.201★ · `Meshtastic-Android` 1.852★ · `Meshtastic-Apple` 932★ · `web` 854★ · `python` 844★ |

Dua fakta yang sering menyesatkan kalau hanya melihat daftar repo:

1. **34 repo berlabel `firmware-dep`** adalah garpu pustaka pihak ketiga yang
   dipakai firmware (RadioLib, TinyGPSPlus, nanopb, GxEPD2, `esp8266-oled-ssd1306`,
   `platform-native`, dll). Itu bukan produk, melainkan dependensi yang
   di-vendor agar build firmware reprodusibel.
2. Repo `.github`, `artifacts`, `gh-runners`, `gh-action-firmware`,
   `translations`, `design`, `rfcs`, `enclosures`, `antenna-reports` adalah
   infrastruktur/dokumen komunitas, bukan perangkat lunak yang dijalankan.

---

## 2. Repo inti (kategori `core`)

| Repo | Bahasa | Isi | Relevansi |
| --- | --- | --- | --- |
| `firmware` | C++ | firmware resmi; cabang kerja **`develop`** = **2.8.1**; rilis terakhir **v2.7.26.54e0d8d** (24 Jun 2026) | menentukan protokol & perilaku node kita; gateway kita di **2.7.15.567b8ea** |
| `protobufs` | Go | definisi protobuf bersama; rilis terakhir **v2.8.0** (30 Agu 2026) | sumber tunggal `MeshPacket`, `ServiceEnvelope`, telemetri, `telemetry.proto` |
| `api` | TypeScript | backend `meshtastic.org`: basis data perangkat keras, build firmware, halaman rilis | sumber data perangkat keras kalau nanti butuh tabel board |
| `meshtastic` | MDX | **dokumentasi + situs** (repo paling padat informasi setelah `firmware`) | rujukan resmi: konfigurasi, MQTT, `meshtasticd`, integrasi |

**Penting:** `firmware/monitor/` **bukan** alat pemantauan — isinya hanya
`filter_c3_exception_decoder.py`, penyaring log untuk chip ESP32-C3. Jangan
ditunggu sebagai exporter resmi.

---

## 3. Klien & antarmuka

| Repo | Bahasa | Bintang | Catatan | Relevansi |
| --- | --- | --- | --- | --- |
| `Meshtastic-Android` | Kotlin | 1.852 | rilis **v2.8.2** (25 Sep 2026), aktif harian | acuan UI & istilah yang dipakai pengguna |
| `Meshtastic-Apple` | Swift | 932 | iOS/iPadOS/macOS/watchOS/visionOS | — |
| `web` | TypeScript | 854 | **monorepo** klien web + pustaka JS; rilis **v2.7.2**; laman `client.meshtastic.org`; berlabel `self-hosted` | bisa di-host sendiri sebagai UI lengkap kalau nanti bosan dengan halaman buatan sendiri |
| `web-flasher` | Nuxt/TS | 357 | `flasher.meshtastic.org`, pasang firmware dari browser | cara upgrade firmware tanpa CLI |
| `python` | Python | 844 | **CLI + API**; rilis **2.7.11** (17 Jul 2026) — **persis versi di venv kita** | pustaka yang kita pakai sehari-hari |
| `c-sharp` | C# | 51 | CLI/pustaka .NET, cabang `master` (Mar 2026) | — |
| `network-management-client` | Rust+TS | 481 | klien desktop Tauri untuk administrasi mesh, rilis **v0.3.1** (Jun 2025), terakhir disentuh Nov 2025 | contoh fitur analisis jaringan desktop |
| `map` | TypeScript | 13 | peta bersama, sepi | — |
| `device-ui` | C | 499 | pustaka UI perangkat (LVGL), dipakai layar TFT node | sumber tema ikon/warna kalau ingin menyeragamkan tampilan |
| `standalone-ui` | C | 30 | UI mandiri untuk HMI/Linux (cabang dari device-ui) | — |

---

## 4. SDK, integrasi, dan perkakas

| Repo | Bahasa | Catatan |
| --- | --- | --- |
| `rust` | Rust | pustaka resmi Rust untuk menyambung & mengonfigurasi radio, terakhir diperbarui Agu 2026 |
| `js` | TypeScript | **DIARSIPKAN** Jul 2025 — jangan dipakai; penerusnya ada di monorepo `web` |
| `meshtastic-sdk` | Kotlin | SDK Kotlin Multiplatform (BLE/TCP/serial) baru, rilis **v0.1.0** (17 Jul 2026) |
| `meshtastic-arduino` | C | pustaka Arduino untuk bicara ke node lewat WiFi/serial (bukan firmware) |
| `home-assistant` | Python | integrasi resmi Home Assistant, rilis **v0.6.1** (23 Apr 2025) walau repo masih aktif |
| `mqtt-converter` | Python | **jembatan protobuf ↔ JSON di atas MQTT** (lihat §6.4) |
| `mqtt` | C# | kerangka broker MQTT yang sadar-paket Meshtastic; eksperimental, terakhir Apr 2025 |
| `MQTTastic-Client-KMP` | Kotlin | klien MQTT 5.0 multiplatform |
| `meshtastic-mcp` | Python | **MCP server resmi untuk agen AI** (lihat §6.5) |
| `node-red-contrib-meshtastic` | TypeScript | simpul Node-RED, terakhir Apr 2024, sepi |
| `meshtastic-bot` | Go | bot komunitas (FAQ, privasi, syarat layanan) |
| `labeltastic` | Python | kios pencetak lencana QR kontak node (Niimbot) — proyek baru Sep 2026 |
| `Meshtasticator` | Python | simulator diskret LoRa/mesh — untuk menguji perilaku jaringan tanpa radio |
| `meshTestic` | TypeScript | rangkaian uji ujung-ke-ujung perangkat & aplikasi |
| `meshtasticd-wasm-node` | JS/WASM | `meshtasticd` dijalankan di WASM (kepala/terminal atau peramban) |
| `meshtastic-site-planner` | TypeScript | perencana lokasi node memakai SPLAT! (analisis RF + profil medan) |
| `antenna-reports` | dokumen | hasil uji antena komunitas — berguna sebelum membeli antena |
| `openwrt` / `openwrt-repo` | Makefile | paket Meshtastic untuk OpenWrt (router) |
| `MeshtasticOS` | dokumen | gambar siap pakai Raspberry Pi; **berhenti** Mar 2025 |
| `homebrew-tap`, `flathub-submission`, `Meshtastic-gui-installer` (arsip) | — | jalur distribusi paket |
| `ATAK-Plugin`, `pluginmeshtastic`, `TAKPacket-SDK` | C/Kotlin | integrasi TAK (situational awareness), TAKPacket-SDK aktif Sep 2026 |
| `defcontastic`, `burntastic`, `38c3`, `web-flasher-events` | C++/Vue | firmware & flasher khusus acara (DEF CON, Burning Man, 38C3) |

---

## 5. Versi yang perlu diingat (28 Sep 2026)

| Komponen | Versi terakhir | Tanggal | Catatan |
| --- | --- | --- | --- |
| `firmware` | v2.7.26.54e0d8d | 24 Jun 2026 | cabang `develop` sudah **2.8.1** |
| `protobufs` | **v2.8.0** | 30 Agu 2026 | naik dari seri 2.7 |
| `python` (CLI/API) | **2.7.11** | 17 Jul 2026 | **sama dengan venv kita** — tidak ada yang tertinggal |
| `web` (klien web) | v2.7.2 | 9 Agu 2026 | |
| `Meshtastic-Android` | v2.8.2 | 25 Sep 2026 | klien sudah di seri 2.8 |
| `meshtastic-sdk` | v0.1.0 | 17 Jul 2026 | |
| `meshtastic-mcp` | v0.1.0 | 3 Jul 2026 | |

Kesimpulan praktis: **pustaka Python kita sudah versi terbaru**, sedangkan
**firmware gateway kita (2.7.15) tertinggal ±11 build** dalam seri 2.7 yang
sama. Lompat ke 2.7.26 masih seri yang sama; ke 2.8 menunggu `python` 2.8
keluar dulu supaya pustaka dan protobuf tidak beda versi.

---

## 6. Yang paling menyentuh pekerjaan kita

### 6.1 Tidak ada exporter Prometheus resmi

Setelah menelusuri seluruh organisasi: **tidak ada repo resmi untuk Prometheus
atau Grafana**. Prometheus bukan bagian dari produk Meshtastic. Jadi exporter
`meshtastic-monitor/exporter-meshtastic.py` memang buatan sendiri, dan itu
wajar. Yang ada hanyalah tiga proyek komunitas, dua di antaranya dirujuk
halaman komunitas resmi:

| Proyek | Sumber data | Penyimpanan | Isi siap pakai |
| --- | --- | --- | --- |
| `cordelster/mesh-metrics` (dirujuk di `meshtastic.org/docs/community/software/community-mesh-metrics/`) | CLI `meshtastic` + node USB | **node_exporter textfile collector** → Prometheus/VictoriaMetrics | skrip + dasbor Grafana + contoh alert |
| `hacktegic/meshtastic-prometheus-exporter` (PyPI `meshtastic-prometheus-exporter` 2.7) | MQTT / BLE / serial / **TCP** | langsung Prometheus (default port 9464) | dasbor Grafana; catatan: dua exporter untuk jaringan yang sama tidak didukung |
| `tcivie/meshtastic-metrics-exporter` | MQTT (broker publik secara bawaan) | **TimescaleDB** (hipertabel, kompresi 14 hari, retensi 30 hari) | 5 dasbor Grafana bertaut + peta + topologi dari `NEIGHBORINFO_APP` |

Yang bisa kita curi tanpa pindah alat: **pola textfile collector** (mesh-metrics)
artinya tidak perlu port HTTP sama sekali — cukup menulis berkas `.prom` yang
sudah dibaca `node_exporter`. Ini alternatif kalau nanti port 9208 dianggap
mengganggu.

### 6.2 Perbandingan penamaan metrik

Metrik kita sudah rapi dan sebagian **lebih kaya** daripada proyek komunitas:

| Kita punya | Punya mereka | Catatan |
| --- | --- | --- |
| `meshtastic_node_direct` (1 = terdengar langsung lewat LoRa) | — | **khas kita**; berguna memisahkan node RF sendiri dari node MQTT |
| `meshtastic_node_favorite` | — | khas kita |
| `meshtastic_gateway_uptime_seconds`, `_reboot_count`, `_nodedb_count`, `_nodes_lora`, `_nodes_mqtt` | — | khas kita; dipakai alert reboot & NodeDB penuh |
| `meshtastic_node_last_heard_seconds` (umur) | `meshtastic_node_info_last_heard_timestamp_seconds` (epoch) | konvensi Prometheus lebih suka **timestamp epoch** |
| `meshtastic_node_snr_db`, `_hops_away`, `_latitude`, `_longitude`, `_altitude_meters` | `meshtastic_neighbor_info_snr_decibels`, `..._last_rx_time` | mereka punya metrik **tetangga** (topologi), kita belum |
| `meshtastic_device_*`, `meshtastic_environment_temp/humidity/pressure` | `meshtastic_telemetry_device_*`, `_env_*`, `_air_quality_pm*`, `_power_ch*`, `_gas_resistance_ohms` | mereka menutup telemetri kualitas udara & daya 3 kanal; **kita belum** |
| `meshtastic_packets_received_total{portnum}` | `meshtastic_mesh_packets_total` | setara |

Dua usulan kecil dari perbandingan ini, keduanya murah:

1. Tambah **alias timestamp**: `meshtastic_node_last_heard_timestamp_seconds`
   (epoch dari `user.lastHeard`) di samping metrik umur yang sudah ada —
   sekaligus membuat dasbor komunitas bisa dipakai langsung.
2. Tambah metrik **tetangga** dari paket `NEIGHBORINFO_APP` (SNR per pasangan
   node) supaya peta topologi bisa digambar seperti `tcivie`.

### 6.3 MQTT — satu-satunya jalur resmi untuk "banyak node"

Fakta dari dokumentasi resmi yang perlu diingat kalau jaringan tumbuh:

- Gateway mengunggah **`ServiceEnvelope`** (protobuf) ke
  `msh/REGION/2/e/CHANNELNAME/USERID`; versi firmware < 2.3.0 memakai `/c/`.
- Bila JSON diaktifkan, hanya portnum ini yang diserialisasi:
  `TEXT_MESSAGE_APP`, `TELEMETRY_APP`, `NODEINFO_APP`, `POSITION_APP`,
  `WAYPOINT_APP`, `NEIGHBORINFO_APP`, `TRACEROUTE_APP`, `DETECTION_SENSOR_APP`,
  `PAXCOUNTER_APP`, `REMOTE_HARDWARE_APP` → ke
  `msh/US/2/json/CHANNELNAME/USERID`. **JSON tidak tersedia di chip nRF52.**
- Broker publik: `mqtt.meshtastic.org:1883`, biasanya `meshdev` / `large4cats`.
- Kebijakan broker publik: **zero-hop** (data tidak menyebar lebih jauh di mesh
  lokal), filter portnum di PSK default, dan **pemotongan presisi lokasi**
  (10–16 bit) di PSK default.
- Downlink JSON dikirim ke `msh/US/2/json/mqtt/` dan butuh kanal bernama
  `mqtt` dengan Downlink aktif, lalu node di-reboot.
- Pada **broker privat**, PSK default justru tidak dianjurkan: tanpa kebijakan
  zero-hop, paket bisa membanjiri mesh.

Artinya: MQTT cocok sebagai **jalur cadangan** ketika koneksi TCP ke gateway
(`192.168.20.31:4403`) bermasalah, dan sebagai cara melihat node jauh tanpa
menggantungkan seluruh pemantauan pada satu gateway.

### 6.4 `mqtt-converter` — jembatan yang dirawat di dalam organisasi

Repo ini adalah **pengganti off-device untuk dukungan JSON MQTT yang dulu
menyatu di firmware**. Ia berlangganan `msh/REGION/2/e/CHANNEL/#`,
mendekripsi (AES-128/256, PSK hex/base64/bawaan), lalu menerbitkan JSON ke
`msh/REGION/2/json/CHANNEL/USERID`; arah sebaliknya mengubah JSON `send*`
menjadi paket protobuf terenkripsi untuk gateway teruskan ke radio. Tersedia
sebagai skrip Python, Docker, atau Docker Compose dengan Mosquitto bawaan.

Untuk kita ini penting: exporter kita sekarang hanya membaca **satu node
gateway lewat TCP**. Dengan `mqtt-converter` + broker sendiri, sumber data
bisa diperluas (beberapa gateway, node di luar jangkauan LoRa langsung) tanpa
mengubah protokol ke atas. Catatan: README-nya mengarahkan masalah ke
<https://github.com/caveman99/meshtastic-mqtt-converter>, jadi ini kontribusi
komunitas yang di-hosting di organisasi.

### 6.5 `meshtastic-mcp` — agen AI bisa memeriksa node sendiri

MCP server resmi (PyPI v0.1.0) dengan **inti portabel** yang bekerja pada
perangkat serial **atau `tcp://host:port`** tanpa perlu checkout firmware:

- `list_devices()`, `device_info(port)`, `list_nodes(port)`, `send_text(...)`,
  `packets_window(port, start="-30s")` untuk memastikan paket TX benar-benar terkirim;
- **recorder** + kueri log/telemetri/paket/peristiwa, plus **replay**
  (perangkat TCP simulasi + mesh sintetis + fuzzer);
- kemampuan tambahan bila prasyaratnya ada: build/flash firmware (PlatformIO),
  orkestrasi emulator Android/iOS, oracle kepatuhan RF lewat RTL-SDR,
  pembacaan Discord, sniffer BLE, dan `mvgrind` (menambang NodeNum cantik).

Kaitan dengan kita: perintah diagnosa di `CATATAN-MESHNODEID.md` §3 bisa
diringkas jadi satu panggilan agen, dan `packets_window` memberi bukti paket
tanpa harus menebak dari log exporter.

### 6.6 `meshtasticd` — node Linux native untuk uji tanpa radio

Dari dokumentasi dan README proyek terkait: `meshtasticd` (portduino)
menjalankan "firmware" Meshtastic sebagai daemon di Linux; node native itu
mendengarkan **TCP `:4403`** dan bisa saling terhubung lewat **UDP multicast
`224.0.0.69:4403`** — **tanpa perangkat LoRa sama sekali**. Dokumentasi:
<https://meshtastic.org/docs/meshtasticd/>, paket OpenWrt tersedia di repo
`openwrt`/`openwrt-repo`.

Manfaat nyata untuk kita: bisa membuat **mesh uji** di dalam jaringan sendiri
lalu menguji ulang `exporter-meshtastic.py`, `notif-meshtastic.py`, dan
`traceroute-node.py` tanpa menyentuh mesh produksi — sesuatu yang sekarang
sulit karena semua uji menumpang gateway `192.168.20.31`.

### 6.7 Alternatif yang belum kita pakai

- **Home Assistant resmi** (`home-assistant`): jalur notifikasi cadangan bila
  ntfy kena `429` seperti yang pernah kita alami — HA punya automasi dan
  riwayat bawaan.
- **Klien web resmi** (`web`, berlabel `self-hosted`): bisa di-host sendiri
  kalau ingin tampilan kaya (peta, daftar pesan, pengaturan) tanpa menulis UI.
- **`Meshtasticator`**: simulator diskret untuk menjawab pertanyaan
  "kalau node ditambah di titik X, apakah tetap terhubung?" sebelum membeli
  perangkat.
- **`meshtastic-site-planner`** + `antenna-reports`: perencanaan lokasi & antena
  berbasis analisis RF (SPLAT!) dan hasil uji komunitas.

### 6.8 `anthonybo/meshtastic-dashboard` — dasbor web (di luar organisasi)

Ditambahkan 28 Sep 2026. Proyek perorangan (**13 commit, 0 bintang** saat
diperiksa), lisensi MIT, bukan bagian organisasi `meshtastic`. Isinya dasbor
web dua lapis:

```
node Meshtastic ──BLE──▶ backend FastAPI (Python) ──WebSocket+REST──▶ frontend Vue 3
                              │                                        (Vite + Pinia +
                              └── PostgreSQL (riwayat pesan/telemetri)   Leaflet + Chart.js)
```

| Hal | Nilai |
| --- | --- |
| Sambungan | **BLE saja** (`meshtastic.ble_interface.BLEInterface`), nama perangkat di `.env` |
| Platform | **macOS / Linux** (butuh Bluetooth); tidak ada jalur serial/TCP |
| Pustaka | `meshtastic==2.7.6` (dipin), FastAPI 0.115, SQLAlchemy 2, asyncpg, Postgres 14+ |
| Endpoint | `/api/connection/{status,connect,disconnect,reset,scan}`, `/api/nodes`, `/api/nodes/live`, `/api/nodes/{id}/traceroute`, `/api/messages`, `/ws` |
| Metrik/alert | **tidak ada** — tidak ada `/metrics`, Prometheus, maupun notifikasi |
| Ruang lingkup | **satu** perangkat, tanpa dukungan banyak gateway / MQTT |

Jadi tidak bisa langsung dipakai untuk Mesh ID: gateway kita dijangkau lewat
**TCP `192.168.20.31:4403`**, sedangkan proyek ini menuntut Bluetooth dan
mesin tempat backend-nya berjalan harus berada dekat perangkat. Nilainya bagi
kita adalah **ide tampilan**, bukan penambah metrik:

| Ide yang bisa ditiru | Keadaan kita sekarang |
| --- | --- |
| **Visualisasi traceroute**: jalur hop digambar di peta, tiap hop diberi SNR | `traceroute-node.py` sudah bisa menanyakan rute, tetapi hasilnya teks saja |
| **Tabel ambang operasional** yang dipublikasikan: ChUtil <25% sehat, 25–40% sedang (throttling mulai), 40–50% tinggi (pembaruan GPS dikurangi), >50% padat; AirUtilTx <5% bagus, 5–8% wajar, >8% kelebihan | alert kita memakai satu ambang kasar (`meshtastic_device_channel_utilization_percent > 60`) |
| **Warna penanda peta menurut jumlah hop** (langsung, 1–2, 3–4, 5+) + penanda berdenyut untuk online/offline | halaman kita menampilkan tabel, belum ada peta berbasis kategori hop |
| **Konsol peristiwa langsung** yang bisa disaring per jenis peristiwa dan dijeda | kita membaca log berkas/`journalctl` |
| **Riwayat pesan + pelacakan ACK/NAK** | kita sengaja belum menyimpan isi pesan (hanya telemetri) |
| **Manajemen koneksi eksplisit** (pindai, sambung ulang, reset bila macet) | kita mengandalkan penyambungan ulang otomatis di exporter |

Yang **tidak** perlu ditiru: PostgreSQL + Node.js + Vue hanya untuk melihat
data satu node, dan ketergantungan pada BLE yang mengunci penempatan layanan.

### 6.9 `Piccolino1965/Meshtastic-Ultimate-Center-ACH` — konsol desktop (di luar organisasi)

Ditambahkan 28 Sep 2026. Proyek perorangan berbahasa Italia (**8 bintang,
17 commit**), GUI **Python + Tkinter**, dan — tidak seperti §6.8 — menyambung
lewat **serial atau TCP/IP**, jadi bisa menunjuk gateway kita
`192.168.20.31:4403`.

| Hal | Nilai |
| --- | --- |
| Berkas inti | `main.py` (pintu masuk), `gui.py` (Tkinter), `core.py` (`MeshtasticDevice`: sambung, baca node, kirim pesan, ACK, backup/restore), `utils.py`, `constants.py` (palet gelap), `i18n.py` + `locales/{it,en}.json`, `tabs.py` |
| Ketergantungan | `meshtastic`, `pypubsub`, `protobuf`, `tkinter`, `plyer` (notifikasi desktop, opsional) |
| Cakupan tab | identitas node, posisi, range test, MQTT, display, radio, WiFi, kanal utama, kanal lain, vista mesh, daftar node, pesan kanal, pesan langsung, status pesan, statistik, pengaturan umum |
| Penulisan konfigurasi | hanya seksi yang berubah (tulis selektif), dengan transaksi bila perlu |
| Backup/restore | snapshot **JSON** penuh: pemilik + `localConfig` + `moduleConfig` + kanal |
| Pesan | kirim teks & pesan langsung dengan pelacakan **ACK**, timeout, riwayat, statistik keberhasilan |
| Lisensi | **“Custom Software License” — All rights reserved.** Redistribusi, sublisensi, penjualan, dan penyebaran versi modifikasi **dilarang tegas**; modifikasi hanya untuk pemakaian pribadi/internal |

**Peringatan lisensi.** Berbeda dari organisasi Meshtastic (GPL-3.0) dan §6.8
(MIT), proyek ini **tidak** boleh kodenya disalin ke dalam repo kita atau
disebarkan ulang. Boleh dipakai sebagai alat di komputer sendiri, tetapi jangan
menyalin potongan kodenya ke `meshtastic-monitor/`.

Yang berguna sebagai **ide alur kerja**, bukan kode:

1. **Backup sebelum berubah.** Kebiasaan mengambil snapshot konfigurasi utuh
   lebih dulu, baru mengubah perangkat — persis yang kita butuhkan sebelum
   `reset-node.py` (reset NodeDB) dijalankan di gateway hidup. Kabar baiknya,
   **tidak perlu menulis alat baru**: CLI resmi di venv kita sudah
   menyediakannya

   ```bash
   cd meshtastic-monitor
   ./venv/Scripts/python -m meshtastic --host 192.168.20.31 --export-config backup-gateway.yaml
   ./venv/Scripts/python -m meshtastic --host 192.168.20.31 --configure backup-gateway.yaml
   ```

   (`--export-config` / `--configure`, format `auto|yaml|binary|protobuf` —
   terverifikasi ada di pustaka 2.7.11 yang kita pakai.)
2. **Tulis selektif per seksi** saat mengubah konfigurasi node, bukan menulis
   seluruh konfigurasi sekaligus — mengurangi risiko mengembalikan pengaturan
   lama yang sudah berubah.
3. **Pesan langsung dengan pelacakan ACK** + riwayat; kita belum menyimpan
   pesan sama sekali.
4. **Antarmuka multibahasa berbasis berkas JSON** (`locales/id.json`) bila suatu
   saat halaman ingin berbahasa Indonesia dan Inggris.

Batasannya sebagai alat: GUI Tkinter butuh layar, jadi tidak cocok dipasang di
host ZimaOS yang tanpa desktop — perannya hanya **konsol sesekali** dari mesin
Windows untuk pekerjaan konfigurasi, bukan untuk pemantauan 24/7.

### 6.10 Situs dokumentasi: bagian About, Legal, dan daftar aplikasi komunitas

```
meshtastic.org/docs/about/     -> pintu ke FAQ + dua halaman enkripsi (isi "about" sebenarnya)
meshtastic.org/docs/faq/       -> FAQ besar (firmware, klien, kanal, ham, mesh)
meshtastic.org/docs/legal/     -> privasi, aturan merek, kode etik
meshtastic.org/docs/community/software/  -> daftar aplikasi komunitas resmi
```

Sitemap resmi memuat **421 URL**; panjang bagian `about` hanya tiga halaman, jadi
isi pentingnya justru ada di halaman **Legal** — dan beberapa di antaranya
menyentuh langsung cara kita memantau mesh.

| Temuan (dari dokumentasi resmi) | Arti bagi kita |
| --- | --- |
| **NodeDB terbatas ~100 node di sebagian besar perangkat**; saat penuh, node tertua/paling tidak menarik tergeser — **kecuali yang bertanda Favorite, dijamin tidak dihapus** | ambang peringatan kita `MESH_DB_AMBANG=190` (halaman menampilkan "117 / 190") **perlu diverifikasi**: angka resmi 100, tetapi gateway kita sudah menyimpan 117 entri, jadi batasnya bergantung perangkat/firmware. Strategi `favorite-node.py` kita **dibenarkan resmi** oleh dokumen ini |
| Kanal memakai **AES-CTR tanpa autentikasi**: pemegang PSK bisa mengirim pesan **mengatasnamakan node lain**, dan penyerang yang tahu sebagian isi bisa mengganti bit atau mengulang paket | privasi & keaslian kanal kita bergantung pada PSK **dan perlindungan fisik tiap node**, bukan pada kriptografi kanal |
| DM sejak 2.5 memakai **x25519 + AES-CCM**, model **TOFU** (tanpa otoritas pusat). Karena NodeDB terbatas, penyerang bisa membanjiri node palsu hingga node sah tergeser, lalu memakai kunci berbeda untuk nomor yang sama | mitigasinya: Favorite tak pernah dihapus, klien menandai kunci yang berubah (ikon kunci merah), dan DM otomatis dijadikan Favorite |
| Peninjau kriptografi mencatat: **modul admin jarak jauh lewat AES-CTR tanpa MAC/AEAD** | perintah admin kita (reset NodeDB, tandai Favorite) juga melintas di kanal itu — jalankan hanya saat perlu, dan lebih aman lewat **TCP ke gateway** daripada lewat udara |
| Peringatan praktis: siapa pun yang **memegang salah satu radio** bisa mengambil kunci kanal atau ikut mendengarkan; membagikan **QR/URL kanal** ke orang yang salah membuat semua pesan kanal (lampau & akan datang) terbaca; perangkat **promiscuous** terhadap klien terdekat; di **mode ham, enkripsi dimatikan** | berhati-hati membagikan tautan kanal; jangan berbagi kunci melalui gambar QR di ruang publik |
| **Privasi resmi**: proyek tidak mengumpulkan data pribadi, tetapi bila **MQTT aktif, data lokasi bisa diakses pihak ketiga** | halaman `meshid.clusternet.my.id` publik dan memuat koordinat GPS — keputusan pemilik, tetapi inilah rambu resminya |
| **Merek**: Meshtastic® adalah merek terdaftar Meshtastic LLC. Situs komunitas **boleh memakai merek tanpa izin tertulis** asal: logo menaut ke meshtastic.org (atau tautan mencolok), atribusi merek disertakan, dan tercantum pernyataan mencolok **"situs ini tidak berafiliasi dengan atau didukung proyek Meshtastic"**. Logo alternatif **M-Powered / M-PWRD** tidak butuh izin sama sekali | halaman Mesh ID memakai nama Meshtastic tetapi **belum** memuat atribusi/penyangkalan itu — tambahan satu baris di kaki halaman sudah cukup untuk patuh |
| FAQ lain yang penting: **tidak ada OTA lewat LoRa**; rilis firmware bertingkat **alpha** (mis. cabang `develop`) dan **beta** (dianjurkan); Meshtastic memakai **LoRa titik-ke-titik, bukan LoRaWAN**; kanal hanya bisa dibagikan lewat URL/QR | rencana naik firmware 2.7.15 → 2.7.26 termasuk jalur "beta" yang dianjurkan |

**Daftar aplikasi komunitas resmi** (halaman `community/software/`) menegaskan
bahwa wilayah yang kita garap memang ramai:

| Proyek | Ringkas |
| --- | --- |
| **MeshMonitor** | dasbor web mandiri untuk memantau mesh + MQTT dalam satu antarmuka; broker MQTT tertanam, kontrol akses per pengguna, notifikasi push, REST API; Docker/Kubernetes, SQLite/PostgreSQL/MySQL |
| **MeshDash** | dasbor web mandiri; serial/TCP/BLE/MQTT/WebSerial, analisis paket "MeshShark", analisis telemetri, penjadwal tugas, sistem plugin, Docker |
| **MeshApp** | klien desktop GPL-3.0 (TCP/serial/BLE) dengan chat multi-kanal, peta node, riwayat traceroute, inspeksi paket LoRa, proksi MQTT, IDE Lua |
| **Meshtastic Web API** | antarmuka REST untuk node lewat sambungan serial |
| **Mesh-metrics**, **Harbor Scale**, **Node-RED Messages Node**, **Contact**, **MeshHessen Client** | pengumpul metrik untuk Prometheus/VictoriaMetrics + Grafana, telemetri ke Grafana Cloud, simpul Node-RED, klien chat terminal, klien Windows untuk perlindungan sipil |

Dua yang pertama itu tandingan paling dekat dengan Mesh ID: fungsinya jauh lebih
luas (notifikasi push, kontrol akses, broker MQTT, administrasi jarak jauh)
tetapi menuntut tumpukan yang jauh lebih berat (Docker, basis data). Berguna
diketahui sebelum memutuskan menambah fitur besar ke exporter sendiri.

---

## 7. Usulan tindak lanjut (urut manfaat)

| # | Usulan | Usaha | Manfaat |
| --- | --- | --- | --- |
| 1 | Tambah `meshtastic_node_last_heard_timestamp_seconds` (epoch) di samping metrik umur | kecil | mengikuti konvensi Prometheus; dasbor komunitas bisa dipakai |
| 2 | ~~Sambungkan Prometheus ZimaOS ke `http://127.0.0.1:9208/metrics` + panel Grafana `meshtastic_*`~~ — **sudah dikerjakan 28 Sep 2026** (job `meshtastic`, dasbor `meshtastic-node`, 13 aturan; lihat §5.13 `CATATAN-MESHNODEID.md`) | kecil | data historis & alert yang sudah dirancang di `alert-meshtastic.yml` benar-benar jalan |
| 3 | Pasang monitor Uptime Kuma untuk `https://meshid.clusternet.my.id` | kecil | tahu halaman mati sebelum pengguna lain tahu |
| 4 | Aktifkan MQTT uplink di gateway + jalankan `mqtt-converter` di ZimaOS | sedang | jalur data kedua, tidak bergantung satu gateway TCP |
| 5 | Node uji `meshtasticd` (TCP :4403 + multicast) untuk menguji exporter/notifier | sedang | uji regresi tanpa mengganggu mesh asli |
| 6 | Tambah metrik `NEIGHBORINFO_APP` (SNR tetangga) untuk peta topologi | sedang | melihat kualitas tautan antar node, bukan hanya ke gateway |
| 7 | Lengkapi telemetri: daya 3 kanal & kualitas udara (PM) bila ada sensornya | sedang | menyamai cakupan exporter komunitas |
| 8 | Rencanakan naik firmware 2.7.15 → **2.7.26** (seri sama) | sedang | perbaikan bug seri 2.7 tanpa menunggu pustaka 2.8 |
| 9 | Pakai `meshtastic-mcp` untuk diagnosa berbasis agen | kecil | mempercepat tindak lanjut ala §3 `CATATAN-MESHNODEID.md` |
| 10 | Selaraskan ambang alert ChUtil/AirUtilTx dengan pedoman di §6.8 | kecil | peringatan lebih dini sebelum kanal padat |
| 11 | Gambar rute `traceroute` di halaman exporter (hop + SNR per tautan) | sedang | memakai data yang sudah bisa diambil `traceroute-node.py` |
| 12 | Simpan snapshot konfigurasi gateway (`--export-config`) sebelum setiap tindakan berisiko (reset NodeDB, naik firmware) | kecil | jalur pemulihan cepat tanpa menebak ulang pengaturan |
| 13 | Verifikasi batas NodeDB sebenarnya untuk `SEEED_XIAO_S3` lalu sesuaikan `MESH_DB_AMBANG` (dokumen resmi menyebut ~100; gateway kita sudah 117) | kecil | peringatan "database hampir penuh" datang di saat yang benar |
| 14 | Tambahkan atribusi merek + pernyataan "tidak berafiliasi" di kaki halaman publik (§6.10) | kecil | halaman patuh aturan merek Meshtastic |

> **Sudah dikerjakan 28 Sep 2026:** #1 (metrik
> `meshtastic_node_last_heard_timestamp_seconds`) dan pewarnaan ambang #10 di
> halaman (kanal, air TX, dan hop) — lihat
> `meshtastic-monitor/README.md`, bagian "Warna ambang di kolom Kanal, Air TX,
> dan Hop". Ujinya: `meshtastic-monitor/uji-halaman-meshtastic.py` (data tiruan,
> tanpa menyentuh node). Tindakan berisiko (#12) dan sisanya belum dikerjakan.

---

## 8. Jebakan & catatan penting

1. **Jangan campur seri.** Firmware `develop` = 2.8.1 dan `protobufs` = 2.8.0,
   tetapi pustaka Python terbaru masih **2.7.11** dan protobuf yang
   disematkan di venv kita ikut 2.7.11. Menaruh `protobufs` 2.8 ke samping
   pustaka 2.7 berisiko salah baca medan.
2. **`js` sudah diarsipkan** (Jul 2025) — kode klien/pustaka JS sekarang ada di
   monorepo `web` (`apps/`, `packages/`).
3. **`firmware/monitor/` bukan alat pemantauan**, hanya penyaring log chip C3.
4. **34 repo `firmware-dep` bukan produk** — garpu pustaka pihak ketiga.
5. **`MeshtasticOS` berhenti** sejak Mar 2025 (repo satu commit); jangan
   dijadikan dasar pemasangan di Raspberry Pi.
6. **NodeDB tidak 190.** Dokumentasi resmi menyebut batasnya **~100 node** pada
   sebagian besar perangkat (dengan Favorite dikecualikan dari penggusuran),
   sedangkan ambang alert kita 190 dan gateway kita sudah memegang 117 entri.
   Jangan menganggap ambang itu benar sebelum diukur di perangkatnya sendiri.
7. **Kanal tanpa autentikasi.** AES-CTR pada kanal tidak menjamin keaslian:
   pemegang PSK bisa mengatasnamakan node lain, dan perintah admin tidak
   dilindungi MAC/AEAD. Jalankan perintah administratif dari TCP bila bisa.
8. **JSON MQTT tidak ada di nRF52** — kalau nanti memakai jalur JSON, pastikan
   perangkatnya ESP32/stm32, bukan nRF52.
9. **PSK default di broker privat berbahaya** (tanpa zero-hop) — untuk broker
   sendiri, pakai kanal privat dengan PSK sendiri, sejalan dengan praktik kita
   sekarang.
10. **Halaman komunitas ≠ resmi**: `mesh-metrics` (cordelster),
    `meshtastic-metrics-exporter` (tcivie), dan aplikasi di
    `community/software/` adalah proyek komunitas yang **dirujuk** situs resmi;
    dukungan ada pada penulis masing-masing.
11. `Antenna-reports`, `enclosures`, `design`, `translations`, `rfcs` adalah
    dokumen — tidak ada kode yang dijalankan.
12. Data pada catatan ini diambil **28 Sep 2026**; repo Meshtastic bergerak
    cepat (beberapa repo terakhir disentuh hari itu juga), jadi segarkan dulu
    dengan `node studi-meshtastic-github.mjs` sebelum memutuskan.

---

## 9. Berkas yang berkaitan

| Berkas | Isi |
| --- | --- |
| `studi-meshtastic-github.mjs` | alat pemeta organisasi meshtastic (ringkasan, saring, penelusuran repo) |
| `CATATAN-MESHNODEID.md` | catatan perawatan Mesh ID (alamat, perintah, kendala, rollback) |
| `meshtastic-monitor/README.md` | penjelasan exporter, metrik, dan kendala kode |
| `meshtastic-monitor/exporter-meshtastic.py` | daftar metrik kita (bagian komentar kepala berkas) |
| `meshtastic-monitor/dashboard-grafana.json`, `alert-meshtastic.yml` | dasbor & aturan alert yang memakai metrik tersebut |
| `meshtastic-monitor/mqtt-downlink.py` | jalur MQTT yang sudah ada di repo kita (berkaitan dengan §6.3–6.4) |
| `meshtastic-monitor/requirements.txt` | pin `meshtastic>=2.5.0` + `prometheus-client` (venv berisi 2.7.11) |
| `meshtastic-monitor/mulai-ulang-zima.sh` | restart unit di host ZimaOS tanpa mengunggah berkas (dipakai saat halaman "hidup tetapi buta") |

> **Batas yang perlu diingat saat menulis perkakas baru** (§6.x): API node
> Meshtastic (port 4403) melayani **satu klien** saja. Setiap perkakas tambahan
> yang menyambung ke radio akan memutus exporter yang sedang jalan — dan
> pustaka Python-nya **tidak** selalu sadar sambungannya dicabut. Karena itu
> perkakas baru sebaiknya membaca `/data.json` exporter, bukan menyambung
> sendiri ke `4403`, kecuali memang perlu menulis ke radio.
