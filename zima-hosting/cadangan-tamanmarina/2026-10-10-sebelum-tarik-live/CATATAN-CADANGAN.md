# Catatan Cadangan — tamanmarina.my.id

- Nama cadangan : 2026-10-10-sebelum-tarik-live
- Dibuat        : 2026-10-10 14:44:23
- Dari          : zima-hosting/ (repo, keadaan lokal SEBELUM menyelaraskan dengan live)
- Catatan       : Cadangan pengaman sebelum menarik keadaan live (7–10 Okt) ke lokal. Isi = versi LOKAL lama apa adanya (aset 6 Okt, backend 24 KB tanpa /api/konten, /api/warga, /api/iuran/*). Dipakai bila hasil tarikan perlu dibalik.

## Isi

| Berkas | Tujuan saat dikembalikan |
|---|---|
| index.html, dasbor.css, dasbor.js, pengguna.js, pengaturan.js, masuk.html, masuk.css, masuk.js, hero.svg | zima-hosting/situs/tamanmarina/ |
| Dockerfile, izin.mjs, penyimpanan.mjs, server.mjs, mula.sh | zima-hosting/auth/ |

Catatan: snapshot ini juga TIDAK memuat `konten.js`, `aduan.js`, `metode.js`, `umkm.json`
— pada saat cadangan dibuat berkas-berkas itu memang belum ada di lokal.

## Cara mengembalikan

Snapshot ini bukan snapshot "live" (tidak pernah diterbitkan ke host), jadi
`kembalikan-tamanmarina.ps1` **tidak** untuk kasus ini — pemulihannya cukup
menyalin berkas kembali ke tempatnya:

```
cp zima-hosting/cadangan-tamanmarina/2026-10-10-sebelum-tarik-live/*.html \
   zima-hosting/cadangan-tamanmarina/2026-10-10-sebelum-tarik-live/*.js \
   zima-hosting/cadangan-tamanmarina/2026-10-10-sebelum-tarik-live/*.css \
   zima-hosting/cadangan-tamanmarina/2026-10-10-sebelum-tarik-live/*.svg \
   zima-hosting/situs/tamanmarina/
cp zima-hosting/cadangan-tamanmarina/2026-10-10-sebelum-tarik-live/Dockerfile \
   zima-hosting/cadangan-tamanmarina/2026-10-10-sebelum-tarik-live/*.mjs \
   zima-hosting/cadangan-tamanmarina/2026-10-10-sebelum-tarik-live/mula.sh \
   zima-hosting/auth/
```

Lihat juga: zima-hosting/AUDIT-PROYEK-2026-10-10.md (temuan K1/K2).
