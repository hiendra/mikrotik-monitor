# ============================================================
# cek-tm-auth.ps1 - periksa & pulihkan container tm-auth di ZimaOS
# ============================================================
# Menjalankan serangkaian perintah sudo via zima-shell.mjs (pola yang
# sama dengan inspeksi-host.ps1) untuk memastikan container tm-auth:
#   1. terlihat di docker ps -a (status?)
#   2. log terakhirnya
#   3. health dari dalam network: docker exec ... wget /api/health
#   4. BILA container belum ada/tidak sehat: build ulang (DOCKER_CONFIG
#      wajib - root FS ZimaOS read-only) lalu jalankan ulang.
#
# Pakai:
#   MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/cek-tm-auth.ps1 -Sandi '<sandi>'
#
# Opsi:
#   -Perbaiki     build ulang image + jalankan ulang container bila perlu
#   -DenganCaddyfileRestart   restart web-router juga (setelah Caddyfile berubah)
# ============================================================

[CmdletBinding()]
param(
    [string]$Sandi = $env:ZIMA_PASS,
    [string]$Pengguna = 'hendra',
    [string]$Ttyd = '',
    [string]$Akar = '/DATA/AppData/zima-hosting',
    [string]$Image = 'tm-auth:22',
    [switch]$Perbaiki,
    [switch]$DenganCaddyfileRestart
)

$ErrorActionPreference = 'Continue'
$root  = $PSScriptRoot
$shell = Join-Path $root 'zima-shell.mjs'

function Info($pesan, $warna = 'Gray') { Write-Host "  $pesan" -ForegroundColor $warna }

if (-not $Sandi) { Info 'sandi kosong: beri -Sandi atau $env:ZIMA_PASS.' 'Red'; exit 1 }

# --- pilih ttyd yang menjawab ---
function Test-Port([string]$Alamat, [int]$Port, [int]$BatasMs = 1500) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $a = $c.BeginConnect($Alamat, $Port, $null, $null)
        if (-not $a.AsyncWaitHandle.WaitOne($BatasMs)) { return $false }
        $c.EndConnect($a); return $true
    } catch { return $false } finally { $c.Close() }
}
if (-not $Ttyd) {
    foreach ($ip in @('192.168.20.36', '192.168.145.252')) {
        if (Test-Port $ip 7681) { $Ttyd = "ws://${ip}:7681/ws"; break }
    }
}
if (-not $Ttyd) { Info 'tidak ada ttyd yang menjawab di 7681.' 'Red'; exit 1 }

$env:ZIMA_PASS = $Sandi
$env:ZIMA_USER = $Pengguna
$env:TTYD_URL  = $Ttyd

Write-Host ''
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host '   CEK tm-auth (backend akun tamanmarina)' -ForegroundColor Cyan
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host ''

Info "ttyd: $Ttyd"

# --- 1. status container ---
Info '== status container =='
& node $shell "sudo docker ps -a --filter name=tm-auth --format '{{.Names}} | {{.Status}} | {{.Image}}'"

# --- 2. log terakhir ---
Info '== log terakhir =='
& node $shell "sudo docker logs --tail 8 tm-auth 2>&1"

# --- 3. health dari dalam network ---
Info '== health (dari dalam container) =='
& node $shell "sudo docker exec tm-auth wget -qO- http://127.0.0.1:3000/api/health"
$sehat = ($LASTEXITCODE -eq 0)

# --- 4. bila diminta: perbaiki ---
if ($Perbaiki) {
    if (-not $sehat) {
        Info 'container belum sehat -> build ulang + jalankan ulang ...' 'Yellow'
        & node $shell "sudo env DOCKER_CONFIG=/DATA/AppData/.docker docker build -t $Image $Akar/auth"
        if ($LASTEXITCODE -ne 0) { Info 'docker build gagal.' 'Red'; exit 1 }
        & node $shell "sudo docker rm -f tm-auth"
        $netJson = (& node $shell "sudo docker inspect web-router --format '{{json .NetworkSettings.Networks}}'") -join ' '
        $namaNet = $null
        if ($netJson -match '"([A-Za-z0-9_-]+)":\s*\{') { $namaNet = $Matches[1] }
        if (-not $namaNet) { $namaNet = 'web'; Info "network tak terbaca, pakai '$namaNet'." 'Yellow' }
        else { Info "tm-auth ikut network: $namaNet" }
        & node $shell "sudo docker run -d --name tm-auth --restart unless-stopped --network $namaNet -v tm-auth_data:/data $Image"
        if ($LASTEXITCODE -ne 0) { Info 'docker run gagal.' 'Red'; exit 1 }
        Start-Sleep -Seconds 3
        & node $shell "sudo docker ps --filter name=tm-auth --format '{{.Names}} | {{.Status}}'" "sudo docker logs --tail 5 tm-auth 2>&1" "sudo docker exec tm-auth wget -qO- http://127.0.0.1:3000/api/health"
        $sehat = ($LASTEXITCODE -eq 0)
    } else {
        Info 'sudah sehat - tidak perlu perbaikan.' 'Green'
    }
}

# --- 5. bila diminta: restart web-router ---
if ($DenganCaddyfileRestart) {
    Info 'restart web-router ...'
    & node $shell 'sudo docker restart web-router'
    Start-Sleep -Seconds 4
}

# --- 6. catatan sandi pertama (bila volume baru) ---
Info '== catatan sandi admin (AWAL.txt, bila ada) =='
& node $shell "sudo docker exec tm-auth sh -c 'cat /data/AWAL.txt 2>/dev/null || echo TIDAK-ADA'"

Write-Host ''
if ($sehat) { Info 'SEHAT: tm-auth menjawab /api/health.' 'Green'; exit 0 }
Info 'BELUM SEHAT: lihat status & log di atas. Jalankan lagi dengan -Perbaiki.' 'Yellow'
exit 1
