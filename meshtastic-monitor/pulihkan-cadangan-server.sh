#!/usr/bin/env bash
# ============================================================
# pulihkan-cadangan-server.sh - kembalikan SATU berkas di host ZimaOS dari
# cadangan bertanggal yang ada di folder yang sama.
# ============================================================
# Dipakai untuk membatalkan penerapan yang salah: sebelum menimpa, berkas yang
# SEKARANG dipakai disalin lebih dulu ke <nama>.sebelum-pulih-<stempel>, jadi
# pemulihan ini sendiri masih bisa dibatalkan.
#
# Jalurnya sama dengan pasang-ke-zima.sh: lewat WebSocket ttyd (zima-shell.mjs),
# tanpa kunci SSH. Sandi hanya lewat variabel lingkungan pada baris perintah.
#
# Pakai (dari akar repo, di Git Bash):
#   ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/pulihkan-cadangan-server.sh \
#       exporter-meshtastic.py.bak-20261001-085424 exporter-meshtastic.py
#
# Lingkungan:
#   ZIMA_PASS  (wajib) sandi akun ZimaOS
#   ZIMA_HOST  (opsional, bawaan 192.168.20.36)
#   TTYD_URL   (opsional, bawaan ws://$ZIMA_HOST:7681/ws)
#   MESH_DIR   (opsional, bawaan /DATA/AppData/meshtastic-monitor)
#   LAYANAN    (opsional, bawaan meshtastic-exporter) unit systemd yang
#              dimulai ulang sesudah pemulihan
#   SHELL_JS   (opsional) jalur zima-hosting/zima-shell.mjs
# ============================================================
set -eu

CADANGAN=${1:?sebutkan nama berkas cadangan, mis. exporter-meshtastic.py.bak-20261001-085424}
SASARAN=${2:-exporter-meshtastic.py}
LAYANAN=${LAYANAN:-meshtastic-exporter}

ZIMA_HOST=${ZIMA_HOST:-192.168.20.36}
TTYD_URL=${TTYD_URL:-ws://$ZIMA_HOST:7681/ws}
TUJUAN=${MESH_DIR:-/DATA/AppData/meshtastic-monitor}

# Jebakan MSYS: tanpa ini, "/DATA/..." berubah menjadi path Windows.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

if [ -z "${ZIMA_PASS:-}" ]; then
  echo "ZIMA_PASS belum diset."
  echo "Jalankan:  ZIMA_PASS='sandi-akun-ZimaOS' sh $0 <berkas-cadangan>"
  exit 1
fi

AKAR=$(cd "$(dirname "$0")/.." && pwd)
SHELL_JS=${SHELL_JS:-$AKAR/zima-hosting/zima-shell.mjs}

# Jalur yang diserahkan KE NODE harus bentuk yang dimengerti node di Windows.
ke_node() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi
}
if [ ! -f "$SHELL_JS" ]; then
  echo "Tidak menemukan $SHELL_JS (dijalankan dari akar repo?)."
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  echo "node tidak ada di PATH."
  exit 1
fi

STEMPEL=$(date +%Y%m%d-%H%M%S)
SIMPAN="$SASARAN.sebelum-pulih-$STEMPEL"

echo "=== memulihkan $SASARAN dari $CADANGAN ==="
echo "    folder : $TUJUAN"
echo "    cadangan berkas sekarang -> $SIMPAN"
echo

# `|| true` dipakai pada baris grep: hitungan nol membuat grep keluar dengan
# kode 1, dan itu akan dianggap kegagalan padahal hasilnya justru yang benar.
TTYD_URL="$TTYD_URL" ZIMA_PASS="$ZIMA_PASS" node "$(ke_node "$SHELL_JS")" \
  "cd '$TUJUAN' && { test -f '$CADANGAN' || { echo 'CADANGAN TIDAK ADA: $CADANGAN'; exit 1; }; }" \
  "cd '$TUJUAN' && sudo cp -p '$SASARAN' '$SIMPAN' && sudo cp -p '$CADANGAN' '$SASARAN' && ls -la --time-style=+%m-%d_%H:%M '$SASARAN' '$SIMPAN'" \
  "cd '$TUJUAN' && echo '--- penanda peta (harus 0) ---' && { grep -c 'data-tab' '$SASARAN' || true; }" \
  "cd '$TUJUAN' && echo '--- fungsi trace/favorit (harus > 0) ---' && { grep -cE '^def (_bentuk_jalur_trace|_laksana_trace|laksana_perintah)' '$SASARAN' || true; }" \
  "sudo systemctl restart '$LAYANAN' && sleep 3 && systemctl is-active '$LAYANAN'"

echo
echo "=== selesai ==="
echo "  berkas yang tadi dipakai disimpan sebagai: $SIMPAN"
echo "  periksa:  curl -s https://meshid.clusternet.my.id/ | grep -c data-tab   (harus 0)"
