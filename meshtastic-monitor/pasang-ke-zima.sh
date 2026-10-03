#!/usr/bin/env bash
# ============================================================
# pasang-ke-zima.sh - kirim & pasang meshtastic-monitor ke host ZimaOS
# ============================================================
# Menjalankan tiga hal sekaligus, dari mesin Windows ini:
#   1. mengemas folder ini jadi satu berkas tar.gz (tanpa venv/cache);
#   2. mengunggahnya ke host ZimaOS lewat zima-hosting/zima-shell.mjs;
#   3. mengekstrak ke $TUJUAN lalu menjalankan pasang-layanan.sh di sana
#      (exporter + notifier; TIMER RESET sengaja tidak dipasang).
#
# Pakai (dari akar repo, di Git Bash):
#   ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/pasang-ke-zima.sh
#
# Sandi TIDAK disimpan di berkas ini dan tidak boleh ditulis ke repo. Isi hanya
# lewat variabel lingkungan pada baris perintah.
#
# Lingkungan:
#   ZIMA_PASS   (wajib)  sandi akun ZimaOS, dipakai menjawab prompt sudo
#   ZIMA_HOST   (opsional, bawaan 192.168.20.36) host ZimaOS dari LAN
#   TTYD_URL    (opsional, bawaan ws://$ZIMA_HOST:7681/ws)
#   MESH_DIR    (opsional, bawaan /DATA/AppData/meshtastic-monitor)
#   MESH_PASANG_TIMER / MESH_PASANG_BERSIH / MESH_HAPUS_HARI
#               (opsional) diteruskan apa adanya ke pasang-layanan.sh di host,
#               mis. MESH_PASANG_BERSIH=1 agar timer bersih-bersih NodeDB ikut
#               dipasang. Tanpa penerusan ini, opsi tersebut harus disetel
#               manual di host - dan mudah dikira sudah jalan padahal belum.
#
# Kenapa lewat WebSocket ttyd dan bukan SSH? Itu jalur yang sudah terbukti di
# repo ini (zima-hosting/CATATAN-KENDALA.md), dan tidak butuh kunci SSH.
# Jebakan yang sudah diketahui: MSYS/Git Bash mengubah argumen berawalan "/"
# menjadi path Windows, jadi MSYS_NO_PATHCONV wajib disetel (lihat di bawah).
# ============================================================
set -eu

ZIMA_HOST=${ZIMA_HOST:-192.168.20.36}
TTYD_URL=${TTYD_URL:-ws://$ZIMA_HOST:7681/ws}
TUJUAN=${MESH_DIR:-/DATA/AppData/meshtastic-monitor}
PAKET_JAUH=/tmp/meshtastic-monitor.tgz

# Jebakan MSYS: tanpa ini, "/tmp/..." dan "/DATA/..." berubah jadi "C:/...".
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

if [ -z "${ZIMA_PASS:-}" ]; then
  echo "ZIMA_PASS belum diset."
  echo "Jalankan:  ZIMA_PASS='sandi-akun-ZimaOS' sh $0"
  exit 1
fi

AKAR=$(cd "$(dirname "$0")/.." && pwd)
SUMBER="$AKAR/meshtastic-monitor"
# Jalur zima-shell.mjs (jalur unggah lewat WebSocket ttyd). Bisa ditimpa lewat
# variabel lingkungan; tanpa bawaan ini, skrip mati di baris pertama karena
# `set -u` dan $SHELL_JS yang belum diisi.
SHELL_JS=${SHELL_JS:-$AKAR/zima-hosting/zima-shell.mjs}

# Node di Windows TIDAK mengenal jalur gaya MSYS (/c/temp/...) - ia mencari
# C:\c\temp\... dan gagal dengan MODULE_NOT_FOUND. Karena skrip ini sengaja
# mematikan konversi jalur otomatis (MSYS_NO_PATHCONV) supaya jalur tujuan
# seperti /DATA tetap utuh, jalur yang diserahkan KE NODE harus diubah sendiri.
# cygpath -m menghasilkan bentuk campuran (C:/temp/...) yang dimengerti node;
# di Linux/macOS fungsinya tidak ada dan jalur dipakai apa adanya.
ke_node() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}
# Arsip dibuat DI LUAR folder sumber; kalau ditulis di dalamnya, tar mengeluh
# "file changed as we read it" dan bisa gagal di tengah jalan.
TMP_LOKAL=${TMPDIR:-/tmp}
PAKET="$TMP_LOKAL/meshtastic-monitor-deploy.tgz"

if [ ! -f "$SHELL_JS" ]; then
  echo "Tidak menemukan $SHELL_JS (dijalankan dari akar repo?)."
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "node tidak ada di PATH."
  exit 1
fi

echo "=== 1. mengemas $SUMBER ==="
rm -f "$PAKET"
# ARTEFAK RUNTIME WAJIB DIKELUARKAN. Berkas *state.json adalah catatan milik
# MESIN YANG MENJALANKAN, bukan sumber. Kalau ikut terkirim, setiap penerapan
# menimpa catatan notifier di host dengan catatan dari mesin ini - dan
# akibatnya sejumlah alarm PALSU yang tampak seperti kejadian sungguhan:
#   * `gateway.reboot_count` yang lama -> "Gateway baru saja reboot" berbunyi
#     (terbukti 28 Sep 2026: dilaporkan "bertambah 8" DUA kali, padahal uptime
#     gateway naik terus dan tidak pernah putus),
#   * `node` yang kosong -> semua node yang sudah offline dilaporkan offline lagi,
#   * daftar `favorit_dilaporkan` yang lama -> saran Favorite terulang.
# Karena itu *state.json dan *.log dikeluarkan, dan sesudahnya DIPERIKSA -
# kegagalan senyap di jalur ini memang pernah lolos tanpa ketahuan.
#
tar czf "$PAKET" \
  --exclude='./venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.csv' \
  --exclude='*.log' \
  --exclude='*state.json' \
  --exclude='reset-terakhir.json' \
  --exclude='.tmp-*' \
  -C "$SUMBER" .
JUMLAH=$(tar tzf "$PAKET" | wc -l)
echo "  ukuran: $(wc -c < "$PAKET") byte, $JUMLAH entri"
if tar tzf "$PAKET" | grep -q '^./venv/'; then
  echo "PERINGATAN: venv ikut terbawa (seharusnya tidak)."
fi
SISA=$(tar tzf "$PAKET" | grep -E '\.(log)$|state\.json$|catat-node\.csv$' || true)
if [ -n "$SISA" ]; then
  echo "GAGAL: artefak runtime ikut terbawa - ini akan menimpa catatan di host"
  echo "       dan memicu alarm palsu. Isi paket yang bermasalah:"
  printf '%s\n' "$SISA" | sed 's/^/         /'
  echo "       Perbaiki daftar --exclude di skrip ini, jangan lanjutkan."
  exit 1
fi
echo "  bersih: tidak ada artefak runtime (state/log) yang ikut terbawa"

echo
echo "=== 2. mengunggah ke $ZIMA_HOST ==="
TTYD_URL="$TTYD_URL" ZIMA_PASS="$ZIMA_PASS" \
  node "$(ke_node "$SHELL_JS")" --upload "$(ke_node "$PAKET")" "$PAKET_JAUH"

echo "=== 3. memasang di host ==="
# Opsi pemasangan diteruskan ke pasang-layanan.sh DI HOST. Ini perlu karena
# `sudo` mereset lingkungan: tanpa `env` di sini, `MESH_PASANG_BERSIH=1 sh
# pasang-ke-zima.sh` akan sampai ke host sebagai tanpa opsi apa pun, dan timer
# tidak terpasang padahal niatnya memasang. (sudo sendiri dijalankan DI DALAM
# zima-shell.mjs, bukan sebagai argumen dari mesin ini.)
LANJUT=""
for nama in MESH_PASANG_TIMER MESH_PASANG_BERSIH MESH_HAPUS_HARI; do
  eval "nilai=\${$nama:-}"
  [ -n "$nilai" ] && LANJUT="$LANJUT $nama=$nilai"
done
if [ -n "$LANJUT" ]; then
  echo "  opsi diteruskan ke pasang-layanan.sh:$LANJUT"
  PERINTAH="sudo env$LANJUT sh '$TUJUAN/pasang-layanan.sh'"
else
  PERINTAH="sudo sh '$TUJUAN/pasang-layanan.sh'"
fi

TTYD_URL="$TTYD_URL" ZIMA_PASS="$ZIMA_PASS" node "$(ke_node "$SHELL_JS")" \
  "sudo mkdir -p '$TUJUAN'" \
  "sudo tar xzf '$PAKET_JAUH' -C '$TUJUAN'" \
  "sudo rm -f '$PAKET_JAUH'" \
  "ls -l '$TUJUAN' | head -30" \
  "$PERINTAH"

rm -f "$PAKET"
echo
echo "=== selesai ==="
echo "Periksa dari LAN:"
echo "  curl -s http://$ZIMA_HOST:9208/metrics | head"
echo "  buka http://$ZIMA_HOST:9208/"
echo
echo "Bila exporter belum hidup, lihat log:"
echo "  journalctl -u meshtastic-exporter -n 50 --no-pager"
