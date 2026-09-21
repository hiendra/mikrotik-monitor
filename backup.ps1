# ============================================================
# backup.ps1 - Backup bertanggal project MikroTik Monitor
# ============================================================
# Cara pakai (buka PowerShell lalu jalankan):
#
#   cd C:\temp\mikrotik_monitor
#   powershell -ExecutionPolicy Bypass -File .\backup.ps1
#
# Hasil: file .zip bertanggal di
#   %USERPROFILE%\MikroTikMonitor-Backups\
#
# Catatan: folder Documents di komputer ini tidak bisa ditulisi oleh
# PowerShell (terkait OneDrive/proteksi folder), maka tujuan dipakai
# folder profil pengguna yang sudah terbukti bisa.
#
# Skrip ini menyimpan 20 backup terbaru dan menghapus yang lebih lama.
# ============================================================

$ErrorActionPreference = 'Stop'

$src     = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$destDir = Join-Path $env:USERPROFILE 'MikroTikMonitor-Backups'
$stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$zip     = Join-Path $destDir ("mikrotik_monitor_{0}.zip" -f $stamp)

Write-Host ""
Write-Host "=== Backup MikroTik Monitor ===" -ForegroundColor Cyan
Write-Host "Sumber : $src"
Write-Host "Tujuan : $zip"

New-Item -ItemType Directory -Force -Path $destDir | Out-Null
if (-not (Test-Path -LiteralPath $destDir)) {
  throw "Folder tujuan tidak bisa dibuat: $destDir"
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }

# --- Buat zip secara manual ---
# Tujuannya supaya:
#   1) nama entri di dalam zip memakai '/' (standar), bukan '\'
#   2) file & folder tersembunyi (.git, .gitignore, secrets.h) ikut masuk
$base = $src.TrimEnd('\') + '\'

$zipStream = [System.IO.File]::Open($zip, [System.IO.FileMode]::Create)
$archive   = New-Object System.IO.Compression.ZipArchive($zipStream, [System.IO.Compression.ZipArchiveMode]::Create)

try {
  $backupSub = Join-Path $src 'backups'
  $files = Get-ChildItem -Force -Recurse -LiteralPath $src -File |
           Where-Object { $_.FullName -notlike "$backupSub\*" }

  foreach ($f in $files) {
    $rel   = $f.FullName.Substring($base.Length).Replace('\', '/')
    $entry = $archive.CreateEntry($rel, [System.IO.Compression.CompressionLevel]::Optimal)
    $out   = $entry.Open()
    $in    = [System.IO.File]::OpenRead($f.FullName)
    try { $in.CopyTo($out) } finally { $in.Dispose(); $out.Dispose() }
  }
} finally {
  $archive.Dispose()
  $zipStream.Dispose()
}

$info   = Get-Item -LiteralPath $zip
$sizeMB = [math]::Round($info.Length / 1MB, 2)
Write-Host ""
Write-Host "Backup BERHASIL dibuat." -ForegroundColor Green
Write-Host ("  {0}" -f $info.FullName)
Write-Host ("  {0} MB, {1} file, {2}" -f $sizeMB, $files.Count, $info.LastWriteTime)

# Rotasi: sisakan 20 backup terbaru saja
$old = Get-ChildItem -LiteralPath $destDir -Filter 'mikrotik_monitor_*.zip' |
       Sort-Object LastWriteTime -Descending |
       Select-Object -Skip 20
if ($old) {
  $old | Remove-Item -Force
  Write-Host ("  (dihapus {0} backup lama)" -f $old.Count)
}

Write-Host ""
Write-Host "CATATAN: arsip ini memuat secrets.h (kredensial asli)." -ForegroundColor Yellow
Write-Host "Jangan diunggah ke internet atau dibagikan ke orang lain." -ForegroundColor Yellow
Write-Host ""
