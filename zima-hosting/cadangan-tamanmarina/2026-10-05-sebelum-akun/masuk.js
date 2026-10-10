/* ============================================================
   masuk.js - logika halaman /masuk tamanmarina.my.id
   Dimuat sebagai berkas terpisah karena CSP situs ini
   `script-src 'self'` (skrip inline diblokir).

   Mengirim POST /api/masuk (JSON) dengan header khusus
   X-Diminta-Dengan: dasbor - penangkal CSRF di API (formulir
   lintas situs tidak bisa menambah header khusus). Cookie sesi
   HttpOnly dipasang server; JS tidak pernah melihat tokennya.

   Bila sesi masih hidup saat halaman dibuka, pengunjung langsung
   dialihkan ke dasbor tanpa menampilkan formulir lagi.
   ============================================================ */

(function () {
  'use strict';

  var form = document.getElementById('formMasuk');
  var kotakGalat = document.getElementById('galat');
  var tombol = document.getElementById('btnMasuk');

  function tujuanAman() {
    // Parameter ?lanjut= hanya menerima jalur same-origin (/...) -
    // menolak "//host-lain" dan "\host-lain" (buka-redirect).
    var p = new URLSearchParams(window.location.search).get('lanjut') || '';
    if (p.charAt(0) === '/' && p.charAt(1) !== '/' && p.charAt(1) !== '\\') return p;
    return '/';
  }

  function tampilGalat(teks) {
    if (!kotakGalat) return;
    kotakGalat.textContent = teks;
    kotakGalat.hidden = !teks;
  }

  if (!form || !window.fetch) return;

  // Sudah punya sesi hidup? Tidak perlu menampilkan formulir lagi.
  fetch('/api/saya', { credentials: 'same-origin', cache: 'no-store' })
    .then(function (r) { if (r.ok) window.location.replace(tujuanAman()); })
    .catch(function () {});

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    tampilGalat('');

    var nama = document.getElementById('pengguna').value.trim();
    var sandi = document.getElementById('sandi').value;
    if (!nama || !sandi) {
      tampilGalat('Isi nama pengguna dan sandi.');
      return;
    }

    if (tombol) tombol.disabled = true;

    fetch('/api/masuk', {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-Diminta-Dengan': 'dasbor',
      },
      body: JSON.stringify({ pengguna: nama, sandi: sandi }),
    })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (d) {
          if (!r.ok) {
            tampilGalat((d && d.galat) || 'Masuk gagal (HTTP ' + r.status + ').');
            if (tombol) tombol.disabled = false;
            return;
          }
          // Akun baru ber-sandi awal dipaksa mengganti sandi dulu;
          // dasbor menampilkannya di bagian "Akun Saya".
          var tujuan = tujuanAman();
          if (d.pengguna && d.pengguna.harus_ganti_sandi) tujuan = '/#akun';
          window.location.assign(tujuan);
        });
      })
      .catch(function () {
        tampilGalat('Tidak bisa menghubungi server. Periksa koneksi lalu coba lagi.');
        if (tombol) tombol.disabled = false;
      });
  });
})();
