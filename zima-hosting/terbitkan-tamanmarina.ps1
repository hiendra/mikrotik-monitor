# ============================================================
# terbitkan-tamanmarina.ps1 - pasang rute + halaman tamanmarina.my.id
# ============================================================
# Kenapa skrip ini ada, padahal sudah ada zima-deployer (:8791)?
#   Deployer di host ternyata TIDAK menulis ke berkas yang dibaca web-router
#   (percobaan 4 Okt 2026: /deploy menjawab HTTP 200 "sehat", tetapi Host
#   tamanmarina.my.id tetap jatuh ke fallback :80). Jadi untuk saat ini satu-
#   satunya jalur yang pasti adalah menulis langsung ke path LIVE:
#     /DATA/AppData/zima-hosting/Caddyfile
#     /DATA/AppData/zima-hosting/situs/tamanmarina/index.html
#
# SSH port 22 di ZimaOS TERTUTUP, jadi jalurnya lewat terminal web ttyd -
# alat yang sama dengan zima-shell.mjs (lihat catatan panjang di berkas itu).
#
# Yang dilakukan, berurutan:
#   1. buat folder situs/tamanmarina + auth di host (kalau belum ada)
#   2. unggah Caddyfile         -> /DATA/AppData/zima-hosting/Caddyfile
#      unggah index.html, dasbor.css, dasbor.js, pengguna.js, pengaturan.js,
#      masuk.html, masuk.css, masuk.js, hero.svg
#                               -> /DATA/AppData/zima-hosting/situs/tamanmarina/
#      unggah Dockerfile + izin.mjs + penyimpanan.mjs + server.mjs
#                               -> /DATA/AppData/zima-hosting/auth/
#      (tiap berkas tujuan dicadangkan lebih dulu sebagai .bak-TANGGALJAM)
#   3. `docker build` image tm-auth lalu jalankan container:
#        - network yang SAMA dengan web-router (deteksi otomatis)
#        - volume tm-auth_data:/data (akun & audit bertahan antar restart)
#        - TANPA port yang dipublikasikan (hanya Caddy yang menghubungi)
#   4. `sudo docker restart web-router`
#   5. periksa dari luar: tamanmarina.my.id harus 200, /masuk 200,
#      /api/health 200, dan clusternet.my.id tetap 200 (tidak ada regresi).
#      Sandi awal admin (bila container baru dibuat) dicetak di layar -
#      catat, masuk, ganti sandi, lalu hapus /data/AWAL.txt di container.
#
# Urutan pemanggilan node PENTING: zima-shell.mjs mengumpulkan semua --upload
# lebih dulu dan menaruh perintah biasa di DEPAN-nya. Karena itu pembuatan
# folder, pengunggahan, dan restart dipecah menjadi tiga pemanggilan terpisah -
# kalau digabung, `docker restart` akan jalan SEBELUM berkas naik.
#
# Pakai:
#   powershell -ExecutionPolicy Bypass -File .\zima-hosting\terbitkan-tamanmarina.ps1
#
# Sandi tidak pernah lewat chat/argumen: diketik di prompt skrip ini, atau
# diberikan lewat variabel $env:ZIMA_PASS.
# ============================================================

[CmdletBinding()]
param(
    [string]$Sandi = $env:ZIMA_PASS,
    [string]$Pengguna = 'hendra',
    [string]$Ttyd = '',
    [string]$Akar = '/DATA/AppData/zima-hosting',
    [switch]$TanpaVerifikasi,
    [string]$Catatan = ''
)

$ErrorActionPreference = 'Continue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root  = $PSScriptRoot
$shell = Join-Path $root 'zima-shell.mjs'
$caddyLokal = Join-Path $root 'Caddyfile'
$situsLokal = Join-Path $root 'situs\tamanmarina'
$halamanLokal = Join-Path $situsLokal 'index.html'
# Aset dasbor yang ikut naik. Tambahkan di sini kalau halaman memakai
# berkas lain (mis. gambar) supaya tidak lupa saat menerbitkan.
$asetLokal = @('index.html', 'dasbor.css', 'dasbor.js', 'pengguna.js', 'pengaturan.js', 'masuk.html', 'masuk.css', 'masuk.js', 'hero.svg')
# Sumber service tm-auth (backend akun) yang di-build di host.
$authLokal = Join-Path $root 'auth'
$authBerkas = @('Dockerfile', 'izin.mjs', 'penyimpanan.mjs', 'server.mjs', 'mula.sh')
$authImage = 'tm-auth:22'

$gagal = 0
function Info($pesan, $warna = 'Gray') { Write-Host "  $pesan" -ForegroundColor $warna }

# Buku catatan rollback (BUKU-PERUBAHAN.md). Di-dot-source di sini, di akar
# skrip, supaya $script:BerkasBuku menunjuk berkas yang benar.
. (Join-Path $root 'buku-catatan.ps1')

# Titik pulih terbaru di repo - ditulis ke entri buku agar tiap penerbitan
# menunjuk ke satu perintah rollback yang jelas, bukan tebakan.
function TitikPulihTerbaru {
    $akarCad = Join-Path $root 'cadangan-tamanmarina'
    if (-not (Test-Path $akarCad)) { return 'belum ada snapshot di cadangan-tamanmarina/' }
    $k = Get-ChildItem -Path $akarCad -Directory |
        Where-Object { $_.Name -notlike 'pra-kembali-*' } | Sort-Object Name
    if (-not $k.Count) { return 'belum ada snapshot di cadangan-tamanmarina/' }
    $pilih = $k[-1].Name
    return "cadangan-tamanmarina/$pilih -> MSYS_NO_PATHCONV=1 pwsh -NoProfile -File ./zima-hosting/kembalikan-tamanmarina.ps1 -Cadangan $pilih -Sandi '<sandi>'"
}

function CatatTerbit($uji) {
    $judul = if ($Catatan) { $Catatan } else { 'Terbit aset dasbor + tm-auth (tanpa catatan)' }
    Tambah-BukuCatatan -Aksi 'Terbit' -Judul $judul -Catatan $Catatan `
        -Berkas ($asetLokal + $authBerkas + @('Caddyfile')) `
        -Uji $uji -Rollback (TitikPulihTerbaru)
    Info 'BUKU-PERUBAHAN.md diperbarui.' 'Green'
}

Write-Host ''
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host '   TERBITKAN tamanmarina.my.id KE ZIMAOS' -ForegroundColor Cyan
Write-Host '  ============================================================' -ForegroundColor DarkGray
Write-Host ''

# ------------------------------------------------------------
# 1. Periksa berkas yang akan dikirim
# ------------------------------------------------------------
foreach ($b in @($shell, $caddyLokal, $halamanLokal)) {
    if (-not (Test-Path $b)) { Info "hilang: $b" 'Red'; $gagal = 1 }
}
foreach ($a in $authBerkas) {
    $jalur = Join-Path $authLokal $a
    if (-not (Test-Path $jalur)) { Info "hilang: $jalur" 'Red'; $gagal = 1 }
}
foreach ($a in $asetLokal) {
    $jalur = Join-Path $situsLokal $a
    if (-not (Test-Path $jalur)) { Info "hilang: $jalur" 'Red'; $gagal = 1 }
}
if ($gagal) { exit 1 }

Info "caddyfile  : $caddyLokal"
Info "situs      : $situsLokal ($($asetLokal -join ', '))"
Info "auth       : $authLokal ($($authBerkas -join ', '))"
Info "akar host  : $Akar"
Write-Host ''

# ------------------------------------------------------------
# 2a. Pilih alamat ttyd yang menjawab
# ------------------------------------------------------------
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
if (-not $Ttyd) {
    Info 'tidak ada ttyd yang menjawab di 7681 (dicoba 192.168.20.36 & 192.168.145.252).' 'Red'
    exit 1
}
Info "ttyd       : $Ttyd"

# ------------------------------------------------------------
# 2b. Sandi ZimaOS
# ------------------------------------------------------------
if (-not $Sandi) {
    $aman = Read-Host -Prompt "  Sandi akun ZimaOS ($Pengguna)" -AsSecureString
    $Sandi = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($aman))
}
if (-not $Sandi) { Info 'sandi kosong - dibatalkan.' 'Red'; exit 1 }

$env:ZIMA_PASS = $Sandi
$env:ZIMA_USER = $Pengguna
$env:TTYD_URL  = $Ttyd
Write-Host ''

# ------------------------------------------------------------
# 3. Tiga langkah terpisah (urutan penting - lihat catatan atas)
# ------------------------------------------------------------
Info '1/4 membuat folder + memastikan path LIVE (mount web-router) ...'
# Diagnosis: cetak sumber mount Caddyfile & situs yang benar-benar dibaca
# web-router. Kalau salah satu baris di bawah TIDAK menunjuk $Akar, hentikan
# dan beri tahu saya - berarti path LIVE berbeda dari yang didokumentasikan.
& node $shell `
    "sudo mkdir -p $Akar/situs/tamanmarina $Akar/auth" `
    "sudo docker inspect -f '{{ json .Mounts }}' web-router"
if ($LASTEXITCODE -ne 0) { Info 'gagal membuat folder / membaca mount.' 'Red'; exit 1 }

Write-Host ''
Info '2/4 mengunggah Caddyfile + halaman & aset + sumber tm-auth (dicadangkan otomatis sebagai .bak-TANGGALJAM) ...'
$unggah = @('--upload', $caddyLokal, "$Akar/Caddyfile")
foreach ($a in $asetLokal) {
    $unggah += @('--upload', (Join-Path $situsLokal $a), "$Akar/situs/tamanmarina/$a")
}
foreach ($a in $authBerkas) {
    $unggah += @('--upload', (Join-Path $authLokal $a), "$Akar/auth/$a")
}
& node $shell @unggah
if ($LASTEXITCODE -ne 0) { Info 'pengiriman gagal - periksa keluaran di atas (sandi? ttyd sedang dipakai?).' 'Red'; exit 1 }

Write-Host ''
Info '3/4 mem-build & menjalankan tm-auth (network web-router, tanpa port publik) ...'
# Nama network diambil dari web-router sendiri - compose App Store kadang
# menamai network dengan awalan proyek, jadi jangan menebak 'web'.
# DOCKER_CONFIG wajib: root FS ZimaOS read-only, tanpa ini docker build
# gagal dengan "mkdir /root/.docker: read-only file system".
& node $shell "sudo env DOCKER_CONFIG=/DATA/AppData/.docker docker build -t $authImage $Akar/auth"
if ($LASTEXITCODE -ne 0) { Info 'docker build tm-auth gagal.' 'Red'; exit 1 }
& node $shell "sudo docker rm -f tm-auth"
# Nama network web-router dibaca dulu (dua langkah, tanpa kutip bersarang):
# compose App Store kadang menamai network dengan awalan proyek.
$cmdNet = "sudo docker inspect web-router --format '{{json .NetworkSettings.Networks}}'"
$netJson = (& node $shell $cmdNet) -join ' '
$namaNet = $null
if ($netJson -match '"([A-Za-z0-9_-]+)":\s*\{') { $namaNet = $Matches[1] }
if (-not $namaNet) { $namaNet = 'web'; Info "network web-router tak terbaca, memakai bawaan '$namaNet'." 'Yellow' }
else { Info "tm-auth ikut network: $namaNet" }
& node $shell "sudo docker run -d --name tm-auth --restart unless-stopped --network $namaNet -v tm-auth_data:/data $authImage"
if ($LASTEXITCODE -ne 0) { Info 'menjalankan container tm-auth gagal.' 'Red'; exit 1 }
Start-Sleep -Seconds 3
& node $shell "sudo docker exec tm-auth wget -qO- http://127.0.0.1:3000/api/health" "sudo docker ps --filter name=tm-auth --format '{{.Names}} {{.Status}}'"
if ($LASTEXITCODE -ne 0) { Info 'tm-auth belum sehat - periksa: sudo docker logs tm-auth' 'Red'; exit 1 }

Write-Host ''
Info '4/4 me-restart web-router ...'
& node $shell 'sudo docker restart web-router'
if ($LASTEXITCODE -ne 0) { Info 'restart gagal.' 'Red'; exit 1 }

Write-Host ''
# Sandi admin pertama hanya ditulis saat volume masih kosong (pemasangan
# baru). Tampilkan agar pemilik bisa masuk pertama kali, lalu wajib ganti.
& node $shell "sudo docker exec tm-auth sh -c 'cat /data/AWAL.txt 2>/dev/null || echo TIDAK-ADA'" | ForEach-Object {
    Info "CATATAN SANDI: $_"
}
Info 'Bila di atas ada sandi: masuk sebagai admin, GANTI sandi, lalu hapus AWAL.txt (docker exec tm-auth rm /data/AWAL.txt).' 'Yellow'

# ------------------------------------------------------------
# 4. Verifikasi dari luar
# ------------------------------------------------------------
if ($TanpaVerifikasi) {
    Info 'verifikasi dilewati (-TanpaVerifikasi).' 'Yellow'
    CatatTerbit 'verifikasi dilewati (TanpaVerifikasi)'
    exit 0
}

Write-Host ''
Info 'menunggu Caddy siap lalu memeriksa rute ...'
Start-Sleep -Seconds 4

$ok = 0
try {
    $r = Invoke-WebRequest -Uri 'https://tamanmarina.my.id/' -UseBasicParsing -TimeoutSec 25
    if ($r.StatusCode -eq 200 -and $r.Content -match 'Taman Marina' -and $r.Content -match 'dasbor.css') {
        Info 'OK: tamanmarina.my.id melayani dasbor warga (200).' 'Green'
        $ok = 1
    } else {
        Info "tamanmarina.my.id menjawab HTTP $($r.StatusCode) tetapi isinya belum seperti diharapkan." 'Red'
        Info '  (cek: docker logs web-router; berkas mungkin belum naik)' 'Yellow'
    }
} catch {
    Info "tamanmarina.my.id belum bisa dibaca: $_" 'Red'
}

# Aset harus ikut terpasang - kalau tidak, halaman tampil tanpa gaya/skrip.
# Cache-buster (`?terbit=`) penting: Cloudflare meng-cache aset statis, jadi
# memeriksa URL polos bisa membaca SALINAN LAMA dan lolos padahal isinya belum
# terganti. Tautan di index.html juga memakai versi (?v=) dengan alasan sama.
$stampCek = [DateTime]::UtcNow.ToString('yyyyMMddHHmmss')
foreach ($a in $asetLokal) {
    if ($a -eq 'index.html') { continue }
    try {
        $h = Invoke-WebRequest -Uri "https://tamanmarina.my.id/$a`?terbit=$stampCek" -UseBasicParsing -TimeoutSec 25
        if ($h.StatusCode -eq 200 -and $h.RawContentLength -gt 0) {
            Info "OK: /$a tersaji ($($h.RawContentLength) bita)." 'Green'
        } else {
            Info "PERHATIAN: /$a menjawab HTTP $($h.StatusCode)." 'Yellow'
            $ok = 0
        }
    } catch {
        Info "PERHATIAN: /$a tidak terbaca: $_" 'Red'
        $ok = 0
    }
}

# Halaman harus memuat bagian-bagian baru (peran, akun, kelola pengguna).
try {
    $p = Invoke-WebRequest -Uri 'https://tamanmarina.my.id/' -UseBasicParsing -TimeoutSec 25
    foreach ($kata in @('Keuangan &amp; Iuran', 'data-atur-peran', 'Kelola Pengguna', 'pengguna.js', 'Akun Saya', 'Status Seluruh Sistem', 'pengaturan.js')) {
        if ($p.Content -match [regex]::Escape($kata)) { Info "OK: halaman memuat '$kata'." 'Green' }
        else { Info "PERHATIAN: halaman tidak memuat '$kata' - aset lama belum terganti." 'Yellow'; $ok = 0 }
    }
} catch {
    Info "PERHATIAN: gagal memeriksa isi halaman: $_" 'Red'
    $ok = 0
}

# Backend akun harus terjangkau lewat domain (bukti handle /api/* aktif).
try {
    $h = Invoke-WebRequest -Uri "https://tamanmarina.my.id/api/health`?terbit=$stampCek" -UseBasicParsing -TimeoutSec 25
    if ($h.StatusCode -eq 200 -and $h.Content -match '"ok":true') {
        Info 'OK: /api/health menjawab 200 lewat domain (tm-auth hidup).' 'Green'
    } else {
        Info "PERHATIAN: /api/health menjawab $($h.StatusCode): $($h.Content)" 'Yellow'
        $ok = 0
    }
} catch {
    Info "PERHATIAN: /api/health tidak terbaca: $_" 'Red'
    $ok = 0
}

# Halaman masuk ikut naik dan dilayani.
try {
    $m = Invoke-WebRequest -Uri "https://tamanmarina.my.id/masuk`?terbit=$stampCek" -UseBasicParsing -TimeoutSec 25
    if ($m.StatusCode -eq 200 -and $m.Content -match 'formMasuk') {
        Info 'OK: /masuk tersaji (halaman login).' 'Green'
    } else {
        Info "PERHATIAN: /masuk menjawab $($m.StatusCode)." 'Yellow'
        $ok = 0
    }
} catch {
    Info "PERHATIAN: /masuk tidak terbaca: $_" 'Red'
    $ok = 0
}

# Rute proxy sensor harus hidup: dasbor mengambil data lingkungan dari sini.
try {
    $s = Invoke-WebRequest -Uri 'https://tamanmarina.my.id/sensor/api/data' -UseBasicParsing -TimeoutSec 25
    if ($s.StatusCode -eq 200 -and $s.Content -match 'suhu') {
        Info 'OK: /sensor/api/data menyajikan data sensor (200).' 'Green'
    } else {
        Info "PERHATIAN: /sensor/api/data menjawab HTTP $($s.StatusCode)." 'Yellow'
        $ok = 0
    }
} catch {
    Info "PERHATIAN: /sensor/api/data tidak terbaca: $_" 'Red'
    $ok = 0
}

# Bukti tidak ada regresi: dua rute yang paling gampang tersenggol.
foreach ($u in @('https://clusternet.my.id/', 'https://udara.clusternet.my.id/')) {
    try {
        $c = Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 25
        if ($c.StatusCode -eq 200) { Info "OK: $u tetap 200 - tidak ada regresi." 'Green' }
        else { Info "PERHATIAN: $u menjawab HTTP $($c.StatusCode)." 'Yellow' }
    } catch {
        Info "PERHATIAN: $u tidak terbaca: $_" 'Red'
    }
}

Write-Host ''
if ($ok) {
    CatatTerbit 'verifikasi luar lolos: halaman 200 + penanda bagian + 9 aset + /api/health + /masuk + /sensor/api/data + clusternet/udara tetap 200'
    Info 'Selesai. Buka https://tamanmarina.my.id dengan Ctrl+Shift+R.' 'Cyan'
    exit 0
}
# Verifikasi gagal: tetap dicatat, supaya jelas penerbitan ini belum sah.
CatatTerbit 'GAGAL diverifikasi - perubahan sudah naik tetapi belum lolos pemeriksaan luar'
Info 'Berkas terkirim, tetapi verifikasi belum lolos - lihat pesan di atas.' 'Yellow'
exit 1
