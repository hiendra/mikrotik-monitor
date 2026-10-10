# Catatan Cadangan — tamanmarina.my.id

- Nama cadangan : 2026-10-06-sesudah-crud-pengaturan
- Dibuat        : 2026-10-06 05:48:47
- Dari          : zima-hosting/ (repo)
- Catatan       : Keadaan baik setelah CRUD Pengaturan terbit: tombol Ubah/Hapus per baris, daftar Pengaturan Lain, /data/pengaturan.json dengan bidang lain. Uji 57/0, aset live cocok bita-per-bita.

## Isi

| Berkas | Tujuan saat dikembalikan |
|---|---|
| index.html, dasbor.css, dasbor.js, pengguna.js, pengaturan.js, masuk.html, masuk.css, masuk.js, hero.svg | zima-hosting/situs/tamanmarina/ |
| Dockerfile, izin.mjs, penyimpanan.mjs, server.mjs, mula.sh | zima-hosting/auth/ |
| Caddyfile | zima-hosting/Caddyfile (seluruh router) |

## Cara mengembalikan

```
MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-06-sesudah-crud-pengaturan -Sandi '<sandi ZimaOS>'
```

Lihat juga: zima-hosting/DASBOR-TAMANMARINA.md bagian 7 (Rollback).
