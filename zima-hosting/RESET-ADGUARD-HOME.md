# Reset Password AdGuard Home (`adguard.clusternet.my.id`)

Halaman login di `https://adguard.clusternet.my.id/login.html` adalah **AdGuard Home** —
bukan aplikasi penyimpan berkas. Sebelum 25 September 2026 subdomain ini pernah
dinamedakan `files.clusternet.my.id`; sekarang sudah diganti `adguard.`

Dokumen ini sudah **diverifikasi langsung di server** (24 September 2026), bukan lagi
perkiraan.

## Ringkasan cepat (fakta terverifikasi)

| Hal | Nilai |
|---|---|
| Aplikasi | AdGuard Home `v0.107.79` |
| Container | `adguardhome` (image `adguard/adguardhome:latest`) |
| Port | host `8080` → container `80` (UI); DNS di `0.0.0.0:53` + `[::]:53` |
| Berkas konfigurasi | `/DATA/AppData/adguardhome/conf/AdGuardHome.yaml` |
| Mount | `conf → /opt/adguardhome/conf`, `work → /opt/adguardhome/work`, `ssl → /ssl` |
| Akun | **satu** akun: `admin` |
| Penyimpanan sandi | hash **bcrypt** (`password: '$2y$10$…'`) — tidak bisa dibalik |
| Percobaan login | `auth_attempts: 5`, `block_auth_min: 15` (5 salah → IP diblokir 15 menit) |
| DNS upstream | Quad9 DoH (`https://dns10.quad9.net/dns-query`) |

Konsekuensi penting: **sandi lama tidak bisa dibaca dari server.** Yang tersimpan hanya
hash bcrypt satu arah. Kalau lupa, satu-satunya jalan adalah mengganti hash-nya
(prosedur di bawah) atau mengosongkan `users:`.

> Jangan menebak-nebak sandi di halaman login: 5 kali salah = IP diblokir 15 menit.

## Prosedur resmi AdGuard (dan cara menjalankannya di ZimaOS)

Mengikuti wiki AdGuard
<https://github.com/AdguardTeam/AdGuardHome/wiki/Configuration#password-reset>:
`htpasswd` menghasilkan hash bcrypt → hash itu ditulis ke `users:` di
`AdGuardHome.yaml` **saat AdGuard berhenti** → AdGuard dijalankan lagi.

### 0. Masuk ke shell ZimaOS

SSH port 22 **tertutup**; satu-satunya jalan adalah terminal web ttyd di
`http://192.168.145.252:7681` (atau `:7682`). Login memakai akun ZimaOS
(`hendra`), lalu **semua perintah docker diawali `sudo`** karena sudah diuji:
akun ini hanya ada di grup `samba` + `wheel`, bukan `docker`.

Catatan prompt di ZimaOS: sudo menulis `Password:` (bukan
`[sudo] password for hendra:`), dan permintaan sandi harus dijawab dengan cepat.

### 1. Siapkan hash bcrypt baru (sebelum container dimatikan)

`htpasswd` tidak ada di host, jadi dipakai image Apache:

```bash
sudo docker run --rm httpd:2.4-alpine \
  htpasswd -B -C 10 -n -b admin 'SandiBaruYangKuat' > /tmp/ag.txt 2>/tmp/ag.err
H=$(cut -d: -f2 /tmp/ag.txt); echo "len=${#H} awal=${H:0:7}"
```

Keluaran `htpasswd` berbentuk `admin:$2y$10$…`; ambil bagian **setelah titik dua**.
Opsi `-B` wajib — hanya bcrypt yang diterima, jadi generator online yang
menghasilkan MD5/SHA tidak bisa dipakai. Panjang hash bcrypt = 60 karakter.

> Taruh langkah ini **sebelum** container dimatikan: kalau image `httpd` belum ada,
> Docker perlu menariknya dulu, dan Anda tidak ingin DNS LAN mati selama itu.

### 2. Cadangkan, hentikan, sunting, jalankan lagi

```bash
Y=/DATA/AppData/adguardhome/conf/AdGuardHome.yaml
sudo cp -a "$Y" "$Y.bak"
sudo docker stop adguardhome
sudo sed -i "16s|password:.*|password: '$H'|" "$Y"   # baris 16 = baris password
sudo sed -n '14,17p' "$Y" | cut -c1-30                # cek: password: '$2y$10$…
sudo docker start adguardhome
```

Poin-poin yang menentukan berhasil/tidak:

- **Berkas harus disunting saat container berhenti.** Program yang sedang jalan
  menulis ulang konfigurasi, jadi perubahan Anda akan hilang.
- Hash mengandung `$` → **bungkus dengan kutip tunggal** di YAML; tanpa kutip
  YAML memotong nilainya dan login akan selalu gagal.
- Nomor baris 16 adalah baris `password:` (baris 14 `users:`, 15 `- name: admin`).
  Hanya ada satu baris `password:` di berkas ini, jadi `sed` tidak menyentuh yang lain.
- Rollback cepat: `sudo cp -a "$Y.bak" "$Y" && sudo docker start adguardhome`.
- Selama container berhenti, **seluruh LAN kehilangan resolusi DNS**. Kerjakan cepat.

### 3. Uji login (tanpa membuka browser)

AdGuard punya endpoint login JSON:

```bash
curl -o /dev/null -w '%{http_code}\n' -X POST \
  -H 'Content-Type: application/json' \
  -d '{"name":"admin","password":"SandiBaruYangKuat"}' \
  http://192.168.145.252:8080/control/login
```

`200` = berhasil, `403` = sandi salah. Uji juga lewat jalur publik:

```bash
curl -o /dev/null -w '%{http_code}\n' -X POST -H 'Content-Type: application/json' \
  -d '{"name":"admin","password":"SandiBaruYangKuat"}' \
  https://adguard.clusternet.my.id/control/login
```

Cek kesehatan mesin DNS (perlu cookie sesi dari login di atas):

```bash
curl -s -b cookies.txt http://192.168.145.252:8080/control/status
```

Harapan: `"running":true` dan `"protection_enabled":true`.

## Jalur cepat: matikan autentikasi (hanya bila langkah di atas macet)

`users:` yang berisi daftar kosong mematikan autentikasi:

```yaml
users: []
```

Setelah `docker stop` → ubah → `docker start`, UI langsung terbuka dan menawarkan
pembuatan akun admin baru. **Tapi** `adguard.clusternet.my.id` saat ini publik:
selama `users: []`, siapa pun di internet bisa mengubah konfigurasi DNS Anda.
Kalau memakai cara ini, hentikan dulu Public Hostname `files.*` di tunnel
Cloudflare (atau pasang Cloudflare Access di depannya), buat akun baru, lalu pulihkan.

## Mengotomatiskan shell ttyd (untuk lain kali)

Antarmuka ttyd adalah canvas xterm: screenshot sering tertinggal satu langkah dan
kadang berhenti compositing, sehingga mengetik lewat browser tidak dapat diandalkan.
Jalan yang jauh lebih stabil: bicara langsung ke WebSocket ttyd (protokol ttyd 1.7):

1. `new WebSocket('ws://192.168.145.252:7681/ws', 'tty')` — **subprotokol `tty` wajib**,
   tanpa itu upgrade ditolak.
2. Frame pertama harus JSON `{"AuthToken":"","columns":240,"rows":60}`.
3. Sesudah itu semua frame **biner**: byte pertama `0` = input, `1` = resize + JSON.
   Keluaran server juga biner dengan awalan `0`.
4. Keluaran berupa teks biasa, jadi bisa ditunggu dengan penanda unik, mis.
   `perintah; echo "__DONE_""7__"` — tanda kutip ganda di tengah membuat teks
   penanda hanya muncul di keluaran, bukan di gema baris perintah.
5. Node ≥ 22 sudah punya `WebSocket` bawaan, jadi tidak perlu paket tambahan.
6. Prompt ZimaOS adalah `hendra@ClusternetCloud:~ ➜ $ ` diikuti escape reset charset —
   tunggu tanda `➜`, jangan mencocokkan `"$ "` di akhir buffer.

## Catatan keamanan

AdGuard Home memegang kendali seluruh resolusi DNS jaringan.

1. Ganti sandi yang pernah tertulis di obrolan/log, simpan di password manager, dan
   jangan taruh di README atau berkas repo (repositori ini pernah membersihkan
   kredensial dari riwayat commit — jangan ulangi).
2. `adguard.clusternet.my.id` **masih publik tanpa Cloudflare Access**. Halaman login
   AdGuard yang terbuka ke internet adalah permukaan serang yang serius; pasang
   Access (email OTP) atau hapus Public Hostname-nya dan akses cukup dari LAN.
3. `zima.`, `immich.`, `grafana.`, dan `portal.` juga belum di balik Access.
4. Port forwarding lama ke `8080`/`8280` dari router sebaiknya ditutup karena
   jalur itu melewati Cloudflare.
