# ============================================================
# terbitkan-dasbor.ps1 - pasang berkas dasbor ke ZimaOS
# ============================================================
# Menjawab satu masalah spesifik: kartu dasbor tidak ikut berubah setelah
# Anda mengubah centang di tab Dasbor panel-kelola.html, karena berkasnya
# belum pernah sampai ke server. Skrip ini menyalinnya.
#
# Kenapa lewat ttyd, bukan scp? SSH port 22 di ZimaOS TERTUTUP (lihat
# RESET-ADGUARD-HOME.md). Satu-satunya jalan masuk adalah terminal web ttyd -
# alat yang sama yang dipakai zima-shell.mjs untuk menjalankan perintah lain
# di server ini.
#
# Alamat ttyd dicari otomatis: host ini punya dua alamat LAN dan tidak selalu
# keduanya menjawab. Saat skrip ini ditulis, 192.168.20.36:7681 melayani
# "ttyd - Terminal", sedangkan 192.168.145.252:7681 menolak koneksi. Karena
# itu keduanya dicoba berurutan, dan yang menjawab dipakai. Bila Anda punya
# alamat lain, berikan lewat -Ttyd.
#
# Tiga berkas yang dikirim:
#   situs/index.html    - halaman yang memuat dasbor.js
#   situs/dasbor.js     - perender kartu
#   situs/layanan.json  - daftar kartu (inilah yang membuat centang Anda berlaku)
#
# Pakai:
#   powershell -ExecutionPolicy Bypass -File .\terbitkan-dasbor.ps1
#   powershell -ExecutionPolicy Bypass -File .\terbitkan-dasbor.ps1 -Manifest "$env:USERPROFILE\Downloads\layanan.json"
#
# Penting: layanan.json yang ada di repo adalah susunan BAWAAN. Bila Anda
# mengubah centang "Kartu di dasbor" di panel, unduh manifestnya dulu
# (panel -> Hasil Caddyfile -> kartu Manifest dasbor -> "Unduh sebagai
# layanan.json"), lalu berikan berkas itu lewat -Manifest. Tanpa itu, skrip
# ini memasang susunan bawaan dan mengembalikan centang lama.
#
# Berkas situs tidak perlu restart apa pun: Caddy membacanya langsung dari
# folder yang di-mount, jadi cukup muat ulang halaman.
#
# Kode keluar: 0 bila ketiga berkas terpasang dan (bila diverifikasi) dasbor
# melayani manifestnya; 1 bila ada yang gagal.
# ============================================================

[CmdletBinding()]
param(
    [string]$Sandi = $env:ZIMA_PASS,
    [string]$Pengguna = 'hendra',
    [string]$Ttyd = '',
    [string]$Tujuan = '/DATA/AppData/zima-hosting/situs',
    [string]$Manifest = '',
    [string]$Domain = 'clusternet.my.id',
    [switch]$TanpaVerifikasi
)

$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $root
$situs = Join-Path $root 'situs'
$shell = Join-Path $root 'zima-shell.mjs'

$gagal = 0
function Info($pesan, $warna = 'Gray') { Write-Host "  $pesan" -ForegroundColor $warna }

# Pola yang sama dipakai cek-domain.ps1: TcpClient + BeginConnect punya batas
# waktu, karena Connect() biasa bisa menggantung puluhan detik di LAN.
function Test-Port([string]$Alamat, [int]$Port, [int]$BatasMs = 1500) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $a = $c.BeginConnect($Alamat, $Port, $null, $null)
        if (-not $a.AsyncWaitHandle.WaitOne($BatasMs)) { return $false }
        $c.EndConnect($a)
        return $true
    } catch { return $false } finally { $c.Close() }
}

Write-Host ''
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host '   TERBITKAN DASBOR KE ZIMAOS' -ForegroundColor Cyan
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host ''

# ------------------------------------------------------------
# 1. Periksa berkas yang akan dikirim
# ------------------------------------------------------------
if (-not (Test-Path $shell)) { Info "tidak menemukan $shell" 'Red'; exit 1 }

$daftar = @(
    @{ Lokal = (Join-Path $situs 'index.html');  Nama = 'index.html' },
    @{ Lokal = (Join-Path $situs 'dasbor.js');   Nama = 'dasbor.js' }
)

# Manifest: pakai berkas yang diberikan, kalau tidak ada pakai bawaan repo.
$sumberManifest = if ($Manifest) { $Manifest } else { Join-Path $situs 'layanan.json' }
if (-not (Test-Path $sumberManifest)) {
    Info "manifest tidak ditemukan: $sumberManifest" 'Red'
    Info 'unduh dulu dari panel (tab Hasil Caddyfile -> Manifest dasbor), lalu berikan lewat -Manifest' 'Yellow'
    exit 1
}

# Manifest yang rusak lebih baik ditolak di sini daripada membuat dasbor
# tampil kosong tanpa penjelasan.
try {
    $isiManifest = Get-Content -Raw -Path $sumberManifest | ConvertFrom-Json
    $jumlahKartu = @($isiManifest.layanan).Count
    if ($jumlahKartu -lt 1) { throw 'tidak memuat satu kartu pun' }
} catch {
    Info "manifest tidak sah: $sumberManifest -> $_" 'Red'
    exit 1
}

$daftar += @{ Lokal = $sumberManifest; Nama = 'layanan.json' }

foreach ($b in $daftar) {
    if (-not (Test-Path $b.Lokal)) { Info "hilang: $($b.Lokal)" 'Red'; $gagal = 1 }
}
if ($gagal) { exit 1 }

Info "tujuan     : $Tujuan"
Info "manifest   : $sumberManifest ($jumlahKartu kartu)"
if ($Manifest) {
    Info 'manifest dari -Manifest, jadi centang di panel ikut terbawa.' 'Green'
} else {
    Info 'memakai manifest bawaan repo - centang di panel TIDAK ikut. Pakai -Manifest bila sudah mengubahnya.' 'Yellow'
}
Write-Host ''

# ------------------------------------------------------------
# 2a. Pilih alamat ttyd yang benar-benar menjawab
# ------------------------------------------------------------
if (-not $Ttyd) {
    foreach ($ip in @('192.168.145.252', '192.168.20.36')) {
        if (Test-Port $ip 7681) { $Ttyd = "ws://${ip}:7681/ws"; break }
    }
}
if (-not $Ttyd) {
    Info 'tidak ada ttyd yang menjawab di 7681 (dicoba 192.168.145.252 dan 192.168.20.36).' 'Red'
    Info 'pindai-layanan.ps1 bisa memastikan port mana yang hidup; atau berikan alamatnya lewat -Ttyd.' 'Yellow'
    exit 1
}
Info "ttyd       : $Ttyd"
Write-Host ''

# ------------------------------------------------------------
# 2b. Sandi ZimaOS
# ------------------------------------------------------------
if (-not $Sandi) {
    $aman = Read-Host -Prompt "  Sandi akun ZimaOS ($Pengguna)" -AsSecureString
    $Sandi = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($aman))
}
if (-not $Sandi) { Info 'sandi kosong - dibatalkan.' 'Red'; exit 1 }

# ------------------------------------------------------------
# 3. Kirim ketiga berkas lewat ttyd
# ------------------------------------------------------------
$argumen = @()
foreach ($b in $daftar) {
    $argumen += '--upload'
    $argumen += $b.Lokal
    $argumen += "$Tujuan/$($b.Nama)"
}

$env:ZIMA_PASS = $Sandi
$env:ZIMA_USER = $Pengguna
$env:TTYD_URL = $Ttyd

Info 'mengirim berkas ke server (tiap berkas dicadangkan dulu sebagai .bak-TANGGALJAM)...'
Write-Host ''
& node $shell @argumen
$kode = $LASTEXITCODE
Write-Host ''

if ($kode -ne 0) {
    Info 'pengiriman gagal - periksa keluaran di atas (sandi? ttyd sedang dipakai hal lain?)' 'Red'
    exit 1
}

# ------------------------------------------------------------
# 4. Verifikasi dari luar: yang penting manifestnya benar-benar dilayani
# ------------------------------------------------------------
if ($TanpaVerifikasi) {
    Info 'verifikasi dilewati (-TanpaVerifikasi).' 'Yellow'
    exit 0
}

Info "memeriksa https://$Domain/layanan.json ..."
$ok = 0
try {
    $r = Invoke-WebRequest -Uri "https://$Domain/layanan.json" -UseBasicParsing -TimeoutSec 20
    $manifesJauh = $r.Content | ConvertFrom-Json
    $jauh = @($manifesJauh.layanan).Count
    if ($r.StatusCode -eq 200 -and $jauh -ge 1) {
        Info "OK: manifest dilayani, $jauh kartu." 'Green'
        $ok = 1
    } else {
        Info "manifest dilayani tetapi isinya tidak seperti diharapkan (HTTP $($r.StatusCode))." 'Red'
    }
} catch {
    Info "belum bisa dibaca: https://$Domain/layanan.json -> $_" 'Red'
}

if ($ok) {
    try {
        $h = Invoke-WebRequest -Uri "https://$Domain/" -UseBasicParsing -TimeoutSec 20
        if ($h.Content -match 'dasbor\.js') {
            Info 'OK: halaman utama memuat dasbor.js - kartu digambar dari manifest.' 'Green'
        } else {
            Info 'halaman utama BELUM memuat dasbor.js - index.html lama masih dilayani.' 'Red'
            $ok = 0
        }
    } catch {
        Info "gagal membaca halaman utama: $_" 'Red'
    }
    Write-Host ''
    Info 'Selesai. Buka https://clusternet.my.id dengan Ctrl+Shift+R untuk melihat hasilnya.' 'Cyan'
    Info 'Mulai sekarang, mengubah centang di tab Dasbor cukup diikuti tombol Terapkan -' 'Gray'
    Info 'selama folder ./situs di-mount ke container zima-deployer (lihat PANDUAN-WEBHOSTING.md).' 'Gray'
    exit 0
}

Write-Host ''
Info 'Berkas terkirim, tetapi verifikasi belum lolos - cek pesan di atas.' 'Yellow'
exit 1
