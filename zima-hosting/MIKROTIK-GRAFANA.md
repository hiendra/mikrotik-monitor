# MikroTik → Grafana: rantai data dan perbaikannya

Dokumen ini ditulis setelah kejadian **"Grafana tidak menampilkan data MikroTik"**
(24 September 2026) dan berisi hasil pemeriksaan langsung ke server.

> Ringkasan gejala → solusi dari beberapa kendala (termasuk router
> `192.168.200.1` yang tidak muncul) ada di **`CATATAN-KENDALA.md`**.

## Alur data

```
router MikroTik ──SNMP──▶ snmp_exporter ──HTTP──▶ Prometheus ──▶ Grafana
192.168.20.1              9116 (modul mikrotik, if_mib)   9090      datasource "Prometheus"
192.168.200.253           9117 (modul routeros_hr)
192.168.200.1
```

| Bagian | Nilai |
|---|---|
| App ZimaOS | `mikrotik-monitor` (`net.mikrotik.monitor`), compose di `/var/lib/casaos/apps/mikrotik-monitor/docker-compose.yml` |
| Container | `mikrotik-prometheus`, `mikrotik-snmp-exporter`, `mikrotik-snmp-exporter-hr` |
| Port host | Prometheus `9090`; kedua exporter hanya `expose` (9116/9117 di jaringan `mikrotik-monitor_default`) |
| Data TSDB | `/DATA/AppData/mikrotik-monitor/prometheus` (retensi 30 hari) |
| Konfigurasi scrape | `/DATA/AppData/mikrotik-monitor/prometheus.yml` → di-mount ke `/etc/prometheus/prometheus.yml` |
| Community SNMP | `public` (auth `public_v2`) |
| Grafana | `grafana.clusternet.my.id` → `192.168.145.252:3003`, admin `admin` |
| Datasource Grafana | nama **`Prometheus`**, uid **`prom-mikrotik`** → `http://172.17.0.1:9090` |
| Dasbor MikroTik | uid **`LyX-A_nnk`** ("Mikrotik", 19 panel), plus `mikrotik-ringkas` ("MikroTik — Ringkasan Router") buatan sendiri |
| Dasbor Mesh ID | uid **`meshtastic-node`** (23 panel) — job `meshtastic`, rinciannya di bagian "Kasus ketiga" di bawah |

## Akar masalah yang ditemukan

Prometheus **crash-loop** (`EXIT=1`, `RESTARTS=9`) dengan pesan:

```
sh: line 0: can't create /etc/prometheus/prometheus.yml: Permission denied
```

Sebabnya: konfigurasi scrape sebelumnya ditulis **dari dalam container** oleh
`entrypoint:` compose (`printf ... > /etc/prometheus/prometheus.yml`). Image
`prom/prometheus` menjalankan prosesnya sebagai user **`nobody`**, sedangkan
`/etc/prometheus` milik root — jadi penulisan selalu gagal dan Prometheus tidak
pernah start. Karena Prometheus menganggur, dasbor Grafana tampil kosong
(datasource `prom-mikrotik` memang menunjuk ke 9090, tetapi tidak ada isinya).

Ini pola kerusakan yang muncul diam-diam setiap `prom/prometheus:latest` ditarik
ulang: konfigurasi hidup di dalam container, bukan di host.

## Perbaikan yang diterapkan

1. Konfigurasi dipindah ke host: `/DATA/AppData/mikrotik-monitor/prometheus.yml`
   (berisi 4 job: `mikrotik`, `mikrotik-ifs`, `mikrotik-hr`, `prometheus`;
   `auth: [public_v2]` ditulis eksplisit di semua job).
2. Compose diganti: blok `entrypoint:` shell **dihapus**, diganti `command:` biasa,
   dan berkas konfigurasi di-mount read-only:

   ```yaml
   command:
       - --config.file=/etc/prometheus/prometheus.yml
       - --storage.tsdb.path=/prometheus
       - --storage.tsdb.retention.time=30d
       - --web.listen-address=:9090
   volumes:
       - type: bind
         source: /DATA/AppData/mikrotik-monitor/prometheus
         target: /prometheus
       - type: bind
         source: /DATA/AppData/mikrotik-monitor/prometheus.yml
         target: /etc/prometheus/prometheus.yml
         read_only: true
   ```

   Compose lama dicadangkan ke `docker-compose.yml.bak-24sep`.
3. `docker compose up -d` di folder app → `mikrotik-prometheus` naik normal.

Jangan kembalikan ke pola `printf > /etc/prometheus/...`: pola itu memang yang rusak.

## Cara memeriksa sendiri

```bash
# 1. Prometheus hidup?
sudo docker ps --filter name=mikrotik-prometheus --format "{{.Status}}"

# 2. Target mana yang UP (jalankan di host, port 9090 tidak terbuka ke subnet lain)
curl -s "http://127.0.0.1:9090/api/v1/query?query=up" | tr ',' '\n' | grep -E "instance|job"

# 3. Uji langsung SNMP tanpa Prometheus (dari dalam jaringan docker)
sudo docker run --rm --network mikrotik-monitor_default python:3-alpine python3 -c \
  "import urllib.request;print(len(urllib.request.urlopen('http://mikrotik-snmp-exporter:9116/snmp?target=192.168.20.1&module=mikrotik&auth=public_v2',timeout=30).read()))"
# keluaran sehat: puluhan ribu byte

# 4. Dari sisi Grafana (datasource prom-mikrotik)
curl -s -u admin:SANDI "http://192.168.145.252:3003/api/datasources/proxy/uid/prom-mikrotik/api/v1/query?query=count(%7Bjob%3D~%22mikrotik.*%22%7D)"
```

Terakhir diverifikasi: ketiga router `UP`, **12.597 seri metrik**, dan dasbor
`LyX-A_nnk` menampilkan CPU 5%, suhu 35 °C, RAM 5%, disk 33%.

## Catatan pemeriksaan Grafana

- Membaca `grafana.db` dengan SQLite **read-only** menyesatkan: perubahan yang
  masih berada di WAL tidak terlihat, sehingga dasbor yang ada bisa tampak
  "tidak ada". Pakai API (`/api/search`, `/api/dashboards/uid/...`) untuk memastikan.
- Port `9090`/`9091`/`9092` di host tidak terjangkau dari subnet lain (mis.
  `192.168.20.x`) meski sudah dipublikasikan — periksa dari dalam host.
- Datasource `Prometheus Air Quality` menunjuk ke `172.17.0.1:9091` (container
  `air-prometheus`) yang **sudah mati sejak 6 hari**; kalau dasbor kualitas udara
  juga ingin hidup, itu masalah terpisah.

## Kasus kedua: router 192.168.200.1 (CCR1009) tidak muncul di Grafana

**Gejala (27 Sep 2026).** Ketiga job untuk instance `192.168.200.1` —
`mikrotik`, `mikrotik-ifs`, `mikrotik-hr` — berstatus `up=0` dengan
`lastError: context deadline exceeded`, sehingga dasbor
**"MikroTik 192.168.200.1 (CCR1009)"** tampil kosong. Dua router lain
(`192.168.20.1`, `192.168.200.253`) sehat.

**Sebab.** SNMP di router itu **aktif**, tetapi community yang dipakai
snmp_exporter (`auth public_v2` → community string `public`) punya
`addresses=103.105.79.0/24`. Permintaan dari host pemantau di
`192.168.20.0/24` dibuang **tanpa balasan** (terlihat di tabel koneksi:
`192.168.200.253 → 192.168.200.1:161` dengan `repl-packets=0`).

**Perbaikan.** Izinkan alamat pemantau pada community `public`:

```routeros
# backup dulu
/system backup save name=sebelum-perbaikan-snmp

# perbaikan (via terminal RouterOS / API 8728)
/snmp community set [find name="public"] addresses=0.0.0.0/0

# verifikasi
/snmp community print
```

> Catatan penting: saat penyelidikan, daftar alamat bertingkat
> (`103.105.79.0/24,192.168.20.0/24,192.168.145.0/24`) tampak "tidak diterima".
> Sebab sebenarnya: **sumber paket dari subnet `192.168.20.x` di-SNAT menjadi
> `192.168.200.253`** sebelum tiba di router ini — jadi alamat aslinya memang
> tak ada di daftar. `0.0.0.0/0` bekerja (seperti community
> `monitoring`/`zabbix`/`server`). Bila ingin dikunci, masukkan alamat NAT-nya
> (`192.168.200.253`). Rinciannya di `CATATAN-KENDALA.md` Entri 5.

**Verifikasi setelah perbaikan.** Ketiga job `up=1`, `count({instance="192.168.200.1"})`
≈ 9.800 seri. Dasbor butuh **beberapa menit** sebelum grafik terlihat: rentang
bawaan `now-6h` sementara data baru mulai terkumpul, dan `rate(ifHCInOctets[5m])`
perlu ≥ 2 sampel. Persempit rentang waktu (mis. "Last 15 minutes") atau tunggu.

## Kasus ketiga: metrik Mesh ID ditambahkan ke Prometheus yang sama

Grafana/Prometheus ini juga dipakai untuk memantau **Mesh ID** (node Meshtastic).
Tidak ada Prometheus baru: yang ditambahkan hanya **satu job scrape**, satu berkas
aturan, dan satu dasbor.

| Bagian | Nilai |
|---|---|
| Job scrape | `meshtastic` → `host.docker.internal:9208/metrics`, `scrape_interval: 30s` |
| Kenapa `host.docker.internal` | exporter mendengarkan di **host**, bukan di jaringan docker; `extra_hosts: [host.docker.internal:host-gateway]` ditambahkan ke compose supaya tidak terikat pada nama jaringan |
| Aturan | `rule_files: [/etc/prometheus/alert-meshtastic.yml]` (13 aturan; volume ketiga read-only `create_host_path: false`) |
| Dasbor | uid **`meshtastic-node`** (23 panel) di `https://grafana.clusternet.my.id/d/meshtastic-node` — lihat juga `meshtastic-monitor/README.md` |
| Datasource | **sama** dengan MikroTik: nama `Prometheus`, uid `prom-mikrotik` → `http://172.17.0.1:9090` |
| Penerbit dasbor | `meshtastic-monitor/terbitkan-dasbor-grafana.py` (lewat API, `--periksa` untuk menguji tiap kueri panel) |

```bash
# dari dalam host (lewat zima-shell.mjs) — target Mesh ID UP?
curl -s "http://127.0.0.1:9090/api/v1/query?query=up{job=%22meshtastic%22}"

# apakah aturan Mesh ID termuat?
sudo docker exec mikrotik-prometheus promtool check rules /etc/prometheus/alert-meshtastic.yml

# jumlah seri job meshtastic
curl -s "http://127.0.0.1:9090/api/v1/query?query=count(%7Bjob%3D%22meshtastic%22%7D)"
```

> **Jebakan:** menyunting `rule_files:` tanpa ikut me-mount berkasnya membuat
> Docker mendirikan **direktori kosong** di jalur itu dan Prometheus **gagal
> start**. Pasang volume bersama perubahannya, lalu `promtool check config`.

## Alat bantu

`zima-hosting/zima-shell.mjs` menjalankan perintah di host ZimaOS lewat WebSocket
ttyd (jauh lebih andal daripada mengetik di halaman terminal canvas-nya):

```bash
ZIMA_PASS=... node zima-hosting/zima-shell.mjs "uname -a" "docker ps"
ZIMA_PASS=... CMD_FILE=daftar-perintah.txt node zima-hosting/zima-shell.mjs
```
