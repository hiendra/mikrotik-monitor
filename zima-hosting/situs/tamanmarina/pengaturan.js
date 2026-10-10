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

  /* ---------- 2. MASTER IURAN, AMBANG & PENGATURAN LAIN ---------- */

  /* Setiap baris punya dua mode: "lihat" (teks + tombol Ubah/Hapus) dan
     "ubah" (input + Selesai/Batal). Menghapus hanya melepas baris dari
     tampilan; yang benar-benar menyimpan ke server adalah tombol
     Simpan Pengaturan (PUT /api/pengaturan). Baris yang ditambah selalu
     mulai dalam mode "ubah"; baris baru yang dibiarkan seluruhnya kosong
     dibuang saat disimpan, sama seperti menekan Batal. */

  function tombolMini(teks, kelas) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'tombol-mini' + (kelas ? ' ' + kelas : '');
    b.textContent = teks;
    return b;
  }

  function wadahAksi(tag) {
    var el = document.createElement(tag);
    el.className = 'tm-aksi';
    return el;
  }

  function periksaIuran(b, no) {
    if (!b.jenis) throw new Error('Baris iuran ' + no + ': nama jenis wajib diisi.');
    if (!Number.isInteger(b.nominal) || b.nominal < 0 || b.nominal > 1000000000) {
      throw new Error('Baris iuran ' + no + ': nominal harus bilangan bulat 0 - 1.000.000.000.');
    }
  }

  function periksaAmbang(b, no) {
    if (b.batas_atas !== null && (!Number.isInteger(b.batas_atas) || b.batas_atas < 0)) {
      throw new Error('Ambang ' + no + ': batas atas harus angka bulat atau dikosongkan.');
    }
    if (!b.pengesahan) throw new Error('Ambang ' + no + ': pengesahan wajib diisi.');
  }

  function periksaLain(b, no) {
    if (!b.nama) throw new Error('Pengaturan lain baris ' + no + ': nama wajib diisi.');
    if (b.nilai.length > 300) throw new Error('Pengaturan lain baris ' + no + ': nilai maksimal 300 karakter.');
  }

  /* Tarik isi input ke model baris (hanya saat mode "ubah").
     Mengembalikan false bila baris seluruhnya kosong. */
  function tarikBaris(el) {
    if (el.getAttribute('data-mode') !== 'ubah' || typeof el._tarik !== 'function') return true;
    return el._tarik() !== false;
  }

  function nomorBaris(el, selektor) {
    return Array.prototype.slice.call(document.querySelectorAll(selektor)).indexOf(el) + 1;
  }

  /* Baris yang seluruh isinya masih kosong dianggap belum ada: dibuang saat
     Batal ditekan maupun saat pengaturan disimpan. */
  function barisKosong(el) {
    return typeof el._kosong === 'function' && el._kosong();
  }

  function batalUbah(el, lukis) {
    if (barisKosong(el)) { el.remove(); segarkanKosong(); return; }
    lukis('lihat');
  }

  function barisIuran(b) {
    var tr = document.createElement('tr');
    tr.setAttribute('data-iuran', '');
    tr._model = b;

    var iJenis, iNominal, iAktif;

    function lukis(mode) {
      tr.setAttribute('data-mode', mode);
      tr.textContent = '';

      if (mode === 'ubah') {
        if (!iJenis) {
          iJenis = document.createElement('input');
          iJenis.type = 'text';
          iJenis.maxLength = 80;
          iJenis.className = 'tm-iuran-jenis';
          iJenis.setAttribute('aria-label', 'Nama jenis iuran');
        }
        if (!iNominal) {
          iNominal = document.createElement('input');
          iNominal.type = 'number';
          iNominal.min = '0';
          iNominal.max = '1000000000';
          iNominal.step = '1000';
          iNominal.className = 'tm-iuran-nominal';
          iNominal.setAttribute('aria-label', 'Nominal');
        }
        if (!iAktif) {
          iAktif = document.createElement('input');
          iAktif.type = 'checkbox';
          iAktif.className = 'tm-iuran-aktif';
          iAktif.setAttribute('aria-label', 'Aktif');
        }
        iJenis.value = b.jenis || '';
        iNominal.value = (b.nominal === null || b.nominal === undefined) ? '' : b.nominal;
        iAktif.checked = !!b.aktif;

        var tdJenis = document.createElement('td');
        tdJenis.appendChild(iJenis);
        var tdNominal = document.createElement('td');
        tdNominal.appendChild(iNominal);
        var tdAktif = document.createElement('td');
        tdAktif.appendChild(iAktif);
        tr.appendChild(tdJenis);
        tr.appendChild(tdNominal);
        tr.appendChild(tdAktif);

        var kotak1 = wadahAksi('td');
        var bSelesai = tombolMini('Selesai');
        bSelesai.addEventListener('click', function () {
          if (tr._tarik() === false) { tr.remove(); segarkanKosong(); return; }
          try { periksaIuran(tr._model, nomorBaris(tr, '#tmIuranBody tr[data-iuran]')); }
          catch (e) { pesan(e.message, 'galat'); return; }
          lukis('lihat');
        });
        var bBatal = tombolMini('Batal');
        bBatal.addEventListener('click', function () { batalUbah(tr, lukis); });
        kotak1.appendChild(bSelesai);
        kotak1.appendChild(bBatal);
        tr.appendChild(kotak1);
      } else {
        var tdJ = document.createElement('td');
        tdJ.textContent = b.jenis || '(nama belum diisi)';
        var tdN = document.createElement('td');
        tdN.textContent = rupiah(b.nominal);
        var tdA = document.createElement('td');
        tdA.textContent = b.aktif ? 'Ya' : 'Tidak';
        tr.appendChild(tdJ);
        tr.appendChild(tdN);
        tr.appendChild(tdA);

        var kotak2 = wadahAksi('td');
        var bUbah = tombolMini('Ubah');
        bUbah.addEventListener('click', function () { lukis('ubah'); });
        var bHapus = tombolMini('Hapus', 'tm-bahaya');
        bHapus.addEventListener('click', function () { tr.remove(); segarkanKosong(); });
        kotak2.appendChild(bUbah);
        kotak2.appendChild(bHapus);
        tr.appendChild(kotak2);
      }
    }

    tr._tarik = function () {
      if (tr.getAttribute('data-mode') !== 'ubah') return true;
      var jenis = iJenis.value.trim();
      var nominalRaw = iNominal.value.trim();
      if (!jenis && !nominalRaw) return false;
      b.jenis = jenis;
      b.nominal = /^\d+$/.test(nominalRaw) ? Number(nominalRaw) : NaN;
      b.aktif = iAktif.checked;
      return true;
    };
    tr._kosong = function () {
      return !b.jenis && (b.nominal === null || b.nominal === undefined);
    };
    tr._lukis = lukis;
    lukis('lihat');
    return tr;
  }

  function teksAmbang(b) {
    var batas = (b.batas_atas === null || b.batas_atas === undefined)
      ? 'Tanpa batas atas'
      : '≤ ' + rupiah(b.batas_atas);
    return batas + ' · disahkan ' + (b.pengesahan || '(belum diisi)');
  }

  function barisAmbang(b) {
    var el = document.createElement('div');
    el.className = 'tm-ambang-baris';
    el.setAttribute('data-ambang', '');
    el._model = b;

    var iBatas, iPengesahan;

    function lukis(mode) {
      el.setAttribute('data-mode', mode);
      el.textContent = '';

      var kotak = wadahAksi('span');

      if (mode === 'ubah') {
        if (!iBatas) {
          iBatas = document.createElement('input');
          iBatas.type = 'number';
          iBatas.min = '0';
          iBatas.step = '100000';
          iBatas.placeholder = 'Batas atas (Rp) — kosong = tanpa batas';
          iBatas.className = 'tm-ambang-batas';
          iBatas.setAttribute('aria-label', 'Batas atas');
        }
        if (!iPengesahan) {
          iPengesahan = document.createElement('input');
          iPengesahan.type = 'text';
          iPengesahan.maxLength = 120;
          iPengesahan.placeholder = 'Siapa yang mengesahkan';
          iPengesahan.className = 'tm-ambang-pengesahan';
          iPengesahan.setAttribute('aria-label', 'Pengesahan');
        }
        iBatas.value = (b.batas_atas === null || b.batas_atas === undefined) ? '' : b.batas_atas;
        iPengesahan.value = b.pengesahan || '';
        el.appendChild(iBatas);
        el.appendChild(iPengesahan);

        var bSelesai = tombolMini('Selesai');
        bSelesai.addEventListener('click', function () {
          if (el._tarik() === false) { el.remove(); segarkanKosong(); return; }
          try { periksaAmbang(el._model, nomorBaris(el, '#tmAmbangDaftar [data-ambang]')); }
          catch (e) { pesan(e.message, 'galat'); return; }
          lukis('lihat');
        });
        var bBatal = tombolMini('Batal');
        bBatal.addEventListener('click', function () { batalUbah(el, lukis); });
        kotak.appendChild(bSelesai);
        kotak.appendChild(bBatal);
      } else {
        var teks = document.createElement('span');
        teks.className = 'tm-ambang-teks';
        teks.textContent = teksAmbang(b);
        el.appendChild(teks);

        var bUbah = tombolMini('Ubah');
        bUbah.addEventListener('click', function () { lukis('ubah'); });
        var bHapus = tombolMini('Hapus', 'tm-bahaya');
        bHapus.addEventListener('click', function () { el.remove(); segarkanKosong(); });
        kotak.appendChild(bUbah);
        kotak.appendChild(bHapus);
      }

      el.appendChild(kotak);
    }

    el._tarik = function () {
      if (el.getAttribute('data-mode') !== 'ubah') return true;
      var batasRaw = iBatas.value.trim();
      var pengesahan = iPengesahan.value.trim();
      if (!batasRaw && !pengesahan) return false;
      b.batas_atas = batasRaw === '' ? null : (/^\d+$/.test(batasRaw) ? Number(batasRaw) : NaN);
      b.pengesahan = pengesahan;
      return true;
    };
    el._kosong = function () {
      return !b.pengesahan && (b.batas_atas === null || b.batas_atas === undefined);
    };
    el._lukis = lukis;
    lukis('lihat');
    return el;
  }

  function barisLain(b) {
    var el = document.createElement('div');
    el.className = 'tm-lain-baris';
    el.setAttribute('data-lain', '');
    el._model = b;

    var iNama, iNilai;

    function lukis(mode) {
      el.setAttribute('data-mode', mode);
      el.textContent = '';

      var kotak = wadahAksi('span');

      if (mode === 'ubah') {
        if (!iNama) {
          iNama = document.createElement('input');
          iNama.type = 'text';
          iNama.maxLength = 80;
          iNama.placeholder = 'Nama pengaturan';
          iNama.className = 'tm-lain-nama';
          iNama.setAttribute('aria-label', 'Nama pengaturan');
        }
        if (!iNilai) {
          iNilai = document.createElement('input');
          iNilai.type = 'text';
          iNilai.maxLength = 300;
          iNilai.placeholder = 'Nilai';
          iNilai.className = 'tm-lain-nilai';
          iNilai.setAttribute('aria-label', 'Nilai pengaturan');
        }
        iNama.value = b.nama || '';
        iNilai.value = b.nilai || '';
        el.appendChild(iNama);
        el.appendChild(iNilai);

        var bSelesai = tombolMini('Selesai');
        bSelesai.addEventListener('click', function () {
          if (el._tarik() === false) { el.remove(); segarkanKosong(); return; }
          try { periksaLain(el._model, nomorBaris(el, '#tmLainDaftar [data-lain]')); }
          catch (e) { pesan(e.message, 'galat'); return; }
          lukis('lihat');
        });
        var bBatal = tombolMini('Batal');
        bBatal.addEventListener('click', function () { batalUbah(el, lukis); });
        kotak.appendChild(bSelesai);
        kotak.appendChild(bBatal);
      } else {
        var teks = document.createElement('span');
        teks.className = 'tm-lain-teks';
        var bNama = document.createElement('b');
        bNama.textContent = b.nama || '(nama belum diisi)';
        teks.appendChild(bNama);
        teks.appendChild(document.createTextNode(' · ' + (b.nilai ? b.nilai : '(kosong)')));
        el.appendChild(teks);

        var bUbah = tombolMini('Ubah');
        bUbah.addEventListener('click', function () { lukis('ubah'); });
        var bHapus = tombolMini('Hapus', 'tm-bahaya');
        bHapus.addEventListener('click', function () { el.remove(); segarkanKosong(); });
        kotak.appendChild(bUbah);
        kotak.appendChild(bHapus);
      }

      el.appendChild(kotak);
    }

    el._tarik = function () {
      if (el.getAttribute('data-mode') !== 'ubah') return true;
      var nama = iNama.value.trim();
      var nilai = iNilai.value.trim();
      if (!nama && !nilai) return false;
      b.nama = nama;
      b.nilai = nilai;
      return true;
    };
    el._kosong = function () { return !b.nama && !b.nilai; };
    el._lukis = lukis;
    lukis('lihat');
    return el;
  }

  /* Catatan "belum ada …" dipasang/dilepas otomatis agar daftar kosong
     tidak menyisakan ruang hampa tanpa penjelasan. */
  function catatanKosong(wadah, selektor, teks) {
    if (!wadah) return;
    var adaBaris = wadah.querySelector(selektor);
    var catatan = wadah.querySelector('[data-kosong]');
    if (adaBaris) { if (catatan) catatan.remove(); return; }
    if (!catatan) {
      catatan = document.createElement('p');
      catatan.className = 'catatan-kecil';
      catatan.setAttribute('data-kosong', '');
      catatan.textContent = teks;
      wadah.appendChild(catatan);
    }
  }

  function segarkanKosong() {
    var tb = $('tmIuranBody');
    if (tb) {
      var kosong = tb.querySelector('tr[data-kosong]');
      if (tb.querySelector('tr[data-iuran]')) {
        if (kosong) kosong.remove();
      } else {
        tb.textContent = '';
        var tr = document.createElement('tr');
        tr.setAttribute('data-kosong', '');
        var td = document.createElement('td');
        td.colSpan = 4;
        td.className = 'catatan-kecil';
        td.textContent = 'Belum ada jenis iuran — klik "+ Tambah Jenis".';
        tr.appendChild(td);
        tb.appendChild(tr);
      }
    }
    catatanKosong($('tmAmbangDaftar'), '[data-ambang]', 'Belum ada ambang — klik "+ Tambah Ambang".');
    catatanKosong($('tmLainDaftar'), '[data-lain]', 'Belum ada pengaturan lain — klik "+ Tambah Pengaturan".');
  }

  function renderPengaturan(p) {
    var tb = $('tmIuranBody');
    if (tb) {
      tb.textContent = '';
      (p.iuran || []).forEach(function (b) { tb.appendChild(barisIuran(b)); });
    }
    var wAmbang = $('tmAmbangDaftar');
    if (wAmbang) {
      wAmbang.textContent = '';
      (p.ambang || []).forEach(function (b) { wAmbang.appendChild(barisAmbang(b)); });
    }
    var wLain = $('tmLainDaftar');
    if (wLain) {
      wLain.textContent = '';
      (p.lain || []).forEach(function (b) { wLain.appendChild(barisLain(b)); });
    }
    segarkanKosong();
  }

  function kumpulPengaturan() {
    var iuran = [];
    var ambang = [];
    var lain = [];
    var buang = [];

    Array.prototype.slice.call(document.querySelectorAll('#tmIuranBody tr[data-iuran]')).forEach(function (tr) {
      if (!tarikBaris(tr) || barisKosong(tr)) { buang.push(tr); return; }
      periksaIuran(tr._model, iuran.length + 1);
      iuran.push({ jenis: tr._model.jenis, nominal: tr._model.nominal, aktif: !!tr._model.aktif });
    });

    Array.prototype.slice.call(document.querySelectorAll('#tmAmbangDaftar [data-ambang]')).forEach(function (el) {
      if (!tarikBaris(el) || barisKosong(el)) { buang.push(el); return; }
      periksaAmbang(el._model, ambang.length + 1);
      ambang.push({ batas_atas: el._model.batas_atas, pengesahan: el._model.pengesahan });
    });

    Array.prototype.slice.call(document.querySelectorAll('#tmLainDaftar [data-lain]')).forEach(function (el) {
      if (!tarikBaris(el) || barisKosong(el)) { buang.push(el); return; }
      periksaLain(el._model, lain.length + 1);
      lain.push({ nama: el._model.nama, nilai: el._model.nilai });
    });

    buang.forEach(function (el) { el.remove(); });
    if (buang.length) segarkanKosong();

    return { iuran: iuran, ambang: ambang, lain: lain };
  }

  function muatPengaturan() {
    return intaan('GET', '/api/pengaturan').then(function (h) {
      if (!h.ok) {
        pesan(h.data.galat || 'Gagal memuat pengaturan.', 'galat');
        return;
      }
      renderPengaturan(h.data.pengaturan || {});
    }).catch(function (e) { pesan('Gagal memuat pengaturan dari server: ' + e.message, 'galat'); });
  }

  function pesanIuran(teks, galat) {
    var el = $('tmIuranPesan'); if (!el) return;
    el.textContent = teks || '';
    el.className = 'status-baris' + (galat ? ' status-galat' : ' status-ok');
    el.hidden = !teks;
  }

  function simpanSemuaPengaturan() {
    var isi;
    try { isi = kumpulPengaturan(); } catch (e) { pesan(e.message, 'galat'); return; }
    var tombol = [$('tmPengaturanSimpan'), $('tmIuranSimpan')].filter(Boolean);
    tombol.forEach(function (b) { b.disabled = true; });
    pesan('Menyimpan perubahan ke server…'); pesanIuran('Menyimpan perubahan ke server…');
    intaan('PUT', '/api/pengaturan', { pengaturan: isi }).then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      renderPengaturan(h.data.pengaturan || isi);
      var konfirmasiSimpan = 'Perubahan berhasil tersimpan di server (' + isi.iuran.length + ' jenis iuran, ' + isi.ambang.length + ' ambang, ' + isi.lain.length + ' pengaturan lain).';
      pesan(konfirmasiSimpan); pesanIuran(konfirmasiSimpan);
      muatTagihanUmum();
      if (dataTagihanSaya) muatTagihanSaya();
    }).catch(function (e) {
      var galatSimpan = 'Perubahan gagal tersimpan: ' + e.message + '. Data di layar masih ada; periksa koneksi/izin lalu coba Simpan lagi.';
      pesan(galatSimpan, 'galat'); pesanIuran(galatSimpan, true);
    }).finally(function () { tombol.forEach(function (b) { b.disabled = false; }); });
  }

  function pasangTombolPengaturan() {
    var tambahIuran = $('tmIuranTambah');
    if (tambahIuran) {
      tambahIuran.addEventListener('click', function () {
        var tb = $('tmIuranBody');
        if (!tb) return;
        var kosong = tb.querySelector('tr[data-kosong]');
        if (kosong) kosong.remove();
        var tr = barisIuran({ jenis: '', nominal: null, aktif: true });
        tb.appendChild(tr);
        tr._lukis('ubah'); // baris baru langsung siap diisi
        var fokus = tr.querySelector('.tm-iuran-jenis');
        if (fokus) fokus.focus();
      });
    }

    var tambahAmbang = $('tmAmbangTambah');
    if (tambahAmbang) {
      tambahAmbang.addEventListener('click', function () {
        var wadah = $('tmAmbangDaftar');
        if (!wadah) return;
        var kosong = wadah.querySelector('[data-kosong]');
        if (kosong) kosong.remove();
        var el = barisAmbang({ batas_atas: null, pengesahan: '' });
        wadah.appendChild(el);
        el._lukis('ubah');
      });
    }

    var tambahLain = $('tmLainTambah');
    if (tambahLain) {
      tambahLain.addEventListener('click', function () {
        var wadah = $('tmLainDaftar');
        if (!wadah) return;
        var kosong = wadah.querySelector('[data-kosong]');
        if (kosong) kosong.remove();
        var el = barisLain({ nama: '', nilai: '' });
        wadah.appendChild(el);
        el._lukis('ubah');
      });
    }

    ['tmPengaturanSimpan', 'tmIuranSimpan'].forEach(function (id) {
      var simpan = $(id);
      if (simpan) simpan.addEventListener('click', simpanSemuaPengaturan);
    });

    var muatUlang = $('tmPengaturanMuatUlang');
    if (muatUlang) {
      muatUlang.addEventListener('click', function () {
        muatUlang.disabled = true;
        muatPengaturan().then(function () {
          muatUlang.disabled = false;
          pesan('Perubahan yang belum disimpan dibatalkan — data dimuat ulang dari server.');
        });
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

  /* ---------- Tagihan akun dan verifikasi pembayaran ---------- */
  var metodeUntukWarga = [];
  var dataTagihanSaya = null;
  var LABEL_STATUS_IURAN = { belum: 'Belum bayar', menunggu: 'Menunggu verifikasi', lunas: 'Lunas', ditolak: 'Ditolak' };
  function rupiahIuran(n) { return 'Rp ' + (Number(n) || 0).toLocaleString('id-ID'); }
  function lencanaIuran(status) {
    var kelas = status === 'lunas' ? 'hijau' : (status === 'ditolak' || status === 'belum' ? 'merah' : 'kuning');
    return '<span class="lencana ' + kelas + '">' + esc(LABEL_STATUS_IURAN[status] || 'Menunggu verifikasi') + '</span>';
  }
  function muatTagihanUmum() {
    var daftar = $('tmTagihanSayaItems');
    var total = $('tmTagihanSayaTotal');
    if (!daftar) return;
    intaan('GET', '/api/jenis-iuran').then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      var item = Array.isArray(h.data.iuran) ? h.data.iuran : [];
      daftar.textContent = '';
      if (!item.length) {
        var kosong = document.createElement('li'); kosong.textContent = 'Belum ada iuran aktif.'; daftar.appendChild(kosong);
      } else item.forEach(function (b) {
        var li = document.createElement('li'), nama = document.createElement('span'), jumlah = document.createElement('b');
        nama.textContent = b.jenis; jumlah.textContent = rupiahIuran(b.nominal); li.appendChild(nama); li.appendChild(jumlah); daftar.appendChild(li);
      });
      if (total) total.textContent = rupiahIuran(h.data.total);
      var sub = document.querySelector('#iuran .section-title .sumber');
      if (sub) sub.textContent = 'Tagihan bulanan · total mengikuti iuran aktif';
    }).catch(function () {
      daftar.textContent = '';
      var err = document.createElement('li'); err.textContent = 'Daftar iuran belum dapat dimuat dari server.'; daftar.appendChild(err);
      if (total) total.textContent = '—';
    });
  }
  function muatMetodeUntukWarga() {
    var pilih = $('tmPilihMetodeTagihan');
    if (!pilih) return Promise.resolve();
    return intaan('GET', '/api/metode-publik').then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      metodeUntukWarga = Array.isArray(h.data.metode) ? h.data.metode : [];
      pilih.textContent = '';
      var awal = document.createElement('option'); awal.value = ''; awal.textContent = 'Pilih metode pembayaran'; pilih.appendChild(awal);
      metodeUntukWarga.forEach(function (m) {
        var o = document.createElement('option'); o.value = String(m.id);
        var jenis = { transfer: 'Transfer', qris: 'QRIS', tunai: 'Tunai', ewallet: 'E-wallet', lainnya: 'Lainnya' }[m.jenis] || m.jenis;
        o.textContent = m.bank + ' · ' + jenis + (m.nomor_rekening ? ' · ' + m.nomor_rekening : ''); pilih.appendChild(o);
      });
    }).catch(function () {
      if (pilih) { pilih.textContent = ''; var e = document.createElement('option'); e.value = ''; e.textContent = 'Metode pembayaran belum tersedia'; pilih.appendChild(e); }
    });
  }
  function renderTagihanSaya(d) {
    dataTagihanSaya = d;
    var status = $('tmTagihanSayaStatus');
    var aksi = $('tmTagihanAksi');
    var masuk = $('tmTagihanMasuk');
    if (status) status.innerHTML = lencanaIuran(d.status) + ' · Periode ' + esc(d.periode || '—');
    if (masuk) masuk.hidden = true;
    if (aksi) aksi.hidden = false;
    var tbody = $('tmRiwayatSaya');
    if (tbody) {
      var riwayat = Array.isArray(d.riwayat) ? d.riwayat : [];
      tbody.innerHTML = riwayat.length ? riwayat.map(function (t) {
        return '<tr><td>' + esc(t.periode) + '</td><td>' + rupiahIuran(t.jumlah) + '</td><td>' + lencanaIuran(t.status) + '</td><td>' + esc(t.metode || '—') + '</td><td>' + esc(jam(t.diajukan)) + '</td><td>' + esc(t.diverifikasi_oleh || '—') + '</td></tr>';
      }).join('') : '<tr><td colspan="6" class="catatan-kecil">Belum ada pengajuan pembayaran.</td></tr>';
    }
    var tombol = $('tmAjukanTagihan');
    if (tombol) tombol.disabled = d.status === 'lunas' || d.status === 'menunggu';
  }
  function muatTagihanSaya() {
    return intaan('GET', '/api/iuran/saya').then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      renderTagihanSaya(h.data);
      return muatMetodeUntukWarga();
    }).catch(function (e) {
      var status = $('tmTagihanSayaStatus');
      if (status) status.textContent = 'Tagihan akun gagal dimuat: ' + e.message;
      return Promise.resolve();
    });
  }
  function ajukanTagihanSaya() {
    var pilih = $('tmPilihMetodeTagihan'); var tombol = $('tmAjukanTagihan');
    if (!pilih || !pilih.value) { if (pilih) pilih.focus(); var s = $('tmTagihanSayaStatus'); if (s) s.textContent = 'Pilih metode pembayaran terlebih dahulu.'; return; }
    if (tombol) tombol.disabled = true;
    intaan('POST', '/api/iuran/saya', { metode_id: pilih.value }).then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      pesan('Pengajuan pembayaran tercatat dan menunggu verifikasi pengurus/admin.');
      return muatTagihanSaya();
    }).catch(function (e) {
      var s = $('tmTagihanSayaStatus'); if (s) s.textContent = 'Pengajuan gagal: ' + e.message;
    }).finally(function () { if (tombol && (!dataTagihanSaya || !['lunas', 'menunggu'].includes(dataTagihanSaya.status))) tombol.disabled = false; });
  }
  function muatVerifikasiIuran() {
    var tb = $('tmVerifikasiIuranBody'); if (!tb) return;
    intaan('GET', '/api/iuran/verifikasi').then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      var daftar = (h.data.transaksi || []).filter(function (t) { return t.status === 'menunggu'; });
      tb.innerHTML = daftar.length ? daftar.map(function (t) {
        return '<tr><td>' + esc(t.nama || t.pengguna) + '<br><small>' + esc(t.pengguna) + '</small></td><td>' + esc(t.blok || '—') + '</td><td>' + esc(t.periode) + '</td><td>' + rupiahIuran(t.jumlah) + '</td><td>' + esc(t.metode) + '</td><td>' + lencanaIuran(t.status) + '</td><td>' + esc(jam(t.diajukan)) + '</td><td class="tm-aksi"><button type="button" class="tombol-mini" data-verif-iuran="lunas" data-id="' + esc(t.id) + '">Verifikasi Lunas</button> <button type="button" class="tombol-mini tm-bahaya" data-verif-iuran="ditolak" data-id="' + esc(t.id) + '">Tolak</button></td></tr>';
      }).join('') : '<tr><td colspan="8" class="catatan-kecil">Tidak ada pembayaran yang menunggu verifikasi.</td></tr>';
    }).catch(function (e) { tb.innerHTML = '<tr><td colspan="8" class="catatan-kecil">Gagal memuat verifikasi: ' + esc(e.message) + '</td></tr>'; });
  }
  function pasangTagihanWarga() {
    muatTagihanUmum();
    var ajukan = $('tmAjukanTagihan'); if (ajukan) ajukan.addEventListener('click', ajukanTagihanSaya);
    var muat = $('tmMuatVerifikasi'); if (muat) muat.addEventListener('click', muatVerifikasiIuran);
    var verif = $('tmVerifikasiIuranBody');
    if (verif) verif.addEventListener('click', function (ev) {
      var b = ev.target.closest && ev.target.closest('[data-verif-iuran]'); if (!b) return;
      var status = b.getAttribute('data-verif-iuran');
      if (!window.confirm(status === 'lunas' ? 'Pastikan pembayaran sudah diterima. Tandai lunas?' : 'Tolak pengajuan pembayaran ini?')) return;
      b.disabled = true;
      intaan('POST', '/api/iuran/verifikasi/' + encodeURIComponent(b.getAttribute('data-id')), { status: status }).then(function (h) {
        if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
        pesan('Status pembayaran berhasil diperbarui.'); muatVerifikasiIuran();
      }).catch(function (e) { pesan('Verifikasi gagal: ' + e.message, 'galat'); b.disabled = false; });
    });
    document.addEventListener('tm-sesi', function (ev) {
      var d = ev.detail || {};
      var aksi = $('tmTagihanAksi'); var masuk = $('tmTagihanMasuk');
      if (d.pengguna) {
        if (aksi) aksi.hidden = false;
        if (masuk) masuk.hidden = true;
        muatTagihanSaya();
        if (d.izin && d.izin['iuran.verifikasi']) muatVerifikasiIuran();
      } else {
        if (aksi) aksi.hidden = true;
        if (masuk) { masuk.hidden = false; masuk.textContent = 'Masuk untuk melihat tagihan dan mengajukan pembayaran akun.'; }
      }
    });
  }
  pasangTagihanWarga();

  /* ---------- 4. TAB PENGATURAN SISTEM ---------- */
  /* Empat tab menyusun hub admin. Tab selain "umum" memuat datanya saat
     pertama dibuka (malas), lalu hasilnya tetap di layar sampai halaman
     dimuat ulang. */

  var TAB_PEMUAT = {};  // nama tab -> fungsi pemuat datanya
  var tabTermuat = {};  // nama tab -> true bila sudah pernah dimuat

  function tabTampilkan(nama) {
    var nav = $('tmTabNav');
    if (!nav) return;
    Array.prototype.slice.call(nav.querySelectorAll('.tm-tab-btn')).forEach(function (b) {
      var aktif = b.getAttribute('data-tab') === nama;
      b.classList.toggle('aktif', aktif);
      b.setAttribute('aria-selected', aktif ? 'true' : 'false');
    });
    var panelAda = false;
    Array.prototype.slice.call(document.querySelectorAll('#pengaturan .tm-tab-panel')).forEach(function (p) {
      var aktif = p.getAttribute('data-tab') === nama;
      if (aktif) panelAda = true;
      p.hidden = !aktif;
      p.classList.toggle('aktif', aktif);
    });
    if (!panelAda) return;
    if (!tabTermuat[nama] && typeof TAB_PEMUAT[nama] === 'function') {
      tabTermuat[nama] = true;
      TAB_PEMUAT[nama]();
    }
  }

  function pasangTab() {
    var nav = $('tmTabNav');
    if (!nav) return;
    Array.prototype.slice.call(nav.querySelectorAll('.tm-tab-btn')).forEach(function (b) {
      b.addEventListener('click', function () { tabTampilkan(b.getAttribute('data-tab')); });
    });
    // Dukungan tautan langsung, mis. /#pengaturan?tab=akuntansi
    var m = (location.hash || '').match(/tab=([a-z]+)/);
    if (m) tabTampilkan(m[1]);
  }

  /* ---- util tabel ---- */

  function sel(isi, kelas) {
    return '<td' + (kelas ? ' class="' + kelas + '"' : '') + '>' + isi + '</td>';
  }

  function barisTabel(selDaftar) {
    return '<tr>' + selDaftar.join('') + '</tr>';
  }

  function isiTabel(id, baris, kolom, kosong) {
    var tb = $(id);
    if (!tb) return;
    if (!baris || !baris.length) {
      tb.innerHTML = '<tr><td colspan="' + kolom + '" class="catatan-kecil">'
        + esc(kosong || 'Belum ada data.') + '</td></tr>';
      return;
    }
    tb.innerHTML = baris.join('');
  }

  function lencana(teks, jenis) {
    return '<span class="tm-lencana' + (jenis ? ' tm-lencana-' + jenis : '') + '">'
      + esc(teks) + '</span>';
  }

  /* ---- tab: Pengguna & Role (data NYATA dari API, bukan salinan) ---- */

  function muatTabPengguna() {
    intaan('GET', '/api/pengguna').then(function (h) {
      if (!h.ok) { isiTabel('tmUserBody', [], 5, 'Gagal memuat pengguna (HTTP ' + h.status + ').'); return; }
      var label = h.data.label || {};
      var bolehAtur = h.data.bolehAtur || [];
      isiTabel('tmUserBody', (h.data.pengguna || []).map(function (u) {
        var role = label[u.peran] || u.peran;
        var aksi = bolehAtur.indexOf(u.peran) !== -1
          ? '<a class="tombol-mini tm-tautan-tombol" href="#pengguna">Kelola</a>'
          : '—';
        return barisTabel([
          sel(esc(u.nama)),
          sel(esc(u.pengguna)),
          sel(esc(role)),
          sel(u.aktif ? lencana('Aktif', 'ok') : lencana('Nonaktif', 'mati')),
          sel(aksi),
        ]);
      }), 5);
    });
    intaan('GET', '/api/peran').then(function (h) {
      if (!h.ok) { isiTabel('tmRoleBody', [], 4, 'Gagal memuat peran (HTTP ' + h.status + ').'); return; }
      isiTabel('tmRoleBody', (h.data.peran || []).map(function (p) {
        return barisTabel([
          sel('<b>' + esc(p.label) + '</b>'),
          sel(esc(p.judul)),
          sel((p.izin || []).length + ' izin'),
          sel(lencana('Tetap', 'ok')),
        ]);
      }), 4);
    });
  }

  /* ---- tab: Sistem Pembayaran (/api/pembayaran) ---- */

  var metodePembayaran = [];

  function pesanMetode(teks, galat) {
    var el = $('tmMetodePesan');
    if (!el) return;
    el.textContent = teks || '';
    el.classList.toggle('galat', !!galat);
    el.classList.toggle('sukses', !!teks && !galat);
    el.hidden = !teks;
  }

  function tutupFormMetode() {
    var form = $('tmMetodeForm');
    if (form) form.hidden = true;
    if (form) form.reset();
    $('tmMetodeIndex').value = '';
    $('tmMetodeId').value = '';
  }

  function bukaFormMetode(index) {
    var form = $('tmMetodeForm');
    if (!form) return;
    form.reset();
    var baru = index === null;
    var item = baru ? {
      bank: '', jenis: 'transfer', nomor_rekening: '', atas_nama: '',
      status: 'aktif', keterangan: '',
    } : metodePembayaran[index];
    if (!item) return;
    $('tmMetodeIndex').value = baru ? '' : String(index);
    $('tmMetodeId').value = baru ? '' : String(item.id);
    $('tmMetodeBank').value = item.bank || '';
    $('tmMetodeJenis').value = item.jenis || 'transfer';
    $('tmMetodeNomor').value = item.nomor_rekening || '';
    $('tmMetodeAtasNama').value = item.atas_nama || '';
    $('tmMetodeStatus').value = item.status === 'nonaktif' ? 'nonaktif' : 'aktif';
    $('tmMetodeKeterangan').value = item.keterangan || '';
    $('tmMetodeJudul').textContent = baru ? 'Tambah Metode Pembayaran' : 'Edit Metode Pembayaran';
    form.hidden = false;
    $('tmMetodeBank').focus();
  }

  function simpanMetode(ev) {
    ev.preventDefault();
    var form = $('tmMetodeForm');
    if (!form.reportValidity()) return;
    var metode = {
      bank: $('tmMetodeBank').value.trim(),
      jenis: $('tmMetodeJenis').value,
      nomor_rekening: $('tmMetodeNomor').value.trim(),
      atas_nama: $('tmMetodeAtasNama').value.trim(),
      status: $('tmMetodeStatus').value,
      keterangan: $('tmMetodeKeterangan').value.trim(),
    };
    if (metode.jenis === 'transfer' && !metode.nomor_rekening) {
      pesanMetode('Nomor rekening wajib untuk transfer.', true);
      $('tmMetodeNomor').focus();
      return;
    }
    var index = $('tmMetodeIndex').value;
    var daftar = metodePembayaran.slice();
    if (index === '') daftar.push(metode);
    else {
      metode.id = metodePembayaran[Number(index)].id;
      daftar[Number(index)] = metode;
    }
    var tombol = $('tmMetodeSimpan');
    tombol.disabled = true;
    intaan('PUT', '/api/pembayaran', { rekening: daftar }).then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      tutupFormMetode();
      pesanMetode('Metode pembayaran berhasil disimpan.');
      muatTabPembayaran();
    }).catch(function (e) {
      pesanMetode('Metode gagal disimpan: ' + e.message, true);
    }).finally(function () { tombol.disabled = false; });
  }

  function hapusMetode(index) {
    var item = metodePembayaran[index];
    if (!item || !window.confirm('Hapus metode ' + (item.bank || 'ini') + '?')) return;
    var daftar = metodePembayaran.filter(function (_, i) { return i !== index; });
    intaan('PUT', '/api/pembayaran', { rekening: daftar }).then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      tutupFormMetode();
      pesanMetode('Metode pembayaran berhasil dihapus.');
      muatTabPembayaran();
    }).catch(function (e) { pesanMetode('Metode gagal dihapus: ' + e.message, true); });
  }

  function pasangFormMetode() {
    var tambah = $('tmMetodeTambah');
    var form = $('tmMetodeForm');
    var batal = $('tmMetodeBatal');
    var tabel = $('tmRekBody');
    if (tambah) tambah.addEventListener('click', function () { bukaFormMetode(null); });
    if (batal) batal.addEventListener('click', tutupFormMetode);
    if (form) form.addEventListener('submit', simpanMetode);
    if (tabel) tabel.addEventListener('click', function (ev) {
      var tombol = ev.target.closest ? ev.target.closest('[data-metode-aksi]') : null;
      if (!tombol) return;
      var index = Number(tombol.getAttribute('data-index'));
      if (!Number.isInteger(index) || index < 0) return;
      if (tombol.getAttribute('data-metode-aksi') === 'edit') bukaFormMetode(index);
      if (tombol.getAttribute('data-metode-aksi') === 'hapus') hapusMetode(index);
    });
  }

  function muatTabPembayaran() {
    intaan('GET', '/api/pembayaran').then(function (h) {
      if (!h.ok) {
        isiTabel('tmRekBody', [], 7, 'Gagal memuat (HTTP ' + h.status + ').');
        isiTabel('tmPayStatusBody', [], 3, 'Gagal memuat.');
        return;
      }
      var d = h.data;
      metodePembayaran = Array.isArray(d.rekening) ? d.rekening : [];
      isiTabel('tmRekBody', metodePembayaran.map(function (k, i) {
        var aksi = '<div class="tm-aksi">'
          + '<button type="button" class="tombol-mini" data-metode-aksi="edit" data-index="' + i + '">Edit</button>'
          + '<button type="button" class="tombol-mini tm-bahaya" data-metode-aksi="hapus" data-index="' + i + '">Hapus</button>'
          + '</div>';
        var labelJenis = {
          transfer: 'Transfer bank', qris: 'QRIS', tunai: 'Tunai',
          ewallet: 'E-wallet', lainnya: 'Lainnya',
        }[k.jenis] || k.jenis || '—';
        return barisTabel([
          sel(esc(k.bank || '—')),
          sel(esc(labelJenis)),
          sel(esc(k.nomor_rekening || '—')),
          sel(esc(k.atas_nama || '—')),
          sel(esc(k.keterangan || '—')),
          sel(k.status === 'aktif' ? lencana('Aktif', 'ok') : lencana('Nonaktif', 'mati')),
          sel(aksi),
        ]);
      }), 7, 'Belum ada metode pembayaran. Klik “Tambah Metode” untuk membuat.');
      isiTabel('tmPayStatusBody', (d.status || []).map(function (s) {
        return barisTabel([sel(esc(s.kode)), sel(esc(s.label)), sel(esc(s.warna))]);
      }), 3);
      var cat = $('tmPembayaranCatatan');
      if (cat) {
        var aktif = metodePembayaran.filter(function (k) { return k.status === 'aktif'; }).length;
        cat.textContent = metodePembayaran.length + ' metode · ' + aktif + ' aktif · '
          + (d.status || []).length + ' status pembayaran. Penyimpanan metode langsung ke server dan tidak mengubah transaksi.';
      }
    }).catch(function (e) {
      isiTabel('tmRekBody', [], 7, 'Gagal memuat: ' + e.message);
    });
  }

  /* ---- tab: Sistem Akuntansi (/api/akuntansi) ---- */

  /* ---- tab: Sistem Akuntansi (/api/akuntansi) ---- */
  var dataAkuntansi = { coa: [], jurnal: [], kas: [] };

  function pesanAkuntansi(teks, galat) {
    var el = $('tmAkuntansiPesan');
    if (!el) return;
    el.textContent = teks || '';
    el.classList.toggle('galat', !!galat);
    el.classList.toggle('sukses', !!teks && !galat);
    el.hidden = !teks;
  }

  function tutupFormAkuntansi(form) {
    if (!form) return;
    form.hidden = true;
    form.reset();
  }

  function isiFormCoa(i) {
    var a = dataAkuntansi.coa[i];
    if (!a) return;
    $('tmCoaIndex').value = i;
    $('tmCoaKode').value = a.kode || '';
    $('tmCoaNama').value = a.nama || '';
    $('tmCoaJenis').value = a.jenis || 'aset';
    $('tmCoaSaldo').value = a.saldo == null ? 0 : a.saldo;
    $('tmCoaStatus').value = a.status === 'nonaktif' ? 'nonaktif' : 'aktif';
    $('tmCoaInduk').value = a.induk == null ? '' : a.induk;
    $('tmCoaForm').hidden = false;
    $('tmCoaKode').focus();
  }

  function isiFormJurnal(i) {
    var a = dataAkuntansi.jurnal[i];
    if (!a) return;
    $('tmJurnalIndex').value = i;
    $('tmJurnalTanggal').value = a.tanggal || '';
    $('tmJurnalBukti').value = a.no_bukti || '';
    $('tmJurnalKeterangan').value = a.keterangan || '';
    $('tmJurnalDebit').value = a.debit || 0;
    $('tmJurnalKredit').value = a.kredit || 0;
    $('tmJurnalForm').hidden = false;
    $('tmJurnalTanggal').focus();
  }

  function isiFormKas(i) {
    var a = dataAkuntansi.kas[i];
    if (!a) return;
    $('tmKasIndex').value = i;
    $('tmKasTanggal').value = a.tanggal || '';
    $('tmKasJenis').value = a.jenis || 'masuk';
    $('tmKasJumlah').value = a.jumlah || 0;
    $('tmKasKeterangan').value = a.keterangan || '';
    $('tmKasForm').hidden = false;
    $('tmKasTanggal').focus();
  }

  function simpanAkuntansi(ev, jenis) {
    ev.preventDefault();
    var form = ev.currentTarget;
    if (!form.reportValidity()) return;
    var i = Number($(jenis === 'coa' ? 'tmCoaIndex' : jenis === 'jurnal' ? 'tmJurnalIndex' : 'tmKasIndex').value);
    var salinan = {
      coa: dataAkuntansi.coa.map(function (x) { return Object.assign({}, x); }),
      jurnal: dataAkuntansi.jurnal.map(function (x) { return Object.assign({}, x); }),
      kas: dataAkuntansi.kas.map(function (x) { return Object.assign({}, x); }),
    };
    if (!Number.isInteger(i) || i < 0 || !salinan[jenis][i]) return;
    if (jenis === 'coa') {
      salinan.coa[i] = Object.assign(salinan.coa[i], {
        kode: $('tmCoaKode').value.trim(),
        nama: $('tmCoaNama').value.trim(),
        jenis: $('tmCoaJenis').value,
        saldo: Number($('tmCoaSaldo').value),
        status: $('tmCoaStatus').value,
        induk: $('tmCoaInduk').value.trim() || null,
      });
    } else if (jenis === 'jurnal') {
      salinan.jurnal[i] = Object.assign(salinan.jurnal[i], {
        tanggal: $('tmJurnalTanggal').value,
        no_bukti: $('tmJurnalBukti').value.trim(),
        keterangan: $('tmJurnalKeterangan').value.trim(),
        debit: Number($('tmJurnalDebit').value),
        kredit: Number($('tmJurnalKredit').value),
      });
    } else {
      salinan.kas[i] = Object.assign(salinan.kas[i], {
        tanggal: $('tmKasTanggal').value,
        jenis: $('tmKasJenis').value,
        jumlah: Number($('tmKasJumlah').value),
        keterangan: $('tmKasKeterangan').value.trim(),
      });
    }
    intaan('PUT', '/api/akuntansi', salinan).then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      dataAkuntansi = h.data;
      tutupFormAkuntansi(form);
      renderAkuntansi();
      pesanAkuntansi('Perubahan akuntansi berhasil disimpan dan dicatat di audit log.');
    }).catch(function (e) {
      pesanAkuntansi('Perubahan gagal disimpan: ' + e.message, true);
    });
  }

  function hapusAkuntansi(jenis, i) {
    var item = (dataAkuntansi[jenis] || [])[i];
    if (!item) return;
    var label = jenis === 'coa' ? item.kode + ' — ' + item.nama
      : jenis === 'jurnal' ? (item.no_bukti || item.keterangan)
      : item.keterangan;
    if (!window.confirm('Hapus permanen catatan ini?\\n\\n' + label + '\\n\\nTindakan ini dicatat di audit log.')) return;
    var salinan = {
      coa: dataAkuntansi.coa.map(function (x) { return Object.assign({}, x); }),
      jurnal: dataAkuntansi.jurnal.map(function (x) { return Object.assign({}, x); }),
      kas: dataAkuntansi.kas.map(function (x) { return Object.assign({}, x); }),
    };
    salinan[jenis].splice(i, 1);
    intaan('PUT', '/api/akuntansi', salinan).then(function (h) {
      if (!h.ok) throw new Error(h.data.galat || ('HTTP ' + h.status));
      dataAkuntansi = h.data;
      tutupFormAkuntansi($('tmCoaForm'));
      tutupFormAkuntansi($('tmJurnalForm'));
      tutupFormAkuntansi($('tmKasForm'));
      renderAkuntansi();
      pesanAkuntansi('Catatan berhasil dihapus dan dicatat di audit log.');
    }).catch(function (e) {
      pesanAkuntansi('Catatan tidak dapat dihapus: ' + e.message, true);
    });
  }

  function pasangFormAkuntansi() {
    var pasangAksi = function (id, isi) {
      var tbody = $(id);
      if (!tbody) return;
      tbody.addEventListener('click', function (ev) {
        var hapus = ev.target.closest ? ev.target.closest('[data-akuntansi-hapus]') : null;
        var tombol = ev.target.closest ? ev.target.closest('[data-akuntansi-edit]') : null;
        var target = hapus || tombol;
        if (!target) return;
        var i = Number(target.getAttribute('data-index'));
        if (!Number.isInteger(i) || i < 0) return;
        if (hapus) hapusAkuntansi(hapus.getAttribute('data-akuntansi-hapus'), i);
        else isi(i);
      });
    };
    pasangAksi('tmCoaBody', isiFormCoa);
    pasangAksi('tmJurnalBody', isiFormJurnal);
    pasangAksi('tmKasBody', isiFormKas);
    [['tmCoaForm','coa'],['tmJurnalForm','jurnal'],['tmKasForm','kas']].forEach(function (x) {
      var form = $(x[0]);
      if (form) form.addEventListener('submit', function (ev) { simpanAkuntansi(ev, x[1]); });
    });
    [['tmCoaBatal','tmCoaForm'],['tmJurnalBatal','tmJurnalForm'],['tmKasBatal','tmKasForm']].forEach(function (x) {
      var tombol = $(x[0]);
      if (tombol) tombol.addEventListener('click', function () { tutupFormAkuntansi($(x[1])); });
    });
  }

  function renderAkuntansi() {
    var d = dataAkuntansi;
    isiTabel('tmCoaBody', (d.coa || []).map(function (a, i) {
      var aksi = '<div class="tm-aksi"><button type="button" class="tombol-mini" data-akuntansi-edit="coa" data-index="' + i + '">Edit</button><button type="button" class="tombol-mini tm-bahaya" data-akuntansi-hapus="coa" data-index="' + i + '">Hapus</button></div>';
      return barisTabel([
        sel(esc(a.kode)),
        sel(esc(a.nama)),
        sel(esc(a.jenis)),
        sel(esc(rupiah(a.saldo)), 'tm-tabel-nominal'),
        sel(a.status === 'aktif' ? lencana('Aktif', 'ok') : lencana('Nonaktif', 'mati')),
        sel(aksi),
      ]);
    }), 6, 'Belum ada akun COA.');
    isiTabel('tmJurnalBody', (d.jurnal || []).map(function (j, i) {
      var aksi = '<div class="tm-aksi"><button type="button" class="tombol-mini" data-akuntansi-edit="jurnal" data-index="' + i + '">Edit</button><button type="button" class="tombol-mini tm-bahaya" data-akuntansi-hapus="jurnal" data-index="' + i + '">Hapus</button></div>';
      return barisTabel([
        sel(esc(j.tanggal)),
        sel(esc(j.no_bukti || '—')),
        sel(esc(j.keterangan || '')),
        sel(esc(rupiah(j.debit)), 'tm-tabel-nominal'),
        sel(esc(rupiah(j.kredit)), 'tm-tabel-nominal'),
        sel(aksi),
      ]);
    }), 6, 'Belum ada jurnal.');
    isiTabel('tmKasBody', (d.kas || []).map(function (k, i) {
      var aksi = '<div class="tm-aksi"><button type="button" class="tombol-mini" data-akuntansi-edit="kas" data-index="' + i + '">Edit</button><button type="button" class="tombol-mini tm-bahaya" data-akuntansi-hapus="kas" data-index="' + i + '">Hapus</button></div>';
      return barisTabel([
        sel(esc(k.tanggal)),
        sel(esc(k.jenis === 'masuk' ? 'Masuk' : 'Keluar')),
        sel(esc(rupiah(k.jumlah)), 'tm-tabel-nominal'),
        sel(esc(k.keterangan || '')),
        sel(aksi),
      ]);
    }), 5, 'Belum ada transaksi kas.');
    var cat = $('tmAkuntansiCatatan');
    if (cat) {
      cat.textContent = (d.coa || []).length + ' akun COA · ' + (d.jurnal || []).length
        + ' jurnal · ' + (d.kas || []).length + ' transaksi kas · hanya admin dapat mengedit/menghapus; akun COA yang masih dirujuk tidak dapat dihapus.';
    }
  }

  function muatTabAkuntansi() {
    intaan('GET', '/api/akuntansi').then(function (h) {
      if (!h.ok) {
        isiTabel('tmCoaBody', [], 6, 'Gagal memuat (HTTP ' + h.status + ').');
        isiTabel('tmJurnalBody', [], 6, 'Gagal memuat.');
        isiTabel('tmKasBody', [], 5, 'Gagal memuat.');
        return;
      }
      dataAkuntansi = h.data;
      renderAkuntansi();
    }).catch(function (e) {
      pesanAkuntansi('Akuntansi gagal dimuat: ' + e.message, true);
    });
  }

  TAB_PEMUAT = {
    pengguna: muatTabPengguna,
    pembayaran: muatTabPembayaran,
    akuntansi: muatTabAkuntansi,
  };

  /* ---------- mulai: tunggu sesi dari pengguna.js ---------- */

  function mulai(izin) {
    if (siap) return;
    siap = true;
    pasangTombolPengaturan();
    pasangFormMetode();
    pasangFormAkuntansi();
    pasangTab();
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
