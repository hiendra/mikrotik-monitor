#!/bin/sh
# ============================================================
# pasang-sinkron-kuma.sh — memasang sinkron-status-kuma.sh sebagai
# systemd timer yang berjalan tiap 5 menit.
# ============================================================
# ZimaOS memakai systemd tetapi TIDAK memasang cron/crond, jadi penjadwalan
# lewat systemd timer adalah cara yang paling andal di sini.
#
# Jalankan sebagai root:
#   sudo sh /DATA/AppData/zima-hosting/pasang-sinkron-kuma.sh
#
# Skrip ini idempoten: aman dijalankan berulang. Kalau ZimaOS diperbarui dan
# unit systemd-nya hilang, cukup jalankan lagi skrip ini.
#
# Cara mencopot:
#   sudo systemctl disable --now sinkron-status-kuma.timer
#   sudo rm /etc/systemd/system/sinkron-status-kuma.{service,timer}
#   sudo systemctl daemon-reload
# ============================================================
set -eu

NAMA=sinkron-status-kuma
DIR=/DATA/AppData/zima-hosting
SKRIP="$DIR/sinkron-status-kuma.sh"
SATUAN=/etc/systemd/system

if [ "$(id -u)" -ne 0 ]; then
  echo "Skrip ini perlu root. Jalankan: sudo sh $0"
  exit 1
fi

if [ ! -f "$SKRIP" ]; then
  echo "Tidak menemukan $SKRIP — unggah dulu berkasnya."
  exit 1
fi

# Pastikan akhir baris gaya Unix dan berkas dapat dieksekusi.
sed -i 's/\r$//' "$SKRIP"
chmod 0755 "$SKRIP"

cat > "$SATUAN/$NAMA.service" <<EOF
[Unit]
Description=Sinkronkan monitor Uptime Kuma ke halaman status (MeshNode)
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/sh $SKRIP
EOF

cat > "$SATUAN/$NAMA.timer" <<EOF
[Unit]
Description=Jalankan sinkronisasi status Uptime Kuma tiap 5 menit

[Timer]
OnBootSec=2min
OnCalendar=*:0/5
Persistent=true
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now "$NAMA.timer"

echo "--- status timer ---"
systemctl --no-pager --full list-timers "$NAMA.timer" || true
echo "--- uji jalan sekali sekarang ---"
systemctl start "$NAMA.service"
systemctl --no-pager --full status "$NAMA.service" 2>&1 | head -12 || true
echo "--- isi log (jika ada) ---"
tail -n 5 "$DIR/sinkron-status-kuma.log" 2>/dev/null || echo "(log masih kosong — berarti tidak ada monitor baru, itu normal)"
