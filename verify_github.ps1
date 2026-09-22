# ============================================================
# verify_github.ps1 - Buktikan apakah project ini sudah BENAR-BENAR
#                    terkirim ke GitHub, dan aman isinya.
# ============================================================
# Cara pakai (buka PowerShell lalu jalankan):
#
#   cd C:\temp\mikrotik_monitor
#   powershell -ExecutionPolicy Bypass -File .\verify_github.ps1
#
# Yang diperiksa:
#   1. remote origin ada dan TIDAK memuat token di dalam URL-nya
#   2. hash commit lokal == hash di server (bukti push benar-benar berhasil)
#   3. tidak ada commit lokal yang tertinggal (belum terkirim)
#   4. daftar file di server sama dengan daftar file lokal
#   5. secrets.h TIDAK ikut terkirim
#   6. nilai kredensial dari secrets.h tidak bocor ke file mana pun di server
#   7. tidak ada .zip / arsip backup / hasil build yang ikut terkirim
#
# Kode keluar: 0 = semua aman, 1 = ada masalah (bisa dipakai otomatis).
# ============================================================

# PENTING: jangan pakai 'Stop' di sini. Git menulis pesan error ke stderr,
# dan dengan 'Stop' hal itu menghentikan seluruh skrip sebelum sempat
# melaporkan hasilnya. Kegagalan git diperiksa lewat $LASTEXITCODE.
$ErrorActionPreference = 'Continue'

# Jangan pernah menggantung menunggu login: kalau belum ada token,
# skrip harus gagal cepat dan memberi pesan, bukan diam menunggu.
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE      = 'never'

$script:GitCode = 0
$script:GitErr  = ''
$script:GitOut  = ''
$script:ok     = 0
$issues        = New-Object System.Collections.Generic.List[string]

function Say  { param([string]$m, [string]$c = 'Gray') Write-Host $m -ForegroundColor $c }
function Head { param([string]$m) Say ''; Say ("=== $m ===") 'Cyan' }
function Pass { param([string]$m) Say ("  [ OK ]     " + $m) 'Green';  $script:ok++ }
function Fail { param([string]$m) Say ("  [ BAHAYA ] " + $m) 'Red';    $issues.Add($m) }
function Warn { param([string]$m) Say ("  [ PERIKSA ]" + $m) 'Yellow'; $issues.Add($m) }
# Skip tidak dihitung sebagai masalah: pemeriksaan yang tidak bisa
# dijalankan karena prasyaratnya belum ada bukan berarti ada kesalahan.
function Skip { param([string]$m) Say ("  [ LEWAT ]  " + $m) 'DarkGray' }

function GitRun {
  # Menjalankan git, mengembalikan stdout sebagai array baris.
  #
  # - stderr dipisah supaya tidak mengotori keluaran yang diurai, tapi
  #   tetap disimpan di $script:GitErr untuk ditampilkan.
  # - $TimeoutSec > 0 dipakai untuk perintah yang menyentuh jaringan
  #   (fetch / ls-remote). Tanpa batas waktu, git bisa menggantung
  #   selamanya menunggu jendela login yang tidak pernah diklik.
  param([string[]]$A, [int]$TimeoutSec = 0)

  $text = ''

  if ($TimeoutSec -gt 0) {
    # Memakai System.Diagnostics.Process langsung, BUKAN Start-Process.
    # Start-Process -PassThru tidak selalu mengisi .ExitCode (terbukti
    # kosong saat diuji), sehingga kegagalan git bisa salah dibaca.
    try {
      $psi = New-Object System.Diagnostics.ProcessStartInfo
      $psi.FileName               = 'git'
      $psi.Arguments              = (($A | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' ')
      $psi.UseShellExecute        = $false
      $psi.RedirectStandardOutput = $true
      $psi.RedirectStandardError  = $true
      $psi.CreateNoWindow         = $true

      $proc = New-Object System.Diagnostics.Process
      $proc.StartInfo = $psi
      $null = $proc.Start()
      $outTask = $proc.StandardOutput.ReadToEndAsync()
      $errTask = $proc.StandardError.ReadToEndAsync()

      if (-not $proc.WaitForExit($TimeoutSec * 1000)) {
        try { $proc.Kill() } catch { }
        $script:GitCode = 124
        $script:GitErr  = "dihentikan otomatis setelah $TimeoutSec detik (menunggu login atau jaringan)"
        Say ("  (git dibatalkan setelah $TimeoutSec detik supaya tidak menggantung)") 'DarkGray'
      } else {
        $proc.WaitForExit()
        $script:GitCode = $proc.ExitCode
        $text           = $outTask.Result
        $script:GitErr  = $errTask.Result
      }
    } catch {
      $script:GitCode = 1
      $script:GitErr  = "$_"
    }
  } else {
    $errFile = [System.IO.Path]::GetTempFileName()
    try {
      $lines = & git $A 2>$errFile
      $script:GitCode = $LASTEXITCODE
      $script:GitErr  = (Get-Content -LiteralPath $errFile -Raw -ErrorAction SilentlyContinue)
      if ($null -ne $lines) { $text = ($lines | Out-String) }
    } catch {
      $script:GitCode = 1
      $script:GitErr  = "$_"
    } finally {
      Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
    }
  }

  $script:GitOut = $text
  if ([string]::IsNullOrWhiteSpace($text)) { return @() }
  return @($text -split "`r?`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
}

function Lines {
  param([string[]]$A)
  $out = GitRun $A
  if ($script:GitCode -ne 0) { return @() }
  return @($out | ForEach-Object { "$_".Trim() } | Where-Object { $_ -ne '' })
}

Set-Location -LiteralPath $PSScriptRoot

Say ''
Say '=== VERIFIKASI GITHUB - MikroTik Monitor ===' 'Cyan'
Say ("Folder : " + $PSScriptRoot)
Say ("Waktu  : " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))

# ------------------------------------------------------------
Head '1. Repo Git lokal'
# ------------------------------------------------------------
# Diperiksa lewat kode keluar, bukan dari teks 'true', supaya tidak
# bergantung pada format keluaran git.
$null = GitRun @('rev-parse', '--git-dir')
if ($script:GitCode -ne 0) {
  Fail 'Folder ini bukan repo Git. Jalankan: git init -b main'
} else {
  Pass 'Folder ini repo Git.'
}

$branch = (Lines @('rev-parse', '--abbrev-ref', 'HEAD')) -join ''
if ($branch -eq 'main') { Pass 'Branch aktif: main' }
else { Warn ("Branch aktif '$branch' (seharusnya 'main')") }

$localHead = (Lines @('rev-parse', 'HEAD')) -join ''
Say ("  Commit lokal terakhir : " + $localHead.Substring(0, [Math]::Min(7, $localHead.Length)))

# ------------------------------------------------------------
Head '2. Remote origin'
# ------------------------------------------------------------
$url = (Lines @('remote', 'get-url', 'origin')) -join ''
if ($url -eq '') {
  Fail 'Remote origin belum diset. Jalankan: git remote add origin https://github.com/USER/REPO.git'
} else {
  Pass ("Remote origin: " + $url)
  # Token di dalam URL akan tertulis polos di .git\config, dan ikut
  # tersalin ke semua zip backup. Jadi ini harus dicegah.
  if ($url -match '://[^/@]+@') {
    Fail 'URL remote memuat kredensial/token di dalamnya. Ganti dengan bentuk https://github.com/USER/REPO.git lalu login lewat Git Credential Manager.'
  } else {
    Pass 'URL remote bersih (tidak memuat token).'
  }
}

# ------------------------------------------------------------
Head '3. Hubungi server'
# ------------------------------------------------------------
if ($url -eq '') {
  Warn 'Dilewati: remote belum ada.'
} else {
  # credential.interactive=never: git tidak boleh membuka jendela login
  # dari skrip ini. Kalau belum ada token, kita mau pesan jelas, bukan
  # jendela yang menggantung.
  $null = GitRun -A @('-c', 'credential.interactive=never', 'fetch', 'origin', '--quiet') -TimeoutSec 25
  if ($script:GitCode -ne 0) {
    $pesan = ("$($script:GitErr) $($script:GitOut)" -replace '\s+', ' ').Trim()
    if ($pesan) { Say ("  Pesan git: " + $pesan) 'DarkGray' }
    Fail 'Tidak bisa membaca repo di server. Penyebab umum: (a) repo belum dibuat di GitHub, (b) kamu belum login (jalankan git push sekali di PowerShell lalu klik "Sign in with your browser"), (c) nama repo/user di remote salah.'
  } else {
    Pass 'Berhasil menghubungi server GitHub.'
  }
}

$remoteHead = ''
$null = GitRun @('rev-parse', '--verify', '--quiet', 'origin/main')
if ($script:GitCode -eq 0) {
  $remoteHead = (Lines @('rev-parse', 'origin/main')) -join ''
} else {
  Fail 'Belum ada branch origin/main di sisi lokal - artinya push pertama belum pernah berhasil.'
}

# ------------------------------------------------------------
Head '4. Bandingkan hash lokal vs server'
# ------------------------------------------------------------
if ($remoteHead -eq '') {
  Skip 'Dilewati: belum ada origin/main, bagian ini butuh push pertama dulu.'
} else {
  Say ("  Lokal  (HEAD)  : " + $localHead)
  Say ("  Server (origin/main) : " + $remoteHead)
  if ($localHead -eq $remoteHead) {
    Pass 'IDENTIK - commit di GitHub sama persis dengan milikmu. Push sudah benar-benar masuk.'
  } else {
    Fail 'BERBEDA - isi server bukan versi terakhirmu. Ada commit yang belum terkirim.'
  }

  $ahead  = ((Lines @('rev-list', '--count', 'origin/main..HEAD')) -join '')
  $behind = ((Lines @('rev-list', '--count', 'HEAD..origin/main')) -join '')
  Say ("  Commit lokal belum terkirim : " + $ahead)
  Say ("  Commit server belum ada di lokal : " + $behind)
  if ($ahead -eq '0' -and $behind -eq '0') { Pass 'Tidak ada selisih commit.' }
  else { Fail 'Ada selisih commit antara lokal dan server.' }

  $total = ((Lines @('rev-list', '--count', 'origin/main')) -join '')
  Say ("  Total commit di server : " + $total)
}

# ------------------------------------------------------------
Head '5. Bandingkan daftar file'
# ------------------------------------------------------------
if ($remoteHead -eq '') {
  Skip 'Dilewati: belum ada origin/main, bagian ini butuh push pertama dulu.'
} else {
  $localFiles  = @(Lines @('ls-tree', '-r', 'HEAD', '--name-only') | Where-Object { $_ -ne '' })
  $remoteFiles = @(Lines @('ls-tree', '-r', 'origin/main', '--name-only') | Where-Object { $_ -ne '' })

  $onlyLocal  = @($localFiles  | Where-Object { $remoteFiles -notcontains $_ })
  $onlyRemote = @($remoteFiles | Where-Object { $localFiles  -notcontains $_ })

  Say ("  File lokal  : " + $localFiles.Count)
  Say ("  File server : " + $remoteFiles.Count)

  if ($onlyLocal.Count -eq 0 -and $onlyRemote.Count -eq 0) {
    Pass 'Daftar file identik di kedua sisi.'
  } else {
    if ($onlyLocal.Count -gt 0) {
      Warn ('Ada di lokal, belum ada di server: ' + ($onlyLocal -join ', '))
    }
    if ($onlyRemote.Count -gt 0) {
      Fail ('Ada di server, TIDAK ada di lokal (mungkin tidak seharusnya terkirim): ' + ($onlyRemote -join ', '))
    }
  }

  # ----------------------------------------------------------
  Head '6. secrets.h tidak boleh terkirim'
  # ----------------------------------------------------------
  $badNames = @($remoteFiles | Where-Object { $_ -match '(?i)secret|passw|credential' })

  if ($badNames.Count -eq 0) {
    Pass 'Tidak ada file bernama secret/password/credential di server.'
  } else {
    $allowed = @('secrets.h.example')
    $bad = @($badNames | Where-Object { $allowed -notcontains $_ })
    if ($bad.Count -eq 0) {
      Pass ('Di server hanya ada template aman: ' + ($badNames -join ', '))
    } else {
      Fail ('KREDENSIAL TERKIRIM KE GITHUB: ' + ($bad -join ', ') + ' -> segera hapus dari riwayat commit!')
    }
  }

  # Apakah nama file yang sama pada commit pertama (riwayat) juga bersih?
  $historicSecret = @(Lines @('log', '--all', '--pretty=format:', '--name-only', '--', 'secrets.h') |
                      Where-Object { $_ -match '(?i)^secrets\.h$' })
  if ($historicSecret.Count -eq 0) {
    Pass 'secrets.h tidak pernah muncul di riwayat commit mana pun.'
  } else {
    Fail ("secrets.h PERNAH ikut ter-commit " + $historicSecret.Count + " kali. File itu masih bisa diambil dari riwayat!")
  }

  # ----------------------------------------------------------
  Head '7. Isi kredensial bocor ke file lain?'
  # ----------------------------------------------------------
  # Nilai asli dibaca dari secrets.h lokal, lalu dicari di seluruh file
  # di sisi server. Nilainya TIDAK pernah ditampilkan di layar.
  $secPath = Join-Path $PSScriptRoot 'secrets.h'
  if (-not (Test-Path -LiteralPath $secPath)) {
    Skip 'secrets.h lokal tidak ditemukan, pemeriksaan isi kredensial dilewati.'
  } else {
    # Nilai diambil bersama NAMA variabelnya. Yang perlu dicari hanya nilai
    # dari variabel rahasia: alamat IP atau nama WiFi memang wajar muncul di
    # dokumentasi dan bukan rahasia. Menguji semua string menghasilkan
    # peringatan palsu yang membuat laporan ini tidak bisa dipercaya.
    $secText = Get-Content -LiteralPath $secPath -Raw
    $pairs = @()
    foreach ($m in [regex]::Matches($secText, '(?m)#define\s+([A-Za-z_]\w*)\s+"([^"]{3,})"')) {
      $pairs += , @($m.Groups[1].Value, $m.Groups[2].Value)
    }
    foreach ($m in [regex]::Matches($secText, '(?m)([A-Za-z_]\w*)\s*=\s*"([^"]{3,})"')) {
      $pairs += , @($m.Groups[1].Value, $m.Groups[2].Value)
    }

    $placeholder = '(?i)^(changeme|change_me|example|your_|isi_|placeholder|todo|none|xxx+|<.*>)$'
    $high = @($pairs | Where-Object { $_[0] -match '(?i)(pass|pwd|secret|key|token|psk|credential)' -and $_[1] -notmatch $placeholder } | Sort-Object { $_[1] } -Unique)
    $med  = @($pairs | Where-Object { $_[0] -match '(?i)(user|ssid|login)'                        -and $_[1] -notmatch $placeholder } | Sort-Object { $_[1] } -Unique)

    Say ("  " + $high.Count + " nilai password/secret dan " + $med.Count + " nilai user/SSID diuji.")

    $leak = New-Object System.Collections.Generic.List[string]
    foreach ($p in $high) {
      foreach ($h in (Lines @('grep', '-l', '--fixed-strings', '-e', $p[1], 'origin/main', '--', '.'))) {
        if (-not $leak.Contains($h)) { $leak.Add($h) }
      }
    }

    if ($leak.Count -eq 0) {
      Pass 'Tidak ada file di server yang memuat nilai password/secret dari secrets.h.'
    } else {
      Fail ('PASSWORD/SECRET ASLI ADA DI FILE SERVER: ' + (@($leak) -join ', ') + ' -> jangan push sebelum ini dibersihkan!')
    }

    # user/SSID bukan rahasia, jadi hanya dicatat dan TIDAK dihitung sebagai masalah.
    if ($med.Count -gt 0) {
      $info = New-Object System.Collections.Generic.List[string]
      foreach ($p in $med) {
        foreach ($h in (Lines @('grep', '-l', '--fixed-strings', '-e', $p[1], 'origin/main', '--', '.'))) {
          if (-not $info.Contains($h)) { $info.Add($h) }
        }
      }
      if ($info.Count -gt 0) {
        Say ('  [ CATATAN ] Nama user/SSID juga muncul di: ' + (@($info) -join ', ')) 'DarkGray'
      }
    }
  }

  # Pola umum: baris yang mengisi password dengan string literal
  $literalPw = Lines @('grep', '-l', '-E', 'password[^\n]*=[^\n]*"[^"]+"', 'origin/main', '--', '.')
  if ($literalPw.Count -eq 0) {
    Pass 'Tidak ada password yang ditulis langsung (hardcoded) di file server.'
  } else {
    Warn ('Perlu dicek, password ditulis langsung di: ' + (@($literalPw) -join ', '))
  }

  # ----------------------------------------------------------
  Head '8. Artefak yang tidak seharusnya terkirim'
  # ----------------------------------------------------------
  $artifacts = @($remoteFiles | Where-Object { $_ -match '(?i)\.(zip|7z|rar|bin|elf|hex|exe|log)$|(^|/)(build|backups|recovered_out)/' })
  if ($artifacts.Count -eq 0) {
    Pass 'Tidak ada arsip/binary/hasil build di server.'
  } else {
    Warn ('Ada file yang sebaiknya tidak di repo: ' + ($artifacts -join ', '))
  }

  $gitignoreIn = @($remoteFiles | Where-Object { $_ -eq '.gitignore' })
  if ($gitignoreIn.Count -eq 1) { Pass '.gitignore ikut terkirim (melindungi secrets.h di masa depan).' }
  else { Warn '.gitignore TIDAK ada di server - kredensial bisa lolos pada commit berikutnya.' }
}

# ------------------------------------------------------------
Head 'RINGKASAN'
# ------------------------------------------------------------
if ($issues.Count -eq 0) {
  Say ("  $script:ok pemeriksaan lulus, 0 masalah.") 'Green'
  Say '  STATUS: AMAN - project sudah terkirim ke GitHub dan tidak ada kredensial yang bocor.' 'Green'
  Say ''
  exit 0
} else {
  Say ("  $script:ok pemeriksaan lulus, " + $issues.Count + " masalah ditemukan:") 'Yellow'
  foreach ($i in $issues) { Say ("   - " + $i) 'Yellow' }
  Say ''
  Say '  STATUS: BELUM AMAN / BELUM SELESAI - lihat daftar di atas.' 'Red'
  Say ''
  exit 1
}
