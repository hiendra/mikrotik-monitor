// ============================================================
// izin.mjs - peran, level, dan matriks izin Taman Marina
// ============================================================
// Tiga peran sesuai permintaan pemilik:
//   warga    -> kebutuhan pribadi (iuran sendiri, pengaduan, forum, UMKM)
//   pengurus -> kebutuhan pengelolaan RT/RW (data warga, verifikasi iuran,
//               laporan, kelola pengumuman & UMKM, BUAT akun warga)
//   admin    -> kebutuhan sistem (kelola semua pengguna, ubah peran,
//               pengaturan, audit log, hapus akun)
//
// Iz induk bersifat KUMULATIF: admin otomatis memiliki semua izin pengurus,
// pengurus memiliki semua izin warga. Jadi menambah izin ke pengurus juga
// menambahkannya ke admin tanpa perlu diedit dua kali.
//
// Ini satu-satunya sumber kebenaran izin. Frontend hanya MENAMPILKAN hasilnya
// (/api/saya mengirim daftar izin), tetapi setiap permintaan tetap diperiksa
// ulang di server - menyembunyikan tombol bukan pengamanan.
// ============================================================

export const PERAN = ['warga', 'pengurus', 'admin'];

// Dipakai untuk membandingkan kedudukan: hanya peran berlevel lebih TINGGI
// (atau admin) yang boleh mengubah pengguna berlevel lebih rendah.
export const LEVEL = { warga: 1, pengurus: 2, admin: 3 };

// Izin yang DIMILIKI LANGSUNG oleh tiap peran (sebelum diwarisi).
const IZIN_LANGSUNG = {
  warga: [
    'dasbor.lihat',
    'profil.lihat',
    'iuran.lihat',
    'pengaduan.buat',
    'forum.tulis',
    'umkm.daftar',
    'dokumen.unduh',
  ],
  pengurus: [
    'datawarga.lihat',
    'iuran.verifikasi',
    'laporan.lihat',
    'pengumuman.kelola',
    'umkm.kelola',
    'pengguna.lihat',
    'pengguna.buat',
    // Pengurus boleh mengurus akun WARGA (ubah data, nonaktifkan, reset
    // sandi) - tetapi TIDAK boleh mengubah peran atau menghapus akun.
    // Batas itu dijaga peranYangBolehDiatur() + izin peran.ubah/pengguna.hapus
    // yang hanya dimiliki admin.
    'pengguna.kelola',
  ],
  admin: [
    'pengguna.kelola',
    'pengguna.hapus',
    'peran.ubah',
    'pengaturan.kelola',
    'audit.lihat',
    'sistem.kelola',
  ],
};

// Urutan warisan: warga <- pengurus <- admin
const WARISAN = { warga: [], pengurus: ['warga'], admin: ['pengurus'] };

const PETA = new Map();
for (const peran of PERAN) {
  const kumpulan = new Set();
  const telusuri = (p) => {
    for (const induk of WARISAN[p] || []) telusuri(induk);
    for (const i of IZIN_LANGSUNG[p] || []) kumpulan.add(i);
  };
  telusuri(peran);
  PETA.set(peran, kumpulan);
}

/** Daftar izin efektif (sudah termasuk warisan) untuk sebuah peran. */
export function izinPeran(peran) {
  return [...(PETA.get(peran) || new Set())];
}

/** Apakah sebuah peran punya izin tertentu. */
export function boleh(peran, izin) {
  const kumpulan = PETA.get(peran);
  return !!kumpulan && kumpulan.has(izin);
}

/** Label manusiawi per peran (dipakai di UI & audit log). */
export const LABEL_PERAN = {
  warga: 'Warga',
  pengurus: 'Pengurus',
  admin: 'Admin',
};

/**
 * Kebutuhan/izin yang membedakan tiap peran - dikirim ke frontend supaya
 * halaman Kelola Pengguna bisa menjelaskan bedanya tanpa menyalin daftar.
 */
export function ringkasPeran() {
  const judul = {
    warga: 'Kebutuhan pribadi warga',
    pengurus: 'Kebutuhan pengelolaan RT/RW',
    admin: 'Kebutuhan sistem & keamanan',
  };
  return PERAN.map((peran) => ({
    peran,
    label: LABEL_PERAN[peran],
    level: LEVEL[peran],
    judul: judul[peran],
    izin: izinPeran(peran),
    // izin yang BARU pada peran ini (bukan warisan) - inilah "kebutuhan berbeda"
    izinKhas: [...(IZIN_LANGSUNG[peran] || [])],
  }));
}

/** Peran apa saja yang boleh diatur oleh sebuah peran. */
export function peranYangBolehDiatur(peranPengelola) {
  if (peranPengelola === 'admin') return PERAN.slice();
  if (peranPengelola === 'pengurus') return ['warga']; // pengurus hanya membuat/mengelola akun warga
  return [];
}
