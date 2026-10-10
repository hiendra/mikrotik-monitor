# ============================================================
# buku-catatan.ps1 - penulis entri untuk BUKU-PERUBAHAN.md
# ============================================================
# Kebiasaan proyek ini: SETIAP penambahan/perubahan program meninggalkan
# dua jejak, bukan satu.
#
#   1. snapshot rollback di cadangan-tamanmarina/<nama>/
#      (dibuat cadangkan-tamanmarina.ps1; berisi CATATAN-CADANGAN.md)
#   2. satu entri di BUKU-PERUBAHAN.md  <-- berkas INI yang menuliskannya
#
# Berkas ini TIDAK dijalankan sendiri; ia di-dot-source oleh tiga skrip:
#   cadangkan-tamanmarina.ps1   -> entri "Cadangan"
#   terbitkan-tamanmarina.ps1   -> entri "Terbit"
#   kembalikan-tamanmarina.ps1  -> entri "Kembali"
#
# Isi entri sengaja datar dan bisa dibaca manusia: apa yang berubah, berkas
# apa, cara mengujinya, dan perintah persis untuk mengembalikannya. Tujuannya
# supaya siapa pun (termasuk diri sendiri enam bulan lagi) bisa memutar balik
# satu perubahan tanpa membedah riwayat git atau bertanya.
# ============================================================

$script:BerkasBuku = Join-Path $PSScriptRoot 'BUKU-PERUBAHAN.md'
$script:PenandaBuku = '<!-- BUKU:ENTRI -->'

function Tulis-KepalaBuku {
    $kepala = @(
        '# Buku Perubahan — tamanmarina.my.id',
        '',
        'Catatan setiap penambahan/perubahan program pada dasbor warga, beserta',
        'cara mengembalikannya (rollback). Entri terbaru ada di paling atas.',
        '',
        '> **Cara pakai:** sebelum mulai perubahan besar, jalankan',
        '> `pwsh -NoProfile -File ./zima-hosting/cadangkan-tamanmarina.ps1 -Nama <label> -Catatan "<apa yang akan diubah>"`.',
        '> Snapshot + entri di buku ini dibuat sekaligus. Setelah selesai dan lolos uji,',
        '> terbitkan dengan `-Catatan "<ringkasan>"` agar jejaknya lengkap.',
        '> Rollback: `kembalikan-tamanmarina.ps1 -Cadangan <nama snapshot> -Sandi <sandi>`.',
        '',
        '---',
        '',
        '## Riwayat',
        '',
        '<!-- BUKU:ENTRI -->',
        '',
        '_(kepala buku ditulis oleh buku-catatan.ps1)_',
        ''
    )
    Set-Content -LiteralPath $script:BerkasBuku -Value ($kepala -join "`n") -Encoding utf8 -NoNewline
}

# Tambah-BukuCatatan <Aksi> <Judul> [-Catatan] [-Berkas] [-Uji] [-Rollback]
#
# Aksi     : label singkat, mis. 'Cadangan', 'Terbit', 'Kembali'.
# Judul    : apa yang ditambah/diubah, satu baris.
# Catatan  : keterangan bebas (boleh kosong).
# Berkas   : daftar berkas yang ikut berubah (boleh kosong).
# Uji      : bukti kelolosan, mis. "uji.sh 57/0 ; validasi-hosting 83/0/0".
# Rollback : nama snapshot / perintah untuk memutar balik perubahan ini.
function Tambah-BukuCatatan {
    [CmdletBinding()]
    param(
        [string]$Aksi = 'Perubahan',
        [string]$Judul = '',
        [string]$Catatan = '',
        [string[]]$Berkas = @(),
        [string]$Uji = '',
        [string]$Rollback = ''
    )

    if (-not (Test-Path $script:BerkasBuku)) { Tulis-KepalaBuku }

    $waktu = (Get-Date).ToString('yyyy-MM-dd HH:mm')
    $b = @("### $waktu · $Aksi — $Judul")
    # Jangan menulis kalimat yang sama dua kali (umum terjadi saat -Catatan
    # dipakai sekaligus sebagai judul entri).
    if ($Catatan -and $Catatan.Trim() -ne $Judul.Trim()) { $b += ''; $b += $Catatan }
    $b += ''
    if ($Berkas.Count) { $b += ('- **Berkas**: `' + ($Berkas -join '`, `') + '`') }
    if ($Uji)          { $b += "- **Uji**: $Uji" }
    if ($Rollback)     { $b += "- **Rollback**: $Rollback" }
    $b += ''
    $blok = ($b -join "`n")

    $isi = Get-Content -LiteralPath $script:BerkasBuku -Raw
    $pos = $isi.IndexOf($script:PenandaBuku)
    if ($pos -ge 0) {
        $potong = $pos + $script:PenandaBuku.Length
        $baru = $isi.Substring(0, $potong) + "`n`n" + $blok + $isi.Substring($potong)
    } else {
        # Penanda hilang (berkas diedit tangan) - taruh entri di akhir saja.
        $baru = $isi.TrimEnd() + "`n`n" + $blok + "`n"
    }
    Set-Content -LiteralPath $script:BerkasBuku -Value $baru -Encoding utf8 -NoNewline
}
