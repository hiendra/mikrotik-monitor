#!/usr/bin/env node
// ============================================================
// tautan-balik-grafana.mjs - tombol pulang di dalam Grafana
// ============================================================
// Grafana tidak bisa disisipi HTML seperti situs statis, tetapi setiap dasbor
// punya daftar `links` yang tampil di bar atas dasbor. Skrip ini menambahkan
// satu tautan "Kembali ke ClusterNet" ke SEMUA dasbor, sehingga dari Grafana
// selalu ada jalan pulang ke dasbor layanan di clusternet.my.id.
//
// Aman dijalankan berulang kali (idempoten): bila tautan yang sama sudah ada,
// tidak ditambahkan dua kali. Dijalankan dari PC, bukan dari server, dan
// menyentuh hanya dasbor - bukan datasource, pengguna, atau pengaturan lain.
//
// Pemakaian:
//   node zima-hosting/tautan-balik-grafana.mjs
//   node zima-hosting/tautan-balik-grafana.mjs --kering   (hanya melaporkan)
//
// Variabel lingkungan (semuanya opsional):
//   GRAFANA_URL   bawaan http://192.168.145.252:3003
//   GRAFANA_USER  bawaan admin
//   GRAFANA_PASS  bawaan admin123
//   GRAFANA_LINK  bawaan https://clusternet.my.id
// ============================================================

const BASE = (process.env.GRAFANA_URL ?? 'http://192.168.145.252:3003').replace(/\/+$/, '');
const USER = process.env.GRAFANA_USER ?? 'admin';
const PASS = process.env.GRAFANA_PASS ?? 'admin123';
const TUJUAN = process.env.GRAFANA_LINK ?? 'https://clusternet.my.id';
const JUDUL = 'Kembali ke ClusterNet';
const KERING = process.argv.includes('--kering');

const AUTH = 'Basic ' + Buffer.from(`${USER}:${PASS}`).toString('base64');
const KEPALA = { Authorization: AUTH, 'Content-Type': 'application/json' };

const tautanBaru = () => ({
  type: 'link',
  title: JUDUL,
  url: TUJUAN,
  targetBlank: true,
  icon: 'external link',
  tooltip: 'Dasbor layanan ClusterNet',
  keepTime: false,
  includeVars: false,
});

async function ambilJson(jalur, opsi) {
  const r = await fetch(jalur, opsi);
  const data = await r.json().catch(() => ({}));
  return { status: r.status, data };
}

const katalog = await ambilJson(`${BASE}/api/search?type=dash-db`, { headers: { Authorization: AUTH } });
if (katalog.status !== 200 || !Array.isArray(katalog.data)) {
  console.error(`Gagal membaca daftar dasbor dari ${BASE} (HTTP ${katalog.status}).`);
  console.error('Periksa GRAFANA_URL / GRAFANA_USER / GRAFANA_PASS.');
  process.exit(1);
}
if (!katalog.data.length) {
  console.log('Tidak ada dasbor di Grafana - tidak ada yang perlu diubah.');
  process.exit(0);
}

let diubah = 0;
for (const item of katalog.data) {
  const { status, data } = await ambilJson(`${BASE}/api/dashboards/uid/${item.uid}`, {
    headers: { Authorization: AUTH },
  });
  if (status !== 200 || !data.dashboard) {
    console.log(`[LEWAT] ${item.title}: tidak bisa dibaca (HTTP ${status}).`);
    continue;
  }

  const dasbor = data.dashboard;
  const sudahAda = (dasbor.links ?? []).some((l) => l && l.url === TUJUAN);
  if (sudahAda) {
    console.log(`[SUDAH ADA] ${item.title} (uid ${item.uid})`);
    continue;
  }

  if (KERING) {
    console.log(`[AKAN DIUBAH] ${item.title} (uid ${item.uid})`);
    diubah += 1;
    continue;
  }

  dasbor.links = [...(dasbor.links ?? []), tautanBaru()];
  // `meta` adalah keluaran baca-saja; mengirimnya kembali akan ditolak Grafana.
  delete dasbor.meta;

  const simpan = await ambilJson(`${BASE}/api/dashboards/db`, {
    method: 'POST',
    headers: KEPALA,
    body: JSON.stringify({
      dashboard: dasbor,
      overwrite: true,
      message: `Tautan balik ke dasbor layanan ClusterNet (${TUJUAN})`,
    }),
  });
  if (simpan.status === 200 && simpan.data.status === 'success') {
    console.log(`[DIPASANG] ${item.title} (uid ${item.uid}, versi ${simpan.data.version})`);
    diubah += 1;
  } else {
    console.log(`[GAGAL] ${item.title}: HTTP ${simpan.status} ${simpan.data.message ?? simpan.data.error ?? ''}`);
  }
}

console.log('');
console.log(KERING
  ? `Selesai (mode kering): ${diubah} dasbor akan diubah.`
  : `Selesai: ${diubah} dasbor diubah dari ${katalog.data.length} dasbor.`);
