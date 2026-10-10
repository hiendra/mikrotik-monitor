/* ============================================================
   pengguna.js - "Akun Saya" + "Kelola Pengguna" dasbor warga
   Dimuat sebagai berkas terpisah karena CSP situs ini
   `script-src 'self'` (skrip inline diblokir).

   Sumber kebenaran izin ada di SERVER (zima-hosting/auth/).
   JS ini hanya menampilkan apa yang boleh dilakukan pengguna
   yang sedang masuk (/api/saya mengirim daftar izin); setiap
   permintaan tetap diperiksa ulang server, jadi membuka tombol
   lewat alat pengembang tidak memberi kuasa apa pun.

   Semua permintaan pengubah membawa header X-Diminta-Dengan:
   dasbor - penangkal CSRF di API (formulir lintas situs tidak
   bisa menambah header khusus).

   Tanpa sesi, modul ini hanya memasang tautan "Masuk" di
   topbar; tampilan dasbor tetap peran Warga seperti semula.
   ============================================================ */

(function () {
  'use strict';

  var KEPALA = { 'Content-Type': 'application/json', 'X-Diminta-Dengan': 'dasbor' };
  var LABEL = { warga: 'Warga', pengurus: 'Pengurus', admin: 'Admin' };

  var saya = null;      // penggunaAman dari /api/saya
  var izin = {};        // himpunan izin peran aktif
  var bolehAtur = [];   // peran yang boleh diatur (dari /api/pengguna)
  var daftar = [];      // cache daftar pengguna untuk modal edit

  /* ---------- util ---------- */

  function $(id) { return document.getElementById(id); }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
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

  function tanggal(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })
      + ' ' + d.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' });
  }

  function punya(namaIzin) { return !!izin[namaIzin]; }

  function pesan(id, teks, jenis) {
    var el = $(id);
    if (!el) return;
    if (!teks) { el.hidden = true; el.textContent = ''; return; }
    el.textContent = teks;
    el.className = 'status-baris ' + (jenis === 'galat' ? 'status-galat' : 'status-ok');
    el.hidden = false;
  }

  function modalBuka(el) { if (el) el.hidden = false; }
  function modalTutup(el) { if (el) el.hidden = true; }

  /* ---------- 1. SESI: /api/saya ---------- */

  function pasangTautanMasuk() {
    var wadah = $('tmAreaSesi');
    if (!wadah) return;
    var a = document.createElement('a');
    a.href = '/masuk';
    a.className = 'tombol-mini';
    a.style.textDecoration = 'none';
    a.textContent = 'Masuk';
    wadah.innerHTML = '';
    wadah.appendChild(a);
  }

  function pasangTombolKeluar() {
    var wadah = $('tmAreaSesi');
    if (!wadah) return;
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'tombol-mini';
    b.textContent = 'Keluar';
    b.addEventListener('click', function () {
      intaan('POST', '/api/keluar').then(function () { window.location.assign('/'); });
    });
    wadah.innerHTML = '';
    wadah.appendChild(b);
  }

  function muatSesi() {
    if (!window.fetch) return Promise.resolve(false);
    return fetch('/api/saya', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) return null;
        return r.json().catch(function () { return null; });
      })
      .then(function (d) {
        if (!d || !d.pengguna) { pasangTautanMasuk(); umumkanSesi(null); return false; }
        saya = d.pengguna;
        izin = {};
        (d.izin || []).forEach(function (i) { izin[i] = true; });
        terapkanSesi();
        return true;
      })
      .catch(function () { pasangTautanMasuk(); umumkanSesi(null); return false; });
  }

  // Bagian Pengaturan Sistem (pengaturan.js) menunggu peristiwa ini -
  // tanpa sesi admin, modul itu tidak memuat apa pun.
  function umumkanSesi(detail) {
    document.dispatchEvent(new CustomEvent('tm-sesi', { detail: detail }));
  }

  function terapkanSesi() {
    if (!saya) return;

    // Identitas topbar dari akun nyata (menggantikan teks contoh).
    var inisial = (saya.nama || saya.pengguna || '?').trim().split(/\s+/)
      .map(function (k) { return k.charAt(0); }).join('').slice(0, 2).toUpperCase() || 'TM';
    var avatar = $('avatar');
    var nama = $('namaPengguna');
    var sub = $('subPengguna');
    var badge = $('peranBadge');
    if (avatar) avatar.textContent = inisial;
    if (nama) nama.textContent = saya.nama || saya.pengguna;
    if (badge) badge.textContent = LABEL[saya.peran] || saya.peran;
    if (sub) {
      sub.textContent = (saya.jabatan ? saya.jabatan + ' · ' : '')
        + (saya.blok ? 'Blok ' + saya.blok : 'Taman Marina');
    }

    // Peran NYATA dari sesi mengambil alih <body data-peran>, sehingga
    // menu & bagian mengikuti hak akses sungguhan. Sakelar peran demo di
    // sidebar disembunyikan (lihat dasbor.js) bila fungsi itu tersedia.
    if (window.__tmSediakanSakelarPeran) window.__tmSediakanSakelarPeran(false);
    document.body.setAttribute('data-peran', saya.peran);

    pasangTombolKeluar();
    renderAkun();

    // Bagian Kelola Pengguna hanya untuk pengurus/admin; audit hanya admin.
    var bolehLihat = punya('pengguna.lihat');
    var seksiPengguna = $('pengguna');
    if (seksiPengguna) seksiPengguna.hidden = !bolehLihat;
    var wadahAudit = $('audit');
    if (wadahAudit) wadahAudit.hidden = !punya('audit.lihat');
    if (bolehLihat) muatPengguna();
    if (punya('audit.lihat')) muatAudit();

    // Akun dengan sandi awal dipaksa ke bagian ganti sandi.
    if (saya.harus_ganti_sandi && $('akun')) {
      pesan('akunPesan', 'Sandi Anda masih sandi awal dari pengurus. Segera ganti di bawah.', 'galat');
      window.setTimeout(function () {
        var akun = $('akun');
        if (akun && akun.scrollIntoView) akun.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 350);
    }

    umumkanSesi({ pengguna: saya, izin: izin });
  }

  /* ---------- 2. AKUN SAYA ---------- */

  function renderAkun() {
    var wadah = $('tmProfilSaya');
    if (!wadah || !saya) return;
    wadah.innerHTML = [
      ['Nama pengguna', saya.pengguna],
      ['Peran', LABEL[saya.peran] || saya.peran],
      ['Jabatan', saya.jabatan || '—'],
      ['Blok / RT / RW', [saya.blok, saya.rt ? 'RT ' + saya.rt : '', saya.rw ? 'RW ' + saya.rw : ''].filter(Boolean).join(' / ') || '—'],
      ['No. WhatsApp', saya.no_hp || '—'],
      ['Terakhir masuk', tanggal(saya.terakhir_masuk)],
    ].map(function (b) {
      return '<div class="tm-baris-profil"><span>' + esc(b[0]) + '</span><b>' + esc(b[1]) + '</b></div>';
    }).join('');
  }

  function pasangFormSandi() {
    var f = $('tmFormSandi');
    if (!f) return;
    f.addEventListener('submit', function (ev) {
      ev.preventDefault();
      pesan('akunPesan', '');
      var lama = $('tmSandiLama').value;
      var baru = $('tmSandiBaru').value;
      var ulang = $('tmSandiUlang').value;
      if (baru.length < 8) { pesan('akunPesan', 'Sandi baru minimal 8 karakter.', 'galat'); return; }
      if (baru !== ulang) { pesan('akunPesan', 'Sandi baru dan ulanginya tidak sama.', 'galat'); return; }
      intaan('POST', '/api/sandi', { sandi_lama: lama, sandi_baru: baru }).then(function (h) {
        if (!h.ok) { pesan('akunPesan', h.data.galat || 'Gagal mengganti sandi.', 'galat'); return; }
        f.reset();
        pesan('akunPesan', 'Sandi berhasil diganti. Perangkat lain otomatis dikeluarkan.');
        saya.harus_ganti_sandi = false;
      });
    });
  }

  /* ---------- 3. DAFTAR PENGGUNA ---------- */

  function tombolAksi(u) {
    var t = [];
    var bolehKelola = bolehAtur.indexOf(u.peran) !== -1;
    if (bolehKelola) t.push('<button type="button" class="tombol-mini" data-aksi="ubah" data-id="' + esc(u.id) + '">Ubah</button>');
    if (bolehKelola && u.id !== saya.id) t.push('<button type="button" class="tombol-mini" data-aksi="sandi" data-id="' + esc(u.id) + '">Reset Sandi</button>');
    if (punya('pengguna.hapus') && u.id !== saya.id) t.push('<button type="button" class="tombol-mini tm-bahaya" data-aksi="hapus" data-id="' + esc(u.id) + '">Hapus</button>');
    return t.join(' ');
  }

  function renderPengguna() {
    var tbody = $('tmTabelPengguna');
    if (!tbody) return;
    if (!daftar.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="catatan-kecil">Belum ada pengguna terdaftar.</td></tr>';
      return;
    }
    tbody.innerHTML = daftar.map(function (u) {
      var status = u.aktif
        ? '<span class="lencana hijau">Aktif</span>'
        : '<span class="lencana merah">Nonaktif</span>';
      var sandi = u.harus_ganti_sandi
        ? ' <span class="lencana kuning" title="Masih sandi awal, wajib diganti">sandi awal</span>'
        : '';
      return '<tr id="tm-akun-' + esc(u.id) + '" data-tm-akun-id="' + esc(u.id) + '" tabindex="-1">'
        + '<td><b>' + esc(u.pengguna) + '</b>' + sandi + '</td>'
        + '<td>' + esc(u.nama || '—') + '</td>'
        + '<td>' + esc(LABEL[u.peran] || u.peran) + '</td>'
        + '<td>' + esc(u.blok ? 'Blok ' + u.blok : '—') + '</td>'
        + '<td>' + status + '</td>'
        + '<td>' + tanggal(u.terakhir_masuk) + '</td>'
        + '<td class="tm-aksi">' + tombolAksi(u) + '</td>'
        + '</tr>';
    }).join('');
  }

  function muatPengguna() {
    return intaan('GET', '/api/pengguna').then(function (h) {
      if (!h.ok) {
        if (h.status === 401) { pasangTautanMasuk(); return; }
        pesan('penggunaPesan', h.data.galat || 'Gagal memuat daftar pengguna.', 'galat');
        return;
      }
      daftar = h.data.pengguna || [];
      bolehAtur = h.data.bolehAtur || [];
      if (h.data.label) LABEL.warga = h.data.label.warga || LABEL.warga;
      renderPengguna();
    });
  }

  /* ---------- 4. DIALOG SANDI AWAL (tampil sekali) ---------- */

  function dialogSandiBaru(pengguna, sandi) {
    var lama = $('tmModalSandi');
    if (!lama) return;
    $('tmSandiUntuk').textContent = pengguna;
    var kotak = $('tmNilaiSandi');
    kotak.textContent = sandi;
    var tombolSalin = $('tmSalinSandi');
    tombolSalin.onclick = function () {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(sandi).then(function () {
          tombolSalin.textContent = 'Tersalin ✓';
        }).catch(function () { /* biarkan pengguna menyalin manual */ });
      }
    };
    tombolSalin.textContent = 'Salin';
    modalBuka(lama);
  }

  /* ---------- 5. MODAL BUAT / UBAH ---------- */

  function opsiPeran(dipilih) {
    var daftarPeran = bolehAtur.slice();
    if (!daftarPeran.length) daftarPeran = ['warga'];
    return daftarPeran.map(function (p) {
      return '<option value="' + esc(p) + '"' + (p === dipilih ? ' selected' : '') + '>' + esc(LABEL[p] || p) + '</option>';
    }).join('');
  }

  function bukaModalBuat() {
    pesan('tmFormBuatPesan', '');
    var f = $('tmFormBuat');
    f.reset();
    var pilih = $('tmBuatPeran');
    pilih.innerHTML = opsiPeran(bolehAtur[0] || 'warga');
    pilih.disabled = bolehAtur.length <= 1;
    var ket = $('tmBuatPeranKet');
    ket.textContent = bolehAtur.length <= 1
      ? 'Anda hanya bisa membuat akun ' + (LABEL[bolehAtur[0]] || 'warga') + '.'
      : 'Warga: kebutuhan pribadi. Pengurus: kelola RT/RW. Admin: sistem & keamanan.';
    modalBuka($('tmModalBuat'));
    var el = $('tmBuatPengguna');
    if (el) el.focus();
  }

  function cariDiDaftar(id) {
    for (var i = 0; i < daftar.length; i += 1) if (daftar[i].id === id) return daftar[i];
    return null;
  }

  function bukaModalUbah(u) {
    pesan('tmFormUbahPesan', '');
    $('tmUbahId').value = u.id;
    $('tmModalUbahJudul').textContent = 'Ubah Akun — ' + (u.nama || u.pengguna);
    $('tmUbahPengguna').value = u.pengguna;
    $('tmUbahNama').value = u.nama || '';
    $('tmUbahJabatan').value = u.jabatan || '';
    $('tmUbahBlok').value = u.blok || '';
    $('tmUbahRt').value = u.rt || '';
    $('tmUbahRw').value = u.rw || '';
    $('tmUbahHp').value = u.no_hp || '';
    $('tmUbahAktif').checked = !!u.aktif;

    var wadahPeran = $('tmUbahWadahPeran');
    var pilih = $('tmUbahPeran');
    // Ubah peran hanya admin; dan hanya ke peran yang boleh diatur.
    var bolehUbahPeran = punya('peran.ubah') && bolehAtur.length > 1;
    wadahPeran.hidden = !bolehUbahPeran;
    if (bolehUbahPeran) {
      pilih.innerHTML = opsiPeran(u.peran);
    }
    modalBuka($('tmModalUbah'));
  }

  function pasangModal() {
    var fBuat = $('tmFormBuat');
    if (fBuat) {
      fBuat.addEventListener('submit', function (ev) {
        ev.preventDefault();
        pesan('tmFormBuatPesan', '');
        var isi = {
          pengguna: $('tmBuatPengguna').value.trim(),
          nama: $('tmBuatNama').value.trim(),
          peran: $('tmBuatPeran').value,
          jabatan: $('tmBuatJabatan').value.trim(),
          blok: $('tmBuatBlok').value.trim(),
          rt: $('tmBuatRt').value.trim(),
          rw: $('tmBuatRw').value.trim(),
          no_hp: $('tmBuatHp').value.trim(),
        };
        var sandiTulis = $('tmBuatSandi').value;
        if (sandiTulis) isi.sandi = sandiTulis;
        if (isi.sandi && isi.sandi.length < 8) {
          pesan('tmFormBuatPesan', 'Sandi minimal 8 karakter; kosongkan bila ingin sandi acak otomatis.', 'galat');
          return;
        }
        intaan('POST', '/api/pengguna', isi).then(function (h) {
          if (!h.ok) { pesan('tmFormBuatPesan', h.data.galat || 'Gagal membuat akun.', 'galat'); return; }
          modalTutup($('tmModalBuat'));
          fBuat.reset();
          var u = h.data.pengguna || {};
          dialogSandiBaru(u.pengguna || isi.pengguna, h.data.sandi_awal || sandiTulis);
          muatPengguna();
        });
      });
    }

    var fUbah = $('tmFormUbah');
    if (fUbah) {
      fUbah.addEventListener('submit', function (ev) {
        ev.preventDefault();
        pesan('tmFormUbahPesan', '');
        var id = $('tmUbahId').value;
        var isi = {
          nama: $('tmUbahNama').value.trim(),
          jabatan: $('tmUbahJabatan').value.trim(),
          blok: $('tmUbahBlok').value.trim(),
          rt: $('tmUbahRt').value.trim(),
          rw: $('tmUbahRw').value.trim(),
          no_hp: $('tmUbahHp').value.trim(),
          aktif: $('tmUbahAktif').checked,
        };
        var wadahPeran = $('tmUbahWadahPeran');
        if (wadahPeran && !wadahPeran.hidden) isi.peran = $('tmUbahPeran').value;
        intaan('PATCH', '/api/pengguna/' + encodeURIComponent(id), isi).then(function (h) {
          if (!h.ok) { pesan('tmFormUbahPesan', h.data.galat || 'Gagal mengubah akun.', 'galat'); return; }
          modalTutup($('tmModalUbah'));
          pesan('penggunaPesan', 'Akun berhasil diubah.');
          if (saya && id === saya.id) muatSesi();
          muatPengguna();
        });
      });
    }

    // Satu pendengar untuk semua tombol aksi di tabel (delegasi).
    var tabel = $('tmTabelPengguna');
    if (tabel) {
      tabel.addEventListener('click', function (ev) {
        var b = ev.target.closest('button[data-aksi]');
        if (!b) return;
        var u = cariDiDaftar(b.getAttribute('data-id'));
        if (!u) return;
        var aksi = b.getAttribute('data-aksi');
        if (aksi === 'ubah') bukaModalUbah(u);
        if (aksi === 'sandi') resetSandi(u);
        if (aksi === 'hapus') hapusPengguna(u);
      });
    }

    // Tutup modal: tombol ×, Batal, latar, dan tombol Escape.
    [['tmModalBuat', 'tmModalBuatTutup', 'tmBuatBatal'],
     ['tmModalUbah', 'tmModalUbahTutup', 'tmUbahBatal'],
     ['tmModalSandi', 'tmModalSandiTutup', null]].forEach(function (t) {
      var m = $(t[0]);
      if (!m) return;
      var x = $(t[1]);
      if (x) x.addEventListener('click', function () { modalTutup(m); });
      var bat = t[2] && $(t[2]);
      if (bat) bat.addEventListener('click', function () { modalTutup(m); });
      m.addEventListener('click', function (ev) { if (ev.target === m || ev.target.classList.contains('modal-backdrop')) modalTutup(m); });
    });
    document.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Escape') return;
      ['tmModalBuat', 'tmModalUbah', 'tmModalSandi'].forEach(function (id) { modalTutup($(id)); });
    });
  }

  function resetSandi(u) {
    var konfirm = 'Reset sandi akun "' + (u.nama || u.pengguna) + '"?\n\n'
      + 'Sandi acak baru akan dibuat dan ditampilkan SEKALI. Sesi akun itu di semua perangkat otomatis keluar.';
    if (!window.confirm(konfirm)) return;
    intaan('POST', '/api/pengguna/' + encodeURIComponent(u.id) + '/sandi', {}).then(function (h) {
      if (!h.ok) { pesan('penggunaPesan', h.data.galat || 'Gagal reset sandi.', 'galat'); return; }
      dialogSandiBaru(u.pengguna, h.data.sandi_awal || '');
      muatPengguna();
    });
  }

  function hapusPengguna(u) {
    var konfirm = 'Hapus permanen akun "' + (u.nama || u.pengguna) + '" (' + (LABEL[u.peran] || u.peran) + ')?\n\n'
      + 'Tindakan ini tidak bisa dibatalkan.';
    if (!window.confirm(konfirm)) return;
    intaan('DELETE', '/api/pengguna/' + encodeURIComponent(u.id)).then(function (h) {
      if (!h.ok) { pesan('penggunaPesan', h.data.galat || 'Gagal menghapus akun.', 'galat'); return; }
      pesan('penggunaPesan', 'Akun ' + u.pengguna + ' dihapus.');
      muatPengguna();
    });
  }

  /* ---------- 6. AUDIT LOG ---------- */

  function muatAudit() {
    var wadah = $('tmAuditDaftar');
    if (!wadah) return;
    intaan('GET', '/api/audit?batas=30').then(function (h) {
      if (!h.ok) { wadah.innerHTML = '<li class="catatan-kecil">Gagal memuat audit log.</li>'; return; }
      var baris = h.data.audit || [];
      if (!baris.length) {
        wadah.innerHTML = '<li class="catatan-kecil">Belum ada aktivitas tercatat.</li>';
        return;
      }
      wadah.innerHTML = baris.map(function (a) {
        return '<li><small>' + esc(tanggal(a.waktu)) + '</small> '
          + esc(a.pelaku) + ' · ' + esc(a.aksi)
          + (a.sasaran ? ' → ' + esc(a.sasaran) : '')
          + (a.catatan ? ' <em>(' + esc(a.catatan) + ')</em>' : '') + '</li>';
      }).join('');
    });
  }

  /* ---------- mulai ---------- */

  function normalisasiNama(s) { return String(s || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase('id-ID'); }

  // Tautan dari detail warga menuju akun dummy yang cocok tepat nama + bloknya.
  document.addEventListener('click', function (ev) {
    var a = ev.target.closest && ev.target.closest('a.tm-tautan-akun');
    if (!a) return;
    var nama = normalisasiNama(a.getAttribute('data-tm-nama'));
    var blok = String(a.getAttribute('data-tm-blok') || '').trim().toLocaleLowerCase('id-ID');
    function sorotAkun() {
      var u = daftar.filter(function (x) {
        return normalisasiNama(x.nama) === nama && String(x.blok || '').trim().toLocaleLowerCase('id-ID') === blok;
      })[0];
      if (!u) {
        pesan('penggunaPesan', 'Akun dengan nama dan blok yang sama tidak ditemukan. Cocokkan data warga dengan akun dummy di Kelola Pengguna.', 'galat');
        return;
      }
      var baris = $('tm-akun-' + u.id);
      if (!baris) return;
      Array.prototype.forEach.call(document.querySelectorAll('#tmTabelPengguna tr.tm-akun-terpilih'), function (r) { r.classList.remove('tm-akun-terpilih'); });
      baris.classList.add('tm-akun-terpilih');
      baris.scrollIntoView({ behavior: 'smooth', block: 'center' });
      baris.focus({ preventScroll: true });
    }
    if (daftar.length) sorotAkun();
    else muatPengguna().then(sorotAkun);
  });

  function pasangTombolBuat() {
    var b = $('tmBtnBuat');
    if (!b) return;
    b.addEventListener('click', function () {
      if (!bolehAtur.length) {
        // Daftar belum termuat: muat dulu, lalu buka.
        muatPengguna().then(bukaModalBuat);
        return;
      }
      bukaModalBuat();
    });
  }

  muatSesi();
  pasangFormSandi();
  pasangModal();
  pasangTombolBuat();
})();
