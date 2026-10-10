// Sistem Aduan Warga — dasbor tamanmarina.my.id
// Alur: warga membuat (Menunggu) -> pengurus menyetujui (Open) -> pengurus
// menutup (Closed) atau menghapus permanen. Data dari GET /api/aduan;
// pengelolaan memakai izin pengaduan.kelola (pengurus & admin) yang dikirim
// server sebagai bendera bolehKelola; pembuatan memakai pengaduan.buat.
(function () {
  'use strict';

  var daftarEl = document.getElementById('aduanDaftar');
  var bulanEl = document.getElementById('aduanBulan');
  var statusEl = document.getElementById('aduanStatus');
  var tambahEl = document.getElementById('aduanTambah');
  var pesanEl = document.getElementById('aduanPesan');
  var ringkasEl = document.getElementById('aduanRingkas');
  var modalEl = document.getElementById('modalAduan');
  var formEl = document.getElementById('formAduan');
  var statEl = document.getElementById('statAduanAktif');
  if (!daftarEl || !formEl || !modalEl) return;

  var aduanSemua = [];
  var bolehKelola = false;
  var bolehBuat = false;
  var termuat = false;

  var BULAN_ID = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
    'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'];
  var LENCANA = { menunggu: 'kuning', open: 'biru', closed: 'abu' };
  var LABEL = { menunggu: 'Menunggu', open: 'Open', closed: 'Closed' };

  function byId(id) { return document.getElementById(id); }
  function buat(tag, kelas, teks) {
    var el = document.createElement(tag);
    if (kelas) el.className = kelas;
    if (teks !== undefined) el.textContent = teks;
    return el;
  }
  function tanggal(iso) {
    if (!iso) return '-';
    var d = new Date(iso);
    return Number.isNaN(d.getTime()) ? String(iso).slice(0, 10)
      : d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
  }
  function api(metode, url, body) {
    var opsi = { method: metode, credentials: 'same-origin', cache: 'no-store' };
    if (body !== undefined) {
      opsi.headers = { 'Content-Type': 'application/json', 'X-Diminta-Dengan': 'dasbor' };
      opsi.body = JSON.stringify(body);
    }
    return fetch(url, opsi).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (d) {
        if (!res.ok) throw new Error((d && d.galat) || 'Permintaan gagal (' + res.status + ').');
        return d;
      });
    });
  }
  function pesan(teks, galat) {
    if (!pesanEl) return;
    pesanEl.textContent = teks || '';
    pesanEl.hidden = !teks;
    pesanEl.classList.toggle('galat', !!galat);
    pesanEl.classList.toggle('sukses', !!teks && !galat);
  }

  /* ---- muat & statistik ---- */
  function muat() {
    return api('GET', '/api/aduan').then(function (d) {
      aduanSemua = d.aduan || [];
      bolehKelola = !!d.bolehKelola;
      termuat = true;
      isiBulan();
      render();
      terapkanStat();
    });
  }
  // Kartu "Pengaduan Aktif" diisi jumlah aduan berstatus Open.
  function terapkanStat() {
    if (!statEl || !termuat) return;
    statEl.textContent = aduanSemua.filter(function (a) { return a && a.status === 'open'; }).length;
  }
  function terapkanTombolBuat() {
    if (tambahEl) tambahEl.hidden = !bolehBuat;
  }

  /* ---- saring bulan & status ("data tampil setiap bulannya") ---- */
  function bulanDari(iso) { return String((iso || '').slice(0, 7)); }
  function labelBulan(kunci) {
    var bagian = String(kunci).split('-');
    var n = Number(bagian[1]);
    return (BULAN_ID[n - 1] || bagian[1]) + ' ' + bagian[0];
  }
  function isiBulan() {
    if (!bulanEl) return;
    var hitung = {};
    aduanSemua.forEach(function (a) {
      var k = bulanDari(a && a.dibuat);
      if (k) hitung[k] = (hitung[k] || 0) + 1;
    });
    var pilihan = bulanEl.value;
    bulanEl.replaceChildren();
    bulanEl.appendChild(Object.assign(document.createElement('option'), { value: '', textContent: 'Semua bulan' }));
    Object.keys(hitung).sort().reverse().forEach(function (k) {
      bulanEl.appendChild(Object.assign(document.createElement('option'),
        { value: k, textContent: labelBulan(k) + ' (' + hitung[k] + ')' }));
    });
    bulanEl.value = pilihan && hitung[pilihan] ? pilihan : '';
  }
  function daftarTampil() {
    return aduanSemua.filter(function (a) {
      if (!a) return false;
      if (bulanEl && bulanEl.value && bulanDari(a.dibuat) !== bulanEl.value) return false;
      if (statusEl && statusEl.value && a.status !== statusEl.value) return false;
      return true;
    }).sort(function (a, b) {
      return String(b.dibuat || '').localeCompare(String(a.dibuat || ''));
    });
  }

  /* ---- render daftar ---- */
  function render() {
    if (!daftarEl) return;
    var tampil = daftarTampil();
    daftarEl.replaceChildren();
    if (ringkasEl) {
      var h = { menunggu: 0, open: 0, closed: 0 };
      tampil.forEach(function (a) { if (h[a.status] !== undefined) h[a.status]++; });
      var judul = bulanEl && bulanEl.value ? labelBulan(bulanEl.value) : 'Semua bulan';
      ringkasEl.textContent = tampil.length
        ? judul + ': ' + tampil.length + ' aduan — ' + h.menunggu + ' menunggu, ' + h.open + ' open, ' + h.closed + ' closed.'
        : judul + ': belum ada aduan.';
    }
    if (!tampil.length) {
      daftarEl.appendChild(buat('p', 'konten-kosong', 'Belum ada aduan.'));
      return;
    }
    tampil.forEach(function (a) { daftarEl.appendChild(kartu(a)); });
  }
  function kartu(a) {
    var item = buat('article', 'aduan-item');
    var kepala = buat('div', 'aduan-kepala');
    var judul = buat('div', 'aduan-judul');
    judul.appendChild(buat('strong', '', a.judul || '(tanpa judul)'));
    judul.appendChild(buat('span', 'aduan-meta',
      (a.kategori || 'Lainnya') +
      (a.lokasi ? ' · ' + a.lokasi : '') +
      ' · ' + (a.pelapor || 'Warga') + (a.blok ? ' (' + a.blok + ')' : '') +
      ' · ' + tanggal(a.dibuat)));
    kepala.appendChild(judul);
    kepala.appendChild(buat('span', 'lencana ' + (LENCANA[a.status] || 'abu'), LABEL[a.status] || a.status));
    item.appendChild(kepala);
    item.appendChild(buat('p', 'aduan-isi', a.isi || ''));
    if (a.status === 'closed' && a.catatanTutup) {
      item.appendChild(buat('p', 'catatan-kecil', 'Catatan pengurus: ' + a.catatanTutup));
    } else if (a.status === 'open' && a.disetujuiOleh) {
      item.appendChild(buat('p', 'catatan-kecil',
        'Disetujui ' + tanggal(a.disetujuiPada) + ' oleh ' + a.disetujuiOleh + ' — dalam penanganan.'));
    }
    if (bolehKelola) {
      var aksi = buat('div', 'aduan-aksi');
      aksi.appendChild(tombolAksi('Setujui', 'setujui', a, a.status !== 'menunggu'));
      aksi.appendChild(tombolAksi('Tutup', 'tutup', a, a.status !== 'open'));
      aksi.appendChild(tombolAksi('Buka Lagi', 'buka', a, a.status !== 'closed'));
      aksi.appendChild(tombolAksi('Hapus', 'hapus', a, false));
      item.appendChild(aksi);
    }
    return item;
  }
  function tombolAksi(teks, aksi, a, nonaktif) {
    var b = buat('button', 'tombol-mini' + (aksi === 'hapus' ? ' tombol-arsip' : ''), teks);
    b.type = 'button';
    b.disabled = !!nonaktif;
    b.addEventListener('click', function () { jalankanAksi(aksi, a); });
    return b;
  }

  /* ---- aksi pengurus/admin ---- */
  function jalankanAksi(aksi, a) {
    if (aksi === 'hapus') {
      if (!window.confirm || !window.confirm('Hapus aduan "' + (a.judul || '') + '"? Data tidak bisa dikembalikan.')) return;
      api('DELETE', '/api/aduan/' + encodeURIComponent(a.id), {}).then(function () {
        pesan('Aduan "' + (a.judul || '') + '" dihapus.');
        return muat();
      }).catch(function (e) { pesan(e.message, true); });
      return;
    }
    var body = { aksi: aksi };
    if (aksi === 'setujui') {
      if (!window.confirm || !window.confirm('Setujui aduan "' + (a.judul || '') + '"? Setelah disetujui tampil di dasbor semua warga.')) return;
    } else if (aksi === 'tutup') {
      var catatan = window.prompt ? window.prompt('Catatan penutup (opsional, maks 300 karakter):', '') : '';
      if (catatan === null) return; // dibatalkan
      body.catatan = String(catatan).slice(0, 300);
    } else if (aksi === 'buka') {
      if (!window.confirm || !window.confirm('Buka kembali aduan "' + (a.judul || '') + '"?')) return;
    }
    api('PATCH', '/api/aduan/' + encodeURIComponent(a.id), body).then(function () {
      pesan('Aduan "' + (a.judul || '') + '" diperbarui (' +
        (aksi === 'setujui' ? 'disetujui' : aksi === 'tutup' ? 'ditutup' : 'dibuka kembali') + ').');
      return muat();
    }).catch(function (e) { pesan(e.message, true); });
  }

  /* ---- modal buat aduan ---- */
  function bukaModal() {
    if (!modalEl) return;
    byId('aduanJudul').value = '';
    byId('aduanKategori').value = 'Fasilitas & Perlengkapan';
    byId('aduanLokasi').value = '';
    byId('aduanIsi').value = '';
    modalEl.hidden = false;
    byId('aduanJudul').focus();
  }
  function tutupModal() { if (modalEl) modalEl.hidden = true; }
  function simpan(ev) {
    ev.preventDefault();
    if (!formEl.reportValidity()) return;
    api('POST', '/api/aduan', {
      judul: byId('aduanJudul').value.trim(),
      kategori: byId('aduanKategori').value,
      lokasi: byId('aduanLokasi').value.trim(),
      isi: byId('aduanIsi').value.trim()
    }).then(function () {
      tutupModal();
      pesan('Aduan terkirim ke pengurus (status: Menunggu persetujuan).');
      return muat();
    }).catch(function (e) { pesan(e.message, true); });
  }

  /* ---- pemasangan ---- */
  if (tambahEl) tambahEl.addEventListener('click', bukaModal);
  if (formEl) formEl.addEventListener('submit', simpan);
  var mClose = byId('modalAduanClose');
  var mBatal = byId('aduanBatal');
  var mBack = byId('modalAduanBackdrop');
  if (mClose) mClose.addEventListener('click', tutupModal);
  if (mBatal) mBatal.addEventListener('click', tutupModal);
  if (mBack) mBack.addEventListener('click', tutupModal);
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') tutupModal(); });
  if (bulanEl) bulanEl.addEventListener('change', render);
  if (statusEl) statusEl.addEventListener('change', render);

  // Saat sesi siap: hak buat dari izin, dan terapkan ulang statistik kartu
  // "Pengaduan Aktif" SETELAH dasbor.js menulis angka data-teks-nya.
  document.addEventListener('tm-sesi', function (ev) {
    var izin = (ev && ev.detail && ev.detail.izin) || {};
    bolehBuat = !!izin['pengaduan.buat'];
    terapkanTombolBuat();
    terapkanStat();
  });

  muat().catch(function (e) {
    pesan('Data aduan tidak dapat dimuat: ' + e.message, true);
  });
})();
