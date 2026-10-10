/* ============================================================
   pengaturan.js - bagian "Pengaturan Sistem" dasbor warga
   Dimuat sebagai berkas terpisah karena CSP situs ini
   `script-src 'self'` (skrip inline diblokir).

   Bagian ini adalah hub admin yang terhubung ke seluruh sistem
   project lewat API tm-auth (semua same-origin):
     - GET  /api/sistem         probe status 13 layanan (di-probe
                                server, bukan browser - jadi bebas
                                CORS & tidak melonggarkan CSP)
     - GET  /api/pengaturan     master iuran + ambang approval
     - PUT  /api/pengaturan     simpan (izin pengaturan.kelola)
     - GET  /api/peran          matriks peran & izin NYATA
     - GET  /api/health         info backend akun

   Inisialisasi menunggu peristiwa `tm-sesi` yang dikirim
   pengguna.js setelah /api/saya selesai - tanpa sesi admin tidak
   ada yang dimuat (bagian pun tersembunyi oleh CSS data-peran).
   ============================================================ */

(function () {
  'use strict';

  var KEPALA = { 'Content-Type': 'application/json', 'X-Diminta-Dengan': 'dasbor' };
  var IKON = { warga: '👤', pengurus: '🏠', admin: '🧑‍💼' };
  var LABEL_STATUS = { ok: 'Hidup', lambat: 'Lambat', mati: 'Mati' };

  var siap = false; // penanda: pengaturan admin sudah dimuat

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function rupiah(n) {
    return 'Rp ' + String(Number(n) || 0).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  }

  function jam(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleString('id-ID', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  }

  function pesan(teks, jenis) {
    var el = $('pengaturanPesan');
    if (!el) return;
    if (!teks) { el.hidden = true; el.textContent = ''; return; }
    el.textContent = teks;
    el.className = 'status-baris ' + (jenis === 'galat' ? 'status-galat' : 'status-ok');
    el.hidden = false;
  }

  function intaan(metode, url, isi) {
    return fetch(url, {
      method: metode,
      credentials: 'same-origin',
      cache: 'no-store',
      headers: KEPALA,
      body: isi === undefined ? undefined : JSON.stringify(isi),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        return { ok: r.ok, status: r.status, data: d || {} };
      });
    });
  }

  /* ---------- 1. STATUS SELURUH SISTEM ---------- */

  function renderSistem(h) {
    var grid = $('tmSistemGrid');
    var waktu = $('tmSistemWaktu');
    if (!grid) return;
    if (!h.ok) {
      grid.innerHTML = '<p class="catatan-kecil">Gagal memuat status: '
        + esc(h.data.galat || ('HTTP ' + h.status)) + '</p>';
      return;
    }
    var daftar = h.data.sistem || [];
    var hidup = daftar.filter(function (s) { return s.status !== 'mati'; }).length;

    grid.innerHTML = daftar.map(function (s) {
      var meta = [];
      meta.push(s.kode ? 'HTTP ' + s.kode : 'tanpa respons');
      if (s.status !== 'mati') meta.push(s.ms + ' ms');
      var galat = s.galat ? '<small class="sistem-galat">' + esc(s.galat) + '</small>' : '';
      return '<div class="sistem-item">'
        + '<div class="sistem-nama"><span class="sistem-titik ' + esc(s.status) + '"></span>'
        + esc(s.nama) + '</div>'
        + '<div class="sistem-meta"><span>' + esc(LABEL_STATUS[s.status] || s.status) + '</span>'
        + '<span>' + esc(meta.join(' · ')) + '</span></div>'
        + '<small>' + esc(s.grup) + ' · ' + esc(s.url) + '</small>'
        + galat
        + '</div>';
    }).join('');

    if (waktu) {
      waktu.textContent = hidup + ' dari ' + daftar.length + ' sistem hidup · diperiksa '
        + jam(h.data.waktu) + (h.data.cache ? ' (cache 15 detik)' : '');
    }
  }

  function muatSistem(paksa) {
    var waktu = $('tmSistemWaktu');
    if (waktu && paksa) waktu.textContent = 'Memeriksa…';
    return intaan('GET', '/api/sistem' + (paksa ? '?segar=1' : '')).then(renderSistem);
  }

  /* ---------- 2. MASTER IURAN & AMBANG ---------- */

  function barisIuran(b) {
    var tr = document.createElement('tr');
    tr.setAttribute('data-iuran', '');

    var tdJenis = document.createElement('td');
    var iJenis = document.createElement('input');
    iJenis.type = 'text';
    iJenis.className = 'tm-iuran-jenis';
    iJenis.maxLength = 80;
    iJenis.value = b.jenis || '';
    iJenis.setAttribute('aria-label', 'Nama jenis iuran');
    tdJenis.appendChild(iJenis);

    var tdNominal = document.createElement('td');
    var iNominal = document.createElement('input');
    iNominal.type = 'number';
    iNominal.min = '0';
    iNominal.max = '1000000000';
    iNominal.step = '1000';
    iNominal.className = 'tm-iuran-nominal';
    iNominal.value = b.nominal != null ? b.nominal : '';
    iNominal.setAttribute('aria-label', 'Nominal');
    tdNominal.appendChild(iNominal);

    var tdAktif = document.createElement('td');
    var iAktif = document.createElement('input');
    iAktif.type = 'checkbox';
    iAktif.className = 'tm-iuran-aktif';
    iAktif.checked = !!b.aktif;
    iAktif.setAttribute('aria-label', 'Aktif');
    tdAktif.appendChild(iAktif);

    var tdHapus = document.createElement('td');
    var bHapus = document.createElement('button');
    bHapus.type = 'button';
    bHapus.className = 'tombol-mini tm-bahaya';
    bHapus.textContent = 'Hapus';
    bHapus.addEventListener('click', function () { tr.remove(); });
    tdHapus.appendChild(bHapus);

    tr.appendChild(tdJenis);
    tr.appendChild(tdNominal);
    tr.appendChild(tdAktif);
    tr.appendChild(tdHapus);
    return tr;
  }

  function barisAmbang(b) {
    var baris = document.createElement('div');
    baris.className = 'tm-ambang-baris';
    baris.setAttribute('data-ambang', '');

    var iBatas = document.createElement('input');
    iBatas.type = 'number';
    iBatas.min = '0';
    iBatas.step = '100000';
    iBatas.placeholder = 'Batas atas (Rp) — kosong = tanpa batas';
    iBatas.className = 'tm-ambang-batas';
    iBatas.value = (b.batas_atas === null || b.batas_atas === undefined) ? '' : b.batas_atas;
    iBatas.setAttribute('aria-label', 'Batas atas');

    var iPengesahan = document.createElement('input');
    iPengesahan.type = 'text';
    iPengesahan.maxLength = 120;
    iPengesahan.placeholder = 'Siapa yang mengesahkan';
    iPengesahan.className = 'tm-ambang-pengesahan';
    iPengesahan.value = b.pengesahan || '';
    iPengesahan.setAttribute('aria-label', 'Pengesahan');

    var bHapus = document.createElement('button');
    bHapus.type = 'button';
    bHapus.className = 'tombol-mini tm-bahaya';
    bHapus.textContent = 'Hapus';
    bHapus.addEventListener('click', function () { baris.remove(); });

    baris.appendChild(iBatas);
    baris.appendChild(iPengesahan);
    baris.appendChild(bHapus);
    return baris;
  }

  function renderPengaturan(p) {
    var tb = $('tmIuranBody');
    if (tb) {
      tb.textContent = '';
      (p.iuran || []).forEach(function (b) { tb.appendChild(barisIuran(b)); });
      if (!(p.iuran || []).length) {
        var trKosong = document.createElement('tr');
        var td = document.createElement('td');
        td.colSpan = 4;
        td.className = 'catatan-kecil';
        td.textContent = 'Belum ada jenis iuran — klik "+ Tambah Jenis".';
        trKosong.appendChild(td);
        tb.appendChild(trKosong);
      }
    }
    var wadah = $('tmAmbangDaftar');
    if (wadah) {
      wadah.textContent = '';
      (p.ambang || []).forEach(function (b) { wadah.appendChild(barisAmbang(b)); });
      if (!(p.ambang || []).length) {
        var kecil = document.createElement('p');
        kecil.className = 'catatan-kecil';
        kecil.textContent = 'Belum ada ambang — klik "+ Tambah Ambang".';
        wadah.appendChild(kecil);
      }
    }
  }

  function kumpulPengaturan() {
    var iuran = [];
    var barisI = document.querySelectorAll('#tmIuranBody tr[data-iuran]');
    for (var i = 0; i < barisI.length; i += 1) {
      var jenis = barisI[i].querySelector('.tm-iuran-jenis').value.trim();
      var nominalRaw = barisI[i].querySelector('.tm-iuran-nominal').value.trim();
      if (!jenis) throw new Error('Baris iuran ' + (i + 1) + ': nama jenis wajib diisi.');
      if (!/^\d+$/.test(nominalRaw)) throw new Error('Baris iuran ' + (i + 1) + ': nominal harus angka bulat.');
      iuran.push({
        jenis: jenis,
        nominal: Number(nominalRaw),
        aktif: barisI[i].querySelector('.tm-iuran-aktif').checked,
      });
    }

    var ambang = [];
    var barisA = document.querySelectorAll('#tmAmbangDaftar [data-ambang]');
    for (var j = 0; j < barisA.length; j += 1) {
      var batasRaw = barisA[j].querySelector('.tm-ambang-batas').value.trim();
      var pengesahan = barisA[j].querySelector('.tm-ambang-pengesahan').value.trim();
      if (batasRaw && !/^\d+$/.test(batasRaw)) {
        throw new Error('Ambang ' + (j + 1) + ': batas atas harus angka bulat atau dikosongkan.');
      }
      if (!pengesahan) throw new Error('Ambang ' + (j + 1) + ': pengesahan wajib diisi.');
      ambang.push({
        batas_atas: batasRaw === '' ? null : Number(batasRaw),
        pengesahan: pengesahan,
      });
    }

    return { iuran: iuran, ambang: ambang };
  }

  function muatPengaturan() {
    return intaan('GET', '/api/pengaturan').then(function (h) {
      if (!h.ok) {
        pesan(h.data.galat || 'Gagal memuat pengaturan.', 'galat');
        return;
      }
      renderPengaturan(h.data.pengaturan || {});
    });
  }

  function pasangTombolPengaturan() {
    var tambahIuran = $('tmIuranTambah');
    if (tambahIuran) {
      tambahIuran.addEventListener('click', function () {
        var tb = $('tmIuranBody');
        if (!tb) return;
        if (tb.querySelector('tr:not([data-iuran])')) tb.textContent = ''; // buang baris "Memuat…"
        tb.appendChild(barisIuran({ jenis: '', nominal: '', aktif: true }));
      });
    }

    var tambahAmbang = $('tmAmbangTambah');
    if (tambahAmbang) {
      tambahAmbang.addEventListener('click', function () {
        var wadah = $('tmAmbangDaftar');
        if (!wadah) return;
        if (!wadah.querySelector('[data-ambang]')) wadah.textContent = '';
        wadah.appendChild(barisAmbang({ batas_atas: null, pengesahan: '' }));
      });
    }

    var simpan = $('tmPengaturanSimpan');
    if (simpan) {
      simpan.addEventListener('click', function () {
        var isi;
        try { isi = kumpulPengaturan(); } catch (e) { pesan(e.message, 'galat'); return; }
        simpan.disabled = true;
        intaan('PUT', '/api/pengaturan', { pengaturan: isi }).then(function (h) {
          simpan.disabled = false;
          if (!h.ok) { pesan(h.data.galat || 'Gagal menyimpan (HTTP ' + h.status + ').', 'galat'); return; }
          pesan('Pengaturan tersimpan (' + isi.iuran.length + ' jenis iuran, '
            + isi.ambang.length + ' ambang). Tercatat di Audit Log.');
        });
      });
    }

    var segar = $('tmSistemSegar');
    if (segar) {
      segar.addEventListener('click', function () {
        segar.disabled = true;
        muatSistem(true).then(function () { segar.disabled = false; });
      });
    }
  }

  /* ---------- 3. Matriks peran & info backend ---------- */

  function muatPeran() {
    var wadah = $('tmPeranDaftar');
    if (!wadah) return;
    intaan('GET', '/api/peran').then(function (h) {
      if (!h.ok) { wadah.innerHTML = '<p class="catatan-kecil">Gagal memuat peran.</p>'; return; }
      var daftar = h.data.peran || [];
      wadah.innerHTML = daftar.map(function (p) {
        return '<div class="tm-peran-kartu">'
          + '<b>' + esc(IKON[p.peran] || '•') + ' ' + esc(p.label) + ' · level ' + esc(p.level) + '</b>'
          + '<small>' + esc(p.judul) + '</small>'
          + '<ul>' + (p.izinKhas || []).map(function (i) {
            return '<li>' + esc(i) + '</li>';
          }).join('') + '</ul>'
          + '</div>';
      }).join('')
        + '<p class="catatan-kecil">Izin lengkap ' + esc(String((daftar[0] && daftar[0].izin || []).length))
        + '/' + esc(String((daftar[daftar.length - 1] && daftar[daftar.length - 1].izin || []).length))
        + ' — izin khas di atas baru yang membedakan peran; sisanya diwarisi dari peran di bawahnya.</p>';
    });
  }

  function muatInfoBackend() {
    var wadah = $('tmBackendInfo');
    if (!wadah) return;
    intaan('GET', '/api/health').then(function (h) {
      var baris = [
        ['Endpoint API', '/api/* (same-origin di belakang Caddy)'],
        ['Akun terdaftar', h.ok ? String(h.data.pengguna) + ' akun' : 'tidak terjangkau'],
        ['Umur sesi', '12 jam (token acak 256-bit, cookie HttpOnly)'],
        ['Batas masuk', '8 percobaan gagal / 15 menit per IP + nama'],
        ['Hash sandi', 'scrypt (N=16384, r=8, p=1) + garam acak'],
        ['Audit log', '500 entri terakhir di /data/audit.json'],
      ];
      wadah.innerHTML = baris.map(function (b) {
        return '<div class="tm-baris-profil"><span>' + esc(b[0]) + '</span><b>' + esc(b[1]) + '</b></div>';
      }).join('');
    });
  }

  /* ---------- mulai: tunggu sesi dari pengguna.js ---------- */

  function mulai(izin) {
    if (siap) return;
    siap = true;
    pasangTombolPengaturan();
    if (izin['sistem.kelola']) muatSistem(false);
    if (izin['pengaturan.kelola']) {
      muatPengaturan();
      muatPeran();
      muatInfoBackend();
    }
  }

  document.addEventListener('tm-sesi', function (ev) {
    var d = ev.detail;
    if (d && d.izin && d.izin['pengaturan.kelola']) mulai(d.izin);
  });
})();
