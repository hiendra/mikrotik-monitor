#!/usr/bin/env node
// ============================================================
// deployer.js - jembatan aman panel-kelola.html -> ZimaOS
// ============================================================
// Dijalankan di ZimaOS sebagai container (zima-deployer). Tugasnya:
//   1. menerima Caddyfile dari panel (wajib Bearer token)
//   2. memvalidasi dengan `caddy validate` (container sesaat yang tidak
//      menyentuh router yang sedang berjalan)
//   3. memasang berkas lalu restart container web-router
//   4. memeriksa kesehatan; bila Caddy gagal hidup, berkas lama
//      dipulihkan otomatis dan restart lagi (rollback)
//   5. menulis situs/layanan.json (manifest dasbor) SETELAH router sehat,
//      supaya kartu di clusternet.my.id tidak pernah mendahului rutenya
//
// Agar langkah 5 bekerja, container ini perlu mount tulis ke folder situs
// dan folder itu di-mount read-only oleh Caddy:
//   volumes:
//     - ./Caddyfile:/data/Caddyfile
//     - ./situs:/data/situs
//   environment:
//     - SITUS_TARGET=/data/situs/layanan.json   # bawaan, boleh dihilangkan
// Bila volume itu belum ada, langkah 5 gagal dengan sopan dan deploy tetap
// dianggap berhasil - tanpa itu, satu berkas dasbor bisa memblokir rute baru.
//
// Keamanan:
//   - token wajib (header Authorization: Bearer <TOKEN>); nilai sama
//     dengan DEPLOY_TOKEN di .env.deploy-token milik stack hosting
//   - port dipublikasikan hanya untuk LAN (panel berjalan di PC), dan
//     setiap permintaan tetap harus membawa token yang benar
// ============================================================
import http from 'node:http';
import { execFile, spawnSync } from 'node:child_process';
import { writeFile, copyFile, access, constants } from 'node:fs/promises';
import { dirname } from 'node:path';

const PORT = 3000;
const TARGET = '/data/Caddyfile';        // mount read-write dari ./Caddyfile host
const CADY_REF = '/data/.Caddyfile.bak'; // salinan untuk rollback
const SITUS_TARGET = (process.env.SITUS_TARGET || '/data/situs/layanan.json').trim();
const TOKEN = (process.env.DEPLOY_TOKEN || '').trim();
const MAX_BODY = 256 * 1024;             // Caddyfile realistis jauh di bawah ini

if (!TOKEN) {
  console.error('DEPLOY_TOKEN belum diisi - menolak jalan tanpa token.');
  process.exit(1);
}

const exec = (cmd, args, timeoutMs = 60000) =>
  new Promise((resolve) => {
    execFile(cmd, args, { timeout: timeoutMs }, (err, stdout, stderr) =>
      resolve({ ok: !err, out: `${stdout}${stderr}`.trim() }),
    );
  });

const docker = (args, timeoutMs) => exec('docker', args, timeoutMs);

async function caddyValidate(teks) {
  // Container sesaat: teks dikirim lewat stdin (-i), tanpa port, tanpa
  // menyentuh router yang berjalan. Container dihapus otomatis (--rm).
  const r = spawnSync(
    'docker',
    ['run', '--rm', '-i', 'caddy:2-alpine', 'caddy', 'validate', '--adapter', 'caddyfile', '--config', '/dev/stdin'],
    { input: teks, timeout: 60000, encoding: 'utf8' },
  );
  return {
    ok: r.status === 0 && !r.error,
    out: `${r.stdout || ''}${r.stderr || ''}`.trim(),
  };
}

function kirim(res, kode, objek) {
  const body = JSON.stringify(objek);
  res.writeHead(kode, {
    'Content-Type': 'application/json; charset=utf-8',
    // panel berjalan di origin berbeda (PC pengguna) - token tetap wajib,
    // jadi CORS terbuka di sini tidak membuka akses tanpa kunci
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
  });
  res.end(body);
}

const server = http.createServer(async (req, res) => {
  // preflight CORS dari panel
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
      'Access-Control-Max-Age': '86400',
    });
    return res.end();
  }

  // ---- autentikasi ----
  const auth = req.headers.authorization || '';
  if (auth !== 'Bearer ' + TOKEN) {
    return kirim(res, 401, { ok: false, error: 'token salah atau tidak ada' });
  }

  // ---- ping (cek hidup dari panel) ----
  if (req.method === 'GET' && req.url === '/ping') {
    const ps = await docker(['ps', '--format', '{{.Names}} {{.Status}}']);
    // Apakah manifest dasbor bisa ditulis? Kalau volume ./situs belum
    // di-mount, panel perlu tahu lebih awal - bukan setelah menekan Terapkan.
    const dasbor = await access(dirname(SITUS_TARGET), constants.W_OK).then(() => true).catch(() => false);
    return kirim(res, 200, { ok: true, layanan: 'zima-deployer', docker: ps.ok, dasbor });
  }

  // ---- deploy ----
  if (req.method === 'POST' && req.url === '/deploy') {
    let body = '';
    let kebesaran = false;
    req.on('data', (c) => {
      body += c;
      if (body.length > MAX_BODY) { kebesaran = true; req.destroy(); }
    });
    req.on('end', async () => {
      if (kebesaran) return;
      try {
        const { caddyfile, layanan } = JSON.parse(body);
        if (typeof caddyfile !== 'string' || caddyfile.trim().length < 20) {
          return kirim(res, 400, { ok: false, error: 'isi caddyfile kosong/terlalu pendek' });
        }

        // 0) simpan salinan lama untuk rollback
        await copyFile(TARGET, CADY_REF).catch(() => {});

        // 1) validasi sebelum menyentuh apa pun
        const v = await caddyValidate(caddyfile);
        if (!v.ok) {
          return kirim(res, 422, {
            ok: false,
            tahap: 'validasi',
            error: 'Caddyfile ditolak oleh `caddy validate`',
            detail: (v.out || '').slice(0, 2000),
          });
        }

        // 2) pasang berkas baru
        await writeFile(TARGET, caddyfile, 'utf8');

        // 3) restart router
        const rs = await docker(['restart', 'web-router'], 90000);
        if (!rs.ok) {
          // pulihkan segera bila restart sendiri gagal
          await copyFile(CADY_REF, TARGET).catch(() => {});
          await docker(['restart', 'web-router'], 90000);
          return kirim(res, 500, { ok: false, tahap: 'restart', error: 'docker restart gagal', detail: rs.out, rollback: true });
        }

        // 4) periksa kesehatan: container masih Up beberapa detik kemudian
        await new Promise((r) => setTimeout(r, 5000));
        const cek = await docker(['ps', '--filter', 'name=web-router', '--format', '{{.Status}}']);
        const up = cek.ok && /^Up/.test(cek.out.trim());
        if (!up) {
          await copyFile(CADY_REF, TARGET).catch(() => {});
          await docker(['restart', 'web-router'], 90000);
          const log = await docker(['logs', '--tail', '30', 'web-router'], 30000);
          return kirim(res, 500, {
            ok: false,
            tahap: 'kesehatan',
            error: 'web-router tidak sehat setelah deploy - dikembalikan ke konfigurasi lama',
            detail: (log.out || '').slice(0, 2000),
            rollback: true,
          });
        }

        // 5) manifest dasbor. Sengaja SETELAH pemeriksaan kesehatan: dasbor
        //    hanya boleh memamerkan layanan yang rutenya benar-benar hidup.
        //    Kegagalan di sini tidak menggagalkan deploy - volume ./situs bisa
        //    saja belum di-mount, dan itu tidak ada hubungannya dengan Caddy.
        let manifest = 'tidak dikirim';
        if (typeof layanan === 'string' && layanan.trim()) {
          try {
            const isi = JSON.parse(layanan);
            const daftar = Array.isArray(isi) ? isi : isi.layanan;
            if (!Array.isArray(daftar)) throw new Error('manifest tidak memuat larik "layanan"');
            await writeFile(SITUS_TARGET, JSON.stringify(isi, null, 2) + '\n', 'utf8');
            manifest = 'ok';
          } catch (e) {
            manifest = String(e).slice(0, 200);
          }
        }

        return kirim(res, 200, {
          ok: true,
          pesan: 'Caddyfile terpasang, web-router sudah restart dan sehat.',
          manifest,
        });
      } catch (e) {
        return kirim(res, 500, { ok: false, error: 'kesalahan tak terduga', detail: String(e).slice(0, 500) });
      }
    });
    return;
  }

  kirim(res, 404, { ok: false, error: 'rute tidak dikenal (pakai GET /ping atau POST /deploy)' });
});

server.listen(PORT, () => console.log('zima-deployer siap di port ' + PORT));
