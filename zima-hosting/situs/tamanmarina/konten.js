(function () {
  'use strict';
  var apiRoot = '/api/konten';
  var items = { informasi: [], kegiatan: [], kontak: [], link: [] };
  var jenisEl = document.getElementById('kontenJenis');
  var form = document.getElementById('kontenForm');
  var list = document.getElementById('kontenDaftar');
  var area = document.getElementById('kelola-konten');
  if (!jenisEl || !form || !list || !area) return;

  var byId = function (id) { return document.getElementById(id); };
  var pesanEl = byId('kontenPesan');
  function pesan(teks, galat) {
    pesanEl.textContent = teks || '';
    pesanEl.hidden = !teks;
    pesanEl.classList.toggle('galat', !!galat);
    pesanEl.classList.toggle('sukses', !!teks && !galat);
  }
  // --- Link Penting (kelola pengurus & admin, izin pengumuman.kelola) ---
  var bolehLink = false;
  var linkTambah = byId('linkTambah');
  var linkDaftar = byId('linkDaftar');
  var linkPesanEl = byId('linkPesan');
  var formLink = byId('formLink');
  var modalLink = byId('modalLink');
  var linkEditId = '';
  function pesanLink(teks, galat) {
    if (!linkPesanEl) return;
    linkPesanEl.textContent = teks || '';
    linkPesanEl.hidden = !teks;
    linkPesanEl.classList.toggle('galat', !!galat);
    linkPesanEl.classList.toggle('sukses', !!teks && !galat);
  }
  function buat(tag, kelas, teks) {
    var el = document.createElement(tag);
    if (kelas) el.className = kelas;
    if (teks !== undefined) el.textContent = teks;
    return el;
  }
  function tanggal(iso) {
    if (!iso) return '-';
    var d = new Date(iso + 'T00:00:00');
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
  }
  function api(metode, url, body) {
    var opsi = { method: metode, credentials: 'same-origin', cache: 'no-store', headers: {} };
    if (body !== undefined) {
      opsi.headers['Content-Type'] = 'application/json';
      opsi.headers['X-Diminta-Dengan'] = 'dasbor';
      opsi.body = JSON.stringify(body);
    }
    return fetch(url, opsi).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) throw new Error(data.galat || 'Permintaan gagal (' + r.status + ').');
        return data;
      });
    });
  }
  function statusLabel(s) {
    return s === 'terbit' ? 'Terbit' : s === 'arsip' ? 'Arsip' : 'Draf';
  }
  function urut(daftar, jenis) {
    return (daftar || []).slice().sort(function (a, b) {
      if (jenis === 'kontak') return (a.jabatan || '').localeCompare(b.jabatan || '', 'id');
      return jenis === 'kegiatan' ? a.tanggal.localeCompare(b.tanggal) : b.tanggal.localeCompare(a.tanggal);
    });
  }
  function renderAdmin() {
    var jenis = jenisEl.value;
    list.replaceChildren();
    var daftar = urut(items[jenis], jenis);
    if (!daftar.length) {
      list.appendChild(buat('p', 'konten-kosong', 'Belum ada konten. Klik "+ Tambah" untuk membuat draf pertama.'));
      return;
    }
    daftar.forEach(function (item) {
      var kartu = buat('article', 'konten-item');
      var utama = buat('div', 'konten-item-utama');
      utama.appendChild(buat('strong', '', jenis === 'kontak' ? item.jabatan + ' — ' + item.nama : item.judul));
      var rincian = jenis === 'informasi' ? item.ringkasan : jenis === 'kontak' ? item.telepon : [item.lokasi, item.waktu].filter(Boolean).join(' · ');
      utama.appendChild(buat('p', 'catatan-kecil', rincian || item.isi || item.deskripsi || item.catatan || ''));
      utama.appendChild(buat('small', 'konten-meta', (jenis === 'kontak' ? '' : tanggal(item.tanggal) + ' · ') + statusLabel(item.status)));
      kartu.appendChild(utama);
      var aksi = buat('div', 'konten-aksi');
      var edit = buat('button', 'tombol-mini', 'Edit');
      edit.type = 'button';
      edit.addEventListener('click', function () { bukaForm(item); });
      aksi.appendChild(edit);
      if (item.status === 'arsip') {
        var pulih = buat('button', 'tombol-mini', 'Pulihkan sebagai draf');
        pulih.type = 'button';
        pulih.addEventListener('click', function () { ubahStatus(item, 'draf'); });
        aksi.appendChild(pulih);
      } else {
        var hapus = buat('button', 'tombol-mini tombol-arsip', 'Hapus');
        hapus.type = 'button';
        hapus.addEventListener('click', function () { arsip(item); });
        aksi.appendChild(hapus);
      }
      kartu.appendChild(aksi);
      list.appendChild(kartu);
    });
  }
  function tampilkanJenis() {
    var info = jenisEl.value === 'informasi';
    var event = jenisEl.value === 'kegiatan';
    var contact = jenisEl.value === 'kontak';
    document.querySelectorAll('.konten-info-field').forEach(function (e) {
      e.hidden = !info; e.querySelector('input,textarea').disabled = !info;
    });
    document.querySelectorAll('.konten-event-field').forEach(function (e) {
      e.hidden = !event; e.querySelector('input,textarea').disabled = !event;
    });
    document.querySelectorAll('.konten-date-field').forEach(function (e) {
      e.hidden = contact; e.querySelector('input').disabled = contact; e.querySelector('input').required = !contact;
    });
    document.querySelectorAll('.konten-contact-field').forEach(function (e) {
      e.hidden = !contact; e.querySelector('input').disabled = !contact;
      e.querySelector('input').required = contact && e.querySelector('input').id !== 'kontenCatatan';
    });
    ['kontenJudul','kontenIsi'].forEach(function (id) { byId(id).disabled = contact; });
    byId('kontenJudul').required = !contact;
    byId('kontenIsi').required = false;
    form.querySelector('label[for="kontenIsi"]').textContent = info ? 'Isi informasi' : 'Deskripsi kegiatan';
  }
  function bukaForm(item) {
    var jenis = jenisEl.value;
    byId('kontenId').value = item ? item.id : '';
    byId('kontenJudul').value = item ? item.judul : '';
    byId('kontenTanggal').value = item ? item.tanggal : new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Jakarta' });
    byId('kontenRingkasan').value = item ? item.ringkasan || '' : '';
    byId('kontenLokasi').value = item ? item.lokasi || '' : '';
    byId('kontenWaktu').value = item ? item.waktu || '' : '';
    byId('kontenIsi').value = item ? item.isi || item.deskripsi || '' : '';
    byId('kontenJabatan').value = item ? item.jabatan || '' : '';
    byId('kontenNama').value = item ? item.nama || '' : '';
    byId('kontenTelepon').value = item ? item.telepon || '' : '';
    byId('kontenCatatan').value = item ? item.catatan || '' : '';
    byId('kontenStatus').value = item ? item.status : 'draf';
    byId('kontenFormJudul').textContent = (item ? 'Edit ' : 'Tambah ') + (jenis === 'informasi' ? 'informasi' : jenis === 'kontak' ? 'kontak pengurus' : 'kegiatan');
    form.hidden = false;
    tampilkanJenis();
    byId('kontenJudul').focus();
  }
  function dataForm() {
    var jenis = jenisEl.value;
    var out = { jenis: jenis, status: byId('kontenStatus').value };
    if (jenis === 'kontak') {
      out.jabatan = byId('kontenJabatan').value;
      out.nama = byId('kontenNama').value;
      out.telepon = byId('kontenTelepon').value;
      out.catatan = byId('kontenCatatan').value;
    } else {
      out.judul = byId('kontenJudul').value;
      out.tanggal = byId('kontenTanggal').value;
    }
    if (jenis === 'informasi') {
      out.ringkasan = byId('kontenRingkasan').value;
      out.isi = byId('kontenIsi').value;
    } else {
      out.lokasi = byId('kontenLokasi').value;
      out.waktu = byId('kontenWaktu').value;
      out.deskripsi = byId('kontenIsi').value;
    }
    return out;
  }
  function muat() {
    return api('GET', apiRoot).then(function (d) {
      items = d.konten || { informasi: [], kegiatan: [], kontak: [], link: [] };
      bolehLink = !!d.bolehKelola;
      area.hidden = !bolehLink;
      if (linkTambah) linkTambah.hidden = !bolehLink;
      if (linkDaftar) linkDaftar.hidden = !bolehLink;
      terapkanPublik(items);
      renderAdmin();
    });
  }
  function renderLinkBar(daftar, wadah) {
    if (!wadah) return;
    wadah.replaceChildren();
    if (!daftar.length) {
      wadah.appendChild(buat('p', 'konten-kosong', 'Belum ada link penting.'));
      return;
    }
    daftar.forEach(function (x) {
      var a = buat('a', '', (x.ikon ? x.ikon + ' ' : '') + (x.nama || ''));
      // URL kosong (entri lama) -> tetap melompat ke bagian kontak seperti sebelumnya.
      a.href = x.url || '#kontak';
      if (x.url) { a.target = '_blank'; a.rel = 'noopener noreferrer'; }
      wadah.appendChild(a);
    });
  }
  function renderLinkKelola(daftar) {
    if (!linkDaftar) return;
    linkDaftar.replaceChildren();
    if (!bolehLink) return;
    if (!daftar.length) {
      linkDaftar.appendChild(buat('p', 'konten-kosong', 'Belum ada link. Klik "+ Tambah Link" untuk menambah.'));
      return;
    }
    daftar.forEach(function (x) {
      var kartu = buat('article', 'konten-item');
      var utama = buat('div', 'konten-item-utama');
      utama.appendChild(buat('strong', '', (x.ikon ? x.ikon + ' ' : '') + (x.nama || '')));
      utama.appendChild(buat('p', 'catatan-kecil', x.url || 'URL belum diisi'));
      kartu.appendChild(utama);
      var aksi = buat('div', 'konten-aksi');
      var edit = buat('button', 'tombol-mini', 'Edit');
      edit.type = 'button';
      edit.addEventListener('click', function () { bukaLink(x); });
      aksi.appendChild(edit);
      var hapus = buat('button', 'tombol-mini tombol-arsip', 'Hapus');
      hapus.type = 'button';
      hapus.addEventListener('click', function () { hapusLink(x); });
      aksi.appendChild(hapus);
      kartu.appendChild(aksi);
      linkDaftar.appendChild(kartu);
    });
  }
  function bukaLink(x) {
    if (!modalLink) return;
    linkEditId = x ? String(x.id) : '';
    byId('linkNama').value = x ? x.nama || '' : '';
    byId('linkUrl').value = x ? x.url || '' : '';
    byId('linkIkon').value = x ? x.ikon || '' : '';
    byId('modalLinkJudul').textContent = x ? 'Edit Link Penting' : 'Tambah Link Penting';
    modalLink.hidden = false;
    byId('linkNama').focus();
  }
  function tutupLink() { if (modalLink) modalLink.hidden = true; }
  function simpanLink(ev) {
    ev.preventDefault();
    if (!formLink || !formLink.reportValidity()) return;
    var data = {
      jenis: 'link',
      nama: byId('linkNama').value.trim(),
      url: byId('linkUrl').value.trim(),
      ikon: byId('linkIkon').value.trim()
    };
    var url = linkEditId ? apiRoot + '/link/' + encodeURIComponent(linkEditId) : apiRoot;
    api(linkEditId ? 'PATCH' : 'POST', url, data).then(function () {
      tutupLink();
      pesanLink('Link berhasil disimpan.');
      return muat();
    }).catch(function (e) { pesanLink(e.message, true); });
  }
  function hapusLink(x) {
    if (!window.confirm || !window.confirm('Hapus link "' + (x.nama || '') + '"?')) return;
    api('DELETE', apiRoot + '/link/' + encodeURIComponent(x.id), {}).then(function () {
      pesanLink('Link "' + (x.nama || '') + '" dihapus.');
      return muat();
    }).catch(function (e) { pesanLink(e.message, true); });
  }
  function terapkanPublik(data) {
    var links = (data.link || []).filter(function (x) { return x && x.status === 'terbit'; });
    renderLinkBar(links, document.getElementById('linksPenting'));
    renderLinkBar(links, document.getElementById('linksKartu'));
    renderLinkKelola(links);
    var kontak = (data.kontak || []).filter(function (x) { return x.status === 'terbit'; });
    kontak.sort(function (a, b) { return (a.jabatan || '').localeCompare(b.jabatan || '', 'id'); });
    var kontakEl = document.getElementById('kontakGrid');
    var kontakSumber = document.getElementById('kontakSumber');
    if (kontakEl) {
      kontakEl.replaceChildren();
      if (kontakSumber) kontakSumber.textContent = kontak.length ? 'Kontak pengurus' : 'Belum ada kontak aktif';
      if (!kontak.length) kontakEl.appendChild(buat('p', 'konten-kosong', 'Belum ada kontak pengurus yang diterbitkan.'));
      kontak.forEach(function (x) {
        var kartu = buat('div', 'kontak');
        kartu.appendChild(buat('small', '', x.jabatan));
        kartu.appendChild(buat('b', '', x.nama));
        if (x.catatan) kartu.appendChild(buat('small', 'catatan-kecil', x.catatan));
        var link = buat('a', '', x.telepon);
        link.href = 'tel:' + String(x.telepon).replace(/[^+0-9]/g, '');
        link.setAttribute('aria-label', 'Telepon ' + x.jabatan + ', ' + x.nama);
        kartu.appendChild(link);
        kontakEl.appendChild(kartu);
      });
    }
    var berita = (data.informasi || []).filter(function (x) { return x.status === 'terbit'; });
    berita.sort(function (a, b) { return b.tanggal.localeCompare(a.tanggal); });
    var beritaEl = document.getElementById('daftar-informasi');
    if (beritaEl) {
      beritaEl.replaceChildren();
      if (!berita.length) beritaEl.appendChild(buat('p', 'konten-kosong', 'Belum ada informasi aktif.'));
      berita.forEach(function (x) {
        var artikel = buat('article', 'news-item');
        artikel.appendChild(buat('div', 'news-image', 'i'));
        var isi = buat('div');
        isi.appendChild(buat('div', 'date', tanggal(x.tanggal)));
        isi.appendChild(buat('h4', '', x.judul));
        isi.appendChild(buat('p', '', x.ringkasan || x.isi || ''));
        artikel.appendChild(isi);
        beritaEl.appendChild(artikel);
      });
    }
    var today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Jakarta' }).format(new Date());
    var acara = (data.kegiatan || []).filter(function (x) { return x.status === 'terbit' && x.tanggal >= today; });
    acara.sort(function (a, b) { return a.tanggal.localeCompare(b.tanggal); });
    var acaraEl = document.getElementById('kegiatan');
    if (acaraEl) {
      acaraEl.querySelectorAll('article.activity, .konten-kosong').forEach(function (e) { e.remove(); });
      if (!acara.length) acaraEl.appendChild(buat('p', 'konten-kosong', 'Belum ada kegiatan mendatang.'));
      acara.forEach(function (x) {
        var kartu = buat('article', 'activity');
        var d = new Date(x.tanggal + 'T00:00:00');
        var t = buat('div', 'activity-date');
        t.appendChild(buat('strong', '', d.toLocaleDateString('id-ID', { day: '2-digit' }).replace(/^0/, '')));
        t.appendChild(buat('small', '', d.toLocaleDateString('id-ID', { month: 'short' })));
        kartu.appendChild(t);
        var detail = buat('div');
        detail.appendChild(buat('h4', '', x.judul));
        if (x.lokasi) detail.appendChild(buat('p', '', 'Lokasi: ' + x.lokasi));
        if (x.waktu) detail.appendChild(buat('p', '', 'Waktu: ' + x.waktu));
        if (x.deskripsi) detail.appendChild(buat('p', 'catatan-kecil', x.deskripsi));
        kartu.appendChild(detail);
        acaraEl.appendChild(kartu);
      });
    }
    var lama = document.querySelectorAll('.announcement');
    if (lama.length) {
      var wadah = lama[0].parentElement;
      lama.forEach(function (e) { e.remove(); });
      berita.slice(0, 3).forEach(function (x) {
        var baris = buat('div', 'announcement');
        baris.appendChild(buat('span', 'dot'));
        var teks = buat('div');
        teks.appendChild(document.createTextNode(x.judul));
        teks.appendChild(document.createElement('br'));
        teks.appendChild(buat('small', '', tanggal(x.tanggal)));
        baris.appendChild(teks);
        wadah.appendChild(baris);
      });
    }
  }
  function simpan(ev) {
    ev.preventDefault();
    if (!form.reportValidity()) return;
    var id = byId('kontenId').value;
    var data = dataForm();
    var url = id ? apiRoot + '/' + data.jenis + '/' + encodeURIComponent(id) : apiRoot;
    api(id ? 'PATCH' : 'POST', url, data).then(function () {
      form.hidden = true;
      pesan('Konten berhasil disimpan.');
      return muat();
    }).catch(function (e) { pesan(e.message, true); });
  }
  function arsip(item) {
    api('DELETE', apiRoot + '/' + jenisEl.value + '/' + encodeURIComponent(item.id), {}).then(function () {
      pesan('Konten dipindahkan ke arsip dan tidak ditampilkan kepada warga.');
      return muat();
    }).catch(function (e) { pesan(e.message, true); });
  }
  function ubahStatus(item, status) {
    var data = Object.assign({}, item, { status: status });
    api('PATCH', apiRoot + '/' + jenisEl.value + '/' + encodeURIComponent(item.id), data).then(function () {
      pesan('Konten dipulihkan sebagai draf.');
      return muat();
    }).catch(function (e) { pesan(e.message, true); });
  }
  byId('kontenTambah').addEventListener('click', function () { bukaForm(null); });
  byId('kontenBatal').addEventListener('click', function () { form.hidden = true; pesan(''); });
  jenisEl.addEventListener('change', function () { form.hidden = true; renderAdmin(); });
  form.addEventListener('submit', simpan);
  if (linkTambah) linkTambah.addEventListener('click', function () { bukaLink(null); });
  if (formLink) formLink.addEventListener('submit', simpanLink);
  var linkClose = byId('modalLinkClose');
  var linkBatal = byId('linkBatal');
  var linkBackdrop = byId('modalLinkBackdrop');
  if (linkClose) linkClose.addEventListener('click', tutupLink);
  if (linkBatal) linkBatal.addEventListener('click', tutupLink);
  if (linkBackdrop) linkBackdrop.addEventListener('click', tutupLink);
  document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape') tutupLink(); });
  muat().catch(function (e) { pesan('Data konten tidak dapat dimuat: ' + e.message, true); });
})();