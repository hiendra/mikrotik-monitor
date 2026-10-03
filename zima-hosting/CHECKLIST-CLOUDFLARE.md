# Checklist Cloudflare — yang tinggal Anda kerjakan

Tiga tahap, urutannya penting. Jangan lompat ke Tahap 3 sebelum Tahap 1–2
terbukti jalan. Centang langsung di berkas ini.

---

## Tahap 1 — Tunnel + token (±10 menit)

- [ ] 1. Buka <https://one.dash.cloudflare.com> → login akun yang punya zona `clusternet.my.id`
- [ ] 2. **Networks → Tunnels → Create a tunnel**
- [ ] 3. Pilih **Cloudflared** → nama tunnel: `zimaos` → **Save tunnel**
- [ ] 4. Di layar "Install and run a connector" pilih **Docker**, lalu **salin token**-nya
      (derpanja panjang yang diawali `eyJ...` — ini kunci server, jangan tempel ke chat)
- [ ] 5. Di PC ini, buat berkas `zima-hosting/.env`:

  ```
  cd zima-hosting
  cp .env.example .env
  notepad .env      # ganti isinya jadi: TUNNEL_TOKEN=tempelan-token-anda
  ```

- [ ] 6. Salin folder `zima-hosting/` **utuh** ke ZimaOS, mis. ke
      `/DATA/AppData/zima-hosting/` (lewat SMB/SCP panel ZimaOS). Isi:
      `docker-compose.yml`, `Caddyfile`, folder `situs/`, `.env`
- [ ] 7. SSH ke ZimaOS lalu:

  ```bash
  cd /DATA/AppData/zima-hosting
  docker compose up -d
  docker compose logs -f cloudflared   # tunggu "Registered tunnel connection" (4x)
  ```

  Hasil yang benar: dua container hidup — `web-router` (Caddy) dan `cf-tunnel`.

---

## Tahap 2 — Daftarkan nama di tunnel (±5 menit)

Di halaman tunnel tadi → tab **Public Hostname** → **Add a public hostname**,
tambahkan **tiga** baris ini (service-nya sama semua, Caddy yang memilah):

| Subdomain | Domain | Path | Service |
|---|---|---|---|
| *(kosong)* | clusternet.my.id | - | `http://caddy:80` |
| `www` | clusternet.my.id | - | `http://caddy:80` |
| `*` | clusternet.my.id | - | `http://caddy:80` |

- [ ] Baris apex (subdomain kosong)
- [ ] Baris `www`
- [ ] Baris `*` (wildcard — ini yang membuat layanan baru TIDAK perlu sentuh DNS lagi)

Cloudflare otomatis membuat CNAME `<id>.cfargotunnel.com` dan menimpa record A
lama ke `103.105.79.7`. Itu memang yang diinginkan.

### Verifikasi cepat (dari PC ini)

```powershell
powershell -ExecutionPolicy Bypass -File .\cek-domain.ps1
```

- [ ] `clusternet.my.id` → header `Server: cloudflare` / ada `cf-ray`
- [ ] `zima.clusternet.my.id` → halaman login ZimaOS (masih lewat tunnel)
- [ ] Subdomain acak mis. `tes-acak123.clusternet.my.id` → **404** dari Caddy,
      bukan NXDOMAIN — ini bukti wildcard bekerja

### Kunci panel admin dengan Cloudflare Access (wajib sebelum Tahap 3)

Zero Trust → **Access → Applications → Add an application → Self-hosted**,
ulangi untuk keempat nama ini (kebijakan sama semua: **Allow → Emails → email Anda**):

- [ ] `zima.clusternet.my.id`     — UI ZimaOS
- [ ] `immich.clusternet.my.id`   — galeri foto
- [ ] `grafana.clusternet.my.id`  — dasbor
- [ ] `billing.clusternet.my.id`  — aplikasi billing PHP "Masuk - CLUSTERNET" (dulu `portal.`)

Sementara itu `adguard.clusternet.my.id` dan situs utama boleh publik — keduanya
sudah punya halaman login sendiri.

---

## Tahap 3 — Bersihkan jalur lama (hanya SETELAH semuanya jalan)

> Tes dulu 1×24 jam dengan tunnel aktif. Bila ada yang bermasalah, jalankan
> bagian Rollback di `PANDUAN-WEBHOSTING.md` — jangan buru-buru menutup jalur lama.

### a. Hapus port forwarding di router MikroTik

Winbox → **IP → Firewall → NAT**, hapus aturan dst-nat untuk:

- [ ] port 8280 (UI ZimaOS)
- [ ] port 8080 (aplikasi SPA)
- [ ] port 22 (SSH)
- [ ] port 8728 (API MikroTik — paling penting, ini terbuka ke publik)

Lalu batasi API hanya untuk LAN:

```
/ip service set api address=192.168.20.0/24,192.168.145.0/24
```

- [ ] Perintah di atas sudah dijalankan

### b. Hapus portproxy di PC ini (14 aturan)

Buka PowerShell **sebagai Administrator**:

```powershell
# lihat dulu daftarnya
netsh interface portproxy show all

# contoh hapus satu per satu (ulangi untuk tiap listenport yang muncul):
# netsh interface portproxy delete v4tov4 listenport=8880 listenaddress=0.0.0.0
```

- [ ] Semua aturan portproxy yang menunjuk `192.168.145.252` sudah dihapus
- [ ] `netsh interface portproxy show all` kini kosong (atau hanya sisa yang memang disengaja)

### c. Verifikasi akhir

```powershell
powershell -ExecutionPolicy Bypass -File .\cek-semua.ps1
```

- [ ] Rekap menunjukkan **0 KRITIS** dan "semua lewat Cloudflare"
- [ ] Dari internet (mis. pakai HP dengan WiFi dimatikan): buka
      `https://clusternet.my.id` → halaman situs muncul dengan gembok

---

## Catatan kecil

- **Immich**: setelah nama domain aktif, buka Immich → Administration → Settings
  → isi *External domain* = `https://immich.clusternet.my.id`, supaya tautan
  berbagi tidak menunjuk alamat internal.
- **Unggahan besar**: Cloudflare gratis menolak upload > 100 MB. Video besar ke
  Immich sebaiknya diunggah dari LAN (lewat `http://192.168.145.252:2283`).
- **Terminal (port 7681/7682)** sengaja tidak dipetakan publik — itu jendela
  langsung ke shell server. Akses dari LAN atau ZeroTier saja.
- **Aplikasi baru lain kali**: cukup buka `zima-hosting/panel-kelola.html`
  (klik dua kali), tambah layanan, salin Caddyfile-nya, `docker compose restart caddy`.
  Tanpa menyentuh DNS, tunnel, atau router. Ingin alamat `http://` tetap?
  Jalankan `node buka-panel.mjs` dari akar repo (port tetap 8788).
