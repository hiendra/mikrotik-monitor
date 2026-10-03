# ============================================================
# pastikan-hidup.ps1 - penjaga otomatis exporter + notifier Meshtastic
# ============================================================
# Dijalankan berkala oleh Task Scheduler (lihat pasang-otomatis.ps1). Tugasnya:
#   1. menyalakan exporter bila belum jalan;
#   2. menyalakan notifier bila belum jalan;
#   3. menandai node radio langsung yang belum Favorite (Favorite melindungi
#      node RF dari penggusuran saat NodeDB penuh).
#
# Kenapa bukan sekadar "jalankan sekali lalu dibiarkan"? Karena proses bisa mati
# karena reboot, log out, atau crash. Skrip ini idempoten: aman dijalankan
# sesering apa pun, dan tidak menyalakan layanan yang sudah hidup.
#
# Yang SENGAJA tidak diotomatiskan: reset/ kosongkan NodeDB. Reset menghapus
# semua tanda Favorite, jadi menjadwalkannya justru merusak perlindungan yang
# sedang kita bangun. Lakukan manual bila benar-benar perlu.
#
# Log: pastikan-hidup.log (satu baris per kejadian penting).
# ============================================================

$ErrorActionPreference = 'Continue'

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $dir

$log = Join-Path $dir 'pastikan-hidup.log'
function Catat([string]$pesan) {
  "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $pesan" | Add-Content -Path $log
}

$py = Join-Path $dir 'venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
  Catat "venv tidak ditemukan di $py - lewati putaran ini."
  exit 1
}

# --- setelan gateway (sama dengan mulai-layanan.bat dan unit systemd) ---
$env:MESH_HOST = '192.168.20.31'
$env:MESH_PORT = '4403'
$env:MESH_EXPORTER_PORT = '9208'
$env:MESH_INTERVAL = '30'
$env:MESH_OFFLINE_SECS = '10800'
$env:MESH_DB_AMBANG = '190'

# --- setelan notifier ---
$env:MESH_DATA = 'http://127.0.0.1:9208/data.json'
$env:NTFY_SERVER = 'https://ntfy.adminforge.de'
$env:NTFY_TOPIK = 'mesh-6h4v8p2rxq'
# Topik kedua: kabar penting (gateway & node). Kosongkan untuk satu topik saja.
$env:NTFY_TOPIK_PENTING = 'mesh-penting-2kevnee56c4'
$env:NTFY_LOKAL = 'http://192.168.200.253:7200'
$env:NOTIF_SNR_AMBANG = '-7'
$env:NOTIF_SNR_MARGIN = '3'
$env:NOTIF_HOP_NAIK = '1'
$env:NOTIF_LINGKUP = 'lora'
$env:NOTIF_JENDELA_RESET = '1800'
# Kabar node LoRa yang terdeteksi LANGSUNG oleh radio gateway (id + kualitas sinyal),
# dengan jeda 6 jam agar pergantian jalur radio <-> MQTT tidak jadi banjir pesan.
$env:NOTIF_KONTAK_BARU = '1'
$env:NOTIF_JEDA_KONTAK = '21600'
# Gateway mati / tidak terbaca (umur data basi & jumlah putaran gagal berturut-turut).
$env:NOTIF_BASI_GW = '180'
$env:NOTIF_ABSEN_GW = '2'

function Jalankan-Proses([string]$nama, [string]$skrip) {
  # Cocokkan lewat command line, JANGAN lewat nama proses: "python.exe" juga
  # dipakai pekerjaan lain milik Anda.
  $ada = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match [regex]::Escape($skrip) }
  if ($ada) { return $false }
  Start-Process -WindowStyle Hidden -FilePath $py `
    -ArgumentList '-u', $skrip -WorkingDirectory $dir `
    -RedirectStandardOutput (Join-Path $dir ($nama + '.log')) `
    -RedirectStandardError (Join-Path $dir ($nama + '.err.log'))
  Catat "menyalakan $skrip (sebelumnya tidak jalan)"
  return $true
}

$null = Jalankan-Proses 'exporter' 'exporter-meshtastic.py'
$null = Jalankan-Proses 'notif' 'notif-meshtastic.py'

# --- Favorite otomatis untuk node radio langsung ---
# Tanpa --node: semua node jalur radio yang belum Favorite. Hanya menulis bila
# ada yang perlu, jadi putaran tanpa perubahan tidak menyentuh perangkat.
try {
  $keluar = & $py (Join-Path $dir 'favorite-node.py') --ya 2>&1 | Out-String
  # Bagian yang bisa dicatat ada di daftar "Rencana perubahan", berbentuk:
  #   !da5a16f8    [B-68]MTL|CBT|ROUTER           -> Favorite
  # (mode sekali-jalan tidak pernah mencetak "+ Favorite" seperti mode jaga).
  $baris = $keluar -split "`r?`n" | Where-Object { $_ -match '->\s*(Favorite|lepas Favorite)' }
  if ($baris) {
    Catat ('Favorite otomatis: ' + (($baris | ForEach-Object { $_.Trim() }) -join ' | '))
  }
} catch {
  Catat "favorite-node.py gagal: $_"
}

exit 0
