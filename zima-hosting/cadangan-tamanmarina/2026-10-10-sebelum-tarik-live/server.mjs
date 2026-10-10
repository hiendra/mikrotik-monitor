// ============================================================
// server.mjs - API manajemen pengguna Taman Marina (tanpa dependensi)
// ============================================================
// Berjalan di belakang Caddy (container `web-router`) pada network Docker
// `web`, TANPA port yang dipublikasikan ke host. Caddy mem-proxy /api/* ke
// sini, jadi dari sudut browser semuanya origin yang SAMA - CSP ketat
// (connect-src 'self') tetap utuh dan tidak ada masalah konten campuran.
//
// Keamanan yang dipasang:
//   - sandi di-hash scrypt (penyimpanan.mjs), tidak pernah dikirim balik
//   - sesi berupa token acak 256-bit, cookie HttpOnly + SameSite=Lax
//   - setiap permintaan pengubah wajib menyertakan header X-Diminta-Dengan.
//     Form lintas situs tidak bisa menambah header khusus, dan kita tidak
//     mengirim header CORS apa pun -> serangan CSRF tertutup tanpa token
//     tambahan. Cookie SameSite=Lax adalah lapis kedua.
//   - pembatasan percobaan masuk per pengguna+IP
//   - izin diperiksa ULANG di server untuk setiap endpoint (bukan sekadar
//     menyembunyikan tombol di browser)
//   - setiap tindakan penting dicatat ke audit log
//
// Jalankan: node server.mjs   (PORT dari env, bawaan 3000)
// ============================================================

import { createServer, request as httpKirim } from 'node:http';
import { request as httpsKirim } from 'node:https';
import {
  ambilPengaturan, aturPengaturan, ambilPembayaran, ambilAkuntansi,
  bootstrap, catatAudit, cariId, cariNama, cocokSandi, daftarAudit, daftarPengguna,
  GalatPengguna, hapusPengguna, hapusSemuaSesi, hapusSesi, jumlahAdminAktif,
  jumlahPengguna, penggunaAman, sesiValid, buatSesi, setSandi, tambahPengguna,
  tandaiMasuk, ubahPengguna, acakSandi, bersihkanSesi,
} from './penyimpanan.mjs';
import { boleh, izinPeran, LABEL_PERAN, peranYangBolehDiatur, PERAN, ringkasPeran } from './izin.mjs';

const PORT = Number(process.env.PORT || 3000);
const NAMA_COOKIE = 'tm_sesi';
const UMUR_COOKIE = 12 * 60 * 60; // detik, selaras dengan UMUR_SESI_MS
const MAKS_BODY = 32 * 1024; // 32 KB cukup untuk semua formulir di sini

// ---------------------------------------------------------------
// Pembatasan percobaan masuk: 8 kali gagal per 15 menit.
// ---------------------------------------------------------------
const BATAS_MASUK = 8;
const JENDELA_MASUK_MS = 15 * 60 * 1000;
const percobaan = new Map(); // kunci -> { jumlah, sampai }

function kunciPercobaan(ip, nama) {
  return `${ip}|${String(nama || '').toLowerCase()}`;
}

function terlaluSering(ip, nama) {
  const k = kunciPercobaan(ip, nama);
  const p = percobaan.get(k);
  if (!p) return false;
  if (p.sampai < Date.now()) {
    percobaan.delete(k);
    return false;
  }
  return p.jumlah >= BATAS_MASUK;
}

function catatGagal(ip, nama) {
  const k = kunciPercobaan(ip, nama);
  const p = percobaan.get(k);
  if (p && p.sampai >= Date.now()) p.jumlah += 1;
  else percobaan.set(k, { jumlah: 1, sampai: Date.now() + JENDELA_MASUK_MS });
}

function hapusPercobaan(ip, nama) {
  percobaan.delete(kunciPercobaan(ip, nama));
}

// ---------------------------------------------------------------
// Pengaturan bawaan - dipakai saat /data/pengaturan.json belum ada.
// Nilai awal = yang tadinya ditulis statis di halaman pengaturan.
// ---------------------------------------------------------------
const PENGATURAN_BAWAAN = {
  iuran: [
    { jenis: 'Iuran Kebersihan', nominal: 30000, aktif: true },
    { jenis: 'Iuran Keamanan', nominal: 50000, aktif: true },
    { jenis: 'Kas RT', nominal: 20000, aktif: true },
    { jenis: 'Iuran Sosial', nominal: 10000, aktif: false },
  ],
  ambang: [
    { batas_atas: 500000, pengesahan: 'Bendahara' },
    { batas_atas: 2000000, pengesahan: 'Bendahara + Ketua RT' },
    { batas_atas: null, pengesahan: 'Bendahara + Ketua RT + Ketua RW' },
  ],
  // Pasangan nama-nilai bebas: admin boleh menambah/mengubah/menghapus
  // sendiri lewat hub Pengaturan. Kosong secara bawaan.
  lain: [],
};

// Validasi ketat: semua datang dari form, tidak pernah dipercaya apa adanya.
function validasiPengaturan(d) {
  if (!d || typeof d !== 'object') throw new GalatPengguna('Isi pengaturan tidak sah.');
  const keluar = { iuran: [], ambang: [], lain: [] };

  if (!Array.isArray(d.iuran) || d.iuran.length > 30) {
    throw new GalatPengguna('Daftar jenis iuran wajib berupa larik (maksimal 30 baris).');
  }
  d.iuran.forEach((b, i) => {
    const jenis = String((b && b.jenis) || '').trim();
    if (!jenis || jenis.length > 80) {
      throw new GalatPengguna(`Baris iuran ${i + 1}: nama jenis wajib diisi (maksimal 80 karakter).`);
    }
    const nominal = Number(b && b.nominal);
    if (!Number.isInteger(nominal) || nominal < 0 || nominal > 1000000000) {
      throw new GalatPengguna(`Baris iuran ${i + 1}: nominal harus bilangan bulat 0 - 1.000.000.000.`);
    }
    keluar.iuran.push({ jenis, nominal, aktif: !!(b && b.aktif) });
  });

  if (!Array.isArray(d.ambang) || d.ambang.length > 10) {
    throw new GalatPengguna('Daftar ambang wajib berupa larik (maksimal 10 baris).');
  }
  d.ambang.forEach((b, i) => {
    let batas = b && b.batas_atas;
    batas = (batas === null || batas === undefined || batas === '') ? null : Number(batas);
    if (batas !== null && (!Number.isInteger(batas) || batas < 0)) {
      throw new GalatPengguna(`Ambang ${i + 1}: batas atas harus bilangan bulat atau dikosongkan.`);
    }
    const pengesahan = String((b && b.pengesahan) || '').trim();
    if (!pengesahan || pengesahan.length > 120) {
      throw new GalatPengguna(`Ambang ${i + 1}: pengesahan wajib diisi (maksimal 120 karakter).`);
    }
    keluar.ambang.push({ batas_atas: batas, pengesahan });
  });

  // Pengaturan lain: pasangan nama-nilai bebas, bentuknya paling longgar
  // tetapi tetap dibatasi panjang & jumlahnya.
  if (!Array.isArray(d.lain) || d.lain.length > 30) {
    throw new GalatPengguna('Daftar pengaturan lain wajib berupa larik (maksimal 30 baris).');
  }
  d.lain.forEach((b, i) => {
    const nama = String((b && b.nama) || '').trim();
    if (!nama || nama.length > 80) {
      throw new GalatPengguna(`Pengaturan lain baris ${i + 1}: nama wajib diisi (maksimal 80 karakter).`);
    }
    const nilai = String((b && b.nilai) === undefined || (b && b.nilai) === null ? '' : b.nilai).trim();
    if (nilai.length > 300) {
      throw new GalatPengguna(`Pengaturan lain baris ${i + 1}: nilai maksimal 300 karakter.`);
    }
    keluar.lain.push({ nama, nilai });
  });

  return keluar;
}

// ---------------------------------------------------------------
// Status sistem: probe paralel ke semua layanan project. Semua URL
// ditulis sekali di sini - menambah layanan baru = tambah satu baris
// (ikuti juga bloknya di Caddyfile).
// Respons apa pun (200/302/403) dihitung HIDUP; timeout/galat jaringan
// = MATI. Latensi menentukan ok vs lambat. Hasil di-cache 15 detik
// supaya tombol segar tidak bisa dipakai membombardir layanan.
// ---------------------------------------------------------------
// Hanya layanan hosting tamanmarina - daftar layanan clusternet.* dihapus
// atas permintaan pemilik (tidak relevan bagi pengelola situs warga).
const SISTEM = [
  { nama: 'Web Router (Caddy)', grup: 'hosting', url: 'http://caddy:80/', host: 'tamanmarina.my.id' },
  { nama: 'Backend Akun (tm-auth)', grup: 'hosting', url: `http://127.0.0.1:${PORT}/api/health` },
  { nama: 'Dasbor Warga', grup: 'tamanmarina', url: 'https://tamanmarina.my.id/' },
  { nama: 'Sensor Udara', grup: 'tamanmarina', url: 'https://tamanmarina.my.id/sensor/api/data' },
];

const MAKS_PROBE_MS = 5000;
let cacheSistem = { waktu: 0, hasil: null };

function probe(s) {
  return new Promise((selesai) => {
    const mulai = Date.now();
    let beres = false;
    const akhir = (status, kode, galat) => {
      if (beres) return;
      beres = true;
      const r = { status, kode, ms: Date.now() - mulai };
      if (galat) r.galat = galat;
      selesai(r);
    };

    let uji;
    try { uji = new URL(s.url); } catch { return akhir('mati', 0, 'alamat tidak sah'); }
    // httpKirim / httpsKirim sudah berupa fungsi request (impor penamaan).
    const kirimPermintaan = uji.protocol === 'https:' ? httpsKirim : httpKirim;
    const opsi = {
      method: 'GET',
      timeout: MAKS_PROBE_MS,
      headers: { 'User-Agent': 'tm-auth/1.0' },
    };
    if (s.host) opsi.headers.Host = s.host;

    try {
      const req = kirimPermintaan(uji, opsi, (jawab) => {
        jawab.resume(); // body dibuang - hanya status & latensi yang dipakai
        const ms = Date.now() - mulai;
        akhir(ms <= 2500 ? 'ok' : 'lambat', jawab.statusCode || 0);
      });
      req.on('timeout', () => req.destroy(new Error('waktu habis')));
      req.on('error', (e) => akhir('mati', 0, e.message));
      req.end();
    } catch (e) {
      akhir('mati', 0, e.message);
    }
  });
}

// ---------------------------------------------------------------
// Utilitas HTTP
// ---------------------------------------------------------------
function kirim(res, kode, data, header = {}) {
  const isi = data === undefined ? '' : JSON.stringify(data);
  res.writeHead(kode, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    ...header,
  });
  res.end(isi);
}

function bacaCookie(req) {
  const mentah = req.headers.cookie || '';
  const keluar = {};
  for (const bagian of mentah.split(';')) {
    const i = bagian.indexOf('=');
    if (i === -1) continue;
    keluar[bagian.slice(0, i).trim()] = decodeURIComponent(bagian.slice(i + 1).trim());
  }
  return keluar;
}

function ipKlien(req) {
  const fwd = req.headers['x-forwarded-for'];
  if (typeof fwd === 'string' && fwd.trim()) return fwd.split(',')[0].trim();
  return req.socket.remoteAddress || 'lokal';
}

function https(req) {
  return String(req.headers['x-forwarded-proto'] || '').split(',')[0].trim() === 'https';
}

function cookieSesi(req, token, kedaluwarsaDetik = UMUR_COOKIE) {
  const bagian = [
    `${NAMA_COOKIE}=${token}`,
    'Path=/',
    'HttpOnly',
    'SameSite=Lax',
    `Max-Age=${kedaluwarsaDetik}`,
  ];
  if (https(req)) bagian.push('Secure');
  return bagian.join('; ');
}

async function bacaBody(req) {
  return new Promise((selesai, gagal) => {
    let panjang = 0;
    const potongan = [];
    req.on('data', (c) => {
      panjang += c.length;
      if (panjang > MAKS_BODY) {
        gagal(new GalatPengguna('Isi permintaan terlalu besar.'));
        req.destroy();
        return;
      }
      potongan.push(c);
    });
    req.on('end', () => {
      const teks = Buffer.concat(potongan).toString('utf8');
      if (!teks) return selesai({});
      try {
        const data = JSON.parse(teks);
        selesai(data && typeof data === 'object' ? data : {});
      } catch {
        gagal(new GalatPengguna('Isi permintaan bukan JSON yang sah.'));
      }
    });
    req.on('error', () => gagal(new GalatPengguna('Gagal membaca isi permintaan.')));
  });
}

// ---------------------------------------------------------------
// Sesi & izin
// ---------------------------------------------------------------
function penggunaSesi(req) {
  return sesiValid(bacaCookie(req)[NAMA_COOKIE]);
}

function peranAktif(req) {
  const u = penggunaSesi(req);
  return u && u.aktif !== false ? u.peran : 'warga';
}

function wajibMasuk(req, res) {
  const u = penggunaSesi(req);
  if (!u || u.aktif === false) {
    kirim(res, 401, { galat: 'Belum masuk atau akun tidak aktif.' });
    return null;
  }
  return u;
}

function wajibIzin(req, res, izin) {
  const u = wajibMasuk(req, res);
  if (!u) return null;
  if (!boleh(u.peran, izin)) {
    kirim(res, 403, { galat: `Peran ${LABEL_PERAN[u.peran] || u.peran} tidak punya izin ${izin}.` });
    return null;
  }
  return u;
}

// ---------------------------------------------------------------
// Rute
// ---------------------------------------------------------------
const rute = [];
const DAFTAR = (pola, metode, penangan, izin = null) => rute.push({ pola, metode, penangan, izin });

// --- publik ---
DAFTAR(/^\/api\/health$/, 'GET', (req, res) => {
  kirim(res, 200, { ok: true, pengguna: jumlahPengguna(), waktu: new Date().toISOString() });
});

DAFTAR(/^\/api\/peran$/, 'GET', (req, res) => {
  kirim(res, 200, { peran: ringkasPeran(), label: LABEL_PERAN });
});

DAFTAR(/^\/api\/saya$/, 'GET', (req, res) => {
  const u = penggunaSesi(req);
  if (!u || u.aktif === false) return kirim(res, 401, { galat: 'Belum masuk.' });
  kirim(res, 200, { pengguna: penggunaAman(u), izin: izinPeran(u.peran), label: LABEL_PERAN });
});

DAFTAR(/^\/api\/masuk$/, 'POST', async (req, res, data) => {
  const ip = ipKlien(req);
  const nama = String(data.pengguna || '').trim();
  if (!nama || !data.sandi) return kirim(res, 400, { galat: 'Nama pengguna dan sandi wajib diisi.' });
  if (terlaluSering(ip, nama)) {
    return kirim(res, 429, { galat: 'Terlalu banyak percobaan masuk. Coba lagi sekitar 15 menit lagi.' });
  }
  const u = cariNama(nama);
  if (!u || !cocokSandi(data.sandi, u.sandi_garam, u.sandi_kunci)) {
    catatGagal(ip, nama);
    return kirim(res, 401, { galat: 'Nama pengguna atau sandi salah.' });
  }
  if (u.aktif === false) return kirim(res, 403, { galat: 'Akun ini dinonaktifkan. Hubungi pengurus.' });
  hapusPercobaan(ip, nama);
  tandaiMasuk(u.id);
  const token = buatSesi(u.id);
  kirim(
    res, 200,
    { pengguna: penggunaAman(u), izin: izinPeran(u.peran), label: LABEL_PERAN },
    { 'Set-Cookie': cookieSesi(req, token) },
  );
});

DAFTAR(/^\/api\/keluar$/, 'POST', (req, res) => {
  const token = bacaCookie(req)[NAMA_COOKIE];
  if (token) hapusSesi(token);
  kirim(res, 200, { ok: true }, { 'Set-Cookie': cookieSesi(req, '', 0) });
});

DAFTAR(/^\/api\/sandi$/, 'POST', async (req, res, data) => {
  const u = wajibMasuk(req, res);
  if (!u) return;
  if (!data.sandi_lama || !data.sandi_baru) {
    return kirim(res, 400, { galat: 'Sandi lama dan sandi baru wajib diisi.' });
  }
  if (!cocokSandi(data.sandi_lama, u.sandi_garam, u.sandi_kunci)) {
    return kirim(res, 400, { galat: 'Sandi lama salah.' });
  }
  setSandi(u.id, data.sandi_baru, false);
  hapusSemuaSesi(u.id);
  const token = buatSesi(u.id); // sesi ini tetap masuk, perangkat lain keluar
  kirim(res, 200, { ok: true }, { 'Set-Cookie': cookieSesi(req, token) });
});

// --- pengguna ---
DAFTAR(/^\/api\/pengguna$/, 'GET', (req, res) => {
  const u = wajibIzin(req, res, 'pengguna.lihat');
  if (!u) return;
  kirim(res, 200, {
    pengguna: daftarPengguna(),
    bolehAtur: peranYangBolehDiatur(u.peran),
    peran: PERAN,
    label: LABEL_PERAN,
  });
});

DAFTAR(/^\/api\/pengguna$/, 'POST', async (req, res, data) => {
  const u = wajibIzin(req, res, 'pengguna.buat');
  if (!u) return;
  const bolehAtur = peranYangBolehDiatur(u.peran);
  const peranBaru = String(data.peran || 'warga');
  if (!PERAN.includes(peranBaru)) return kirim(res, 400, { galat: 'Peran tidak dikenal.' });
  if (!bolehAtur.includes(peranBaru)) {
    return kirim(res, 403, { galat: `Peran ${LABEL_PERAN[u.peran]} hanya boleh membuat akun: ${bolehAtur.map((p) => LABEL_PERAN[p]).join(', ')}.` });
  }
  const sandiAwal = data.sandi && String(data.sandi).length >= 8 ? String(data.sandi) : acakSandi(10);
  const pakaiSandiSendiri = !!(data.sandi && String(data.sandi).length >= 8);
  const baru = tambahPengguna({
    pengguna: data.pengguna,
    sandi: sandiAwal,
    nama: data.nama,
    peran: peranBaru,
    jabatan: data.jabatan,
    blok: data.blok,
    rt: data.rt,
    rw: data.rw,
    no_hp: data.no_hp,
    aktif: data.aktif,
    harusGanti: true,
  });
  catatAudit({
    pelaku: u.pengguna,
    aksi: 'pengguna.buat',
    sasaran: baru.pengguna,
    catatan: `peran ${LABEL_PERAN[peranBaru]}`,
  });
  kirim(res, 201, {
    pengguna: penggunaAman(baru),
    sandi_awal: pakaiSandiSendiri ? null : sandiAwal,
  });
});

DAFTAR(/^\/api\/pengguna\/([^/]+)$/, 'PATCH', async (req, res, data, cocok) => {
  const u = wajibIzin(req, res, 'pengguna.kelola');
  if (!u) return;
  const sasaran = cariId(cocok[1]);
  if (!sasaran) return kirim(res, 404, { galat: 'Pengguna tidak ditemukan.' });

  // Aturan kedudukan: pengurus hanya boleh mengubah akun warga; admin bebas
  // (tetapi tidak boleh menurunkan/menonaktifkan admin aktif terakhir).
  const bolehAtur = peranYangBolehDiatur(u.peran);
  if (!bolehAtur.includes(sasaran.peran)) {
    return kirim(res, 403, { galat: `Peran ${LABEL_PERAN[u.peran]} tidak boleh mengubah akun berperan ${LABEL_PERAN[sasaran.peran]}.` });
  }
  if (data.peran !== undefined) {
    if (!boleh(u.peran, 'peran.ubah')) return kirim(res, 403, { galat: 'Hanya admin yang boleh mengubah peran.' });
    const peranBaru = String(data.peran);
    if (!PERAN.includes(peranBaru)) return kirim(res, 400, { galat: 'Peran tidak dikenal.' });
    if (sasaran.peran === 'admin' && peranBaru !== 'admin' && jumlahAdminAktif() <= 1) {
      return kirim(res, 400, { galat: 'Tidak bisa menurunkan admin aktif terakhir.' });
    }
    data.peran = peranBaru;
  }
  if (data.aktif !== undefined && data.aktif === false && sasaran.peran === 'admin' && jumlahAdminAktif() <= 1) {
    return kirim(res, 400, { galat: 'Tidak bisa menonaktifkan admin aktif terakhir.' });
  }

  const ubah = {};
  for (const b of ['nama', 'jabatan', 'blok', 'rt', 'rw', 'no_hp', 'peran', 'aktif']) {
    if (data[b] !== undefined) ubah[b] = data[b];
  }
  const hasil = ubahPengguna(sasaran.id, ubah);
  if (ubah.aktif === false || ubah.peran !== undefined) hapusSemuaSesi(sasaran.id);
  catatAudit({
    pelaku: u.pengguna,
    aksi: 'pengguna.ubah',
    sasaran: sasaran.pengguna,
    catatan: Object.keys(ubah).join(', '),
  });
  kirim(res, 200, { pengguna: penggunaAman(hasil) });
});

DAFTAR(/^\/api\/pengguna\/([^/]+)\/sandi$/, 'POST', async (req, res, data, cocok) => {
  const u = wajibIzin(req, res, 'pengguna.kelola');
  if (!u) return;
  const sasaran = cariId(cocok[1]);
  if (!sasaran) return kirim(res, 404, { galat: 'Pengguna tidak ditemukan.' });
  const bolehAtur = peranYangBolehDiatur(u.peran);
  if (!bolehAtur.includes(sasaran.peran)) {
    return kirim(res, 403, { galat: `Peran ${LABEL_PERAN[u.peran]} tidak boleh mengatur sandi akun ${LABEL_PERAN[sasaran.peran]}.` });
  }
  const sandiBaru = data.sandi && String(data.sandi).length >= 8 ? String(data.sandi) : acakSandi(10);
  setSandi(sasaran.id, sandiBaru, true);
  hapusSemuaSesi(sasaran.id);
  catatAudit({ pelaku: u.pengguna, aksi: 'pengguna.reset-sandi', sasaran: sasaran.pengguna });
  kirim(res, 200, { ok: true, sandi_awal: data.sandi ? null : sandiBaru });
});

DAFTAR(/^\/api\/pengguna\/([^/]+)$/, 'DELETE', async (req, res, data, cocok) => {
  const u = wajibIzin(req, res, 'pengguna.hapus');
  if (!u) return;
  const sasaran = cariId(cocok[1]);
  if (!sasaran) return kirim(res, 404, { galat: 'Pengguna tidak ditemukan.' });
  if (sasaran.id === u.id) return kirim(res, 400, { galat: 'Tidak bisa menghapus akun sendiri.' });
  if (sasaran.peran === 'admin' && jumlahAdminAktif() <= 1) {
    return kirim(res, 400, { galat: 'Tidak bisa menghapus admin aktif terakhir.' });
  }
  hapusPengguna(sasaran.id);
  hapusSemuaSesi(sasaran.id);
  catatAudit({ pelaku: u.pengguna, aksi: 'pengguna.hapus', sasaran: sasaran.pengguna });
  kirim(res, 200, { ok: true });
});

// --- audit ---
DAFTAR(/^\/api\/audit$/, 'GET', (req, res, data, cocok, url) => {
  const u = wajibIzin(req, res, 'audit.lihat');
  if (!u) return;
  kirim(res, 200, { audit: daftarAudit(url.searchParams.get('batas')) });
});

// --- pengaturan situs (admin) ---
DAFTAR(/^\/api\/pengaturan$/, 'GET', (req, res) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  kirim(res, 200, { pengaturan: ambilPengaturan(PENGATURAN_BAWAAN) });
});

DAFTAR(/^\/api\/pengaturan$/, 'PUT', (req, res, data) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  const bersih = validasiPengaturan(data.pengaturan || data);
  aturPengaturan(bersih);
  catatAudit({
    pelaku: u.pengguna,
    aksi: 'pengaturan.ubah',
    sasaran: 'situs',
    catatan: `${bersih.iuran.length} jenis iuran, ${bersih.ambang.length} ambang`,
  });
  kirim(res, 200, { pengaturan: bersih });
});

// --- pembayaran & akuntansi (dipindah dari berkas JSON publik di web
//     root ke endpoint ber-izin; pengganti /payments.json &
//     /accounting.json yang dulu terbaca siapa pun) ---
DAFTAR(/^\/api\/pembayaran$/, 'GET', (req, res) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  kirim(res, 200, ambilPembayaran());
});

DAFTAR(/^\/api\/akuntansi$/, 'GET', (req, res) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  kirim(res, 200, ambilAkuntansi());
});

// --- status seluruh sistem project (admin) ---
DAFTAR(/^\/api\/sistem$/, 'GET', async (req, res, data, cocok, url) => {
  const u = wajibIzin(req, res, 'sistem.kelola');
  if (!u) return;
  // ?segar=1 melewati cache; tanpa itu hasil 15 detik terakhir dipakai ulang.
  const paksaSegar = url.searchParams.get('segar') === '1';
  if (!paksaSegar && cacheSistem.hasil && Date.now() - cacheSistem.waktu < 15000) {
    return kirim(res, 200, { ...cacheSistem.hasil, cache: true });
  }
  const hasil = await Promise.all(
    SISTEM.map(async (s) => ({
      nama: s.nama,
      grup: s.grup,
      url: s.url,
      ...(await probe(s)),
    })),
  );
  const ringkas = { sistem: hasil, waktu: new Date().toISOString(), cache: false };
  cacheSistem = { waktu: Date.now(), hasil: ringkas };
  kirim(res, 200, ringkas);
});

// ---------------------------------------------------------------
// Server
// ---------------------------------------------------------------
const METODE_PENGUBAH = new Set(['POST', 'PATCH', 'PUT', 'DELETE']);

const server = createServer(async (req, res) => {
  let url;
  try {
    url = new URL(req.url, 'http://lokal');
  } catch {
    return kirim(res, 400, { galat: 'Alamat tidak sah.' });
  }
  const jalur = url.pathname;

  if (!jalur.startsWith('/api/')) return kirim(res, 404, { galat: 'Hanya jalur /api/ yang dilayani.' });

  // CSRF: permintaan pengubah wajib membawa header khusus.
  if (METODE_PENGUBAH.has(req.method) && req.headers['x-diminta-dengan'] !== 'dasbor') {
    return kirim(res, 403, { galat: 'Permintaan ditolak: header X-Diminta-Dengan tidak ada.' });
  }

  let data = {};
  if (METODE_PENGUBAH.has(req.method)) {
    try {
      data = await bacaBody(req);
    } catch (e) {
      return kirim(res, 400, { galat: e.message });
    }
  }

  for (const r of rute) {
    if (r.metode !== req.method) continue;
    const cocok = jalur.match(r.pola);
    if (!cocok) continue;
    try {
      await r.penangan(req, res, data, cocok, url);
    } catch (e) {
      const pesan = e instanceof GalatPengguna ? e.message : 'Kesalahan di server.';
      if (!(e instanceof GalatPengguna)) console.error('[galat]', e);
      if (!res.headersSent) kirim(res, 400, { galat: pesan });
    }
    return;
  }

  // Metode lain untuk jalur yang ada -> 405, sisanya 404.
  const jalurAda = rute.some((r) => jalur.match(r.pola));
  kirim(res, jalurAda ? 405 : 404, { galat: jalurAda ? 'Metode tidak diizinkan.' : 'Titik akhir tidak ditemukan.' });
});

const hasilBootstrap = bootstrap();
if (hasilBootstrap.dibuat) {
  console.log('[bootstrap] Akun admin pertama dibuat (pengguna: admin).');
  console.log(`[bootstrap] Sandi awal ditulis ke ${hasilBootstrap.jalurCatatan} - segera ganti lalu hapus berkas itu.`);
}
setInterval(bersihkanSesi, 30 * 60 * 1000).unref();

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[auth] tamanmarina auth API mendengarkan di :${PORT} (${jumlahPengguna()} pengguna).`);
});

for (const sinyal of ['SIGTERM', 'SIGINT']) {
  process.on(sinyal, () => {
    console.log(`[auth] ${sinyal} diterima, berhenti dengan rapi.`);
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 3000).unref();
  });
}
