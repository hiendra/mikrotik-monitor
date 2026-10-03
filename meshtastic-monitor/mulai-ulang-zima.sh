#!/usr/bin/env bash
# ============================================================
# mulai-ulang-zima.sh - nyalakan ulang layanan Meshtastic di host ZimaOS
# ============================================================
# Dipakai saat halaman produksi memuat kerangka halaman TETAPI TANPA node
# ("hidup tetapi buta"): proses exporter masih berjalan dan port 9208 tetap
# melayani, tetapi sambungannya ke gateway sudah mati dan pustaka meshtastic
# tidak memulihkannya sendiri. Satu restart sudah cukup memulihkannya.
#
# Berbeda dari pasang-ke-zima.sh, skrip ini TIDAK mengunggah apa pun - ia
# hanya memerintah host menyalakan ulang unit yang diminta lalu melaporkan
# keadaannya. Jadi aman dipakai kapan saja, juga saat berkas lokal sedang
# setengah jadi.
#
# Pakai (dari akar repo, di Git Bash):
#   ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/mulai-ulang-zima.sh
#   ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/mulai-ulang-zima.sh \
#       meshtastic-notif.service
#
# Lingkungan:
#   ZIMA_PASS   (wajib)  sandi akun ZimaOS, dipakai menjawab prompt sudo
#   ZIMA_HOST   (opsional, bawaan 192.168.20.36) host ZimaOS dari LAN
#   TTYD_URL    (opsional, bawaan ws://$ZIMA_HOST:7681/ws)
#   MESH_PORT   (opsional, bawaan 9208) port HTTP exporter untuk uji petik
# ============================================================
set -eu

ZIMA_HOST=${ZIMA_HOST:-192.168.20.36}
TTYD_URL=${TTYD_URL:-ws://$ZIMA_HOST:7681/ws}
UNIT=${1:-meshtastic-exporter.service}
MESH_PORT=${MESH_PORT:-9208}

# Jebakan MSYS: tanpa ini, "/tmp/..." dan "/DATA/..." berubah jadi "C:/...".
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

if [ -z "${ZIMA_PASS:-}" ]; then
  echo "ZIMA_PASS belum diset."
  echo "Jalankan:  ZIMA_PASS='sandi-akun-ZimaOS' sh $0 [unit]"
  exit 1
fi

AKAR=$(cd "$(dirname "$0")/.." && pwd)
SHELL_JS=${SHELL_JS:-$AKAR/zima-hosting/zima-shell.mjs}

# Node di Windows tidak mengenal jalur gaya MSYS (/c/temp/...); ia mencari
# C:\c\temp\... dan gagal. cygpath -m menuliskan bentuk campuran yang
# dimengerti node, dan di Linux/macOS fungsinya tidak ada.
ke_node() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -m "$1"
  else
    printf '%s\n' "$1"
  fi
}

if [ ! -f "$SHELL_JS" ]; then
  echo "Tidak menemukan $SHELL_JS (dijalankan dari akar repo?)."
  exit 1
fi

echo "=== menyalakan ulang $UNIT di $ZIMA_HOST ==="
TTYD_URL="$TTYD_URL" ZIMA_PASS="$ZIMA_PASS" node "$(ke_node "$SHELL_JS")" \
  "sudo systemctl restart '$UNIT'" \
  "sleep 8; systemctl is-active '$UNIT'; systemctl show -p MainPID -p ActiveEnterTimestamp -p NRestarts '$UNIT'" \
  "curl -s http://127.0.0.1:$MESH_PORT/data.json | head -c 400" \
  "curl -s http://127.0.0.1:$MESH_PORT/metrics | grep -E 'exporter_up|cuplikan_umur'"

echo
echo "=== selesai ==="
echo "Bila halaman masih kosong, lihat log:"
echo "  journalctl -u $UNIT -n 50 --no-pager"
