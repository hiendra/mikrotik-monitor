@echo off
rem ============================================================
rem hentikan-layanan.bat - hentikan exporter + notifier Meshtastic
rem ============================================================
rem Sengaja TIDAK memakai "taskkill /IM python.exe": itu akan mematikan
rem SEMUA proses Python milik Anda, bukan hanya layanan ini.
rem
rem Penyaringan memakai NAMA SKRIP, bukan nama folder. Pelajaran dari percobaan
rem nyata: venv\Scripts\python.exe di mesin ini adalah peluncur (venv
rem redirector) yang MENJALANKAN interpreter dasar dari pyvenv.cfg sebagai
rem proses ANAK, dengan argumen yang sama. Command line anak itu berbunyi
rem "C:\Espressif\tools\python\python.exe -u exporter-meshtastic.py" - TIDAK
rem memuat kata "meshtastic-monitor", sehingga penyaringan lama (yang mencari
rem nama folder) hanya mematikan peluncurnya dan meninggalkan anaknya, yang
rem justru PEMEGANG port 9208. Akibatnya "hentikan" tampak berhasil padahal
rem layanan masih jalan.
rem
rem Pola di bawah cocok pada peluncur MAUPUN anaknya, dan hanya bila
rem exporter-meshtastic.py / notif-meshtastic.py muncul sebagai nama berkas
rem utuh - jadi uji-notif-meshtastic.py tidak ikut mati.
rem ============================================================
setlocal
set "POLA=(^|[\\/ ])(exporter-meshtastic\.py|notif-meshtastic\.py)( |$)"
echo Menghentikan proses Meshtastic (exporter + notifier) ...
powershell -NoProfile -Command "$pola = $env:POLA; Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match $pola } | ForEach-Object { Write-Host ('  mematikan PID ' + $_.ProcessId + ' :: ' + $_.CommandLine); Stop-Process -Id $_.ProcessId -Force }"
echo Selesai.
endlocal
