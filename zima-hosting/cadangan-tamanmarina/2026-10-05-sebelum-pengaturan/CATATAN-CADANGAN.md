# Catatan Cadangan — tamanmarina.my.id

- Nama cadangan : 2026-10-05-sebelum-pengaturan
- Dibuat        : 2026-10-06 05:15:46
- Dari          : zima-hosting/ (repo)
- Catatan       : Keadaan baik sebelum hub Pengaturan Sistem diterbitkan: pengaturan.js baru, GET/PUT /api/pengaturan, GET /api/sistem (13 layanan), master iuran + ambang tersimpan di server

## Isi

| Berkas | Tujuan saat dikembalikan |
|---|---|
| index.html, dasbor.css, dasbor.js, pengguna.js, pengaturan.js, masuk.html, masuk.css, masuk.js, hero.svg | zima-hosting/situs/tamanmarina/ |
| Dockerfile, izin.mjs, penyimpanan.mjs, server.mjs, mula.sh | zima-hosting/auth/ |
| Caddyfile | zima-hosting/Caddyfile (seluruh router) |

## Cara mengembalikan

```
MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-05-sebelum-pengaturan -Sandi '<sandi ZimaOS>'
```

Lihat juga: zima-hosting/DASBOR-TAMANMARINA.md bagian 7 (Rollback).
