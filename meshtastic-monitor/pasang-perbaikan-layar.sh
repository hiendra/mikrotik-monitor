#!/usr/bin/env bash
# ============================================================
# pasang-perbaikan-layar.sh - kirim perbaikan "posisi layar" ke host ZimaOS
# ============================================================
# Bukan pemasangan penuh: HANYA berkas yang diperbaiki di folder
# meshtastic-monitor/lacak-kerja yang dikirim, supaya pekerjaan lain di folder
# produksi (lacak_node.py, lacak.sqlite3, leaflet/, berkas uji) tidak tersentuh.
#
# PENTING - urutan pemanggilan zima-shell.mjs. Skrip itu MENGUMPULKAN semua
# --upload lebih dulu dan baru menaruh perintahnya di BELAKANG perintah biasa
# (lihat zima-hosting/zima-shell.mjs: uploads diubah jadi perintah setelah
# loop argumen). Akibatnya, kalau upload dan perintah verifikasi/restart
# dicampur dalam satu panggilan, restart berjalan SEBELUM berkas terkirim -
# dan yang dimulai ulang masih kode lama. Karena itu di sini dipakai TIGA
# panggilan berurutan: cadangkan -> unggah -> mulai ulang & verifikasi.
#
# Pengaman: berkas yang akan ditimpa disalin dulu ke <nama>.sebelum-layar-<stempel>.
#
# Pakai (dari akar repo, di Git Bash):
#   ZIMA_PASS='sandi-akun-ZimaOS' sh meshtastic-monitor/pasang-perbaikan-layar.sh
# ============================================================
set -eu

ZIMA_HOST=${ZIMA_HOST:-192.168.20.36}
TTYD_URL=${TTYD_URL:-ws://$ZIMA_HOST:7681/ws}
TUJUAN=${MESH_DIR:-/DATA/AppData/meshtastic-monitor}
LAYANAN=${LAYANAN:-meshtastic-exporter}
BERKAS="exporter-meshtastic.py lacak_halaman.py lacak_node.py"

export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

if [ -z "${ZIMA_PASS:-}" ]; then
  echo "ZIMA_PASS belum diset."
  echo "Jalankan:  ZIMA_PASS='<sandi-ZimaOS>' sh $0"
  exit 1
fi

AKAR=$(cd "$(dirname "$0")/.." && pwd)
SUMBER=${SUMBER:-$AKAR/meshtastic-monitor/lacak-kerja}
SHELL_JS=${SHELL_JS:-$AKAR/zima-hosting/zima-shell.mjs}
ke_node() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s\n' "$1"; fi
}
[ -f "$SHELL_JS" ] || { echo "Tidak menemukan $SHELL_JS"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "node tidak ada di PATH."; exit 1; }
for f in $BERKAS; do
  [ -f "$SUMBER/$f" ] || { echo "Berkas sumber tidak ada: $SUMBER/$f"; exit 1; }
done

STEMPEL=$(date +%Y%m%d-%H%M%S)

echo "=== 1. cadangkan berkas lama di host ==="
TTYD_URL="$TTYD_URL" ZIMA_PASS="$ZIMA_PASS" node "$(ke_node "$SHELL_JS")" \
  "echo 'CADANGAN-MULAI'; cd '$TUJUAN' && { for f in $BERKAS; do sudo cp -p \"\$f\" \"\$f.sebelum-layar-$STEMPEL\"; done; } && ls -1 *sebelum-layar-$STEMPEL; echo 'CADANGAN-SELESAI'" 2>&1 \
  | grep -E "CADANGAN-|sebelum-layar" || true

echo
echo "=== 2. unggah berkas yang diperbaiki ==="
TTYD_URL="$TTYD_URL" ZIMA_PASS="$ZIMA_PASS" node "$(ke_node "$SHELL_JS")" \
  --upload "$(ke_node "$SUMBER/exporter-meshtastic.py")" "$TUJUAN/exporter-meshtastic.py" \
  --upload "$(ke_node "$SUMBER/lacak_halaman.py")" "$TUJUAN/lacak_halaman.py" \
  --upload "$(ke_node "$SUMBER/lacak_node.py")" "$TUJUAN/lacak_node.py" 2>&1 \
  | grep -E "TERPASANG|byte|CADANGAN_OK|TANPA_CADANGAN" || true

echo
echo "=== 3. mulai ulang + verifikasi ==="
TTYD_URL="$TTYD_URL" ZIMA_PASS="$ZIMA_PASS" node "$(ke_node "$SHELL_JS")" \
  "echo 'VERIF-MULAI'; cd '$TUJUAN' && ./venv/bin/python -c 'import lacak_halaman; print(\"IMPOR-OK\")' && sudo systemctl restart '$LAYANAN' && sleep 4 && systemctl is-active '$LAYANAN'" \
  "echo 'ISI-MULAI'; cd '$TUJUAN' && for n in $BERKAS; do printf 'BERKAS %s %s byte layar=%s peta=%s nol=%s\n' \"\$n\" \$(wc -c < \$n) \$(grep -c meshid-layar-1 \$n) \$(grep -c meshid-peta-view-1 \$n) \$(grep -c posisi_bersih \$n); done; echo 'ISI-SELESAI'" 2>&1 \
  | grep -E "IMPOR-OK|active|BERKAS|ISI-SELESAI" || true

echo
echo "=== selesai ==="
echo "  cadangan: *.sebelum-layar-$STEMPEL"
echo "  periksa : curl -s https://meshid.clusternet.my.id/ | grep -c meshid-layar-1"
