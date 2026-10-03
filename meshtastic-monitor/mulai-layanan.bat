@echo off
rem ============================================================
rem mulai-layanan.bat - jalankan exporter + notifier Meshtastic di Windows
rem ============================================================
rem Cara tercepat menghidupkan pemantauan dari mesin Windows yang sudah
rem terhubung ke gateway. Tanpa systemd, tanpa sandi, tanpa venv baru -
rem asalkan folder ven\Scripts\python.exe sudah ada (lihat README).
rem
rem Pakai: klik dua kali, atau dari Git Bash:  cmd //c mulai-layanan.bat
rem Hentikan dengan: hentikan-layanan.bat
rem
rem Skrip ini MEMATIKAN dulu layanan yang masih jalan sebelum menyalakan yang
rem baru. Tanpa itu, menekan dua kali berturut-turut meninggalkan layanan
rem kembar: exporter kedua tidak bisa memegang port 9208 (sudah dipakai),
rem tetapi ia TETAP menyambung ke gateway, dan notifier kembar mengirim alarm
rem dua kali sampai server ntfy membalas 429. Selalu lewat satu pintu saja.
rem
rem Kenapa -u (tanpa sangga)? Tanpa itu, Python menahan keluaran di memori dan
rem exporter.log / notif.log tetap kosong sampai proses lama berjalan.
rem ============================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

rem --- alamat gateway ---
set MESH_HOST=192.168.20.31
set MESH_PORT=4403
set MESH_EXPORTER_PORT=9208
set MESH_INTERVAL=30
rem 3 jam: node ROUTER memancarkan telemetry sendiri hanya ~tiap 12 jam.
set MESH_OFFLINE_SECS=10800
set MESH_DB_AMBANG=190

rem --- notifier: baca dari exporter di mesin ini ---
set MESH_DATA=http://127.0.0.1:9208/data.json
set NTFY_SERVER=https://ntfy.adminforge.de
set NTFY_TOPIK=mesh-6h4v8p2rxq
rem Topik KEDUA untuk kabar penting (gateway & node); kosongkan untuk satu topik.
set NTFY_TOPIK_PENTING=mesh-penting-2kevnee56c4
set NTFY_LOKAL=http://192.168.200.253:7200
set NOTIF_SNR_AMBANG=-7
set NOTIF_SNR_MARGIN=3
set NOTIF_HOP_NAIK=1
rem Cakupan radio saja: database memuat ratusan node internet lewat MQTT.
set NOTIF_LINGKUP=lora
set NOTIF_JENDELA_RESET=1800
rem Node LoRa yang terdeteksi LANGSUNG oleh radio gateway dikabari beserta
rem id node dan kualitas sinyalnya (SNR yang diukur gateway sendiri).
set NOTIF_KONTAK_BARU=1
rem Jeda kabar "kontak radio kembali" per node (detik). Jalur paket bisa
rem bergantian radio <-> MQTT, jadi tanpa jeda tiap pergantian jadi notifikasi.
set NOTIF_JEDA_KONTAK=21600
rem Gateway mati/tidak terbaca: ambang umur data exporter (detik) dan berapa
rem putaran gagal berturut-turut sebelum dilaporkan.
set NOTIF_BASI_GW=180
set NOTIF_ABSEN_GW=2

if not exist "venv\Scripts\python.exe" (
  echo venv\Scripts\python.exe tidak ada. Buat dulu:
  echo   python -m venv venv ^&^& venv\Scripts\pip install -r requirements.txt
  exit /b 1
)

echo Menghentikan layanan lama (bila ada) ...
call "%~dp0hentikan-layanan.bat" >nul 2>&1

echo Menyalakan exporter di http://127.0.0.1:9208/ ...
rem Exporter menulis log lewat modul logging Python, yang memakai stderr.
rem Karena itu keluarannya dipisah: stdout ke .log, stderr ke .err.log.
start "meshtastic-exporter" /b "venv\Scripts\python.exe" -u exporter-meshtastic.py >> exporter.log 2>> exporter.err.log

echo Menyalakan notifier ntfy ...
start "meshtastic-notif" /b "venv\Scripts\python.exe" -u notif-meshtastic.py >> notif.log 2>> notif.err.log

echo.
echo Selesai. Cek beberapa detik lagi:
echo   http://127.0.0.1:9208/          halaman semua data node
echo   http://127.0.0.1:9208/metrics   metrik Prometheus
echo   exporter.err.log               log exporter (logging Python ke stderr)
echo   notif.log                      log notifier
endlocal
