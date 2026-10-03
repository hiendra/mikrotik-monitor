#!/bin/sh
# ============================================================
# pasang-layanan.sh - pasang layanan Meshtastic sebagai systemd di ZimaOS
# ============================================================
# Memasang DUA layanan tetap, idempoten:
#   1. meshtastic-exporter.service  - exporter + halaman web
#   2. meshtastic-notif.service     - notifikasi ntfy
#
#
# TIMER RESET SENGAJA TIDAK DIAKTIFKAN. Reset NodeDB menghapus semua tanda
# Favorite, jadi menjadwalkannya berkala akan menghapus perlindungan node RF
# berulang kali. Selama downlink MQTT sudah mati (lihat mqtt-downlink.py),
# daftar tidak lagi terisi node internet sehingga reset berkala tak diperlukan.
# Bila Anda memang ingin memasangnya, jalankan eksplisit:
#   MESH_PASANG_TIMER=1 sudo sh pasang-layanan.sh
#
# TIMER BERSIH-BERSIH (bersih-node.py) juga TIDAK dipasang secara bawaan,
# meski dampaknya jauh lebih kecil daripada reset: ia hanya menghapus node
# jalur MQTT yang sudah lewat ambang umur (bawaan 5 hari) dan meninggalkan node
# Favorite serta node jalur radio. Pasang bila memang ingin berjalan sendiri:
#   MESH_PASANG_BERSIH=1 sudo sh pasang-layanan.sh
#
# Kedua timer itu bersifat TIGA KEADAAN: 1 = pasang & nyalakan, 0 = cabut,
# tidak disebut = biarkan apa adanya. Tanpa keadaan ketiga, `pasang-ke-zima.sh`
# (yang tidak menyebut opsi apa pun) akan mematikan jadwal yang sudah disetujui
# pada setiap penerapan kode - gagal secara senyap.
#
# ZimaOS memakai systemd tetapi TIDAK memasang cron/crond, jadi penjadwalan
# lewat systemd timer adalah cara paling andal di host ini (pola yang sama
# dipakai udara/pasang-notif-udara.sh).
#
# Pakai
# -----
#   sudo sh /DATA/AppData/meshtastic-monitor/pasang-layanan.sh
#
# Berkas skrip + berkas unit (.service/.timer) harus sudah ada di DIR di bawah.
# Berkas unit di salin ke /etc/systemd/system dengan path /opt/meshtastic-monitor
# diganti $DIR, sehingga template di repo tetap menjadi satu-satunya sumber.
#
# Idempoten: aman dijalankan berulang. Bila ZimaOS diperbarui dan unit systemd
# hilang, cukup jalankan lagi skrip ini.
#
# Mencopot:
#   sudo systemctl disable --now meshtastic-exporter meshtastic-notif
#   sudo systemctl disable --now meshtastic-reset.timer meshtastic-bersih.timer
#   sudo rm /etc/systemd/system/meshtastic-{exporter,notif,reset,bersih}.{service,timer}
#   sudo systemctl daemon-reload
# ============================================================
set -eu

DIR=${MESH_DIR:-/DATA/AppData/meshtastic-monitor}
SATUAN=/etc/systemd/system
PY="$DIR/venv/bin/python"

if [ "$(id -u)" -ne 0 ]; then
  echo "Skrip ini perlu root. Jalankan: sudo sh $0"
  exit 1
fi

if [ ! -f "$DIR/exporter-meshtastic.py" ]; then
  echo "Tidak menemukan $DIR/exporter-meshtastic.py - unggah dulu folder ini ke $DIR."
  exit 1
fi

# --- 1. rapikan berkas skrip (akhir baris Unix, izin eksekusi) ---
for f in "$DIR"/*.py; do
  [ -f "$f" ] || continue
  sed -i 's/\r$//' "$f"
  chmod 0755 "$f"
done

# --- 2. siapkan venv + dependensi bila belum ada ---
if [ ! -x "$PY" ]; then
  echo "Membuat venv di $DIR/venv ..."
  python3 -m venv "$DIR/venv"
  "$PY" -m pip install --upgrade pip >/dev/null
  "$PY" -m pip install -r "$DIR/requirements.txt"
else
  echo "venv sudah ada: $PY"
fi

# --- 3. tulis unit systemd dari template di DIR ---
pasang_unit() {
  nama=$1
  src="$DIR/$nama"
  if [ ! -f "$src" ]; then
    echo "PERINGATAN: template $src tidak ada, dilewati."
    return 0
  fi
  # Ganti path template -> DIR nyata, dan buang baris User= (ZimaOS tak punya
  # user khusus; layanan berjalan seperti pola notif-udara.sh).
  sed -e "s#/opt/meshtastic-monitor#$DIR#g" -e '/^User=/d' "$src" > "$SATUAN/$nama"
  echo "  -> $SATUAN/$nama"
}

echo "Menulis unit systemd:"
pasang_unit meshtastic-exporter.service
pasang_unit meshtastic-notif.service

if [ "${MESH_PASANG_TIMER:-0}" = "1" ]; then
  pasang_unit meshtastic-reset.service
  pasang_unit meshtastic-reset.timer
fi

if [ "${MESH_PASANG_BERSIH:-0}" = "1" ]; then
  pasang_unit meshtastic-bersih.service
  pasang_unit meshtastic-bersih.timer
fi

# --- 4. aktifkan ---
systemctl daemon-reload

# KENDALA YANG PERNAH TERJADI (28 Sep 2026): `systemctl enable --now` HANYA
# menyalakan unit yang belum berjalan. Pada unit yang sudah aktif, perintah itu
# tidak melakukan apa pun - jadi setelah mengunggah kode baru, layanan tetap
# memakai kode LAMA yang sudah termuat di memori, dan halaman web tetap versi
# lama walau berkas di disk sudah diperbarui. Karena itu: enable dulu (agar
# tetap hidup setelah reboot), lalu RESTART supaya kode yang baru benar-benar
# dipakai. Timer tidak perlu di-restart - restart hanya akan menggeser jadwalnya.
systemctl enable meshtastic-exporter.service meshtastic-notif.service
systemctl restart meshtastic-exporter.service meshtastic-notif.service

# Timer bersifat TIGA KEADAAN, dan itu disengaja:
#   1 -> pasang & nyalakan;  0 -> cabut;  tidak disebut -> biarkan apa adanya.
# Keadaan ketiga itu penting. pasang-ke-zima.sh memanggil skrip ini tanpa
# menyebut opsi apa pun, jadi kalau "tidak disebut" diperlakukan seperti 0,
# setiap penerapan kode rutin akan diam-diam MEMATIKAN jadwal yang sudah
# dipasang dan disetujui sebelumnya - kegagalan yang sunyi, tanpa pesan galat.
pasang_timer() {
  nama=$1
  menurut=${2:-x}
  case "$menurut" in
    1) systemctl enable --now "$nama" && echo "  $nama: dinyalakan" ;;
    0) systemctl disable --now "$nama" 2>/dev/null || true
       echo "  $nama: dicabut (diminta 0)" ;;
    *) echo "  $nama: dibiarkan seperti apa adanya (opsi tidak disebut)" ;;
  esac
}

pasang_timer meshtastic-reset.timer "${MESH_PASANG_TIMER:-x}"
pasang_timer meshtastic-bersih.timer "${MESH_PASANG_BERSIH:-x}"

echo
echo "--- layanan tetap ---"
systemctl --no-pager --full --lines=0 status meshtastic-exporter.service || true
systemctl --no-pager --full --lines=0 status meshtastic-notif.service || true

echo
echo "--- jadwal timer (keadaan sebenarnya, bukan niat) ---"
for t in meshtastic-reset.timer meshtastic-bersih.timer; do
  printf '  %-28s %s\n' "$t" "$(systemctl is-enabled "$t" 2>/dev/null || echo 'tidak ada')"
done
systemctl --no-pager --full list-timers 'meshtastic-*' 2>/dev/null || true

echo
echo "--- cara mengubah ---"
echo "  reset 2 harian : MESH_PASANG_TIMER=1 sudo sh $0   (cabut: MESH_PASANG_TIMER=0)"
echo "  bersih harian  : MESH_PASANG_BERSIH=1 sudo sh $0  (cabut: MESH_PASANG_BERSIH=0)"
echo "  tanpa opsi     : timer dibiarkan seperti apa adanya - jadi penerapan kode"
echo "                   rutin tidak akan mematikan jadwal yang sudah dipasang."
echo
echo "  Uji bersih-bersih tanpa menghapus : \"$PY\" \"$DIR/bersih-node.py\""
echo "  Uji reset tanpa mengubah        : \"$PY\" \"$DIR/reset-node.py\""

echo
echo "--- uji jalur (periksa-saja, tidak mengubah apa pun) ---"
"$PY" "$DIR/reset-node.py" --tanpa-notif || true

if [ "${MESH_PASANG_TIMER:-0}" = "1" ]; then
  echo
echo "Timer reset aktif: 02:30 tanggal ganjil, hanya bila isi NodeDB >= 190."
  echo "Ingat: setiap reset menghapus Favorite. Tandai ulang dengan favorite-node.py."
  echo "Uji paksa:  sudo systemctl start meshtastic-reset.service"
else
  echo
echo "Timer reset TIDAK dipasang. Cukup pantau isi NodeDB; bila suatu saat perlu"
  echo "dikosongkan, lakukan manual sekali lalu tandai ulang Favorite:"
  echo "  python reset-node.py --ya  &&  python favorite-node.py --ya"
fi
