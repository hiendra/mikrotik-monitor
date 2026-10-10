# Catatan Cadangan — tamanmarina.my.id

- Nama cadangan : 2026-10-05-sebelum-akun
- Dibuat        : 2026-10-05 21:30:51
- Dari          : zima-hosting/ (repo)
- Catatan       : Keadaan baik sebelum modul akun (tm-auth) diterbitkan: masuk.html/css/js, pengguna.js, perbaikan modal UMKM, handle /api/*

## Isi

| Berkas | Tujuan saat dikembalikan |
|---|---|
| index.html, dasbor.css, dasbor.js, pengguna.js, masuk.html, masuk.css, masuk.js, hero.svg | zima-hosting/situs/tamanmarina/ |
| Dockerfile, izin.mjs, penyimpanan.mjs, server.mjs | zima-hosting/auth/ |
| Caddyfile | zima-hosting/Caddyfile (seluruh router) |

## Cara mengembalikan

```
MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-05-sebelum-akun -Sandi '<sandi ZimaOS>'
```

Lihat juga: zima-hosting/DASBOR-TAMANMARINA.md bagian 7 (Rollback).
