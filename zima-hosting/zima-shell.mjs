#!/usr/bin/env node
// ============================================================
// zima-shell.mjs - menjalankan perintah shell di host ZimaOS
// ============================================================
// Kenapa lewat WebSocket, bukan lewat halaman terminalnya langsung?
// Antarmuka ttyd memakai canvas xterm: screenshot sering tertinggal satu
// langkah dan kadang berhenti compositing, jadi mengetik lewat browser tidak
// dapat diandalkan. WebSocket-nya memberi keluaran teks biasa yang bisa
// ditunggu dengan penanda unik.
//
// Pemakaian:
//   ZIMA_PASS=... node zima-hosting/zima-shell.mjs "uname -a" "docker ps"
//   ZIMA_PASS=... CMD_FILE=daftar-perintah.txt node zima-hosting/zima-shell.mjs
//   ZIMA_PASS=... node zima-hosting/zima-shell.mjs \
//     --upload zima-hosting/situs/index.html /DATA/AppData/zima-hosting/situs/index.html
//
// Di Git Bash (Windows), awali dengan MSYS_NO_PATHCONV=1 supaya jalur tujuan
// seperti /DATA/... tidak diubah menjadi jalur Windows (C:/Program Files/...).
//
// --upload <lokal> <tujuan>  mengirim berkas ke host (dipotong sebagai base64),
//   mencadangkan berkas tujuan lebih dulu ({tujuan}.bak-TANGGALJAM), lalu menimpa
//   dengan `tee` agar pemilik dan izin berkas lama tetap terjaga. Berkas situs
//   tidak perlu restart apa pun: caddy membacanya langsung dari folder yang
//   di-mount.
//
// Variabel lingkungan:
//   ZIMA_PASS  (wajib)  sandi akun ZimaOS
//   ZIMA_USER  (opsional, bawaan "hendra")
//   TTYD_URL   (opsional, bawaan "ws://192.168.145.252:7681/ws")
//   CMD_FILE   (opsional) berkas berisi satu perintah per baris
//   SUDO_PRIME (bawaan "1")  jalankan `sudo -v` dulu supaya tidak terputus
//                            oleh permintaan sandi di tengah jalan
//
// Catatan: docker di ZimaOS butuh root, jadi perintah docker harus
// berawalan `sudo`. Sandi sudo ditulis otomatis saat prompt "Password:" muncul.
//
// Protokol ttyd 1.7 (dari berkas kliennya, sudah diverifikasi):
//   1. upgrade WebSocket wajib memakai subprotokol "tty";
//   2. frame PERTAMA harus JSON {"AuthToken":"","columns":..,"rows":..};
//   3. sesudah itu semua frame biner: byte awal '0' = input, '1' = resize;
//   4. keluaran server juga biner dengan awalan '0'.
// ============================================================

import { readFileSync } from 'node:fs';

const WS_URL = process.env.TTYD_URL ?? 'ws://192.168.145.252:7681/ws';
const USER = process.env.ZIMA_USER ?? 'hendra';
const PASS = process.env.ZIMA_PASS;
const CMD_FILE = process.env.CMD_FILE ?? '';
const SUDO_PRIME = (process.env.SUDO_PRIME ?? '1') !== '0';

const argv = process.argv.slice(2);
const commands = [];
const uploads = [];

for (let i = 0; i < argv.length; i += 1) {
  if (argv[i] === '--upload') {
    const local = argv[i + 1];
    const remote = argv[i + 2];
    if (!local || !remote) {
      console.error('--upload butuh dua argumen: <berkas-lokal> <tujuan-di-host>');
      process.exit(2);
    }
    uploads.push({ local, remote });
    i += 2;
  } else {
    commands.push(argv[i]);
  }
}

if (CMD_FILE) {
  commands.push(
    ...readFileSync(CMD_FILE, 'utf8')
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith('#')),
  );
}

// Ubah setiap --upload menjadi rangkaian perintah: kirim potongan base64,
// uraikan sekali untuk memeriksa ukurannya, cadangkan tujuan, lalu timpa.
for (const [i, up] of uploads.entries()) {
  const b64 = readFileSync(up.local).toString('base64');
  const tmp = `/tmp/zima-put-${i}.b64`;
  commands.push(`rm -f ${tmp}`);
  for (let p = 0; p < b64.length; p += 1500) {
    commands.push(`echo -n '${b64.slice(p, p + 1500)}' >> ${tmp}`);
  }
  commands.push(`base64 -d ${tmp} > ${tmp}.out && wc -c ${tmp}.out`);
  // Catatan: tanda $(date ...) HARUS di luar tanda kutip tunggal. Kalau
  // ditulis di dalamnya, shell jarak jauh tidak mengekspansinya dan yang
  // lahir justru berkas bernama harfiah "...bak-$(date +%F-%H%M)".
  commands.push(`TT=$(date +%F-%H%M); [ -f '${up.remote}' ] && sudo cp -a '${up.remote}' '${up.remote}.bak-'$TT && echo CADANGAN_OK || echo TANPA_CADANGAN`);
  commands.push(`base64 -d ${tmp} | sudo tee '${up.remote}' > /dev/null && echo TERPASANG: ${up.remote}`);
  commands.push(`ls -l '${up.remote}'`);
}

if (!PASS || !commands.length) {
  console.error(
    'usage: ZIMA_PASS=... node zima-hosting/zima-shell.mjs "<perintah>" [...]\n' +
      '   atau: ZIMA_PASS=... CMD_FILE=berkas.txt node zima-hosting/zima-shell.mjs',
  );
  process.exit(2);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const enc = new TextEncoder();

let buf = '';
let answered = 0;
const ws = new WebSocket(WS_URL, 'tty');
ws.binaryType = 'arraybuffer';

const send = (text) => ws.send(enc.encode('0' + text));

// Setiap prompt sandi (login getty maupun sudo) dijawab otomatis, jadi
// rangkaian perintah tidak pernah berhenti menunggu ketikan.
function answerPrompts() {
  const seen = (buf.match(/[Pp]assword:/g) ?? []).length;
  while (answered < seen && answered < 8) {
    answered += 1;
    send(PASS + '\r');
  }
}

ws.addEventListener('message', (ev) => {
  let data = ev.data;
  if (typeof data !== 'string') data = Buffer.from(data).toString('utf8');
  if (!data.startsWith('0')) return;
  const text = data.slice(1);
  buf += text;
  process.stdout.write(text);
  answerPrompts();
});
ws.addEventListener('close', () => process.stdout.write('\n[ws closed]\n'));
ws.addEventListener('error', () => process.stdout.write('\n[ws error]\n'));

const opened = new Promise((resolve, reject) => {
  ws.addEventListener('open', () => resolve());
  ws.addEventListener('error', () => reject(new Error('websocket error')));
  ws.addEventListener('close', () => reject(new Error('websocket closed')));
});

async function waitFor(re, timeoutMs, label) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (re.test(buf)) return;
    answerPrompts();
    await sleep(120);
  }
  throw new Error(`timeout ${timeoutMs}ms menunggu ${label}`);
}

// Penanda dibuat dari dua potongan kutipan berdekatan, jadi teks penanda
// hanya muncul pada keluaran asli - bukan pada gema baris perintahnya.
async function step(index, command) {
  const marker = `__DONE_${index}__`;
  process.stdout.write(`\n>>> ${command}\n`);
  send(`${command}; echo "__DONE_""${index}__"\r`);
  await waitFor(new RegExp(marker), 180000, `penanda ${marker}`);
  await sleep(200);
}

try {
  await opened;
  ws.send(enc.encode(JSON.stringify({ AuthToken: '', columns: 240, rows: 60 })));
  await sleep(400);

  process.stdout.write(`>>> login sebagai ${USER}\n`);
  await waitFor(/login:\s*$/, 20000, 'prompt login');
  send(USER + '\r');
  await waitFor(/➜/, 30000, 'prompt shell');
  await sleep(400);

  if (SUDO_PRIME) {
    send('sudo -v; echo "__SUDO_""READY__"\r');
    await waitFor(/__SUDO_READY__/, 60000, 'sudo siap');
    await sleep(200);
  }

  for (const [i, cmd] of commands.entries()) await step(i, cmd);

  process.stdout.write('\n*** SELESAI ***\n');
  ws.close();
  process.exit(0);
} catch (err) {
  process.stdout.write(`\n*** GAGAL: ${err.message} ***\n`);
  process.exit(1);
}
