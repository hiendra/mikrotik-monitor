# ============================================================
# pasang-otomatis.ps1 - daftarkan penjaga layanan ke Task Scheduler
# ============================================================
# Setelah ini, exporter + notifier Meshtastic mengurus dirinya sendiri:
#   * dinyalakan saat Anda log in;
#   * diperiksa tiap 10 menit - kalau ada yang mati, dinyalakan lagi;
#   * node radio langsung yang belum Favorite ikut ditandai otomatis.
#
# Pakai:
#   powershell -NoProfile -ExecutionPolicy Bypass -File pasang-otomatis.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File pasang-otomatis.ps1 lepas
#
# Idempoten: aman dijalankan berulang (-Force menimpa tugas yang sudah ada).
#
# Tidak butuh hak administrator: tugas didaftarkan untuk pengguna yang sedang
# aktif, dan hanya berjalan saat pengguna itu log in.
# ============================================================

$ErrorActionPreference = 'Stop'

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$penjaga = Join-Path $dir 'pastikan-hidup.ps1'
$nama = 'Meshtastic Monitor'
$modeLepas = ($args -contains 'lepas')

if ($modeLepas) {
  $ada = Get-ScheduledTask -TaskName $nama -ErrorAction SilentlyContinue
  if (-not $ada) {
    Write-Host "Tugas '$nama' belum terpasang. Tidak ada yang perlu dilepas."
    exit 0
  }
  Unregister-ScheduledTask -TaskName $nama -Confirm:$false
  Write-Host "Tugas '$nama' dilepas. Layanan yang sedang jalan TIDAK dimatikan;"
  Write-Host "hentikan manual dengan hentikan-layanan.bat bila perlu."
  exit 0
}

if (-not (Test-Path $penjaga)) {
  Write-Host "Tidak menemukan $penjaga"
  exit 1
}

$aksi = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$penjaga`""

# Dua pemicu: saat log in (langsung hidup), dan berkala tiap 10 menit (sembuh
# sendiri bila proses mati di tengah jalan).
$pemicuLogon = New-ScheduledTaskTrigger -AtLogOn
$pemicuBerkala = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
  -RepetitionInterval (New-TimeSpan -Minutes 10)

$setelan = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -MultipleInstances IgnoreNew `
  -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

# Prinsipal ditulis eksplisit untuk pengguna yang sedang aktif. Ini penting
# bila skrip dijalankan lewat elevasi: tanpa ini, tugas bisa terdaftar untuk
# akun yang salah dan tidak pernah berbunyi saat Anda log in.
$prinsipal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
  -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $nama -Action $aksi `
  -Trigger $pemicuLogon, $pemicuBerkala -Settings $setelan -Principal $prinsipal `
  -Description 'Menjaga exporter + notifier Meshtastic tetap hidup, dan menandai node radio yang belum Favorite.' `
  -Force | Out-Null

Write-Host "Tugas '$nama' terpasang untuk: $env:USERDOMAIN\$env:USERNAME"
Write-Host
Get-ScheduledTask -TaskName $nama |
  Select-Object TaskName, State |
  Format-Table -AutoSize

Write-Host "Pemicu:"
(Get-ScheduledTask -TaskName $nama).Triggers |
  ForEach-Object { Write-Host ("  - " + $_.CimClass.CimClassName) }

Write-Host
Write-Host "Menjalankan sekali sekarang untuk membuktikan jalurnya ..."
Start-ScheduledTask -TaskName $nama
Start-Sleep -Seconds 12
Get-ScheduledTaskInfo -TaskName $nama |
  Select-Object LastRunTime, LastTaskResult, NextRunTime |
  Format-List

Write-Host "Log penjaga: $dir\pastikan-hidup.log"
Write-Host "Mencopot otomatisasi: powershell -NoProfile -File pasang-otomatis.ps1 lepas"
