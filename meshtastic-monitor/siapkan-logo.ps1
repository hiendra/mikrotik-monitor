# siapkan-logo.ps1 - kecilkan logo MeshNodeID untuk halaman exporter
# ============================================================
# Halaman exporter menyegar sendiri tiap 5 detik, jadi gambar TIDAK boleh
# disisipkan ke dalam HTML: berkas asli 2048x2048 (3,1 MB) akan terunduh ulang
# setiap penyegaran dan halaman membengkak berkali-kali. Karena itu logo
# disiapkan sebagai dua berkas kecil di folder yang sama dengan
# exporter-meshtastic.py, lalu dilayani terpisah di /logo.png dan /favicon.png:
#
#   meshnodeid-256.png  -> <img> di samping judul "Meshnode-ID Monitor"
#   meshnodeid-64.png   -> <link rel="icon">, ikon pada tab peramban
#
# Skrip ini juga memangkas pinggiran transparan sebelum mengecilkan gambar.
# Tanpa itu, logo yang punya banyak ruang kosong di tepinya akan tampil kecil
# di halaman walau berkasnya besar.
#
# Pakai (dari folder meshtastic-monitor):
#   powershell -NoProfile -File siapkan-logo.ps1
#   powershell -NoProfile -File siapkan-logo.ps1 -Sumber D:\lain\logo.png
#
# Lingkungan:
#   -Sumber   (opsional, bawaan %USERPROFILE%\Downloads\meshnodeid.png)
#   -Besar    (opsional, bawaan 256) ukuran berkas untuk kepala halaman
#   -Kecil    (opsional, bawaan 64)  ukuran berkas untuk ikon tab
# ============================================================
param(
    [string]$Sumber = "$env:USERPROFILE\Downloads\meshnodeid.png",
    [int]$Besar = 256,
    [int]$Kecil = 64,
    [int]$BatasTransparan = 8
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if (-not (Test-Path -LiteralPath $Sumber)) {
    Write-Host "Tidak menemukan berkas sumber: $Sumber" -ForegroundColor Red
    Write-Host "Tentukan sendiri dengan: -Sumber <jalur-png>"
    exit 1
}

$jalurSumber = (Resolve-Path -LiteralPath $Sumber).Path
$src = [System.Drawing.Bitmap]::FromFile($jalurSumber)
Write-Host ("Sumber : {0}" -f $jalurSumber)
Write-Host ("         {0} x {1} px, {2:N0} byte" -f $src.Width, $src.Height,
            (Get-Item -LiteralPath $jalurSumber).Length)

# --- 1. cari batas gambar sebenarnya, buang pinggiran transparan -------------
# Diperiksa tiap 4 piksel saja: cukup untuk menemukan pinggiran, dan jauh lebih
# cepat daripada memeriksa 4 juta piksel satu per satu lewat GetPixel.
$langkah = 4
$kiri = $src.Width; $atas = $src.Height; $kanan = 0; $bawah = 0
for ($y = 0; $y -lt $src.Height; $y += $langkah) {
    for ($x = 0; $x -lt $src.Width; $x += $langkah) {
        if ($src.GetPixel($x, $y).A -gt $BatasTransparan) {
            if ($x -lt $kiri)  { $kiri = $x }
            if ($y -lt $atas)  { $atas = $y }
            if ($x -gt $kanan) { $kanan = $x }
            if ($y -gt $bawah) { $bawah = $y }
        }
    }
}
if ($kanan -le $kiri -or $bawah -le $atas) {
    # Seluruh gambar tembus pandang (atau berkas tanpa kanal alfa): pakai utuh.
    Write-Host "Tidak ada piksel nyata yang terdeteksi - gambar dipakai apa adanya."
    $kiri = 0; $atas = 0; $kanan = $src.Width - 1; $bawah = $src.Height - 1
}

$lebar = $kanan - $kiri + 1
$tinggi = $bawah - $atas + 1
$sisi = [Math]::Max($lebar, $tinggi)
$margin = [int]($sisi * 0.02)          # 2% ruang supaya tepi tidak terasa terpotong
$sisi = $sisi + 2 * $margin
$pusatX = [int](($kiri + $kanan) / 2)
$pusatY = [int](($atas + $bawah) / 2)
$x0 = $pusatX - [int]($sisi / 2)
$y0 = $pusatY - [int]($sisi / 2)

# Bila potongan itu keluar dari kanvas gambar, pakai gambar utuh - lebih baik
# ada sedikit ruang kosong daripada ada bagian logo yang terpotong.
if ($x0 -lt 0 -or $y0 -lt 0 -or ($x0 + $sisi) -gt $src.Width -or ($y0 + $sisi) -gt $src.Height) {
    $x0 = 0; $y0 = 0
    $sisi = [Math]::Min($src.Width, $src.Height)
}

Write-Host ("Isi    : {0} x {1} px mulai ({2},{3}) - dipotong ke {4} x {4} px" -f `
            $lebar, $tinggi, $kiri, $atas, $sisi)

# --- 2. gambar ulang ke kanvas persegi berlatar tembus pandang --------------
$kotakSumber = New-Object System.Drawing.Rectangle($x0, $y0, $sisi, $sisi)

function Buat-Berkas([int]$ukuran, [string]$nama) {
    $hasil = New-Object System.Drawing.Bitmap($ukuran, $ukuran,
        [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($hasil)
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)
    $kotakTujuan = New-Object System.Drawing.Rectangle(0, 0, $ukuran, $ukuran)
    $g.DrawImage($src, $kotakTujuan, $kotakSumber, [System.Drawing.GraphicsUnit]::Pixel)
    $g.Dispose()
    $jalur = Join-Path $PSScriptRoot $nama
    $hasil.Save($jalur, [System.Drawing.Imaging.ImageFormat]::Png)
    $hasil.Dispose()
    Write-Host ("  {0,-20} {1} x {1} px  {2:N0} byte" -f `
                $nama, $ukuran, (Get-Item -LiteralPath $jalur).Length)
}

Write-Host "Hasil  :"
Buat-Berkas $Besar 'meshnodeid-256.png'
Buat-Berkas $Kecil 'meshnodeid-64.png'
$src.Dispose()

Write-Host ""
Write-Host "Selesai. Kedua berkas itu diunggah bersama exporter-meshtastic.py;"
Write-Host "exporter melayaninya di /logo.png dan /favicon.png."
