#!/bin/sh
# ============================================================
# sinkron-status-kuma.sh — menjaga halaman status Uptime Kuma
# ============================================================
# Kenapa perlu skrip ini?
# Uptime Kuma TIDAK punya fitur "tambahkan monitor baru ke halaman status
# secara otomatis" — permintaan itu masih berupa feature request yang belum
# diimplementasikan (louislam/uptime-kuma#2810). Akibatnya tiap monitor baru
# harus dipasangkan manual, dan monitor yang terlewat akan tampak "hilang"
# padahal ada (persis kasus mqtt2.meshnode.id).
#
# Skrip ini menambalnya: setiap kali dijalankan, semua monitor AKTIF yang
# belum ada di grup halaman status akan dimasukkan ke grup tersebut.
#
# Sifatnya idempoten: monitor yang sudah ada tidak disentuh dan urutan yang
# sudah ada tidak diubah; yang baru selalu ditambahkan di urutan paling
# belakang. Kalau tidak ada yang baru, skrip diam (tidak menulis log).
#
# Dipasang sebagai systemd timer oleh pasang-sinkron-kuma.sh, tapi bisa juga
# dijalankan manual:  sudo sh sinkron-status-kuma.sh
#
# Lingkungan (opsional):
#   KUMA_HALAMAN        slug halaman status      (bawaan "mesh")
#   KUMA_GRUP           nama grup di halaman     (bawaan "MeshNode")
#   KUMA_SERTAKAN_GRUP  "1" untuk ikut memasukkan monitor bertipe "group"
#                       (bawaan 0: grup bukan layanan, jadi dilewati)
#   KUMA_KONTAINER      nama kontainer           (bawaan "uptimekuma")
#   KUMA_LOG            berkas log               (bawaan di /DATA/.../sinkron-status-kuma.log)
# ============================================================
set -eu

HALAMAN="${KUMA_HALAMAN:-mesh}"
GRUP="${KUMA_GRUP:-MeshNode}"
SERTAKAN_GRUP="${KUMA_SERTAKAN_GRUP:-0}"
KONTAINER="${KUMA_KONTAINER:-uptimekuma}"
LOG="${KUMA_LOG:-/DATA/AppData/zima-hosting/sinkron-status-kuma.log}"
SOKET=/app/data/run/mariadb.sock

# systemd menjalankan skrip ini sebagai root, jadi docker tidak perlu sudo.
if [ "$(id -u)" -eq 0 ]; then DOCKER="docker"; else DOCKER="sudo docker"; fi

catat() { printf '%s  %s\n' "$(date '+%F %T')" "$1" >> "$LOG"; }

# Log dibatasi ~2000 baris terakhir supaya tidak tumbuh tanpa henti.
if [ -f "$LOG" ]; then
  tail -n 2000 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG"
fi

if ! $DOCKER ps --format '{{.Names}}' | grep -qx "$KONTAINER"; then
  catat "LEWAT: kontainer $KONTAINER sedang tidak berjalan"
  exit 0
fi

# Jalankan SQL dan kembalikan hanya nilai (tanpa nama kolom, tanpa bingkai).
SQL() {
  $DOCKER exec "$KONTAINER" mariadb \
    --socket="$SOKET" -u root kuma --batch --skip-column-names -e "$1"
}

GID=$(SQL "SELECT g.id FROM \`group\` g
           JOIN status_page sp ON sp.id = g.status_page_id
           WHERE sp.slug = '$HALAMAN' AND g.name = '$GRUP' LIMIT 1;" | tr -d '\r')

if [ -z "$GID" ]; then
  catat "GAGAL: grup '$GRUP' pada halaman '$HALAMAN' tidak ditemukan"
  exit 1
fi

FILTER_GRUP="AND m.type <> 'group'"
if [ "$SERTAKAN_GRUP" = "1" ]; then FILTER_GRUP=""; fi

BELUM_MASUK="FROM monitor m
            LEFT JOIN monitor_group mg ON mg.group_id = $GID AND mg.monitor_id = m.id
            WHERE m.active = 1 $FILTER_GRUP AND mg.id IS NULL"

BARU=$(SQL "SELECT COUNT(*) $BELUM_MASUK;" | tr -d '\r')

if [ -z "$BARU" ] || [ "$BARU" = "0" ]; then
  exit 0   # tidak ada yang baru — tidak perlu menulis apa pun
fi

# Dicatat SEBELUM disisipkan supaya pesan log berisi hanya monitor baru.
NAMA=$(SQL "SELECT GROUP_CONCAT(m.name ORDER BY m.id SEPARATOR ', ') $BELUM_MASUK;" | tr -d '\r')

# Hitung bobot (urutan) baru di tabel sementara, lalu sisipkan. Bobot dasar
# diambil lebih dulu ke variabel supaya INSERT tidak membaca tabel tujuan
# secara langsung di sub-kueri (dilarang MySQL/MariaDB).
SQL "SET @base := (SELECT COALESCE(MAX(weight), 0) FROM monitor_group WHERE group_id = $GID);
     CREATE TEMPORARY TABLE _sinkron AS
       SELECT m.id AS monitor_id, @base + ROW_NUMBER() OVER (ORDER BY m.id) AS new_weight
       FROM monitor m
       LEFT JOIN monitor_group mg ON mg.group_id = $GID AND mg.monitor_id = m.id
       WHERE m.active = 1 $FILTER_GRUP AND mg.id IS NULL;
     INSERT INTO monitor_group (monitor_id, group_id, weight)
       SELECT monitor_id, $GID, new_weight FROM _sinkron;
     DROP TEMPORARY TABLE _sinkron;"

catat "TAMBAH $BARU monitor ke '$GRUP': $NAMA"
