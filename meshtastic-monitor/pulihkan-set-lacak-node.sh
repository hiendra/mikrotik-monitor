#!/usr/bin/env bash
# ============================================================
# pulihkan-set-lacak-node.sh - kembalikan set "lacak node" ke folder produksi
# ============================================================
# Latar: folder /DATA/AppData/meshtastic-monitor dipakai bersama beberapa
# pekerjaan, dan `exporter-meshtastic.py` di sana pernah tertimpa. Modul
# pendukung `lacak_halaman.py` / `lacak_node.py` masih ada, tetapi versi
# `lacak_halaman.py` yang tersisa TIDAK punya `halaman_peta` - jadi
# memulihkan exporter saja akan gagal. Karena itu tiga berkas dipulihkan
# bersama sebagai satu set yang cocok (exporter memanggil kedua modul itu).
#
# Yang TIDAK disentuh: lacak.sqlite3 (berisi riwayat pelacakan), folder
# leaflet/, dan berkas uji.
#
# Dua pengaman:
#   1. setiap berkas yang akan ditimpa disalin lebih dulu ke
#      <nama>.sebelum-lacak-<stempel>;
#   2. layanan BARU dimulai ulang kalau modulnya lolos impor - kalau impor
#      gagal, layanan lama dibiarkan jalan (tidak jadi makai kode rusak).
#
# Pakai (dari akar repo, di Git Bash):
#   ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/pulihkan-set-lacak-node.sh
#
# Lingkungan: ZIMA_PASS (wajib), ZIMA_HOST, TTYD_URL, MESH_DIR, SUMBER, LAYANAN
# ============================================================
set -eu

SUMBER=${SUMBER:-/DATA/AppData/opencode/projects/lacak-node/work}
ZIMA_HOST=${ZIMA_HOST:-192.168.20.36}
TTYD_URL=${TTYD_URL:-ws://$ZIMA_HOST:7681/ws}
TUJUAN=${MESH_DIR:-/DATA/AppData/meshtastic-monitor}
LAYANAN=${LAYANAN:-meshtastic-exporter}
BERKAS="exporter-meshtastic.py lacak_halaman.py lacak_node.py"

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

if [ -z "${ZIMA_PASS:-}" ]; then
  echo "ZIMA_PASS belum diset."
  echo "Jalankan:  ZIMA_PASS='sandi-akun-ZimaOS' sh $0"
  exit 1
fi

AKAR=$(cd "$(dirname "$0")/.." && pwd)
SHELL_JS=${SHELL_JS:-$AKAR/zima-hosting/zima-shell.mjs}
ke_node() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi
}
[ -f "$SHELL_JS" ] || { echo "Tidak menemukan $SHELL_JS"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "node tidak ada di PATH."; exit 1; }

STEMPEL=$(date +%Y%m%d-%H%M%S)
SUFIKS=".sebelum-lacak-$STEMPEL"

echo "=== memulihkan set lacak node ==="
echo "    sumber : $SUMBER"
echo "    tujuan : $TUJUAN"
echo "    berkas : $BERKAS"
echo

TTYD_URL="$TTYD_URL" ZIMA_PASS="$ZIMA_PASS" node "$(ke_node "$SHELL_JS")" \
  "cd '$SUMBER' && { for f in $BERKAS; do test -f \"\$f\" || { echo \"SUMBER TIDAK LENGKAP: \$f\"; exit 1; }; done; } && echo '--- sumber ---' && ls -la --time-style=+%m-%d_%H:%M $BERKAS" \
  "cd '$TUJUAN' && { for f in $BERKAS; do sudo cp -p \"\$f\" \"\$f$SUFIKS\"; done; } && echo '--- cadangan berkas lama ---' && ls -la --time-style=+%m-%d_%H:%M *$SUFIKS" \
  "{ for f in $BERKAS; do sudo cp -p '$SUMBER/'\$f '$TUJUAN/'\$f; done; } && echo '--- berkas terpasang ---' && ls -la --time-style=+%m-%d_%H:%M $TUJUAN/*.py | grep -E 'exporter-meshtastic|lacak_halaman|lacak_node' | grep -v sebelum-lacak" \
  "cd '$TUJUAN' && ./venv/bin/python -c 'import lacak_halaman, lacak_node; print(\"impor modul lacak OK\")' && sudo systemctl restart '$LAYANAN' && sleep 4 && systemctl is-active '$LAYANAN'" \
  "cd '$TUJUAN' && echo '--- rute yang disajikan exporter ---' && grep -nE 'halaman_peta|halaman_daftar|halaman_node|startswith\(.\"/' exporter-meshtastic.py | head -18" \
  "cd '$TUJUAN' && echo '--- 20 baris log terakhir ---' && journalctl -u '$LAYANAN' -n 20 --no-pager 2>/dev/null | tail -20"

echo
echo "=== selesai ==="
echo "  berkas lama disimpan dengan akhiran: $SUFIKS"
echo "  periksa:  curl -s https://meshid.clusternet.my.id/ | grep -c halaman_peta"
