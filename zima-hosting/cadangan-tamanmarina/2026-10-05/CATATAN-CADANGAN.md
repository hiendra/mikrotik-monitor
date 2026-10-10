# Catatan Cadangan — tamanmarina.my.id

- Nama cadangan : 2026-10-05
- Dibuat        : 2026-10-05
- Dari          : zima-hosting/ (repo), keadaan saat dasbor versi peran+keuangan+sensor diterbitkan
- Catatan       : titik baik setelah menambahkan sakelar peran, Keuangan & Iuran,
                  bagian menu yang tadinya mati, dan integrasi sensor `/sensor`.

## Isi

| Berkas | Tujuan saat dikembalikan |
|---|---|
| index.html, dasbor.css, dasbor.js, hero.svg | zima-hosting/situs/tamanmarina/ |
| Caddyfile | zima-hosting/Caddyfile (seluruh router) |

Ukuran berkas situs saat snapshot: index.html 30588 · dasbor.css 22402 ·
dasbor.js 9291 · hero.svg 4703 bita. Tautan aset memakai `?v=20261005`.

## Cara mengembalikan

```
MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan 2026-10-05 -Sandi '<sandi ZimaOS>'
```

Caddyfile hanya ikut dikembalikan bila `-DenganCaddyfile` ditambahkan.

Lihat juga: `zima-hosting/DASBOR-TAMANMARINA.md` bagian 7 (Rollback).
