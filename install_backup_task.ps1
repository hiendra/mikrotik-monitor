<#
    install_backup_task.ps1
    ---------------------------------------------------------------
    Mendaftarkan (atau memperbarui) tugas harian di Windows Task
    Scheduler supaya backup.ps1 berjalan otomatis tanpa dijalankan manual.

    Cara pakai (dari folder ini):
        powershell -NoProfile -ExecutionPolicy Bypass -File .\install_backup_task.ps1
        powershell ... -File .\install_backup_task.ps1 -Jam 21:30

    Sifatnya idempotent: boleh dijalankan berulang kali, tugas lama
    akan diganti dengan pengaturan yang sama.
#>

[CmdletBinding()]
param(
    # Jam backup harian (format HH:mm, 24 jam)
    [string]$Jam = "23:00",
    # Nama tugas di Task Scheduler
    [string]$NamaTugas = "MikroTik Monitor Backup Harian"
)

$ErrorActionPreference = "Stop"

# --- Lokasi project = folder tempat skrip ini berada ---------------------
$ProjectDir = $PSScriptRoot
if (-not $ProjectDir) { $ProjectDir = (Get-Location).Path }
$ProjectDir = (Resolve-Path $ProjectDir).Path
$Skrip = Join-Path $ProjectDir "backup.ps1"

if (-not (Test-Path $Skrip)) {
    throw "Tidak menemukan backup.ps1 di: $Skrip"
}

# --- Validasi jam --------------------------------------------------------
$parsed = [datetime]::MinValue
if (-not [datetime]::TryParseExact($Jam, "HH:mm", $null, [System.Globalization.DateTimeStyles]::None, [ref]$parsed)) {
    throw "Format jam tidak valid: '$Jam'. Gunakan HH:mm, contoh 23:00."
}

# --- Siapa yang menjalankan tugas ---------------------------------------
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Hari ini untuk StartBoundary; kalau jamnya sudah lewat, mulai besok.
$StartBoundary = (Get-Date).Date.Add([timespan]::Parse($Jam))
if ($StartBoundary -lt (Get-Date)) { $StartBoundary = $StartBoundary.AddDays(1) }
$StartBoundaryStr = $StartBoundary.ToString("yyyy-MM-ddTHH:mm:ss")

# --- Template XML tugas --------------------------------------------------
# Catatan pengaturan penting:
#   StartWhenAvailable       = true  -> kalau komputer mati saat jadwalnya,
#                                       backup menyusul begitu komputer hidup.
#   DisallowStartIfOnBatteries = false -> tetap jalan saat pakai baterai.
#   StopIfGoingOnBatteries     = false -> tidak dibatalkan saat kabel dicabut.
$Xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Backup harian source MikroTik Monitor (zip bertanggal + log) dijalankan otomatis oleh Task Scheduler.</Description>
    <Author>$env:USERNAME</Author>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$StartBoundaryStr</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$UserId</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <WakeToRun>false</WakeToRun>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File "$Skrip"</Arguments>
      <WorkingDirectory>$ProjectDir</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@

# schtasks wajib membaca XML versi Unicode (UTF-16 LE)
$XmlPath = Join-Path $env:TEMP "mikrotik_backup_task.xml"
[System.IO.File]::WriteAllText($XmlPath, $Xml, [System.Text.Encoding]::Unicode)

# --- Daftarkan tugas -----------------------------------------------------
Write-Host "Mendaftarkan tugas '$NamaTugas' ..."
& schtasks.exe /create /tn "$NamaTugas" /xml "$XmlPath" /f | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Gagal mendaftarkan tugas (schtasks exit code $LASTEXITCODE)."
}
Remove-Item $XmlPath -Force -ErrorAction SilentlyContinue

# --- Tampilkan ringkasan -------------------------------------------------
$info = & schtasks.exe /query /tn "$NamaTugas" /fo LIST /v
$info | Select-String -Pattern "TaskName|Next Run Time|Status|Last Result|Task To Run|Schedule Type|Start Time|Logon Mode" |
    ForEach-Object { $_.Line.Trim() }

Write-Host ""
Write-Host "Selesai. Backup akan berjalan setiap hari pukul $Jam."
Write-Host "Uji sekarang : schtasks /run /tn `"$NamaTugas`""
Write-Host "Cek hasilnya : Get-Content `"$env:USERPROFILE\MikroTikMonitor-Backups\backup.log`" -Tail 20"
Write-Host "Hapus tugas  : schtasks /delete /tn `"$NamaTugas`" /f"
