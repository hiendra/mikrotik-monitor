/* ============================================================
   dasbor.js - interaksi dasbor warga tamanmarina.my.id
   Dimuat sebagai berkas terpisah karena CSP situs ini
   `script-src 'self'` (skrip inline diblokir).

   Isi:
     1. buka/tutup sidebar di layar kecil (+ overlay, Esc, klik tautan)
     2. penyaring kotak "Cari informasi..." pada daftar Informasi Terbaru
     3. tinggi grafik pengaduan dihitung dari data-nilai
     4. menu sidebar mengikuti bagian yang sedang terlihat
     5. sakelar peran Warga / Pengurus / Admin (mengubah <body data-peran>,
        identitas di topbar, dan angka pada kartu statistik)
     6. kartu Info Lingkungan dari sensor udara Taman Marina (/sensor/api/data)
   Tanpa JavaScript halaman tetap terbaca: grafik punya tinggi bawaan
   di atribut style, menu tetap tautan biasa, dan tampilan default
   adalah peran Warga (data-peran="warga" sudah ada di <body>).
   ============================================================ */

(function () {
  'use strict';

  /* ---------- 1. SIDEBAR ---------- */
  var sidebar = document.getElementById('sidebar');
  var overlay = document.getElementById('overlay');
  var menuBtn = document.getElementById('menuBtn');
  var menu = document.getElementById('menu');

  function aturSidebar(buka) {
    if (!sidebar || !overlay) return;
    sidebar.classList.toggle('buka', buka);
    overlay.hidden = !buka;
    if (menuBtn) {
      menuBtn.setAttribute('aria-expanded', buka ? 'true' : 'false');
      menuBtn.setAttribute('aria-label', buka ? 'Tutup menu' : 'Buka menu');
    }
  }

  if (menuBtn) {
    menuBtn.addEventListener('click', function () {
      aturSidebar(!sidebar.classList.contains('buka'));
    });
  }
  if (overlay) {
    overlay.addEventListener('click', function () { aturSidebar(false); });
  }
  if (menu) {
    menu.addEventListener('click', function (ev) {
      if (ev.target.closest('a')) aturSidebar(false);
    });
  }
  document.addEventListener('keydown', function (ev) {
    if (ev.key === 'Escape') aturSidebar(false);
  });
  window.addEventListener('resize', function () {
    if (window.innerWidth > 768) aturSidebar(false);
  });

  /* ---------- 2. PENYARING INFORMASI ---------- */
  var kotakCari = document.getElementById('cari');
  var daftar = document.getElementById('daftar-informasi');
  var pesanKosong = document.getElementById('kosong');

  if (kotakCari && daftar) {
    var butir = Array.prototype.slice.call(daftar.querySelectorAll('.news-item'));

    var saring = function () {
      var kunci = kotakCari.value.trim().toLowerCase();
      var tampil = 0;

      butir.forEach(function (el) {
        var cocok = !kunci || el.textContent.toLowerCase().indexOf(kunci) !== -1;
        el.hidden = !cocok;
        if (cocok) tampil += 1;
      });

      if (pesanKosong) pesanKosong.hidden = tampil > 0;
    };

    kotakCari.addEventListener('input', saring);
    kotakCari.addEventListener('search', saring);
  }

  /* ---------- 3. GRAFIK PENGADUAN ---------- */
  var batang = Array.prototype.slice.call(document.querySelectorAll('.chart .bar'));

  if (batang.length) {
    var nilai = batang.map(function (el) {
      return Number(el.getAttribute('data-nilai')) || 0;
    });
    var tertinggi = Math.max.apply(null, nilai) || 1;

    // Tinggi maksimum 95px dari area grafik 190px, sisakan ruang untuk label.
    batang.forEach(function (el, i) {
      var tinggi = Math.round((nilai[i] / tertinggi) * 95);
      el.style.height = Math.max(tinggi, 10) + 'px';
      el.title = nilai[i] + ' pengaduan';
    });
  }

  /* ---------- 4. MENU MENGIKUTI BAGIAN TERLIHAT ---------- */
  if (menu && 'IntersectionObserver' in window) {
    var tautan = Array.prototype.slice.call(menu.querySelectorAll('a[href^="#"]'));
    var peta = {};

    tautan.forEach(function (a) {
      var id = a.getAttribute('href').slice(1);
      var bagian = document.getElementById(id);
      if (bagian) peta[id] = a;
    });

    var pengamat = new IntersectionObserver(function (entri) {
      entri.forEach(function (e) {
        if (!e.isIntersecting) return;
        var aktif = peta[e.target.id];
        if (!aktif || aktif.hidden || aktif.offsetParent === null) return;
        tautan.forEach(function (a) { a.classList.remove('aktif'); });
        aktif.classList.add('aktif');
      });
    }, { rootMargin: '-45% 0px -45% 0px' });

    Object.keys(peta).forEach(function (id) {
      pengamat.observe(document.getElementById(id));
    });
  }

  /* ---------- 5. SAKELAR PERAN ---------- */
  var PERAN = {
    warga: { avatar: 'TM', nama: 'Warga Taman Marina', sub: 'RT 004 / RW 020', badge: 'Warga' },
    pengurus: { avatar: 'RT', nama: 'Pengurus RT 004', sub: 'RW 020 · Taman Marina', badge: 'Ketua RT' },
    admin: { avatar: 'AD', nama: 'Admin Sistem', sub: 'Super Admin · RW 020', badge: 'Admin' }
  };

  var tombolPeran = Array.prototype.slice.call(document.querySelectorAll('[data-atur-peran]'));
  var avatar = document.getElementById('avatar');
  var namaPengguna = document.getElementById('namaPengguna');
  var subPengguna = document.getElementById('subPengguna');
  var peranBadge = document.getElementById('peranBadge');

  function aturPeran(nama) {
    if (!PERAN[nama]) return;

    document.body.setAttribute('data-peran', nama);

    tombolPeran.forEach(function (b) {
      var aktif = b.getAttribute('data-atur-peran') === nama;
      b.classList.toggle('aktif', aktif);
      b.setAttribute('aria-pressed', aktif ? 'true' : 'false');
    });

    var p = PERAN[nama];
    if (avatar) avatar.textContent = p.avatar;
    if (namaPengguna) namaPengguna.textContent = p.nama;
    if (subPengguna) subPengguna.textContent = p.sub;
    if (peranBadge) peranBadge.textContent = p.badge;

    // Angka kartu statistik yang berbeda per peran.
    Array.prototype.slice.call(document.querySelectorAll('[data-teks]')).forEach(function (el) {
      var peta = {};
      try { peta = JSON.parse(el.getAttribute('data-teks')) || {}; } catch (e) { peta = {}; }
      if (peta[nama] != null) el.textContent = peta[nama];
    });

    aturSidebar(false);
  }

  tombolPeran.forEach(function (b) {
    b.addEventListener('click', function () {
      aturPeran(b.getAttribute('data-atur-peran'));
    });
  });
  aturPeran(document.body.getAttribute('data-peran') || 'warga');

  /* ---------- 6. KARTU INFO LINGKUNGAN (SENSOR) ---------- */
  var kartuLingkungan = document.getElementById('lingkungan');
  var tombolSensor = document.getElementById('segarkanSensor');

  function isi(id, teks) {
    var el = document.getElementById(id);
    if (el) el.textContent = teks;
  }

  function angkaPendek(v, desimal) {
    if (v == null || isNaN(Number(v))) return '—';
    var n = Number(v);
    var t = n.toFixed(desimal == null ? 1 : desimal);
    return t.replace('.', ',');
  }

  function muatSensor() {
    if (!kartuLingkungan || !window.fetch) return;
    if (tombolSensor) tombolSensor.classList.add('memuat');

    fetch('/sensor/api/data', { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        isi('sensorAqi', d.aqi != null ? String(d.aqi) : '—');
        isi('sensorSuhu', angkaPendek(d.suhu));
        isi('sensorLembab', angkaPendek(d.kelembaban, 0));
        isi('sensorEco2', d.eco2 != null ? String(d.eco2) : '—');

        var status = document.getElementById('sensorStatus');
        if (status) {
          status.textContent = d.status || '—';
          status.className = 'lencana ' + (String(d.status || '').toLowerCase().indexOf('baik') !== -1 ? 'hijau' : 'kuning');
        }

        isi('sensorSumber', (d.lokasi || 'Sensor udara Taman Marina') + (d.mode ? ' · ' + d.mode : ''));
        isi('sensorWaktu', 'Diperbarui ' + (d.waktu || '—'));

        // Suhu sensor juga dipakai di kartu cuaca.
        isi('cuacaSuhu', angkaPendek(d.suhu));
        if (d.status) isi('cuacaStatus', 'Kualitas udara: ' + d.status);
        isi('cuacaDetail', 'Kelembapan ' + angkaPendek(d.kelembaban, 0) + '% • eCO₂ ' + (d.eco2 != null ? d.eco2 : '—') + ' ppm');

        kartuLingkungan.classList.remove('kedaluwarsa');
      })
      .catch(function () {
        isi('sensorSumber', 'Sensor tidak terjangkau — menampilkan data contoh');
        kartuLingkungan.classList.add('kedaluwarsa');
      })
      .then(function () {
        if (tombolSensor) tombolSensor.classList.remove('memuat');
      });
  }

  if (tombolSensor) tombolSensor.addEventListener('click', muatSensor);
  muatSensor();
  window.setInterval(muatSensor, 300000); // segarkan tiap 5 menit

  /* ---------- 7. TOMBOL UPLOAD BUKTI (placeholder) ---------- */
  var tombolBukti = document.getElementById('tombolBukti');
  if (tombolBukti) {
    tombolBukti.addEventListener('click', function () {
      var pesan = document.getElementById('pesanBukti');
      if (!pesan) {
        pesan = document.createElement('p');
        pesan.id = 'pesanBukti';
        pesan.className = 'catatan-kecil';
        tombolBukti.parentNode.insertBefore(pesan, tombolBukti.nextSibling);
      }
      pesan.textContent = 'Terima kasih! Fitur upload bukti transfer akan aktif setelah modul keuangan (backend) dipasang.';
    });
  }
})();
