# ============================================================
# cadangkan-tamanmarina.ps1 - snapshot dasbor tamanmarina.my.id
# ============================================================
# Menyalin keadaan BAIK yang ada di repo ke sebuah folder bertanggal di
# luar web root, supaya bisa dikembalikan dengan kembalikan-tamanmarina.ps1
# bila perubahan berikutnya bermasalah.
#
# Yang disalin (15 berkas):
#   situs/tamanmarina/index.html, dasbor.css, dasbor.js, pengguna.js,
#     pengaturan.js, masuk.html, masuk.css, masuk.js, hero.svg
#   auth/Dockerfile, izin.mjs, penyimpanan.mjs, server.mjs, mula.sh (backend akun)
#   Caddyfile   (blok tamanmarina + seluruh router - untuk rollback utuh)
#
# Keluaran: cadangan-tamanmarina/<nama>/  +  CATATAN-CADANGAN.md di dalamnya,
#           dan satu entri baru di BUKU-PERUBAHAN.md (buku rollback).
#
# Pakai:
#   pwsh -NoProfile -File .\zima-hosting\cadangkan-tamanmarina.ps1
#   pwsh -NoProfile -File .\zima-hosting\cadangkan-tamanmarina.ps1 -Nama sebelum-ubah-tema
# ============================================================

[CmdletBinding()]
param(
    [string]$Nama = (Get-Date -Format 'yyyy-MM-dd'),
    [string]$Catatan = ''
)

$ErrorActionPreference = 'Stop'
$root     = $PSScriptRoot
$situs    = Join-Path $root 'situs\tamanmarina'
$akarCad  = Join-Path $root 'cadangan-tamanmarina'
$tujuan   = Join-Path $akarCad $Nama

$aset = @('index.html', 'dasbor.css', 'dasbor.js', 'pengguna.js', 'pengaturan.js', 'masuk.html', 'masuk.css', 'masuk.js', 'hero.svg')
$auth = @('Dockerfile', 'izin.mjs', 'penyimpanan.mjs', 'server.mjs', 'mula.sh')
$authLokal = Join-Path $root 'auth'
$sumber = @()
foreach ($a in $aset) { $sumber += Join-Path $situs $a }
foreach ($a in $auth) { $sumber += Join-Path $authLokal $a }
$sumber += Join-Path $root 'Caddyfile'

function Info($pesan, $warna = 'Gray') { Write-Host "  $pesan" -ForegroundColor $warna }

Write-Host ''
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host '   CADANGKAN dasbor tamanmarina.my.id' -ForegroundColor Cyan
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host ''

# --- 1. Pastikan sumber lengkap ---
$hilang = @()
foreach ($s in $sumber) { if (-not (Test-Path $s)) { $hilang += $s } }
if ($hilang.Count) {
    foreach ($h in $hilang) { Info "hilang: $h" 'Red' }
    Info 'cadangan dibatalkan - perbaiki berkas di atas dulu.' 'Red'
    exit 1
}

if (Test-Path $tujuan) {
    Info "folder tujuan sudah ada: $tujuan" 'Yellow'
    Info 'pakai nama lain dengan -Nama, atau hapus folder itu lebih dulu.' 'Yellow'
    exit 1
}

# --- 2. Salin ---
New-Item -ItemType Directory -Path $tujuan -Force | Out-Null
foreach ($s in $sumber) {
    $t = Join-Path $tujuan (Split-Path $s -Leaf)
    Copy-Item -LiteralPath $s -Destination $t
    $ukuran = (Get-Item $t).Length
    Info ("{0,-16} {1,8} bita  ->  {2}" -f (Split-Path $s -Leaf), $ukuran, (Split-Path $t -Leaf)) 'Green'
}

# --- 3. Catatan di dalam snapshot ---
$waktu = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
$baris = @(
    "# Catatan Cadangan — tamanmarina.my.id",
    "",
    "- Nama cadangan : $Nama",
    "- Dibuat        : $waktu",
    "- Dari          : zima-hosting/ (repo)",
    "- Catatan       : $Catatan",
    "",
    "## Isi",
    "",
    "| Berkas | Tujuan saat dikembalikan |",
    "|---|---|",
    "| index.html, dasbor.css, dasbor.js, pengguna.js, pengaturan.js, masuk.html, masuk.css, masuk.js, hero.svg | zima-hosting/situs/tamanmarina/ |",
    "| Dockerfile, izin.mjs, penyimpanan.mjs, server.mjs, mula.sh | zima-hosting/auth/ |",
    "| Caddyfile | zima-hosting/Caddyfile (seluruh router) |",
    "",
    "## Cara mengembalikan",
    "",
    '```',
    "MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan $Nama -Sandi '<sandi ZimaOS>'",
    '```',
    "",
    "Lihat juga: zima-hosting/DASBOR-TAMANMARINA.md bagian 7 (Rollback).",
    ""
)
Set-Content -LiteralPath (Join-Path $tujuan 'CATATAN-CADANGAN.md') -Value ($baris -join "`n") -Encoding utf8 -NoNewline
Info 'CATATAN-CADANGAN.md ditulis.' 'Green'

# --- 4. Catat di BUKU-PERUBAHAN.md ---
# Snapshot tanpa catatan mudah terlupakan; buku ini yang membuat titik pulih
# bisa ditemukan dan dipakai orang lain (termasuk diri sendiri nanti).
. (Join-Path $root 'buku-catatan.ps1')
Tambah-BukuCatatan -Aksi 'Cadangan' -Judul $Nama -Catatan $Catatan `
    -Berkas ($aset + $auth + @('Caddyfile')) `
    -Rollback "snapshot: cadangan-tamanmarina/$Nama (lihat CATATAN-CADANGAN.md di dalamnya). Kembalikan: MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan $Nama -Sandi '<sandi ZimaOS>'"
Info 'BUKU-PERUBAHAN.md diperbarui.' 'Green'

Write-Host ''
Info "Selesai. Cadangan ada di: $tujuan" 'Cyan'
exit 0
