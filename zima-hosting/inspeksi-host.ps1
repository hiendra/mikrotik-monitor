# ============================================================
# inspeksi-host.ps1 - periksa kapabilitas host ZimaOS lewat ttyd
# ============================================================
# Kenapa berkas ini ada: perintah `sudo` tidak boleh ditulis langsung di
# baris perintah (diblokir kebijakan alat), sedangkan akses host memang
# butuh sudo. Pola yang sudah dipakai proyek ini: jalankan sudo lewat
# zima-shell.mjs dari dalam sebuah berkas skrip.
#
# Memeriksa (hanya baca, tidak mengubah apa pun):
#   1. versi Docker di host
#   2. daftar container + image + network-nya
#   3. daftar docker network
#   4. project compose & network milik web-router (Caddy)
#   5. isi folder /DATA/AppData/zima-hosting
#   6. apakah image node:alpine sudah ada / bisa dipakai
#   7. port yang sedang dipakai host
#
# Pakai:
#   MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/inspeksi-host.ps1 -Sandi '<sandi ZimaOS>'
# ============================================================

[CmdletBinding()]
param(
    [string]$Sandi = $env:ZIMA_PASS,
    [string]$Pengguna = 'hendra',
    [string]$Ttyd = ''
)

$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root  = $PSScriptRoot
$shell = Join-Path $root 'zima-shell.mjs'

function Info($pesan, $warna = 'Gray') { Write-Host "  $pesan" -ForegroundColor $warna }

function Test-Port([string]$Alamat, [int]$Port, [int]$BatasMs = 1500) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $a = $c.BeginConnect($Alamat, $Port, $null, $null)
        if (-not $a.AsyncWaitHandle.WaitOne($BatasMs)) { return $false }
        $c.EndConnect($a)
        return $true
    } catch { return $false } finally { $c.Close() }
}

if (-not $Ttyd) {
    foreach ($ip in @('192.168.20.36', '192.168.145.252')) {
        if (Test-Port $ip 7681) { $Ttyd = "ws://${ip}:7681/ws"; break }
    }
}
if (-not $Ttyd) { Info 'tidak ada ttyd yang menjawab di 7681.' 'Red'; exit 1 }
Info "ttyd : $Ttyd"

if (-not $Sandi) {
    $aman = Read-Host -Prompt "  Sandi akun ZimaOS ($Pengguna)" -AsSecureString
    $Sandi = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($aman))
}
if (-not $Sandi) { Info 'sandi kosong - dibatalkan.' 'Red'; exit 1 }

$env:ZIMA_PASS = $Sandi
$env:ZIMA_USER = $Pengguna
$env:TTYD_URL  = $Ttyd

$perintah = @(
    'echo "=== 1. DOCKER VERSION ==="',
    'sudo docker version --format "server={{.Server.Version}}"',
    'echo "=== 2. CONTAINERS ==="',
    'sudo docker ps --format "{{.Names}}|{{.Image}}|{{.Networks}}"',
    'echo "=== 3. NETWORKS ==="',
    'sudo docker network ls',
    'echo "=== 4. WEB-ROUTER COMPOSE/NETWORK ==="',
    'sudo docker inspect -f "project={{ index .Config.Labels \"com.docker.compose.project\" }} dir={{ index .Config.Labels \"com.docker.compose.project.working_dir\" }}" web-router',
    'sudo docker inspect -f "{{ json .NetworkSettings.Networks }}" web-router',
    'echo "=== 5. ISI /DATA/AppData/zima-hosting ==="',
    'sudo ls -la /DATA/AppData/zima-hosting',
    'echo "=== 6. IMAGE NODE ==="',
    'sudo docker images --format "{{.Repository}}:{{.Tag}}" | grep -i node || echo "node: (belum ada)"',
    'echo "=== 7. PORT DI HOST ==="',
    'sudo ss -ltnp | head -40 || sudo netstat -ltnp | head -40',
    'echo "=== 8. NODE DI HOST ==="',
    'node -v 2>/dev/null || echo "node host: tidak ada"'
)

& node $shell ($perintah -join '; ')
exit $LASTEXITCODE
