// ============================================================
// penyimpanan.mjs - pengguna, sandi (scrypt), sesi, dan audit log
// ============================================================
// Sengaja TANPA dependensi npm: hanya modul bawaan Node (node:fs,
// node:crypto). Alasannya praktis - host ZimaOS tidak punya Node, jadi
// layanan ini berjalan di container `node:22-alpine` dengan folder sumber
// yang di-mount. Tanpa node_modules, tidak ada langkah `npm install` yang
// bisa gagal karena jaringan atau arsitektur.
//
// Berkas data (di volume /data, di luar web root):
//   /data/pengguna.json   daftar akun + hash sandi
//   /data/audit.json      catatan tindakan penting (maksimal 500 entri)
//   /data/AWAL.txt        sandi admin pertama (hanya dibuat sekali)
//
// Sesi hidup di memori saja: restart container = semua orang keluar. Itu
// pilihan sadar - menaruh token sesi di berkas menambah permukaan serangan
// tanpa manfaat nyata untuk skala satu lingkungan warga.
// ============================================================

import { randomBytes, scryptSync, timingSafeEqual, randomUUID } from 'node:crypto';
import { readFileSync, writeFileSync, renameSync, mkdirSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const DATA = process.env.DATA_DIR || '/data';
const F_PENGGUNA = join(DATA, 'pengguna.json');
const F_AUDIT = join(DATA, 'audit.json');
const F_AWAL = join(DATA, 'AWAL.txt');

const MAKS_AUDIT = 500;
const UMUR_SESI_MS = 12 * 60 * 60 * 1000; // 12 jam

mkdirSync(DATA, { recursive: true });

// ---------------------------------------------------------------
// Tulis atomik: tulis ke berkas sementara lalu rename. Kalau container
// mati di tengah penulisan, berkas asli tetap utuh (rename bersifat atomik
// di sistem berkas yang sama).
// ---------------------------------------------------------------
function tulisAtomik(jalur, isi) {
  const tmp = `${jalur}.tmp-${process.pid}`;
  writeFileSync(tmp, isi, { mode: 0o600 });
  renameSync(tmp, jalur);
}

function bacaJson(jalur, bawaan) {
  try {
    return JSON.parse(readFileSync(jalur, 'utf8'));
  } catch {
    return bawaan;
  }
}

// ---------------------------------------------------------------
// Sandi: scrypt + garam acak per akun.
// ---------------------------------------------------------------
const PANJANG_KUNCI = 64;
const OPSI_SCRYPT = { N: 16384, r: 8, p: 1, maxmem: 64 * 1024 * 1024 };

export function acakSandi(panjang = 10) {
  // Alfabet tanpa karakter yang mudah tertukar (0/O, 1/l/I).
  const alfabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789';
  const bita = randomBytes(panjang);
  let keluar = '';
  for (let i = 0; i < panjang; i += 1) keluar += alfabet[bita[i] % alfabet.length];
  return keluar;
}

export function hashSandi(sandi, garam = randomBytes(16).toString('hex')) {
  const kunci = scryptSync(String(sandi), garam, PANJANG_KUNCI, OPSI_SCRYPT).toString('hex');
  return { garam, kunci };
}

export function cocokSandi(sandi, garam, kunciTersimpan) {
  try {
    const kunci = scryptSync(String(sandi), garam, PANJANG_KUNCI, OPSI_SCRYPT);
    const tersimpan = Buffer.from(kunciTersimpan, 'hex');
    if (kunci.length !== tersimpan.length) return false;
    return timingSafeEqual(kunci, tersimpan);
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------
// Pengguna
// ---------------------------------------------------------------
let pengguna = bacaJson(F_PENGGUNA, null);

function simpan() {
  tulisAtomik(F_PENGGUNA, JSON.stringify(pengguna, null, 2));
}

/** Bentuk aman untuk dikirim ke klien: TANPA hash/garam sandi. */
export function penggunaAman(u) {
  if (!u) return null;
  return {
    id: u.id,
    pengguna: u.pengguna,
    nama: u.nama,
    peran: u.peran,
    jabatan: u.jabatan || '',
    blok: u.blok || '',
    rt: u.rt || '',
    rw: u.rw || '',
    no_hp: u.no_hp || '',
    aktif: u.aktif !== false,
    harus_ganti_sandi: !!u.harus_ganti_sandi,
    dibuat: u.dibuat,
    terakhir_masuk: u.terakhir_masuk || null,
  };
}

export function cariId(id) {
  return pengguna.find((u) => u.id === id) || null;
}

export function cariNama(nama) {
  const n = String(nama || '').trim().toLowerCase();
  return pengguna.find((u) => u.pengguna.toLowerCase() === n) || null;
}

export function daftarPengguna() {
  return pengguna
    .slice()
    .sort((a, b) => a.pengguna.localeCompare(b.pengguna, 'id'))
    .map(penggunaAman);
}

function buatId() {
  return randomUUID();
}

export function tambahPengguna({ pengguna: nama, sandi, nama: namaLengkap, peran, jabatan, blok, rt, rw, no_hp, aktif = true, harusGanti = true }) {
  const namaBersih = String(nama || '').trim();
  if (!/^[a-zA-Z0-9._-]{3,32}$/.test(namaBersih)) {
    throw new GalatPengguna('Nama pengguna harus 3-32 karakter (huruf, angka, titik, garis bawah, atau tanda hubung).');
  }
  if (cariNama(namaBersih)) throw new GalatPengguna('Nama pengguna itu sudah dipakai.');
  if (String(sandi || '').length < 8) throw new GalatPengguna('Sandi minimal 8 karakter.');

  const { garam, kunci } = hashSandi(sandi);
  const baru = {
    id: buatId(),
    pengguna: namaBersih,
    nama: String(namaLengkap || namaBersih).trim(),
    peran,
    jabatan: jabatan || '',
    blok: blok || '',
    rt: rt || '',
    rw: rw || '',
    no_hp: no_hp || '',
    aktif: aktif !== false,
    harus_ganti_sandi: harusGanti !== false,
    sandi_garam: garam,
    sandi_kunci: kunci,
    dibuat: new Date().toISOString(),
    terakhir_masuk: null,
  };
  pengguna.push(baru);
  simpan();
  return baru;
}

export function ubahPengguna(id, ubah) {
  const u = cariId(id);
  if (!u) throw new GalatPengguna('Pengguna tidak ditemukan.');
  const bidang = ['nama', 'jabatan', 'blok', 'rt', 'rw', 'no_hp'];
  for (const b of bidang) {
    if (ubah[b] !== undefined) u[b] = String(ubah[b]);
  }
  if (ubah.aktif !== undefined) u.aktif = !!ubah.aktif;
  if (ubah.peran !== undefined) u.peran = ubah.peran;
  simpan();
  return u;
}

export function hapusPengguna(id) {
  const i = pengguna.findIndex((u) => u.id === id);
  if (i === -1) throw new GalatPengguna('Pengguna tidak ditemukan.');
  const [dihapus] = pengguna.splice(i, 1);
  simpan();
  return dihapus;
}

export function setSandi(id, sandi, harusGanti = false) {
  const u = cariId(id);
  if (!u) throw new GalatPengguna('Pengguna tidak ditemukan.');
  if (String(sandi || '').length < 8) throw new GalatPengguna('Sandi minimal 8 karakter.');
  const { garam, kunci } = hashSandi(sandi);
  u.sandi_garam = garam;
  u.sandi_kunci = kunci;
  u.harus_ganti_sandi = !!harusGanti;
  simpan();
  return u;
}

export function tandaiMasuk(id) {
  const u = cariId(id);
  if (u) {
    u.terakhir_masuk = new Date().toISOString();
    simpan();
  }
}

export function jumlahPengguna() {
  return pengguna.length;
}

export function jumlahAdminAktif() {
  return pengguna.filter((u) => u.peran === 'admin' && u.aktif !== false).length;
}

// ---------------------------------------------------------------
// Sesi (memori)
// ---------------------------------------------------------------
const sesi = new Map(); // token -> { id, kedaluwarsa }

export function buatSesi(idPengguna) {
  const token = randomBytes(32).toString('hex');
  sesi.set(token, { id: idPengguna, kedaluwarsa: Date.now() + UMUR_SESI_MS });
  return token;
}

export function sesiValid(token) {
  if (!token) return null;
  const s = sesi.get(token);
  if (!s) return null;
  if (s.kedaluwarsa < Date.now()) {
    sesi.delete(token);
    return null;
  }
  return cariId(s.id);
}

export function hapusSesi(token) {
  sesi.delete(token);
}

export function hapusSemuaSesi(idPengguna) {
  for (const [token, s] of sesi) if (s.id === idPengguna) sesi.delete(token);
}

// Pembersih sesi kedaluwarsa (dipanggil berkala, bukan per permintaan).
export function bersihkanSesi() {
  const kini = Date.now();
  for (const [token, s] of sesi) if (s.kedaluwarsa < kini) sesi.delete(token);
}

// ---------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------
let audit = bacaJson(F_AUDIT, []);

export function catatAudit({ pelaku, aksi, sasaran, catatan }) {
  audit.unshift({
    waktu: new Date().toISOString(),
    pelaku: pelaku || 'sistem',
    aksi,
    sasaran: sasaran || '',
    catatan: catatan || '',
  });
  if (audit.length > MAKS_AUDIT) audit.length = MAKS_AUDIT;
  tulisAtomik(F_AUDIT, JSON.stringify(audit, null, 2));
}

export function daftarAudit(batas = 100) {
  return audit.slice(0, Math.max(1, Math.min(Number(batas) || 100, MAKS_AUDIT)));
}

// ---------------------------------------------------------------
// Pengaturan situs (master iuran, ambang approval, pengaturan lain bebas)
// Satu berkas JSON di volume /data; baca-tulis lewat API admin saja
// (izin pengaturan.kelola di server.mjs).
// ---------------------------------------------------------------
const F_PENGATURAN = join(DATA, 'pengaturan.json');
let pengaturan = bacaJson(F_PENGATURAN, null);

/** Ambil pengaturan tersimpan; nilai bawaan diisi dari field yang belum ada. */
export function ambilPengaturan(bawaan) {
  if (pengaturan && typeof pengaturan === 'object') return { ...bawaan, ...pengaturan };
  return bawaan;
}

/** Timpa pengaturan lalu tulis atomik ke /data/pengaturan.json. */
export function aturPengaturan(data) {
  pengaturan = data;
  tulisAtomik(F_PENGATURAN, JSON.stringify(pengaturan, null, 2));
  return pengaturan;
}

export class GalatPengguna extends Error {}

// ---------------------------------------------------------------
// Data pembayaran & akuntansi (dibaca-saja lewat /api/pembayaran dan
// /api/akuntansi, izin pengaturan.kelola). Dipindah dari berkas JSON
// di web root yang dulu TERBACA PUBLIK tanpa login.
// ---------------------------------------------------------------
const F_PEMBAYARAN = join(DATA, 'pembayaran.json');
const F_AKUNTANSI = join(DATA, 'akuntansi.json');

function bacaData(jalur, bawaan) {
  const isi = bacaJson(jalur, null);
  if (isi && typeof isi === 'object' && !Array.isArray(isi)) return isi;
  return bawaan;
}

export function ambilPembayaran() {
  return bacaData(F_PEMBAYARAN, { rekening: [], qris: [], status: [] });
}

/** Simpan daftar metode tanpa mengubah QRIS/status dan data pembayaran lain. */
export function aturMetodePembayaran(rekening) {
  const pembayaran = ambilPembayaran();
  pembayaran.rekening = rekening.map((item) => ({ ...item }));
  tulisAtomik(F_PEMBAYARAN, JSON.stringify(pembayaran, null, 2));
  return pembayaran;
}

// Catatan pengajuan pembayaran per akun dan periode, disimpan privat di volume.
const F_TAGIHAN = join(DATA, 'tagihan-warga.json');
export function ambilTagihanWarga() {
  const data = bacaData(F_TAGIHAN, { transaksi: [] });
  return { transaksi: Array.isArray(data.transaksi) ? data.transaksi : [] };
}
export function aturTagihanWarga(transaksi) {
  const data = { transaksi: transaksi.map((item) => ({ ...item })) };
  tulisAtomik(F_TAGIHAN, JSON.stringify(data, null, 2));
  return data;
}

// Daftar rumah/kk per blok - dahulu berkas warga.json di web root yang
// TERBACA PUBLIK tanpa login (audit 2026-10-09); kini privat di volume
// dan hanya dilayani lewat /api/warga (izin datawarga.lihat).
const F_WARGA = join(DATA, 'warga.json');
export function ambilRosterWarga() {
  const data = bacaJson(F_WARGA, null);
  return data && typeof data === 'object' && Array.isArray(data.warga) ? data : null;
}

// Direktori UMKM & iklan warga — daftar usaha yang tampil di bagian
// 🏪 UMKM. Kelola khusus admin lewat /api/umkm (lihat server.mjs).
const F_UMKM = join(DATA, 'umkm.json');
export function ambilUmkm() {
  const data = bacaData(F_UMKM, { umkm: [] });
  return { umkm: Array.isArray(data.umkm) ? data.umkm : [] };
}
export function aturUmkm(daftar) {
  const data = { umkm: daftar.map((item) => ({ ...item })) };
  tulisAtomik(F_UMKM, JSON.stringify(data, null, 2));
  return data;
}

// Direktori Aduan Warga — alur: warga membuat (menunggu) -> pengurus
// menyetujui (open) -> ditutup (closed) atau dihapus (lihat server.mjs).
const F_ADUAN = join(DATA, 'aduan.json');
export function ambilAduan() {
  const data = bacaData(F_ADUAN, { aduan: [] });
  return { aduan: Array.isArray(data.aduan) ? data.aduan : [] };
}
export function aturAduan(daftar) {
  const data = { aduan: daftar.map((item) => ({ ...item })) };
  tulisAtomik(F_ADUAN, JSON.stringify(data, null, 2));
  return data;
}

export function ambilAkuntansi() {
  return bacaData(F_AKUNTANSI, { coa: [], jurnal: [], kas: [] });
}

export function aturAkuntansi(data) {
  tulisAtomik(F_AKUNTANSI, JSON.stringify(data, null, 2));
  return data;
}

// ---------------------------------------------------------------
// Bootstrap: buat admin pertama bila belum ada pengguna sama sekali.
// Sandi dibuat acak lalu ditulis SEKALI ke /data/AWAL.txt, dan akun itu
// ditandai harus_ganti_sandi sehingga wajib diganti saat pertama masuk.
// ---------------------------------------------------------------
export function bootstrap() {
  if (Array.isArray(pengguna) && pengguna.length > 0) return { dibuat: false };
  pengguna = [];
  const sandi = acakSandi(12);
  const admin = tambahPengguna({
    pengguna: 'admin',
    sandi,
    nama: 'Admin Sistem',
    peran: 'admin',
    jabatan: 'Super Admin',
    rt: '-',
    rw: '-',
    harusGanti: true,
  });
  const isiCatatan = [
    'AKUN ADMIN PERTAMA - tamanmarina.my.id',
    '',
    '  Pengguna : admin',
    `  Sandi    : ${sandi}`,
    '',
    'Sandi ini hanya ditulis sekali. Segera masuk lewat /masuk lalu ganti',
    'sandi (sistem akan memaksa), lalu HAPUS berkas ini:',
    '  rm /data/AWAL.txt',
    '',
    `Dibuat: ${new Date().toISOString()}`,
    '',
  ].join('\n');
  tulisAtomik(F_AWAL, isiCatatan);
  catatAudit({ pelaku: 'sistem', aksi: 'bootstrap.admin', sasaran: admin.id, catatan: 'Akun admin pertama dibuat otomatis.' });
  return { dibuat: true, sandi, jalurCatatan: F_AWAL };
}


// Konten warga: pengumuman dan kegiatan. Tersimpan di volume privat /data.
const F_KONTEN = join(DATA, 'konten.json');
// 'link' = Link Penting (bagian Kontak Pengurus); kelola oleh pengurus & admin.
const JENIS_KONTEN = ['informasi', 'kegiatan', 'kontak', 'link'];
let konten = bacaJson(F_KONTEN, { informasi: [], kegiatan: [], kontak: [], link: [] });
if (!konten || typeof konten !== 'object' || Array.isArray(konten)) {
  konten = { informasi: [], kegiatan: [], kontak: [], link: [] };
}
for (const jenis of JENIS_KONTEN) {
  if (!Array.isArray(konten[jenis])) konten[jenis] = [];
}

export function ambilKonten(termasukNonaktif = false) {
  const hasil = { informasi: [], kegiatan: [], kontak: [], link: [] };
  for (const jenis of JENIS_KONTEN) {
    hasil[jenis] = konten[jenis]
      .filter((item) => termasukNonaktif || item.status === 'terbit')
      .map((item) => ({ ...item }));
  }
  return hasil;
}

export function simpanKonten(jenis, daftar) {
  if (!JENIS_KONTEN.includes(jenis) || !Array.isArray(daftar)) {
    throw new GalatPengguna('Jenis atau daftar konten tidak sah.');
  }
  konten = { ...konten, [jenis]: daftar.map((item) => ({ ...item })) };
  tulisAtomik(F_KONTEN, JSON.stringify(konten, null, 2));
  return ambilKonten(true)[jenis];
}
