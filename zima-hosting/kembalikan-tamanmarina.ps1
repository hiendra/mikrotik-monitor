# ============================================================
# kembalikan-tamanmarina.ps1 - rollback dasbor tamanmarina.my.id
# ============================================================
# Mengembalikan berkas repo dari sebuah snapshot di cadangan-tamanmarina/,
# lalu (opsional) menerbitkan ulang ke ZimaOS lewat jalur yang sama dengan
# terbitkan-tamanmarina.ps1.
#
# Yang dipulihkan: 9 aset situs (index.html, dasbor.css, dasbor.js, pengguna.js,
# pengaturan.js, masuk.html, masuk.css, masuk.js, hero.svg) + 5 berkas auth
# (Dockerfile, izin.mjs, penyimpanan.mjs, server.mjs, mula.sh). Berkas yang
# tidak ada di snapshot lama dilewati dengan peringatan. Setiap rollback juga
# menulis entri ke BUKU-PERUBAHAN.md (lihat buku-catatan.ps1).
#
# Aman secara bawaan:
#   - keadaan repo SEKARANG dicadangkan dulu ke cadangan-tamanmarina/pra-kembali-<stamp>
#     sebelum ditimpa (jadi rollback pun bisa dibatalkan).
#   - Caddyfile TIDAK ikut dikembalikan kecuali diminta dengan -DenganCaddyfile,
#     karena Caddyfile memuat SELURUH router: mengembalikannya bisa membatalkan
#     perubahan tak terkait (termasuk layanan clusternet.my.id). Berkas itu
#     biasanya cukup dipulihkan sendiri bila memang blok tamanmarina yang rusak.
#
# Pakai:
#   # snapshot terbaru, hanya berkas situs, lalu terbitkan:
#   pwsh -NoProfile -File .\zima-hosting\kembalikan-tamanmarina.ps1 -Sandi '<sandi>'
#
#   # snapshot tertentu + kembalikan Caddyfile juga:
#   pwsh -NoProfile -File .\zima-hosting\kembalikan-tamanmarina.ps1 -Cadangan 2026-10-05 -DenganCaddyfile -Sandi '<sandi>'
#
#   # hanya menyiapkan berkas lokal (tanpa menyentuh host):
#   pwsh -NoProfile -File .\zima-hosting\kembalikan-tamanmarina.ps1 -Cadangan 2026-10-05 -TanpaTerbit
# ============================================================

[CmdletBinding()]
param(
    [string]$Cadangan = '',
    [switch]$DenganCaddyfile,
    [switch]$TanpaTerbit,
    [string]$Sandi = $env:ZIMA_PASS,
    [string]$Pengguna = 'hendra',
    [string]$Ttyd = '',
    [string]$Akar = '/DATA/AppData/zima-hosting'
)

$ErrorActionPreference = 'Stop'
$root    = $PSScriptRoot
$situs   = Join-Path $root 'situs\tamanmarina'
$authDir = Join-Path $root 'auth'
$akarCad = Join-Path $root 'cadangan-tamanmarina'

# Berkas yang ikut dikembalikan. Daftar ini HARUS sejalan dengan $asetLokal /
# $authBerkas di terbitkan-tamanmarina.ps1 dan $aset / $auth di
# cadangkan-tamanmarina.ps1 - kalau menambah berkas baru, tambahkan di ketiganya.
# Snapshot lama boleh tidak lengkap (mis. belum ada pengaturan.js): berkas yang
# tidak ada di snapshot DILEWATI dengan peringatan, bukan menggagalkan rollback.
$asetSitus = @('index.html', 'dasbor.css', 'dasbor.js', 'pengguna.js', 'pengaturan.js', 'masuk.html', 'masuk.css', 'masuk.js', 'hero.svg')
$asetAuth  = @('Dockerfile', 'izin.mjs', 'penyimpanan.mjs', 'server.mjs', 'mula.sh')
$wajib     = @('index.html', 'dasbor.css', 'dasbor.js')

# Buku catatan rollback (BUKU-PERUBAHAN.md).
. (Join-Path $root 'buku-catatan.ps1')

function Info($pesan, $warna = 'Gray') { Write-Host "  $pesan" -ForegroundColor $warna }

Write-Host ''
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host '   KEMBALIKAN dasbor tamanmarina.my.id (rollback)' -ForegroundColor Cyan
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host ''

# --- 1. Pilih snapshot ---
if (-not $Cadangan) {
    if (-not (Test-Path $akarCad)) { Info "tidak ada folder cadangan: $akarCad" 'Red'; exit 1 }
    $kandidat = Get-ChildItem -Path $akarCad -Directory |
        Where-Object { $_.Name -notlike 'pra-kembali-*' } |
        Sort-Object Name
    if (-not $kandidat.Count) { Info 'belum ada snapshot. Jalankan cadangkan-tamanmarina.ps1 dulu.' 'Red'; exit 1 }
    $Cadangan = $kandidat[-1].Name
    Info "snapshot terbaru dipakai: $Cadangan" 'Yellow'
}

$sumber = Join-Path $akarCad $Cadangan
if (-not (Test-Path $sumber)) { Info "snapshot tidak ditemukan: $sumber" 'Red'; exit 1 }

# --- 2. Periksa isi snapshot ---
foreach ($a in $wajib) {
    if (-not (Test-Path (Join-Path $sumber $a))) {
        Info "snapshot tidak lengkap, hilang: $a" 'Red'
        exit 1
    }
}
if ($DenganCaddyfile -and -not (Test-Path (Join-Path $sumber 'Caddyfile'))) {
    Info 'snapshot tidak memuat Caddyfile, tetapi -DenganCaddyfile diminta.' 'Red'
    exit 1
}

# Rencana pemulihan: pasangan (berkas di snapshot -> tujuannya di repo).
$rencana = @()
foreach ($a in $asetSitus) {
    $rencana += [pscustomobject]@{
        Nama = $a
        Asal = (Join-Path $sumber $a)
        Tujuan = (Join-Path $situs $a)
        Label = "situs/tamanmarina/$a"
    }
}
foreach ($a in $asetAuth) {
    $rencana += [pscustomobject]@{
        Nama = $a
        Asal = (Join-Path $sumber $a)
        Tujuan = (Join-Path $authDir $a)
        Label = "auth/$a"
    }
}
$adaDiSnapshot = @($rencana | Where-Object { Test-Path $_.Asal })
$takAda = @($rencana | Where-Object { -not (Test-Path $_.Asal) })
if ($takAda.Count) {
    Info ("snapshot tanpa " + $takAda.Count + " berkas (wajar untuk snapshot lama), dilewati: " + (($takAda | ForEach-Object { $_.Nama }) -join ', ')) 'Yellow'
}

Info "snapshot  : $sumber"
Info ("dipulihkan: " + (($adaDiSnapshot | ForEach-Object { $_.Label }) -join ', '))
Info ("caddyfile : " + $(if ($DenganCaddyfile) { 'IKUT dikembalikan' } else { 'tidak diubah (pakai -DenganCaddyfile bila perlu)' }))
Write-Host ''

# --- 3. Cadangkan keadaan sekarang (supaya rollback bisa dibatalkan) ---
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$pra = Join-Path $akarCad "pra-kembali-$stamp"
New-Item -ItemType Directory -Path $pra -Force | Out-Null
foreach ($r in $adaDiSnapshot) {
    if (Test-Path $r.Tujuan) { Copy-Item -LiteralPath $r.Tujuan -Destination (Join-Path $pra $r.Nama) }
}
Copy-Item -LiteralPath (Join-Path $root 'Caddyfile') -Destination (Join-Path $pra 'Caddyfile') -ErrorAction SilentlyContinue
Info "keadaan sekarang diselamatkan ke: $pra" 'Green'

# --- 4. Tulis ulang berkas dari snapshot ---
foreach ($r in $adaDiSnapshot) {
    New-Item -ItemType Directory -Path (Split-Path $r.Tujuan) -Force | Out-Null
    Copy-Item -LiteralPath $r.Asal -Destination $r.Tujuan -Force
    Info "dipulihkan: $($r.Label)" 'Green'
}
if ($DenganCaddyfile) {
    Copy-Item -LiteralPath (Join-Path $sumber 'Caddyfile') -Destination (Join-Path $root 'Caddyfile') -Force
    Info 'dipulihkan: Caddyfile (SELURUH router)' 'Yellow'
}

# --- 5. Terbitkan ulang ---
if ($TanpaTerbit) {
    Write-Host ''
    Tambah-BukuCatatan -Aksi 'Kembali' -Judul "Rollback lokal ke $Cadangan" `
        -Berkas ($adaDiSnapshot | ForEach-Object { $_.Label }) `
        -Catatan 'Hanya berkas lokal yang dipulihkan; host belum disentuh.' `
        -Uji 'belum diterbitkan (-TanpaTerbit)' `
        -Rollback "keadaan sebelum rollback: cadangan-tamanmarina/pra-kembali-$stamp"
    Info 'BUKU-PERUBAHAN.md diperbarui.' 'Green'
    Info 'Berkas lokal sudah dipulihkan. Terbitkan manual bila siap:' 'Cyan'
    Info '  MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/terbitkan-tamanmarina.ps1 -Sandi <sandi>' 'Gray'
    exit 0
}

$terbit = Join-Path $root 'terbitkan-tamanmarina.ps1'
if (-not (Test-Path $terbit)) { Info "tidak menemukan $terbit - berkas lokal sudah dipulihkan." 'Yellow'; exit 1 }

Write-Host ''
Info 'menerbitkan ulang ke ZimaOS ...' 'Cyan'
$arg = @{ Akar = $Akar; Pengguna = $Pengguna }
if ($Sandi) { $arg['Sandi'] = $Sandi }
if ($Ttyd)  { $arg['Ttyd']  = $Ttyd }
& $terbit @arg
$kode = $LASTEXITCODE
Write-Host ''
Tambah-BukuCatatan -Aksi 'Kembali' -Judul "Rollback ke $Cadangan" `
    -Berkas ($adaDiSnapshot | ForEach-Object { $_.Label }) `
    -Uji "terbit ulang kode $kode" `
    -Rollback "keadaan sebelum rollback: cadangan-tamanmarina/pra-kembali-$stamp"
Info 'BUKU-PERUBAHAN.md diperbarui.' 'Green'
if ($kode -eq 0) { Info "Rollback selesai (snapshot: $Cadangan)." 'Cyan' }
else { Info "Penerbitan gagal (kode $kode). Berkas lokal tetap sudah dipulihkan; periksa keluaran di atas." 'Yellow' }
exit $kode
