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
        identitas di topbar, dan angka pada kartu statistik). Sekadar DEMO:
        begitu sesi nyata ditemukan (pengguna.js), sakelar disembunyikan dan
        peran diambil dari akun yang masuk - server yang memutuskan.
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

  /* Sakelar ini hanya demo saat belum ada sesi nyata. Setelah pengguna.js
     menemukan sesi, ia memanggil sediakanSakelar(false) untuk menyembunyikan
     sakelar dan menonaktifkan tombolnya - peran lalu ditentukan akun. */
  function sediakanSakelar(aktif) {
    tombolPeran.forEach(function (b) { b.disabled = !aktif; });
    var grup = document.querySelector('.sidebar .peran');
    if (grup) grup.hidden = !aktif;
  }
  window.__tmSediakanSakelarPeran = sediakanSakelar;
  window.__tmAturPeran = aturPeran;

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

  /* ---------- 8. UMKM & IKLAN WARGA ---------- */
  var umkmGrid = document.getElementById("umkmGrid");
  var umkmStatus = document.getElementById("umkmStatus");
  var btnDaftarkanUmkm = document.getElementById("btnDaftarkanUmkm");
  var modalUmkm = document.getElementById("modalUmkm");
  var modalUmkmBackdrop = document.getElementById("modalUmkmBackdrop");
  var modalUmkmClose = document.getElementById("modalUmkmClose");
  var btnUmkmBatal = document.getElementById("btnUmkmBatal");
  var formUmkm = document.getElementById("formUmkm");
  var btnTambahUmkm = document.getElementById("btnTambahUmkm");
  var umkmJudul = document.getElementById("modalUmkmJudul");
  var umkmCatatanForm = document.getElementById("umkmCatatanForm");
  var btnUmkmKirim = document.getElementById("btnUmkmKirim");
  var umkmSemua = [];      // entri terakhir dari server (prefill edit & hapus)
  var umkmAdmin = false;   // izin pengaturan.kelola -> tombol kelola admin
  var umkmMode = "ajukan"; // "ajukan" (WA) | "tambah" | "ubah" (API admin)
  var umkmEditId = null;

  function formatWa(wa) {
    if (!wa) return "";
    var w = String(wa).replace(/[^0-9]/g, "");
    if (w.startsWith("0")) w = "62" + w.substring(1);
    if (!w.startsWith("62")) w = "62" + w;
    return w;
  }
  function setNilaiForm(id, nilai) {
    var el = document.getElementById(id);
    if (el) el.value = nilai == null ? "" : String(nilai);
  }
  function setPilihan(id, nilai) {
    var el = document.getElementById(id);
    if (!el) return;
    var ada = false;
    var opsi = el.options || [];
    for (var i = 0; i < opsi.length; i++) if (opsi[i].value === nilai) { ada = true; break; }
    if (!ada && nilai && el.appendChild) {
      var op = document.createElement("option");
      op.value = String(nilai);
      op.textContent = String(nilai);
      el.appendChild(op);
    }
    el.value = nilai || "";
  }
  function bukaModalUmkm(mode, entri) {
    if (!modalUmkm) return;
    umkmMode = mode || "ajukan";
    umkmEditId = null;
    if (formUmkm) formUmkm.reset();
    var kelola = umkmMode !== "ajukan";
    if (umkmJudul) {
      umkmJudul.textContent = umkmMode === "ubah" ? "Edit UMKM & Iklan Warga"
        : (kelola ? "Tambah UMKM & Iklan Warga" : "Daftarkan Usaha Warga");
    }
    if (btnUmkmKirim) btnUmkmKirim.textContent = kelola ? "Simpan ke Daftar" : "Kirim Pengajuan via WhatsApp";
    if (umkmCatatanForm) {
      umkmCatatanForm.textContent = kelola
        ? "Data langsung tersimpan di server dan tampil di daftar UMKM; perubahan tercatat di audit log."
        : "Pengajuan akan dikirim via WhatsApp ke pengurus UMKM untuk diverifikasi. Setelah disetujui, data akan masuk ke daftar.";
    }
    if (umkmMode === "ubah" && entri) {
      umkmEditId = String(entri.id);
      setNilaiForm("umkmNama", entri.nama);
      setNilaiForm("umkmPemilik", entri.pemilik);
      setPilihan("umkmKategori", entri.kategori);
      setPilihan("umkmBlok", entri.blok);
      setNilaiForm("umkmWA", entri.whatsapp);
      setNilaiForm("umkmDesk", entri.deskripsi);
      setNilaiForm("umkmIcon", entri.icon);
    }
    modalUmkm.hidden = false;
    var namaEl = document.getElementById("umkmNama");
    if (namaEl) namaEl.focus();
  }
  function tutupModalUmkm() {
    if (!modalUmkm) return;
    modalUmkm.hidden = true;
  }
  function renderUmkm(list) {
    if (!umkmGrid) return;
    var data = Array.isArray(list) ? list : [];
    data = data.filter(function (x) { return x && x.aktif !== false; });
    if (data.length === 0) {
      umkmGrid.innerHTML = "<p class=\"catatan-kecil\">Belum ada UMKM terdaftar.</p>";
      return;
    }
    umkmGrid.innerHTML = data.map(function (u) {
      var icon = u.icon || "🏪";
      var blok = u.blok ? (" · Blok " + u.blok) : "";
      // Kategori sudah tercetak di baris small di atas; jangan digandakan
      // di deskripsi (bug lama: kategori muncul dua kali).
      var desc = u.deskripsi || "";
      var wa = formatWa(u.whatsapp);
      var linkWa = wa ? ("https://wa.me/" + wa) : "#";
      var target = wa ? " target=\"_blank\" rel=\"noopener\"" : "";
      var btn = wa ? "<a class=\"tombol-mini\" style=\"margin-top:8px;width:fit-content;text-decoration:none\" href=\"" + linkWa + "\"" + target + ">Hubungi via WA</a>" : "";
      var aksi = "";
      if (umkmAdmin) {
        aksi = "<span class=\"umkm-aksi\">" +
          "<button type=\"button\" class=\"tombol-mini\" data-umkm-act=\"ubah\" data-umkm-id=\"" + escWarga(u.id) + "\">✏️ Edit</button>" +
          "<button type=\"button\" class=\"tombol-mini\" data-umkm-act=\"hapus\" data-umkm-id=\"" + escWarga(u.id) + "\">🗑️ Hapus</button>" +
          "</span>";
      }
      return "<article class=\"umkm\"><span aria-hidden=\"true\">" + icon + "</span><b>" + (u.nama || "-") + "</b><small>" + (u.kategori || "") + blok + "</small>" + (desc ? "<small style=\"color:var(--muted)\">" + desc + "</small>" : "") + btn + aksi + "</article>";
    }).join("");
  }
  function muatUmkm() {
    if (!umkmGrid || !window.fetch) return Promise.resolve(false);
    if (umkmStatus) {
      umkmStatus.hidden = false;
      umkmStatus.textContent = "Memuat UMKM...";
    }
    // Sumber utama: API backend (real-time, boleh diedit admin).
    return fetch("/api/umkm", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (j) {
        umkmSemua = Array.isArray(j.umkm) ? j.umkm : [];
        renderUmkm(umkmSemua);
        if (umkmStatus) umkmStatus.hidden = true;
        return true;
      })
      .catch(function () {
        // Backend lama / belum terjangkau -> umkm.json statis.
        return fetch("umkm.json", { cache: "no-store" })
          .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
          })
          .then(function (json) {
            umkmSemua = (json && (json.umkm || json.data)) ? (json.umkm || json.data) : [];
            renderUmkm(umkmSemua);
            if (umkmStatus) umkmStatus.hidden = true;
            return true;
          })
          .catch(function () {
            if (umkmStatus) {
              umkmStatus.hidden = false;
              umkmStatus.textContent = "Gagal memuat daftar UMKM.";
            }
            renderUmkm([
              { nama: "Warung Bu Siti", kategori: "Makanan & Minuman", blok: "Q5", icon: "🍜", aktif: true },
              { nama: "Laundry Marina", kategori: "Cuci & Setrika", blok: "Q2", icon: "👕", aktif: true },
              { nama: "Servis AC Pak Andi", kategori: "Teknisi Pendingin", blok: "Q9", icon: "🔧", aktif: true },
              { nama: "Sayur Segar Warga", kategori: "Belanja Harian", blok: "Q1", icon: "🥦", aktif: true }
            ]);
            return false;
          });
      });
  }

  // --- Kelola UMKM (admin) ---
  function umkmKirim(url, metode, isi) {
    return fetch(url, {
      method: metode,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-Diminta-Dengan": "dasbor" },
      body: isi === undefined ? undefined : JSON.stringify(isi)
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.galat || ("HTTP " + r.status));
        return j;
      });
    });
  }
  function simpanUmkmKelola(isi) {
    var ubah = umkmMode === "ubah";
    var url = "/api/umkm" + (ubah ? "/" + encodeURIComponent(umkmEditId) : "");
    if (umkmStatus) { umkmStatus.hidden = false; umkmStatus.textContent = "Menyimpan..."; }
    umkmKirim(url, ubah ? "PATCH" : "POST", isi)
      .then(function () {
        tutupModalUmkm();
        return muatUmkm();
      })
      .then(function () {
        // Pesan konfirmasi ditulis SETELAH muatUmkm() agar tidak tertimpa
        // teks "Memuat UMKM..." saat daftar dimuat ulang.
        if (umkmStatus) {
          umkmStatus.hidden = false;
          umkmStatus.textContent = "UMKM \"" + isi.nama + "\" " + (ubah ? "diperbarui" : "ditambahkan") + ".";
        }
      })
      .catch(function (e) {
        if (umkmStatus) { umkmStatus.hidden = false; umkmStatus.textContent = "Gagal menyimpan: " + (e.message || ""); }
      });
  }
  function hapusUmkm(entri) {
    var yakin = window.confirm && window.confirm("Hapus UMKM \"" + (entri.nama || "") + "\" dari daftar? Tindakan ini tercatat di audit log.");
    if (!yakin) return;
    if (umkmStatus) { umkmStatus.hidden = false; umkmStatus.textContent = "Menghapus..."; }
    umkmKirim("/api/umkm/" + encodeURIComponent(String(entri.id)), "DELETE")
      .then(function () { return muatUmkm(); })
      .then(function () {
        // Lihat catatan di simpanUmkmKelola: pesan setelah reload.
        if (umkmStatus) { umkmStatus.hidden = false; umkmStatus.textContent = "UMKM \"" + entri.nama + "\" dihapus."; }
      })
      .catch(function (e) {
        if (umkmStatus) { umkmStatus.hidden = false; umkmStatus.textContent = "Gagal menghapus: " + (e.message || ""); }
      });
  }
  // Tombol kelola hanya untuk admin (izin pengaturan.kelola); warga & pengurus
  // tetap melihat daftar + pengajuan via WhatsApp seperti semula.
  document.addEventListener("tm-sesi", function (ev) {
    var izin = ev.detail && ev.detail.izin;
    umkmAdmin = !!(izin && izin["pengaturan.kelola"]);
    if (btnTambahUmkm) btnTambahUmkm.hidden = !umkmAdmin;
    if (btnDaftarkanUmkm) btnDaftarkanUmkm.hidden = umkmAdmin; // admin memakai + Tambah
    renderUmkm(umkmSemua);
  });

  if (btnDaftarkanUmkm) btnDaftarkanUmkm.addEventListener("click", function () { bukaModalUmkm("ajukan"); });
  if (btnTambahUmkm) btnTambahUmkm.addEventListener("click", function () { bukaModalUmkm("tambah"); });
  if (umkmGrid) umkmGrid.addEventListener("click", function (ev) {
    var t = ev.target;
    var b = t && t.closest ? t.closest("button[data-umkm-act]") : null;
    if (!b) return;
    var id = b.getAttribute("data-umkm-id");
    var entri = umkmSemua.filter(function (u) { return String(u.id) === String(id); })[0];
    if (!entri) return;
    if (b.getAttribute("data-umkm-act") === "ubah") bukaModalUmkm("ubah", entri);
    else hapusUmkm(entri);
  });
  if (modalUmkmClose) modalUmkmClose.addEventListener("click", tutupModalUmkm);
  if (btnUmkmBatal) btnUmkmBatal.addEventListener("click", tutupModalUmkm);
  if (modalUmkmBackdrop) modalUmkmBackdrop.addEventListener("click", tutupModalUmkm);
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") tutupModalUmkm(); });
  if (formUmkm) {
    formUmkm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var nama = document.getElementById("umkmNama").value.trim();
      var pemilik = document.getElementById("umkmPemilik").value.trim();
      var kategori = document.getElementById("umkmKategori").value;
      var blok = document.getElementById("umkmBlok").value;
      var wa = formatWa(document.getElementById("umkmWA").value);
      var desk = document.getElementById("umkmDesk").value.trim();
      var icon = document.getElementById("umkmIcon").value.trim() || "🏪";
      if (umkmMode === "tambah" || umkmMode === "ubah") {
        // Mode kelola (admin): simpan langsung ke backend, bukan via WhatsApp.
        simpanUmkmKelola({
          nama: nama, pemilik: pemilik, kategori: kategori, blok: blok,
          whatsapp: wa, deskripsi: desk, icon: icon
        });
        return;
      }
      var pesan = "*PENGAJUAN UMKM TAMAN MARINA*\n\nNama Usaha: " + nama + "\nPemilik: " + pemilik + "\nKategori: " + kategori + "\nBlok: " + blok + "\nNo WA: " + wa + "\nDeskripsi: " + desk + "\n\n_Mohon verifikasi & masukkan ke daftar UMKM._";
      window.open("https://wa.me/?text=" + encodeURIComponent(pesan), "_blank", "noopener");
      tutupModalUmkm();
      if (umkmStatus) {
        umkmStatus.hidden = false;
        umkmStatus.textContent = "Pengajuan dibuka di WhatsApp. Silakan kirim untuk diverifikasi pengurus.";
      }
    });
  }
  muatUmkm();

  /* ---------- 9. DATA WARGA: HIERARKI + STATUS PEMBAYARAN ---------- */
  var tmBlokGrid = document.getElementById("tmBlokGrid");
  var tmWargaBody = document.getElementById("tmWargaBody");
  var tmWargaFilterBlok = document.getElementById("tmWargaFilterBlok");
  var tmWargaCari = document.getElementById("tmWargaCari");
  var tmWargaRingkas = document.getElementById("tmWargaRingkas");
  var tmWargaStatus = document.getElementById("tmWargaStatus");
  var tmModalWarga = document.getElementById("tmModalWarga");
  var tmWargaDetailIsi = document.getElementById("tmWargaDetailIsi");
  var tmWargaDetailJudul = document.getElementById("tmWargaDetailJudul");
  var tmWargaDetailTutup = document.getElementById("tmWargaDetailTutup");

  var wargaSemua = [];          // daftar warga dari /api/warga (volume privat)
  var pembayaranMap = {};       // warga_id -> transaksi statis (kini selalu kosong)
  var transaksiAkunWarga = [];   // status resmi dari pengajuan akun (pengurus/admin)
  var pembayaranRiwayat = {};   // warga_id -> transaksi per periode
  var periodeWargaAktif = "";
  var iuranDefaultWarga = 0;
  var wargaBlokAktif = "";      // "" = semua blok
  var wargaKataKunci = "";
  var tmWargaSegar = document.getElementById("tmWargaSegar");
  var sumberStatusWarga = "";   // "server" | "statis" — asal status tabel
  var riwayatBackendWarga = {}; // kunci nama|blok -> {periode: trx terpetakan}

  function escWarga(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function fmtRpWarga(n) {
    return (Number(n) || 0).toLocaleString("id-ID");
  }
  function fmtTglWarga(iso) {
    if (!iso) return "-";
    var b = String(iso).split("-");
    if (b.length !== 3) return iso;
    var bln = ["Jan","Feb","Mar","Apr","Mei","Jun","Jul","Agu","Sep","Okt","Nov","Des"];
    return Number(b[2]) + " " + (bln[Number(b[1]) - 1] || b[1]) + " " + b[0];
  }

  function normalWarga(s) {
    return String(s || "").trim().replace(/\s+/g, " ").toLocaleLowerCase("id-ID");
  }
  function kunciAkunWarga(nama, blok) {
    return normalWarga(nama) + "|" + normalWarga(blok);
  }
  // Periode berjalan (Asia/Jakarta) — harus sama dengan perhitungan server
  // (/api/iuran/saya) supaya pencocokan transaksi backend tidak meleset.
  // periode_aktif kini dihitung server (/api/warga) - tidak diganti manual.
  function periodeBerjalan() {
    try {
      var bagian = new Intl.DateTimeFormat("en-US", { timeZone: "Asia/Jakarta", year: "numeric", month: "2-digit" }).formatToParts(new Date());
      var tahun = bagian.find(function (x) { return x.type === "year"; }).value;
      var bulan = bagian.find(function (x) { return x.type === "month"; }).value;
      return tahun + "-" + bulan;
    } catch (e) {
      return periodeWargaAktif;
    }
  }
  // Bentuk transaksi backend menjadi struktur riwayat per periode
  function petakanTrxBackend(t) {
    return {
      periode: String(t.periode || ""),
      status: String(t.status || "belum"),
      jumlah: Number(t.jumlah) || 0,
      metode: t.metode || "-",
      tgl_bayar: String(t.diverifikasi || t.diajukan || "").slice(0, 10),
      diajukan: String(t.diajukan || ""),
      sumber: "server"
    };
  }
  // Ambil seluruh transaksi pengajuan iuran dari server. null = server tak
  // terjangkau (belum masuk / tanpa izin / jaringan) -> pakai data statis.
  function muatTransaksiBackend() {
    if (!window.fetch) return Promise.resolve(null);
    return fetch("/api/iuran/verifikasi", { credentials: "same-origin", cache: "no-store" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return (j && Array.isArray(j.transaksi)) ? j.transaksi : null; })
      .catch(function () { return null; });
  }

  // Status pembayaran -> warna lencana + label
  var LABEL_BAYAR = {
    lunas: { kelas: "hijau", label: "Lunas" },
    verifikasi: { kelas: "kuning", label: "Verifikasi" },
    menunggu: { kelas: "kuning", label: "Verifikasi" },
    proses: { kelas: "kuning", label: "Proses" },
    ditolak: { kelas: "merah", label: "Ditolak" },
    belum: { kelas: "merah", label: "Belum" }
  };
  function lencanaBayar(status) {
    var s = String(status || "belum").toLowerCase();
    var m = LABEL_BAYAR[s] || LABEL_BAYAR.belum;
    return "<span class=\"lencana " + m.kelas + "\">" + m.label + "</span>";
  }

  // Gunakan transaksi periode aktif untuk status tabel; riwayat hanya menampilkan data yang tersedia.
  function gabungWarga() {
    wargaSemua = wargaSemua.map(function (w) {
      var trx = pembayaranMap[w.id];
      var tagihanTerbaru = w.tagihan_terbaru || {};
      var tagihan = (tagihanTerbaru.periode === periodeWargaAktif && tagihanTerbaru.jumlah) || w.iuran_bulanan || iuranDefaultWarga || 0;
      var keluar = {
        id: w.id, blok: w.blok, nomor_rumah: w.nomor_rumah,
        kepala_keluarga: w.kepala_keluarga, jumlah_anggota: w.jumlah_anggota,
        iuranBulanan: w.iuran_bulanan || iuranDefaultWarga || 0,
        tagihanTerbaru: tagihanTerbaru,
        tagihan: tagihan,
        status: w.status_pembayaran || "belum",
        metode: "-", tglBayar: "", jumlahBayar: 0
      };
      if (trx) {
        if (trx.status) keluar.status = trx.status;
        keluar.metode = trx.metode || "-";
        keluar.tglBayar = trx.tgl_bayar || "";
        keluar.jumlahBayar = trx.jumlah || keluar.tagihan;
      }
      return keluar;
    });
  }

  function rumahLabel(w) {
    return (w.blok || "") + " No. " + (w.nomor_rumah || "");
  }

  function terapkanVerifikasiAkun() {
    riwayatBackendWarga = {};
    if (!transaksiAkunWarga.length || !wargaSemua.length) return;
    var berjalan = periodeBerjalan();
    // Kumpulkan riwayat per periode milik tiap akun (untuk modal detail),
    // dipetakan ke kunci nama|blok agar bisa dicocokkan dengan daftar warga.
    transaksiAkunWarga.forEach(function (t) {
      if (!t || !t.nama) return;
      var k = kunciAkunWarga(t.nama, t.blok);
      var m = petakanTrxBackend(t);
      if (!riwayatBackendWarga[k]) riwayatBackendWarga[k] = {};
      var lama = riwayatBackendWarga[k][m.periode];
      if (!lama || m.diajukan >= lama.diajukan) riwayatBackendWarga[k][m.periode] = m;
    });
    // Status tabel: transaksi periode berjalan milik warga yang cocok.
    wargaSemua.forEach(function (w) {
      var t = transaksiAkunWarga.filter(function (x) {
        return x.periode === berjalan && normalWarga(x.nama) === normalWarga(w.kepala_keluarga) && normalWarga(x.blok) === normalWarga(w.blok);
      }).sort(function (a, b) { return String(b.diajukan || "").localeCompare(String(a.diajukan || "")); })[0];
      if (!t) return;
      w.status = t.status === "menunggu" ? "verifikasi" : t.status;
      w.metode = t.metode || "-";
      w.tglBayar = String(t.diverifikasi || t.diajukan || "").slice(0, 10);
      w.jumlahBayar = Number(t.jumlah) || 0;
    });
  }

  function urutBlok(a, b) {
    var na = Number(String(a).replace(/\D/g, "")) || 0;
    var nb = Number(String(b).replace(/\D/g, "")) || 0;
    return na - nb;
  }

  function renderBlokGrid() {
    if (!tmBlokGrid) return;
    var peta = {};
    wargaSemua.forEach(function (w) {
      var b = w.blok || "-";
      if (!peta[b]) peta[b] = { total: 0, lunas: 0 };
      peta[b].total += 1;
      if (w.status === "lunas") peta[b].lunas += 1;
    });
    tmBlokGrid.innerHTML = Object.keys(peta).sort(urutBlok).map(function (b) {
      var v = peta[b];
      var utang = v.total - v.lunas;
      var aktif = wargaBlokAktif === b ? " aktif" : "";
      return "<a class=\"blok" + aktif + "\" href=\"#datawarga\" data-blok=\"" + escWarga(b) + "\">" +
        "<b>" + escWarga(b) + "</b><small>" + v.total + " rumah</small>" +
        "<span class=\"blok-hitung lunas\">" + v.lunas + " lunas</span>" +
        (utang > 0 ? "<span class=\"blok-hitung utang\">" + utang + " belum</span>" : "") +
        "</a>";
    }).join("");
  }

  function wargaTerfilter() {
    var kata = wargaKataKunci.toLowerCase();
    return wargaSemua.filter(function (w) {
      if (wargaBlokAktif && w.blok !== wargaBlokAktif) return false;
      if (!kata) return true;
      var teks = (w.kepala_keluarga + " " + w.blok + " No. " + w.nomor_rumah + " " + w.id).toLowerCase();
      return teks.indexOf(kata) !== -1;
    });
  }

  function renderTabelWarga() {
    if (!tmWargaBody) return;
    var list = wargaTerfilter();
    if (list.length === 0) {
      tmWargaBody.innerHTML = "<tr><td colspan=\"8\" class=\"catatan-kecil\">Tidak ada warga yang cocok.</td></tr>";
    } else {
      tmWargaBody.innerHTML = list.map(function (w) {
        var tagih = fmtRpWarga(w.tagihan);
        var bayar = w.jumlahBayar ? fmtRpWarga(w.jumlahBayar) : "-";
        return "<tr>" +
          "<td>" + escWarga(rumahLabel(w)) + "</td>" +
          "<td><button type=\"button\" class=\"tm-warga-nama\" data-warga-id=\"" + escWarga(w.id) + "\">" + escWarga(w.kepala_keluarga) + "</button></td>" +
          "<td>" + escWarga(w.jumlah_anggota) + "</td>" +
          "<td>" + tagih + "</td>" +
          "<td>" + lencanaBayar(w.status) + "</td>" +
          "<td>" + escWarga(w.metode) + "</td>" +
          "<td>" + fmtTglWarga(w.tglBayar) + "</td>" +
          "<td>" + bayar + "</td>" +
          "</tr>";
      }).join("");
    }
    if (tmWargaRingkas) {
      var lunas = list.filter(function (w) { return w.status === "lunas"; }).length;
      var utang = list.length - lunas;
      tmWargaRingkas.textContent = list.length + " rumah · " + lunas + " lunas · " + utang + " belum/proses · " +
        (sumberStatusWarga === "server" ? "sumber: server (real-time)" : "sumber: daftar server");
    }
  }

  function isiFilterBlok() {
    if (!tmWargaFilterBlok) return;
    var lama = tmWargaFilterBlok.value;
    var ada = [];
    wargaSemua.forEach(function (w) { if (ada.indexOf(w.blok) === -1) ada.push(w.blok); });
    tmWargaFilterBlok.innerHTML = "<option value=\"\">Semua Blok</option>" +
      ada.sort(urutBlok).map(function (b) {
        return "<option value=\"" + escWarga(b) + "\">Blok " + escWarga(b) + "</option>";
      }).join("");
    tmWargaFilterBlok.value = lama; // pertahankan pilihan lama
  }

  function muatWarga(pilihan) {
    var diam = !!(pilihan && pilihan.diam);
    if (!tmWargaBody || !window.fetch) return Promise.resolve(false);
    if (tmWargaStatus && !diam) { tmWargaStatus.hidden = false; tmWargaStatus.textContent = "Memuat data warga…"; }

    return Promise.all([
      // Daftar rumah/kk kini lewat API privat (dahulu warga.json statis yang
      // terbaca publik - audit 2026-10-09). Gagal di sini = server tak jalan.
      fetch("/api/warga", { credentials: "same-origin", cache: "no-store" }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      }),
      muatTransaksiBackend() // null = overlay status verifikasi tak terjangkau
    ]).then(function (hasil) {
      var wj = hasil[0] || {};
      wargaSemua = wj.warga || wj.data || [];
      var trxBackend = hasil[1];
      periodeWargaAktif = (wj.meta && wj.meta.periode_aktif) || "";
      iuranDefaultWarga = (wj.meta && Number(wj.meta.iuran_bulanan_default)) || 0;
      transaksiAkunWarga = trxBackend || [];
      sumberStatusWarga = trxBackend ? "server" : "";
      pembayaranMap = {};
      pembayaranRiwayat = {};

      gabungWarga();
      terapkanVerifikasiAkun();
      isiFilterBlok();
      renderBlokGrid();
      renderTabelWarga();
      if (tmWargaStatus) tmWargaStatus.hidden = true;
      return true;
    }).catch(function () {
      sumberStatusWarga = "";
      if (tmWargaStatus) {
        tmWargaStatus.hidden = false;
        tmWargaStatus.textContent = "Gagal memuat daftar warga dari server.";
      }
      if (tmWargaBody) {
        tmWargaBody.innerHTML = "<tr><td colspan=\"8\" class=\"catatan-kecil\">Data warga tidak dapat dimuat.</td></tr>";
      }
      return false;
    });
  }

  function bukaDetailWarga(w) {
    if (!tmModalWarga || !tmWargaDetailIsi || !w) return;
    // Salinan riwayat statis, lalu timpa dengan riwayat server (real-time)
    // untuk akun yang cocok — supaya modal sejalan dengan kolom status tabel.
    var riwayat = {};
    var statis = pembayaranRiwayat[w.id] || {};
    Object.keys(statis).forEach(function (p) { riwayat[p] = statis[p]; });
    var riwayatServer = riwayatBackendWarga[kunciAkunWarga(w.kepala_keluarga, w.blok)];
    if (riwayatServer) {
      Object.keys(riwayatServer).forEach(function (p) { riwayat[p] = riwayatServer[p]; });
    }
    var periodeTerbaru = w.tagihanTerbaru && w.tagihanTerbaru.periode;
    if (periodeTerbaru && !riwayat[periodeTerbaru]) riwayat[periodeTerbaru] = null;
    if (periodeWargaAktif && !riwayat[periodeWargaAktif]) riwayat[periodeWargaAktif] = null;
    var periode = Object.keys(riwayat).sort().reverse();
    var tagihanSaatIni = (w.tagihanTerbaru && periodeTerbaru === periodeWargaAktif && w.tagihanTerbaru.jumlah) || w.iuranBulanan || iuranDefaultWarga || w.tagihan || 0;
    if (tmWargaDetailJudul) tmWargaDetailJudul.textContent = "Detail Warga — " + (w.kepala_keluarga || "Tanpa nama");
    var tautanAkun = '<p><a class="tm-tautan-akun" href="#pengguna" data-tm-nama="' + escWarga(w.kepala_keluarga) + '" data-tm-blok="' + escWarga(w.blok) + '">Buka akun terkait di Kelola Pengguna</a></p>';
    var baris = periode.map(function (bln) {
      var trx = riwayat[bln];
      var iniAktif = bln === periodeWargaAktif;
      var tagih = (iniAktif && periodeTerbaru === bln && w.tagihanTerbaru.jumlah) || w.iuranBulanan || iuranDefaultWarga || 0;
      var status = trx && trx.status ? trx.status : (iniAktif ? w.status : "belum");
      var jumlah = trx && trx.jumlah ? fmtRpWarga(trx.jumlah) : "—";
      return '<tr><td>' + escWarga(bln) + (iniAktif ? ' <small>(aktif)</small>' : '') + '</td><td>Rp ' + fmtRpWarga(tagih) + '</td><td>' + lencanaBayar(status) + '</td><td>' + jumlah + '</td><td>' + escWarga(trx && trx.metode || "—") + '</td><td>' + escWarga(trx && trx.tgl_bayar ? fmtTglWarga(trx.tgl_bayar) : "—") + '</td></tr>';
    }).join("");
    var isiRiwayat = baris ? '<div class="tabel-bungkus tm-warga-riwayat"><table class="tabel"><thead><tr><th>Periode</th><th>Tagihan</th><th>Status</th><th>Dibayar</th><th>Metode</th><th>Tgl bayar</th></tr></thead><tbody>' + baris + '</tbody></table></div>' : '<p class="catatan-kecil">Belum ada data periode pembayaran.</p>';
    tmWargaDetailIsi.innerHTML = '<div class="tm-warga-detail-grid"><div><span>Rumah</span><b>' + escWarga(rumahLabel(w)) + '</b></div><div><span>Kepala keluarga</span><b>' + escWarga(w.kepala_keluarga) + '</b></div><div><span>Jumlah anggota</span><b>' + escWarga(w.jumlah_anggota || "—") + '</b></div><div><span>Tagihan periode aktif' + (periodeWargaAktif ? ' (' + escWarga(periodeWargaAktif) + ')' : '') + '</span><b>Rp ' + fmtRpWarga(tagihanSaatIni) + '</b></div></div>' + tautanAkun + '<h5>Riwayat pembayaran bulanan</h5>' + isiRiwayat + '<p class="catatan-kecil">' + (riwayatServer
      ? 'Riwayat digabung dari server (real-time) dan data lokal; periode lama yang belum tercatat tidak ditampilkan.'
      : 'Riwayat menampilkan periode yang tersedia di data pembayaran; periode lama yang belum tercatat tidak ditampilkan.') + '</p>';
    tmModalWarga.hidden = false;
    var fokus = tmWargaDetailTutup || tmModalWarga.querySelector("button, a");
    if (fokus) fokus.focus();
  }

  if (tmWargaBody) tmWargaBody.addEventListener("click", function (ev) {
    var tombol = ev.target && ev.target.closest ? ev.target.closest(".tm-warga-nama") : null;
    if (!tombol) return;
    var warga = wargaSemua.filter(function (w) { return String(w.id) === tombol.getAttribute("data-warga-id"); })[0];
    bukaDetailWarga(warga);
  });
  if (tmWargaDetailTutup) tmWargaDetailTutup.addEventListener("click", function () { tmModalWarga.hidden = true; });
  if (tmModalWarga) tmModalWarga.addEventListener("click", function (ev) { if (ev.target === tmModalWarga || (ev.target.classList && ev.target.classList.contains("modal-backdrop"))) tmModalWarga.hidden = true; });
  if (tmModalWarga) tmModalWarga.addEventListener("click", function (ev) { if (ev.target.closest && ev.target.closest(".tm-tautan-akun")) tmModalWarga.hidden = true; });
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && tmModalWarga && !tmModalWarga.hidden) tmModalWarga.hidden = true; });

  // Filter lewat dropdown blok
  if (tmWargaFilterBlok) {
    tmWargaFilterBlok.addEventListener("change", function () {
      wargaBlokAktif = tmWargaFilterBlok.value || "";
      renderBlokGrid();
      renderTabelWarga();
    });
  }

  // Pencarian KK / No. rumah (debounce 150ms)
  if (tmWargaCari) {
    var jedaCari;
    tmWargaCari.addEventListener("input", function () {
      clearTimeout(jedaCari);
      jedaCari = setTimeout(function () {
        wargaKataKunci = tmWargaCari.value.trim();
        renderTabelWarga();
      }, 150);
    });
  }

  // Klik kartu blok = toggle filter blok itu
  if (tmBlokGrid) {
    tmBlokGrid.addEventListener("click", function (ev) {
      var t = ev.target;
      var a = t && t.closest ? t.closest("a.blok") : null;
      if (!a) return;
      ev.preventDefault();
      var b = a.getAttribute("data-blok") || "";
      wargaBlokAktif = (wargaBlokAktif === b) ? "" : b; // klik lagi = lepas
      if (tmWargaFilterBlok) tmWargaFilterBlok.value = wargaBlokAktif;
      renderBlokGrid();
      renderTabelWarga();
    });
  }

  // Sesudah sesi terbit (pengurus/admin yang punya izin verifikasi), muat
  // ulang lewat satu pintu muatWarga() agar status diambil dari server tanpa
  // jalur ganda/race. Yang tanpa izin tetap memakai data statis.
  document.addEventListener("tm-sesi", function (ev) {
    var sesi = ev.detail || {};
    if (!sesi.izin || !sesi.izin["iuran.verifikasi"]) return;
    muatWarga({ diam: true });
  });

  // Tombol ↻ Segarkan — tarik status terbaru kapan pun (mis. sesudah
  // verifikasi di tab/perangkat lain).
  if (tmWargaSegar) {
    tmWargaSegar.addEventListener("click", function () {
      tmWargaSegar.disabled = true;
      muatWarga().then(function () { tmWargaSegar.disabled = false; });
    });
  }

  /* ---------- LAPORAN RT — angka riil dari backend (bukan angka contoh) ---------- */
  var tmLaporanGrid = document.getElementById("tmLaporanGrid");
  var tmLaporanBlok = document.getElementById("tmLaporanBlok");
  var tmLaporanSumber = document.getElementById("tmLaporanSumber");
  var bolehLaporan = false;

  function labelPeriode(p) {
    var bagian = String(p || "").split("-");
    if (bagian.length !== 2) return p || "";
    var bulan = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
      "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
    var i = Number(bagian[1]) - 1;
    return (bulan[i] || bagian[1]) + " " + bagian[0];
  }

  function muatLaporan(pilihan) {
    if (!tmLaporanGrid || !window.fetch) return;
    var diam = !!(pilihan && pilihan.diam);
    if (tmLaporanSumber && !diam) tmLaporanSumber.textContent = "memuat…";
    Promise.all([
      fetch("/api/jenis-iuran", { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
      fetch("/api/iuran/verifikasi", { credentials: "same-origin", cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }),
      fetch("/api/warga", { credentials: "same-origin", cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; })
    ]).then(function (h) {
      var ji = h[0], vf = h[1], wr = h[2];
      if (!ji || !vf || !wr) {
        tmLaporanGrid.innerHTML = '<div class="laporan"><small>Laporan</small><b>Gagal memuat dari server</b></div>';
        if (tmLaporanBlok) tmLaporanBlok.innerHTML = "";
        if (tmLaporanSumber) tmLaporanSumber.textContent = "server tidak terjangkau";
        return;
      }
      var periode = (wr.meta && wr.meta.periode_aktif) || "";
      var nominal = Number(ji.total) || 0;
      var rumah = (Array.isArray(wr.warga) ? wr.warga : [])
        .filter(function (w) { return String(w.status_rumah || "aktif") === "aktif"; });
      var trx = (Array.isArray(vf.transaksi) ? vf.transaksi : [])
        .filter(function (t) { return t && (!periode || t.periode === periode); });
      var jumlahDengan = function (status) {
        return trx.filter(function (t) { return t.status === status; })
          .reduce(function (n, t) { return n + (Number(t.jumlah) || 0); }, 0);
      };
      var totalTagihan = rumah.length * nominal;
      var sudahDibayar = jumlahDengan("lunas");
      var belumDibayar = Math.max(totalTagihan - sudahDibayar, 0);
      var laju = totalTagihan > 0 ? Math.round((sudahDibayar / totalTagihan) * 100) : 0;
      var sel = function (label, isi) {
        return '<div class="laporan"><small>' + escWarga(label) + "</small><b>" + isi + "</b></div>";
      };
      tmLaporanGrid.innerHTML =
        sel("Total Tagihan", "Rp " + fmtRpWarga(totalTagihan)) +
        sel("Sudah Dibayar", "Rp " + fmtRpWarga(sudahDibayar)) +
        sel("Belum Dibayar", "Rp " + fmtRpWarga(belumDibayar)) +
        sel("Collection Rate", laju + "%");
      // Per blok: rumah terdaftar vs pengajuan lunas tercatat di periode ini.
      var perBlok = {};
      rumah.forEach(function (w) {
        var b = w.blok || "?";
        if (!perBlok[b]) perBlok[b] = { total: 0, lunas: 0 };
        perBlok[b].total++;
      });
      trx.forEach(function (t) {
        if (t.status === "lunas" && t.blok && perBlok[t.blok]) perBlok[t.blok].lunas++;
      });
      if (tmLaporanBlok) {
        tmLaporanBlok.innerHTML = Object.keys(perBlok).sort(urutBlok).map(function (b) {
          var d = perBlok[b];
          var pct = d.total > 0 ? Math.round((d.lunas / d.total) * 100) : 0;
          return "<div><span>" + escWarga(b) + '</span><div class="batang-keuangan"><div class="isi'
            + (pct < 80 ? " keluar" : "") + '" style="width:' + pct + '%"></div></div><b>' + pct + "%</b></div>";
        }).join("");
      }
      if (tmLaporanSumber) {
        tmLaporanSumber.textContent = "sumber: server · periode " + (labelPeriode(periode) || "-");
      }
    });
  }

  document.addEventListener("tm-sesi", function (ev) {
    var izin = ev.detail && ev.detail.izin;
    bolehLaporan = !!(izin && izin["iuran.verifikasi"]);
    if (bolehLaporan) muatLaporan();
  });

  // Jaga status tetap segar selama bagian Data Warga tidak disembunyikan
  // (hanya pengurus/admin yang melihatnya) — setiap 60 detik, tanpa pesan.
  window.setInterval(function () {
    var sec = document.getElementById("datawarga");
    if (!sec || sec.offsetParent === null) return;
    muatWarga({ diam: true });
    if (bolehLaporan) muatLaporan({ diam: true });
  }, 60000);

  muatWarga();

})();
/* TAB PENGATURAN */
(function(){
  var nav = document.getElementById("tmTabNav");
  if (!nav) return;
  var btns = Array.prototype.slice.call(nav.querySelectorAll(".tm-tab-btn"));
  var panels = Array.prototype.slice.call(document.querySelectorAll(".tm-tab-panel"));
  btns.forEach(function(b){
    b.addEventListener("click", function(){
      var t = b.getAttribute("data-tab");
      btns.forEach(function(x){ var a=x===b; x.classList.toggle("aktif",a); x.setAttribute("aria-selected", a?"true":"false"); });
      panels.forEach(function(p){ var a=p.getAttribute("data-tab")===t; p.hidden=!a; p.classList.toggle("aktif",a); });
    });
  });
  try {
    var m = location.hash.match(/tab=([a-z]+)/);
    if (m) {
      btns.forEach(function(b){ if(b.getAttribute("data-tab")===m[1]) b.click(); });
    }
  } catch(e) {}
})();
