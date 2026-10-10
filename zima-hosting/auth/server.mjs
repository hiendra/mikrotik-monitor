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
import { randomUUID } from 'node:crypto';
import { request as httpsKirim } from 'node:https';
import {
  ambilPengaturan, aturPengaturan, ambilPembayaran, aturMetodePembayaran, ambilTagihanWarga, aturTagihanWarga, ambilAkuntansi, aturAkuntansi,
  bootstrap, catatAudit, cariId, cariNama, cocokSandi, daftarAudit, daftarPengguna,
  GalatPengguna, hapusPengguna, hapusSemuaSesi, hapusSesi, jumlahAdminAktif,
  jumlahPengguna, penggunaAman, sesiValid, buatSesi, setSandi, tambahPengguna,
  tandaiMasuk, ubahPengguna, acakSandi, bersihkanSesi,
  ambilKonten, simpanKonten,
  ambilUmkm, aturUmkm,
  ambilAduan, aturAduan,
  ambilRosterWarga,
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

// Nilai iuran aktif bukan data pribadi; warga memerlukannya untuk melihat tagihan.
DAFTAR(/^\/api\/jenis-iuran$/, 'GET', (_req, res) => {
  const p = ambilPengaturan(PENGATURAN_BAWAAN);
  const iuran = (Array.isArray(p.iuran) ? p.iuran : []).filter((b) => b && b.aktif)
    .map((b) => ({ jenis: String(b.jenis || ''), nominal: Number(b.nominal) || 0 }));
  kirim(res, 200, { iuran, total: iuran.reduce((n, b) => n + b.nominal, 0) });
});

// Daftar rumah/kk per blok - dahulu berkas warga.json di web root yang
// terbaca publik tanpa login (audit 2026-10-09). Kini disimpan di volume
// dan hanya dilayani kepada izin datawarga.lihat. Nominal & periode
// diambil dari pengaturan/berjalan - satu sumber kebenaran.
DAFTAR(/^\/api\/warga$/, 'GET', (req, res) => {
  const u = wajibIzin(req, res, 'datawarga.lihat');
  if (!u) return;
  const roster = ambilRosterWarga();
  if (!roster) return kirim(res, 404, { galat: 'Daftar warga belum tersedia di server.' });
  const p = ambilPengaturan(PENGATURAN_BAWAAN);
  const total = (Array.isArray(p.iuran) ? p.iuran : [])
    .filter((b) => b && b.aktif)
    .reduce((n, b) => n + (Number(b.nominal) || 0), 0);
  // Bulan berjalan menurut waktu Jakarta (container bisa berzona UTC).
  const jkt = new Date(Date.now() + 7 * 3600 * 1000);
  const periode = `${jkt.getUTCFullYear()}-${String(jkt.getUTCMonth() + 1).padStart(2, '0')}`;
  const meta = { ...(roster.meta || {}), periode_aktif: periode };
  if (total > 0) meta.iuran_bulanan_default = total;
  const warga = roster.warga.map((baris) => {
    const w = { ...baris };
    if (total > 0) w.iuran_bulanan = total;
    if (total > 0 && w.tagihan_terbaru && w.tagihan_terbaru.periode === periode) {
      w.tagihan_terbaru = { ...w.tagihan_terbaru, jumlah: total };
    }
    return w;
  });
  kirim(res, 200, {
    meta,
    blok_list: Array.isArray(roster.blok_list) ? roster.blok_list : [],
    warga,
  });
});

// Data yang memang ditampilkan kepada warga: metode aktif saja, tanpa
// transaksi, status verifikasi, atau data rekening internal lainnya.
DAFTAR(/^\/api\/metode-publik$/, 'GET', (_req, res) => {
  const data = ambilPembayaran();
  const rekening = Array.isArray(data.rekening) ? data.rekening : [];
  const metode = rekening.filter((item) => item && item.status === 'aktif').map((item) => ({
    id: String(item.id), bank: String(item.bank || ''), jenis: String(item.jenis || 'lainnya'),
    nomor_rekening: String(item.nomor_rekening || ''), atas_nama: String(item.atas_nama || ''),
    keterangan: String(item.keterangan || ''),
  }));
  // Opsi tunai bawaan dapat dipakai langsung; setelah admin membuat/nonaktifkan
  // metode tunai tersimpan, pilihan mengikuti status yang dikonfigurasi.
  if (!rekening.some((item) => item && item.jenis === 'tunai')) {
    metode.push({ id: 'tunai-pengurus', bank: 'Tunai ke Pengurus', jenis: 'tunai', nomor_rekening: '', atas_nama: '', keterangan: 'Serahkan langsung ke pengurus; menunggu konfirmasi penerimaan.' });
  }
  kirim(res, 200, { metode });
});

function periodeTagihanAktif() {
  const bagian = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Jakarta', year: 'numeric', month: '2-digit' }).formatToParts(new Date());
  const tahun = bagian.find((x) => x.type === 'year').value;
  const bulan = bagian.find((x) => x.type === 'month').value;
  return tahun + '-' + bulan;
}
function rincianIuranAktif() {
  const p = ambilPengaturan(PENGATURAN_BAWAAN);
  const rincian = (Array.isArray(p.iuran) ? p.iuran : []).filter((b) => b && b.aktif)
    .map((b) => ({ jenis: String(b.jenis || ''), nominal: Number(b.nominal) || 0 }));
  return { rincian, jumlah: rincian.reduce((n, b) => n + b.nominal, 0) };
}
function urutTagihan(a, b) { return String(b.diajukan || '').localeCompare(String(a.diajukan || '')); }

// Rincian dan riwayat hanya milik akun yang sedang masuk.
DAFTAR(/^\/api\/iuran\/saya$/, 'GET', (req, res) => {
  const u = wajibMasuk(req, res);
  if (!u) return;
  const aktif = rincianIuranAktif();
  const periode = periodeTagihanAktif();
  const riwayat = ambilTagihanWarga().transaksi.filter((t) => t.akun_id === u.id).sort(urutTagihan);
  const sekarang = riwayat.find((t) => t.periode === periode) || null;
  kirim(res, 200, { periode, rincian: aktif.rincian, jumlah: aktif.jumlah, status: sekarang ? sekarang.status : 'belum', riwayat });
});

DAFTAR(/^\/api\/iuran\/saya$/, 'POST', (req, res, data) => {
  const u = wajibMasuk(req, res);
  if (!u) return;
  const aktif = rincianIuranAktif();
  if (!aktif.rincian.length || aktif.jumlah <= 0) return kirim(res, 400, { galat: 'Belum ada iuran aktif untuk ditagihkan.' });
  const pembayaran = ambilPembayaran();
  const rekening = Array.isArray(pembayaran.rekening) ? pembayaran.rekening : [];
  let metode = rekening.find((m) => m && String(m.id) === String(data.metode_id) && m.status === 'aktif');
  if (!metode && data.metode_id === 'tunai-pengurus' && !rekening.some((m) => m && m.jenis === 'tunai')) {
    metode = { id: 'tunai-pengurus', bank: 'Tunai ke Pengurus', jenis: 'tunai', keterangan: 'Serahkan langsung ke pengurus.' };
  }
  if (!metode) return kirim(res, 400, { galat: 'Pilih metode pembayaran yang masih aktif.' });
  const periode = periodeTagihanAktif();
  const dataTagihan = ambilTagihanWarga();
  const lama = dataTagihan.transaksi.filter((t) => t.akun_id === u.id && t.periode === periode).sort(urutTagihan)[0];
  if (lama && lama.status !== 'ditolak') return kirim(res, 409, { galat: lama.status === 'lunas' ? 'Tagihan periode ini sudah lunas.' : 'Pengajuan periode ini masih menunggu verifikasi.' });
  const metodeLabel = String(metode.bank || metode.jenis || 'Pembayaran');
  const trx = {
    id: randomUUID(), akun_id: u.id, pengguna: u.pengguna, nama: u.nama || u.pengguna,
    blok: u.blok || '', periode, rincian: aktif.rincian, jumlah: aktif.jumlah,
    metode_id: String(metode.id), metode: metodeLabel, jenis_metode: String(metode.jenis || 'lainnya'),
    status: 'menunggu', diajukan: new Date().toISOString(), diverifikasi: null, diverifikasi_oleh: '', catatan_verifikasi: '',
  };
  dataTagihan.transaksi.push(trx);
  aturTagihanWarga(dataTagihan.transaksi);
  catatAudit({ pelaku: u.pengguna, aksi: 'iuran.ajukan', sasaran: periode, catatan: 'Rp ' + trx.jumlah + ' · ' + trx.metode });
  kirim(res, 201, { transaksi: trx });
});

DAFTAR(/^\/api\/iuran\/verifikasi$/, 'GET', (req, res) => {
  const u = wajibIzin(req, res, 'iuran.verifikasi');
  if (!u) return;
  const transaksi = ambilTagihanWarga().transaksi.slice().sort(urutTagihan);
  kirim(res, 200, { transaksi });
});

DAFTAR(/^\/api\/iuran\/verifikasi\/([0-9a-f-]{36})$/, 'POST', (req, res, data, cocok) => {
  const u = wajibIzin(req, res, 'iuran.verifikasi');
  if (!u) return;
  const status = String(data.status || '');
  if (!['lunas', 'ditolak'].includes(status)) return kirim(res, 400, { galat: 'Status verifikasi harus Lunas atau Ditolak.' });
  const dataTagihan = ambilTagihanWarga();
  const trx = dataTagihan.transaksi.find((t) => t.id === cocok[1]);
  if (!trx) return kirim(res, 404, { galat: 'Pengajuan pembayaran tidak ditemukan.' });
  if (trx.akun_id === u.id) {
    return kirim(res, 403, { galat: 'Tidak boleh memverifikasi pengajuan pembayaran sendiri.' });
  }
  trx.status = status;
  trx.diverifikasi = new Date().toISOString();
  trx.diverifikasi_oleh = u.nama || u.pengguna;
  trx.catatan_verifikasi = String(data.catatan || '').trim().slice(0, 300);
  aturTagihanWarga(dataTagihan.transaksi);
  catatAudit({ pelaku: u.pengguna, aksi: 'iuran.verifikasi', sasaran: trx.pengguna, catatan: trx.periode + ' · ' + status + ' · Rp ' + trx.jumlah });
  kirim(res, 200, { transaksi: trx });
});

function teksMetodePembayaran(nilai, nama, batas, wajib = false) {
  const hasil = String(nilai === undefined || nilai === null ? '' : nilai).trim();
  if (wajib && !hasil) throw new GalatPengguna(nama + ' wajib diisi.');
  if (hasil.length > batas) throw new GalatPengguna(nama + ' maksimal ' + batas + ' karakter.');
  return hasil;
}

function validasiMetodePembayaran(data) {
  if (!data || !Array.isArray(data.rekening) || data.rekening.length > 100) {
    throw new GalatPengguna('Daftar metode pembayaran tidak sah (maksimal 100 metode).');
  }
  const idTerpakai = new Set();
  return data.rekening.map((item, i) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) {
      throw new GalatPengguna('Metode pembayaran baris ' + (i + 1) + ' tidak sah.');
    }
    const jenis = teksMetodePembayaran(item.jenis, 'Jenis metode', 20, true);
    if (!['transfer', 'qris', 'tunai', 'ewallet', 'lainnya'].includes(jenis)) {
      throw new GalatPengguna('Jenis metode pembayaran tidak dikenal.');
    }
    const bank = teksMetodePembayaran(item.bank, 'Nama bank/penyedia', 80, true);
    const nomor = teksMetodePembayaran(item.nomor_rekening, 'Nomor/tujuan pembayaran', 100);
    if (jenis === 'transfer' && !nomor) {
      throw new GalatPengguna('Nomor rekening wajib untuk metode transfer.');
    }
    const status = teksMetodePembayaran(item.status, 'Status metode', 12, true);
    if (!['aktif', 'nonaktif'].includes(status)) {
      throw new GalatPengguna('Status metode harus aktif atau nonaktif.');
    }
    let id = item.id;
    if (id === undefined || id === null || id === '') id = randomUUID();
    if (!(typeof id === 'string' && /^[a-zA-Z0-9._:-]{1,64}$/.test(id)) &&
        !(Number.isSafeInteger(id) && id >= 0)) {
      throw new GalatPengguna('ID metode pembayaran tidak sah.');
    }
    const kunci = String(id);
    if (idTerpakai.has(kunci)) throw new GalatPengguna('ID metode pembayaran tidak boleh ganda.');
    idTerpakai.add(kunci);
    return {
      id,
      bank,
      nomor_rekening: nomor,
      atas_nama: teksMetodePembayaran(item.atas_nama, 'Atas nama', 120),
      jenis,
      status,
      keterangan: teksMetodePembayaran(item.keterangan, 'Instruksi/catatan', 300),
    };
  });
}

DAFTAR(/^\/api\/pembayaran$/, 'PUT', (req, res, data) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  const rekening = validasiMetodePembayaran(data);
  const hasil = aturMetodePembayaran(rekening);
  catatAudit({
    pelaku: u.pengguna,
    aksi: 'pembayaran.metode.ubah',
    sasaran: 'metode',
    catatan: rekening.length + ' metode pembayaran',
  });
  kirim(res, 200, hasil);
});

DAFTAR(/^\/api\/akuntansi$/, 'GET', (req, res) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  kirim(res, 200, ambilAkuntansi());
});

function validasiAkuntansi(data, lama, pengguna) {
  if (!data || !Array.isArray(data.coa) || !Array.isArray(data.jurnal) ||
      !Array.isArray(data.kas) || data.coa.length > 300 ||
      data.jurnal.length > 1000 || data.kas.length > 1000) {
    throw new GalatPengguna('Data akuntansi tidak sah atau melebihi batas.');
  }
  const teks = (nilai, nama, batas, wajib = false) => {
    const hasil = String(nilai === undefined || nilai === null ? '' : nilai).trim();
    if (wajib && !hasil) throw new GalatPengguna(nama + ' wajib diisi.');
    if (hasil.length > batas) throw new GalatPengguna(nama + ' maksimal ' + batas + ' karakter.');
    return hasil;
  };
  const angka = (nilai, nama, minimal = 0, maksimal = 1000000000000) => {
    const hasil = Number(nilai);
    if (!Number.isFinite(hasil) || hasil < minimal || hasil > maksimal) {
      throw new GalatPengguna(nama + ' harus berupa angka antara ' + minimal + ' dan ' + maksimal + '.');
    }
    return hasil;
  };
  const tanggal = (nilai) => {
    const hasil = teks(nilai, 'Tanggal', 10, true);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(hasil) ||
        !Number.isFinite(Date.parse(hasil + 'T00:00:00Z')) ||
        new Date(hasil + 'T00:00:00Z').toISOString().slice(0, 10) !== hasil) {
      throw new GalatPengguna('Tanggal harus berupa tanggal kalender yang sah.');
    }
    return hasil;
  };
  const akunLama = lama.coa || [];
  const jurnalLama = lama.jurnal || [];
  const kasLama = lama.kas || [];
  const kodeDipakai = new Set();
  const coa = data.coa.map((item, i) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new GalatPengguna('Baris COA tidak sah.');
    const kode = teks(item.kode, 'Kode akun', 24, true);
    if (kodeDipakai.has(kode.toLowerCase())) throw new GalatPengguna('Kode akun tidak boleh ganda.');
    kodeDipakai.add(kode.toLowerCase());
    const jenis = teks(item.jenis, 'Jenis akun', 24, true);
    if (!['aset', 'kewajiban', 'modal', 'pendapatan', 'beban'].includes(jenis)) throw new GalatPengguna('Jenis akun tidak dikenal.');
    const status = teks(item.status, 'Status akun', 12, true);
    if (!['aktif', 'nonaktif'].includes(status)) throw new GalatPengguna('Status akun harus aktif atau nonaktif.');
    const induk = item.induk === null || item.induk === undefined || item.induk === '' ? null : teks(item.induk, 'Akun induk', 24);
    return { ...(akunLama[i] || {}), kode, nama: teks(item.nama, 'Nama akun', 120, true), jenis,
      induk, saldo: angka(item.saldo, 'Saldo akun', -1000000000000), status };
  });
  const validId = (item, lamaItem, daftarIds, nama) => {
    let id = item.id === undefined || item.id === null || item.id === '' ? (lamaItem && lamaItem.id) : item.id;
    if (id === undefined || id === null || id === '') id = randomUUID();
    if (!(typeof id === 'string' && /^[a-zA-Z0-9._:-]{1,64}$/.test(id)) &&
        !(Number.isSafeInteger(id) && id >= 0)) throw new GalatPengguna('ID ' + nama + ' tidak sah.');
    const kunci = String(id);
    if (daftarIds.has(kunci)) throw new GalatPengguna('ID ' + nama + ' tidak boleh ganda.');
    daftarIds.add(kunci);
    return id;
  };
  const idsJurnal = new Set();
  const jurnal = data.jurnal.map((item, i) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new GalatPengguna('Baris jurnal tidak sah.');
    const lamaItem = jurnalLama.find((x) => String(x.id) === String(item.id)) || jurnalLama[i] || {};
    const id = validId(item, lamaItem, idsJurnal, 'jurnal');
    const debit = angka(item.debit, 'Debit');
    const kredit = angka(item.kredit, 'Kredit');
    if (debit === 0 && kredit === 0) throw new GalatPengguna('Debit atau kredit harus berisi nilai.');
    return { ...lamaItem, id, tanggal: tanggal(item.tanggal),
      no_bukti: teks(item.no_bukti, 'Nomor bukti', 60),
      keterangan: teks(item.keterangan, 'Keterangan jurnal', 300, true),
      debit, kredit,
      akun_debit: teks(item.akun_debit === undefined ? lamaItem.akun_debit : item.akun_debit, 'Akun debit', 24),
      akun_kredit: teks(item.akun_kredit === undefined ? lamaItem.akun_kredit : item.akun_kredit, 'Akun kredit', 24),
      dibuat_oleh: lamaItem.dibuat_oleh || pengguna };
  });
  const idsKas = new Set();
  const kas = data.kas.map((item, i) => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new GalatPengguna('Baris kas tidak sah.');
    const lamaItem = kasLama.find((x) => String(x.id) === String(item.id)) || kasLama[i] || {};
    const id = validId(item, lamaItem, idsKas, 'kas');
    const jenis = teks(item.jenis, 'Jenis transaksi kas', 12, true);
    if (!['masuk', 'keluar'].includes(jenis)) throw new GalatPengguna('Jenis transaksi kas harus masuk atau keluar.');
    return { ...lamaItem, id, tanggal: tanggal(item.tanggal), jenis,
      jumlah: angka(item.jumlah, 'Jumlah kas'),
      keterangan: teks(item.keterangan, 'Keterangan kas', 300, true),
      dibuat_oleh: lamaItem.dibuat_oleh || pengguna };
  });
  return { ...lama, coa, jurnal, kas };
}

DAFTAR(/^\/api\/akuntansi$/, 'PUT', (req, res, data) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  const lama = ambilAkuntansi();
  const bersih = validasiAkuntansi(data, lama, u.pengguna);
  const kodeTersisa = new Set(bersih.coa.map((a) => String(a.kode).toLowerCase()));
  const akunDihapus = (lama.coa || []).filter((a) => !kodeTersisa.has(String(a.kode).toLowerCase()));
  for (const akun of akunDihapus) {
    const kode = String(akun.kode);
    const punyaTurunan = bersih.coa.some((a) => String(a.induk || '').toLowerCase() === kode.toLowerCase());
    const dipakaiJurnal = bersih.jurnal.some((j) =>
      String(j.akun_debit || '').toLowerCase() === kode.toLowerCase() ||
      String(j.akun_kredit || '').toLowerCase() === kode.toLowerCase());
    if (punyaTurunan || dipakaiJurnal) {
      throw new GalatPengguna('Akun ' + kode + ' masih digunakan oleh akun turunan atau jurnal; nonaktifkan akun jika tidak dipakai lagi.');
    }
  }
  const jurnalTersisa = new Set(bersih.jurnal.map((x) => String(x.id)));
  const kasTersisa = new Set(bersih.kas.map((x) => String(x.id)));
  const jumlahDihapus = {
    coa: akunDihapus.length,
    jurnal: (lama.jurnal || []).filter((x) => !jurnalTersisa.has(String(x.id))).length,
    kas: (lama.kas || []).filter((x) => !kasTersisa.has(String(x.id))).length,
  };
  aturAkuntansi(bersih);
  const adaHapus = jumlahDihapus.coa + jumlahDihapus.jurnal + jumlahDihapus.kas > 0;
  catatAudit({
    pelaku: u.pengguna,
    aksi: adaHapus ? 'akuntansi.hapus' : 'akuntansi.ubah',
    sasaran: 'coa,jurnal,kas',
    catatan: adaHapus
      ? jumlahDihapus.coa + ' akun, ' + jumlahDihapus.jurnal + ' jurnal, ' + jumlahDihapus.kas + ' transaksi kas dihapus'
      : bersih.coa.length + ' akun, ' + bersih.jurnal.length + ' jurnal, ' + bersih.kas.length + ' transaksi kas diperbarui',
  });
  kirim(res, 200, bersih);
});


// Pengelolaan informasi warga: pengumuman dan kegiatan.
function teksKonten(nilai, nama, batas, wajib = false) {
  const hasil = String(nilai === undefined || nilai === null ? '' : nilai).trim();
  if (wajib && !hasil) throw new GalatPengguna(nama + ' wajib diisi.');
  if (hasil.length > batas) throw new GalatPengguna(nama + ' maksimal ' + batas + ' karakter.');
  return hasil;
}

function validasiKonten(jenis, data, lama = {}) {
  if (!['informasi', 'kegiatan', 'kontak', 'link'].includes(jenis)) throw new GalatPengguna('Jenis konten tidak dikenal.');
  const gabung = { ...lama, ...(data || {}) };
  if (jenis === 'link') {
    // Link Penting: URL opsional (entri lama bisa dulu tanpa alamat), bila diisi
    // harus http(s). Selalu terbit; hapus = permanen (cabang di rute DELETE).
    const url = teksKonten(gabung.url, 'URL', 500);
    if (url && !/^https?:\/\/\S+/i.test(url)) throw new GalatPengguna('URL harus diawali http:// atau https://.');
    return {
      nama: teksKonten(gabung.nama, 'Nama link', 80, true),
      url,
      ikon: teksKonten(gabung.ikon, 'Ikon', 12),
      status: 'terbit',
    };
  }
  const status = teksKonten(gabung.status || 'draf', 'Status', 12, true);
  if (!['draf', 'terbit', 'arsip'].includes(status)) throw new GalatPengguna('Status konten tidak dikenal.');
  if (jenis === 'kontak') {
    const telepon = teksKonten(gabung.telepon, 'Nomor telepon', 20, true);
    if (!/^\+?[0-9][0-9\s().-]{1,18}[0-9]$/.test(telepon) || telepon.replace(/\D/g, '').length < 3) {
      throw new GalatPengguna('Nomor telepon hanya boleh berisi angka dan tanda pemisah yang wajar.');
    }
    return {
      jabatan: teksKonten(gabung.jabatan, 'Jabatan', 120, true),
      nama: teksKonten(gabung.nama, 'Nama', 120, true),
      telepon, catatan: teksKonten(gabung.catatan, 'Catatan', 240), status,
    };
  }
  const tanggal = teksKonten(gabung.tanggal, 'Tanggal', 10, true);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(tanggal) ||
      !Number.isFinite(Date.parse(tanggal + 'T00:00:00Z')) ||
      new Date(tanggal + 'T00:00:00Z').toISOString().slice(0, 10) !== tanggal) {
    throw new GalatPengguna('Tanggal harus berupa tanggal kalender yang sah.');
  }
  const hasil = { judul: teksKonten(gabung.judul, 'Judul', 160, true), tanggal, status };
  if (jenis === 'informasi') {
    hasil.ringkasan = teksKonten(gabung.ringkasan, 'Ringkasan', 300);
    hasil.isi = teksKonten(gabung.isi, 'Isi informasi', 4000);
  } else {
    hasil.lokasi = teksKonten(gabung.lokasi, 'Lokasi', 160);
    hasil.waktu = teksKonten(gabung.waktu, 'Waktu', 80);
    hasil.deskripsi = teksKonten(gabung.deskripsi, 'Deskripsi kegiatan', 2000);
  }
  return hasil;
}

DAFTAR(/^\/api\/konten$/, 'GET', (req, res) => {
  const u = penggunaSesi(req);
  const bolehKelola = !!u && u.aktif !== false && boleh(u.peran, 'pengumuman.kelola');
  kirim(res, 200, { konten: ambilKonten(bolehKelola), bolehKelola });
});

DAFTAR(/^\/api\/konten$/, 'POST', (req, res, data) => {
  const u = wajibIzin(req, res, 'pengumuman.kelola');
  if (!u) return;
  const jenis = String(data.jenis || '');
  const bersih = validasiKonten(jenis, data);
  const waktu = new Date().toISOString();
  const baru = { id: randomUUID(), ...bersih, dibuat: waktu, diubah: waktu };
  simpanKonten(jenis, [baru, ...ambilKonten(true)[jenis]]);
  catatAudit({ pelaku: u.pengguna, aksi: 'konten.' + jenis + '.buat', sasaran: baru.id, catatan: baru.judul || (baru.jabatan ? baru.jabatan + ' — ' + baru.nama : baru.nama) });
  kirim(res, 201, { item: baru });
});

DAFTAR(/^\/api\/konten\/(informasi|kegiatan|kontak|link)\/([0-9a-f-]{36})$/i, 'PATCH', (req, res, data, cocok) => {
  const u = wajibIzin(req, res, 'pengumuman.kelola');
  if (!u) return;
  const jenis = cocok[1].toLowerCase();
  const id = cocok[2];
  const daftar = ambilKonten(true)[jenis];
  const index = daftar.findIndex((item) => item.id === id);
  if (index < 0) return kirim(res, 404, { galat: 'Konten tidak ditemukan.' });
  const perubahan = validasiKonten(jenis, data, daftar[index]);
  const hasil = { ...daftar[index], ...perubahan, diubah: new Date().toISOString() };
  daftar[index] = hasil;
  simpanKonten(jenis, daftar);
  catatAudit({ pelaku: u.pengguna, aksi: 'konten.' + jenis + '.ubah', sasaran: id, catatan: hasil.judul || (hasil.jabatan ? hasil.jabatan + ' — ' + hasil.nama : hasil.nama) });
  kirim(res, 200, { item: hasil });
});

DAFTAR(/^\/api\/konten\/(informasi|kegiatan|kontak|link)\/([0-9a-f-]{36})$/i, 'DELETE', (req, res, _data, cocok) => {
  const u = wajibIzin(req, res, 'pengumuman.kelola');
  if (!u) return;
  const jenis = cocok[1].toLowerCase();
  const id = cocok[2];
  const daftar = ambilKonten(true)[jenis];
  const index = daftar.findIndex((item) => item.id === id);
  if (index < 0) return kirim(res, 404, { galat: 'Konten tidak ditemukan.' });
  if (jenis === 'link') {
    // Link Penting dihapus permanen (bukan arsip) — daftar kecil & sengaja dihapus.
    const [buang] = daftar.splice(index, 1);
    simpanKonten(jenis, daftar);
    catatAudit({ pelaku: u.pengguna, aksi: 'konten.link.hapus', sasaran: id, catatan: buang.nama || '' });
    return kirim(res, 200, { ok: true, item: buang });
  }
  daftar[index] = { ...daftar[index], status: 'arsip', diubah: new Date().toISOString() };
  simpanKonten(jenis, daftar);
  catatAudit({ pelaku: u.pengguna, aksi: 'konten.' + jenis + '.arsip', sasaran: id, catatan: daftar[index].judul || (daftar[index].jabatan + ' — ' + daftar[index].nama) });
  kirim(res, 200, { ok: true, item: daftar[index] });
});

// --- UMKM & iklan warga (direktori usaha) ---
// Baca publik; tambah/ubah/hapus terkunci izin pengaturan.kelola (admin
// saja - sengaja, agar pengurus tidak ikut mengelola data UMKM).
// Setiap perubahan tercatat di audit log.
function teksUmkm(nilai, nama, batas, wajib = false) {
  const teks = String(nilai === undefined || nilai === null ? '' : nilai).trim();
  if (wajib && !teks) throw new GalatPengguna(nama + ' wajib diisi.');
  if (teks.length > batas) throw new GalatPengguna(nama + ' maksimal ' + batas + ' karakter.');
  return teks;
}

function validasiUmkm(data, lama = {}) {
  const gabung = { ...lama, ...(data || {}) };
  const whatsapp = teksUmkm(gabung.whatsapp, 'Nomor WhatsApp', 25);
  if (whatsapp && !/^[0-9+\s()-.]{5,25}$/.test(whatsapp)) {
    throw new GalatPengguna('Nomor WhatsApp hanya boleh berisi angka dan tanda pemisah yang wajar.');
  }
  return {
    nama: teksUmkm(gabung.nama, 'Nama usaha', 80, true),
    kategori: teksUmkm(gabung.kategori, 'Kategori', 40, true),
    pemilik: teksUmkm(gabung.pemilik, 'Nama pemilik', 80),
    blok: teksUmkm(gabung.blok, 'Blok', 10),
    icon: teksUmkm(gabung.icon, 'Ikon', 8) || '🏪',
    whatsapp,
    deskripsi: teksUmkm(gabung.deskripsi, 'Deskripsi', 300),
  };
}

DAFTAR(/^\/api\/umkm$/, 'GET', (req, res) => {
  const u = penggunaSesi(req);
  const bolehKelola = !!u && u.aktif !== false && boleh(u.peran, 'pengaturan.kelola');
  const daftar = ambilUmkm().umkm
    .filter((x) => bolehKelola || (x && x.aktif !== false))
    .map((x) => ({ ...x }));
  kirim(res, 200, { umkm: daftar, bolehKelola });
});

DAFTAR(/^\/api\/umkm$/, 'POST', (req, res, data) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  const bersih = validasiUmkm(data);
  const waktu = new Date().toISOString();
  const baru = { id: randomUUID(), ...bersih, aktif: true, terverifikasi: true, dibuat: waktu, diubah: waktu };
  aturUmkm([baru, ...ambilUmkm().umkm]);
  catatAudit({ pelaku: u.pengguna, aksi: 'umkm.tambah', sasaran: baru.id, catatan: baru.nama + ' — ' + baru.kategori });
  kirim(res, 201, { item: baru });
});

DAFTAR(/^\/api\/umkm\/([^/]+)$/, 'PATCH', (req, res, data, cocok) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  const id = cocok[1];
  const daftar = ambilUmkm().umkm;
  const index = daftar.findIndex((x) => x && String(x.id) === id);
  if (index < 0) return kirim(res, 404, { galat: 'UMKM tidak ditemukan.' });
  const perubahan = validasiUmkm(data, daftar[index]);
  const hasil = { ...daftar[index], ...perubahan, diubah: new Date().toISOString() };
  daftar[index] = hasil;
  aturUmkm(daftar);
  catatAudit({ pelaku: u.pengguna, aksi: 'umkm.ubah', sasaran: id, catatan: hasil.nama + ' — ' + hasil.kategori });
  kirim(res, 200, { item: hasil });
});

DAFTAR(/^\/api\/umkm\/([^/]+)$/, 'DELETE', (req, res, _data, cocok) => {
  const u = wajibIzin(req, res, 'pengaturan.kelola');
  if (!u) return;
  const id = cocok[1];
  const daftar = ambilUmkm().umkm;
  const index = daftar.findIndex((x) => x && String(x.id) === id);
  if (index < 0) return kirim(res, 404, { galat: 'UMKM tidak ditemukan.' });
  const [buang] = daftar.splice(index, 1);
  aturUmkm(daftar);
  catatAudit({ pelaku: u.pengguna, aksi: 'umkm.hapus', sasaran: id, catatan: (buang && buang.nama) || '' });
  kirim(res, 200, { ok: true, item: buang });
});

// --- Aduan warga ---
// Alur: warga membuat (menunggu) -> pengurus menyetujui (open) -> pengurus
// menutup (closed) atau menghapus permanen. Setelah disetujui, aduan tampil
// di dasbor semua warga; yang masih menunggu hanya terlihat oleh pelapornya
// sendiri dan pengurus/admin. Pengelolaan memakai izin pengaduan.kelola
// (pengurus & admin); pembuatan memakai pengaduan.buat (semua peran).
const KATEGORI_ADUAN = ['Fasilitas & Perlengkapan', 'Keamanan', 'Kebersihan & Lingkungan', 'Sosial & Warga', 'Iuran & Keuangan', 'Lainnya'];

function validasiAduan(data, lama = {}) {
  const gabung = { ...lama, ...(data || {}) };
  const kategori = teksUmkm(gabung.kategori, 'Kategori', 40, true);
  return {
    judul: teksUmkm(gabung.judul, 'Judul aduan', 120, true),
    kategori: KATEGORI_ADUAN.includes(kategori) ? kategori : 'Lainnya',
    isi: teksUmkm(gabung.isi, 'Isi aduan', 1000, true),
    lokasi: teksUmkm(gabung.lokasi, 'Lokasi', 120),
  };
}

DAFTAR(/^\/api\/aduan$/, 'GET', (req, res) => {
  const u = wajibMasuk(req, res);
  if (!u) return;
  const bolehKelola = boleh(u.peran, 'pengaduan.kelola');
  const daftar = ambilAduan().aduan
    .filter((a) => bolehKelola || (a && (a.status !== 'menunggu' || a.pelaporId === u.id)))
    .map((a) => ({ ...a }));
  kirim(res, 200, { aduan: daftar, bolehKelola });
});

DAFTAR(/^\/api\/aduan$/, 'POST', (req, res, data) => {
  const u = wajibIzin(req, res, 'pengaduan.buat');
  if (!u) return;
  const bersih = validasiAduan(data);
  const waktu = new Date().toISOString();
  const baru = {
    id: randomUUID(),
    ...bersih,
    status: 'menunggu',
    pelapor: u.nama || u.pengguna,
    pelaporId: u.id,
    blok: u.blok || '',
    catatanTutup: '',
    dibuat: waktu,
    diubah: waktu,
  };
  aturAduan([baru, ...ambilAduan().aduan]);
  catatAudit({ pelaku: u.pengguna, aksi: 'aduan.buat', sasaran: baru.id, catatan: baru.judul });
  kirim(res, 201, { item: baru });
});

DAFTAR(/^\/api\/aduan\/([^/]+)$/, 'PATCH', (req, res, data, cocok) => {
  const u = wajibIzin(req, res, 'pengaduan.kelola');
  if (!u) return;
  const id = cocok[1];
  const aksi = String(data.aksi || '');
  const daftar = ambilAduan().aduan;
  const index = daftar.findIndex((a) => a && String(a.id) === id);
  if (index < 0) return kirim(res, 404, { galat: 'Aduan tidak ditemukan.' });
  const lama = daftar[index];
  const waktu = new Date().toISOString();
  const hasil = { ...lama, diubah: waktu };
  if (aksi === 'setujui') {
    if (lama.status !== 'menunggu') return kirim(res, 400, { galat: 'Hanya aduan berstatus menunggu yang bisa disetujui.' });
    hasil.status = 'open';
    hasil.disetujuiOleh = u.pengguna;
    hasil.disetujuiPada = waktu;
  } else if (aksi === 'tutup') {
    if (lama.status !== 'open') return kirim(res, 400, { galat: 'Hanya aduan berstatus open yang bisa ditutup.' });
    hasil.status = 'closed';
    hasil.catatanTutup = teksUmkm(data.catatan, 'Catatan penutup', 300);
    hasil.ditutupOleh = u.pengguna;
    hasil.ditutupPada = waktu;
  } else if (aksi === 'buka') {
    if (lama.status !== 'closed') return kirim(res, 400, { galat: 'Hanya aduan berstatus closed yang bisa dibuka kembali.' });
    hasil.status = 'open';
    hasil.catatanTutup = '';
    hasil.ditutupOleh = '';
    hasil.ditutupPada = '';
  } else {
    return kirim(res, 400, { galat: 'Aksi tidak dikenal. Gunakan: setujui, tutup, atau buka.' });
  }
  daftar[index] = hasil;
  aturAduan(daftar);
  catatAudit({ pelaku: u.pengguna, aksi: 'aduan.' + aksi, sasaran: id, catatan: hasil.judul + ' -> ' + hasil.status });
  kirim(res, 200, { item: hasil });
});

DAFTAR(/^\/api\/aduan\/([^/]+)$/, 'DELETE', (req, res, _data, cocok) => {
  const u = wajibIzin(req, res, 'pengaduan.kelola');
  if (!u) return;
  const id = cocok[1];
  const daftar = ambilAduan().aduan;
  const index = daftar.findIndex((a) => a && String(a.id) === id);
  if (index < 0) return kirim(res, 404, { galat: 'Aduan tidak ditemukan.' });
  const [buang] = daftar.splice(index, 1);
  aturAduan(daftar);
  catatAudit({ pelaku: u.pengguna, aksi: 'aduan.hapus', sasaran: id, catatan: (buang && buang.judul) || '' });
  kirim(res, 200, { ok: true, item: buang });
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
