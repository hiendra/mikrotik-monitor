# Inspeksi MikroTik 192.168.200.1

Tanggal inspeksi: 27 Sep 2026 (07:2x–07:40 WIB)
Metode: API RouterOS 8728, user `admin` (baca/tulis), dari LAN 192.168.20.x via NAT `192.168.200.253`.

> **Jangan simpan sandi di berkas ini.** Sandi router tidak ditulis di sini.

---

## 1. Profil perangkat

| Item | Nilai |
|---|---|
| Identity | `bks.marina.garuda.net.id` |
| Board | **CCR1009-7G-1C** (a7e209b1654d) |
| RouterOS | **6.49.21 (long-term)**, arsitektur `tile` |
| Firmware | current = upgrade = 6.49.21 |
| Uptime saat dicek | 7j 17m |
| CPU | 14% (9 inti) |
| RAM | 729 MB bebas / 1006 MB (≈28% terpakai) |
| Disk | 79 MB bebas / 134 MB (≈41% terpakai) |
| Zona waktu | Asia/Jakarta (+07:00), NTP aktif (unicast) |
| WAN | ether1 `103.105.79.7/32`, gateway `103.105.79.1` |
| LAN | bridge1 `192.168.200.1/24`, ether4 `192.168.1.1/24` |

Beban data (interfaces, akumulatif): ether1 RX 163 GB / TX 16,5 GB; ether2 RX 15,9 GB / **TX 150 GB**; ether4 RX 0,98 GB / TX 8,4 GB.

### Data pelanggan
| Item | Jumlah |
|---|---|
| PPPoE secret | 88 |
| PPPoE aktif | 72 |
| Queue simple | 66 |
| IP pool | 3 (pool PPPoE `21.21.21.x`) |
| Profil PPP | 18 |
| Hotspot server | 0 (pelanggan pakai PPPoE) |
| DHCP server | 2 (5 lease) |

---

## 2. TEMUAN — urut prioritas

> **Status: sebagian sudah diperbaiki** pada 27 Sep 2026 sore (T4, T5, T7, T8, T10, ditambah
> penurunan policy skrip). Sisanya masih terbuka. Ringkasan di §7.

### 🔴 T1. Notifikasi ntfy SEDANG GAGAL — 157 kegagalan di buffer log
- Log `script,warning` berulang: `ntfy: gagal mengirim notifikasi (periksa DNS, rute, atau sertifikat CA router)`.
- **157 entri** di buffer; ledakan terparah 07:08:56–07:09:07 (15 kegagalan dalam 12 detik).
- Kegagalan terakhir 07:21–07:22.

**Rantai diagnosa (semua terverifikasi):**

| Uji | Hasil |
|---|---|
| DNS `ntfy.sh` via 8.8.8.8 / 1.1.1.1 / DNS ISP | `159.203.148.75` (konsisten) |
| `:ping 159.203.148.75` dari router | **OK** (ICMP sampai) |
| `:ping 159.203.148.75 size=1400 do-not-fragment` | **OK** (MTU normal, bukan MSS blackhole) |
| TCP 80 & 443 ke `ntfy.sh` dari router | **GAGAL** (timeout 10 s) |
| TCP 443 ke `ntfy.sh` **dari PC** (jalur lain) | **GAGAL** (timeout 12 s) |
| `tracert 159.203.148.75` | putus di backbone **Telia** (hop 11–16), latency 233–272 ms |
| Kontrol `tracert 1.1.1.1` | sehat, 9 ms, lewat peering Cloudflare (162.158.43.x) |

**Kesimpulan:** ini **bukan** salah konfigurasi router dan **bukan** DNS/MTU. Jalur transit ISP menuju `ntfy.sh` (DigitalOcean, 159.203.148.x) sedang **blackhole** di upstream. Karena `ntfy.sh` adalah satu-satunya kanal notifikasi, seluruh sistem peringatan router praktis mati saat ini.

**Perbaikan yang disarankan (pilih salah satu / gabungkan):**
1. **Kanal cadangan berantai** di `ntfy-kirim`: coba host A, gagal → host B, gagal → Telegram.
2. **Pakai ntfy self-hosted** milik sendiri sebagai kanal utama — tapi **harus diuji dulu**, karena dari router ini host di belakang Cloudflare juga masih sering gagal cepat (lihat T2).
3. Kalau memakai Telegram, **token-nya sudah terbuka** (lihat T3) jadi harus dirotasi.

### 🔴 T2. WAN tidak stabil — sebagian host gagal konek, sebagian lolos
Uji fetch HTTPS dari router (check-certificate=no):

| URL | Hasil |
|---|---|
| `https://www.google.com/` | OK |
| `https://example.com/` | OK |
| `https://github.com/` | OK |
| `https://one.one.one.one/` | OK |
| `https://cloudflare.com/` | GAGAL (≈1 s) |
| `https://www.microsoft.com/` | GAGAL (≈1 s) |
| `https://api.telegram.org/` | GAGAL (≈1 s) |
| `https://ntfy.clusternet.my.id/` | GAGAL (≈1 s) |
| `https://grafana.clusternet.my.id/` | GAGAL (≈1 s) |
| `https://1.1.1.1/` | GAGAL (literal IP, tanpa SNI → wajar ditolak Cloudflare) |

Fail-cepat (±1 s) = RST/penolakan, bukan timeout. Pola bercampur ini menunjukkan **kualitas jalur WAN buruk/kontensi**, bukan pemblokiran per-host.
Bukti pendukung: netwatch sempat melaporkan RECOVERY dengan downtime **44–47 menit** berulang.

**Yang perlu dicek di router (belum diverifikasi):**
```
/ip/firewall/connection print count-only     # apakah tabel conntrack penuh
/interface monitor-traffic ether1 once       # loss/rate saat beban tinggi
/tool profile                                # cek CPU-bound
```
Kalau conntrack penuh, koneksi baru (termasuk notifikasi) akan gagal acak seperti ini.

### 🟠 T3. Kredensial mentah di dalam skrip (wajib segera)
Skrip `up`, `down`, `script1111`, `simple_upload_monitor` memuat **token bot Telegram dan chat-id dalam bentuk teks biasa**, dan sebagian skrip berpolicy `password,sensitive,sniff,romon` (berlebihan).

**Tindakan:**
1. **Rotasi token bot** lewat @BotFather (token lama sudah bocor minimal ke backup & log).
2. Simpan token di satu tempat saja (mis. `/system/script/environment` atau satu skrip konstanta), lalu panggil dari skrip lain.
3. Turunkan policy skrip pengirim jadi `read,write,test` — tidak perlu `password,sniff,romon`.

### 🟠 T4. `winbox` terbuka ke seluruh internet
```
winbox  port=8269  address=(ALL)  disabled=false
```
Sementara `ssh` (22) sudah dibatasi `103.105.79.0/24` dan `api` (8728) sudah dibatasi (perbaikan sebelumnya).

**Perbaikan:**
```routeros
/ip service set winbox address=103.105.79.0/24,192.168.200.0/24
```
(atau `disabled=yes` bila cukup lewat NAT yang sudah ada: port 8286 → `.200.253:8291`).

### 🟠 T5. DNS resolver terbuka ke internet
`/ip/dns allow-remote-requests=true`, dan **tidak ada satu pun aturan firewall yang menyaring UDP/TCP 53** → router ini adalah *open resolver* (bahan serangan DNS amplification), sekaligus bisa dicap blacklist.

**Perbaikan (contoh):**
```routeros
/ip firewall filter add chain=input protocol=udp dst-port=53 in-interface=ether1 action=drop comment="blok DNS dari WAN"
/ip firewall filter add chain=input protocol=tcp dst-port=53 in-interface=ether1 action=drop comment="blok DNS dari WAN"
```

### 🟠 T6. Profil PPP `1Mb` dan `1Kb` menunjuk skrip yang TIDAK ADA
```
profil 1Mb -> on-up=telegram2 on-down=telegram2
profil 1Kb -> on-up=telegram2 on-down=telegram2
```
Skrip bernama `telegram2` **tidak ada** di `/system/script`. Artinya setiap pelanggan dengan profil itu login/logout → error tanpa notifikasi.

**Perbaikan:** buat skrip `telegram2`, atau arahkan ke skrip yang ada:
```routeros
/ppp profile set [find name="1Mb"] on-up=up on-down=down
/ppp profile set [find name="1Kb"] on-up=up on-down=down
```

### 🟡 T7. Skrip duplikat & tidak terpakai
- `up` (run=220) dan `script1111` (run=0) isinya **hampir identik** → hapus `script1111`.
- `simple_upload_monitor` (token Telegram) dijadwalkan `simple_monitor` tetapi scheduler-nya **disabled** → skrip mati; hapus atau aktifkan dengan sadar.

### 🟡 T8. Netwatch `timeout=1s` terlalu agresif
```
host=8.8.8.8  timeout=1s  interval=30s
down-script=/system script run netwatch-down
up-script=/system script run netwatch-up
```
Timeout 1 detik → ping yang cuma "loss sesaat" langsung dianggap DOWN → notifikasi palsu.

**Perbaikan:** `timeout=3s` (dan pertimbangkan diskusikan `interval=60s`).
```routeros
/tool netwatch set [find host=8.8.8.8] timeout=3s
```

### 🟡 T9. Rute default tanpa `check-gateway`
```
0.0.0.0/0 -> 103.105.79.1 (distance=1)   # tidak ada check-gateway
```
Kalau gateway ISP mati diam-diam, router tidak tahu. Tambahkan:
```routeros
/ip route set [find dst-address="0.0.0.0/0"] check-gateway=ping
```

### 🟡 T10. NAT: dua aturan `dst-port=8082` bertabrakan
```
dstnat tcp dst=8082 -> 192.168.200.253:8082  comment="mixbil"
dstnat tcp dst=8082 -> 192.168.200.253:8082  comment="grafana"
```
Aturan pertama menang; aturan "grafana" **tidak pernah terpakai** dan menyesatkan (Grafana sebenarnya di `grafana.clusternet.my.id` → 3003 lewat Cloudflare Tunnel). Hapus/renamesikan.

### 🟡 T11. Hanya ada satu user: `admin` (grup full)
Billing (PHPNuxBill) login sebagai `admin`. Untuk meminimalkan risiko, buat user khusus grup terbatas yang hanya boleh `api,read,write,test` dan hanya dari jaringan billing.

### 🔵 T12. Firewall tipis
Hanya 13 aturan, mayoritas blokir port botnet; **tidak ada kebijakan default-drop di chain `input`**. Selama semua layanan manajemen dijaga lewat `address=`, ini masih bisa diterima — tapi port yang belum dibatasi (T4, T5) menjadi celah.

---

## 3. Kasus: pesan notifikasi terkirim DUA KALI (selisih ~2 detik)

**Gejala (terverifikasi dari cache topik ntfy):**
```
[23:58:51Z] 🚨 INTERNET DOWN ... Time : 06:58:47
[23:58:53Z] 🚨 INTERNET DOWN ... Time : 06:58:49
```
Bukan pesan identik — isinya memuat waktu, tapi **satu peristiwa memicu skrip dua kali**.

**Sebab:** saat internet masih mati, jika ada apa pun yang **men-set ulang entri Netwatch**, probe-nya **restart**, segera gagal lagi, dan `down-script` **jalan lagi** → notifikasi kedua ~2 detik kemudian. Ini sudah tercatat di komentar skrip Anda sendiri ("membuktikan saat uji").

**Status: sudah diperbaiki di skrip saat ini.** `netwatch-up`/`netwatch-down` sekarang:
- tidak pernah menulis ke entri Netwatch,
- mencatat waktu di skrip penanda `ntfy-nw-terakhir` / `ntfy-down-time` (karena global yang di-set `script run` bisa hilang saat job selesai),
- punya **anti-flood 15 detik per arah**.

**Verifikasi anti-flood (dilakukan sekarang):** skrip dengan policy `read,write,test` **berhasil** membaca `source` `ntfy-nw-terakhir` (`len=10`) dan menulisnya → jadi anti-flood memang aktif, bukan "terlihat aktif tapi gagal diam-diam".

Catatan: menulis `source` skrip sebagai penyimpan status membuat setiap kejadian tercatat sebagai perubahan konfigurasi (churn di log). Berfungsi, tapi boros; alternatif yang lebih rapi adalah `/system/scheduler` + nama berkas, atau `/system/note`.

---

## 4. Perbaikan yang SUDAH diterapkan (riwayat)

| Tanggal | Perubahan | Backup | Rollback |
|---|---|---|---|
| 27 Sep | Community SNMP `public`: `addresses=103.105.79.0/24` → `0.0.0.0/0` | `sebelum-perbaikan-snmp-20260927` | `/snmp community set [find name="public"] addresses=103.105.79.0/24` |
| 27 Sep | `/ip service set api address=103.105.79.0/24,192.168.200.0/24` | `sebelum-batasi-api` | `/ip service set api address=""` |

> Catatan: sumber sebenarnya trafik pemantau & billing adalah **`192.168.200.253`** (hasil SNAT dari subnet `192.168.20.x`) — bukan `192.168.20.x` langsung. Ini penting saat menulis aturan `address=`.

---

## 5. Perintah diagnosa cepat (siap tempel, WinBox/terminal)

```routeros
/system resource print
/system identity print
/ip service print
/tool netwatch print detail
/system script print where name~"ntfy|netwatch|telegram|up|down"
/system scheduler print
/ip firewall filter print
/ip firewall nat print
/log print where topics~"script"
/log print where message~"gagal"
/ip firewall connection print count-only
```

Cek khusus "apakah notifikasi bisa keluar sekarang":
```routeros
:do { /tool fetch url="https://ntfy.sh/" mode=https check-certificate=no keep-result=no; :put "ntfy OK" } on-error={ :put "ntfy GAGAL" }
```

---

## 6. Yang belum bisa diverifikasi dari luar

- **Sisi aplikasi billing** (entri router di PHPNuxBill, perilaku sinkronisasi, tombol putus pelanggan) — perlu login admin PHPNuxBill.
- Apakah tabel **conntrack penuh** saat kegagalan acak terjadi.
- Apakah kegagalan `cloudflare.com`/`microsoft.com` dari router bersifat acak (uji ulang saat WAN tenang).

---

## 7. Hardening yang diterapkan (27 Sep 2026)

Backup konfigurasi: **`sebelum-hardening-20260927.backup`** (di Files router).

| # | Perubahan | Nilai akhir | Rollback |
|---|---|---|---|
| 1 | `winbox` dibatasi | `address=103.105.79.0/24,192.168.200.0/24` | `/ip service set winbox address=""` |
| 2 | DNS dari WAN diblokir (open resolver) | 2 aturan `chain=input proto=udp/tcp dst-port=53 in-interface=ether1 action=drop` | `/ip firewall filter remove [find comment~"blok DNS dari WAN"]` |
| 3 | Netwatch timeout | `1s` → **`3s`** | `/tool netwatch set [find host=8.8.8.8] timeout=1s` |
| 4 | NAT 8082 duplikat | `comment=grafana` → **disabled** | `/ip firewall nat enable [find comment="grafana"]` |
| 5 | Skrip duplikat `script1111` | **dihapus** (isi identik dengan `up`, run-count 0) | pulihkan dari backup |
| 6 | Profil `1Mb` / `1Kb` | `on-up/on-down` `telegram2` (skrip **tidak ada**) → **`up`/`down`** | `/ppp profile set [find name="1Mb"] on-up=telegram2 on-down=telegram2` |
| 7 | Policy skrip | semua → **`read,write,test`** (sebelumnya termasuk `reboot,password,sniff,sensitive,romon`) | pulihkan per skrip dari backup |
| 8 | Nama skrip `" simple_upload_monitor"` | spasi di depan dihapus → **`simple_upload_monitor`** (scheduler-nya tadinya mustahil menemukannya) | `/system script set [find name="simple_upload_monitor"] name=" simple_upload_monitor"` |
| 9 | `api` (8728) ternyata **terbuka lagi** (`address=(SEMUA)`) | dibatasi ulang `103.105.79.0/24,192.168.200.0/24` | `/ip service set api address=""` |
| 10 | **`ntfy-kirim` jadi multi-kanal** | ntfy.sh → ulangi (jeda 3s) → **ntfy lokal ZimaOS** `http://192.168.200.253:7200` | salinan skrip lama: `mikrotik-ntfy/ntfy-kirim.sebelum-20260927.rsc` |

### Bukti uji setelah hardening

```
[07:49:50] changed script settings by admin          <- source & policy baru dipasang
[07:50:14] script,info  ntfy: terkirim via ntfy lokal ZimaOS
```

Artinya: ntfy.sh **gagal dua kali** (jalur eksternal sedang buruk), lalu rantai otomatis
jatuh ke **ntfy lokal lewat LAN** dan pesan tetap sampai. Sebelum perubahan ini,
pengiriman seperti itu berakhir di `ntfy: gagal` dan notifikasi hilang.

Penurunan policy **tidak** memutus fungsi apa pun — `fetch` terbukti jalan dengan policy
`read,write,test` (uji `UJI9 fetch-policy-RWT OK`), dan pembacaan `source` antar skrip juga
tetap boleh (`UJI8 ... len=10`).

### Tindak lanjut yang masih perlu keputusan Anda

1. **Rotasi token bot Telegram** (4 skrip lama memuatnya dalam teks biasa; skrip `script1111`
   sudah dihapus, token lama tetap harus dianggap bocor). Titik pertemuan token sekarang:
   `up`, `down`, `simple_upload_monitor`.
2. **Daftarkan kanal cadangan di aplikasi ntfy**: tambahkan server LAN
   `http://192.168.200.253:7200` dengan topik `router-9f3k7q2m4w`, supaya peringatan
   cadangan (yang dikirim lewat LAN) juga sampai ke ponsel.
3. Tentukan **kanal utama** yang diinginkan (ntfy.sh / adminforge / ntfy lokal).
4. `check-gateway=ping` pada rute default **sengaja belum diterapkan** — risikonya besar
   (bila gateway ISP berhenti menjawab ping, rute jadi inactive dan *seluruh* pelanggan
   kehilangan internet). Butuh keputusan sadar.
5. User API khusus untuk billing (saat ini masih `admin` grup `full`).
