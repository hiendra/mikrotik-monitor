#!/usr/bin/env python3
# ============================================================
# uji-kuma-ntfy.py - memeriksa kanal notifikasi Uptime Kuma -> ntfy
# ============================================================
# Menjawab satu pertanyaan: "kalau monitor di Uptime Kuma mati, apakah
# pesannya benar-benar sampai ke ntfy?" Caranya TIDAK menebak dari berkas
# konfigurasi, tetapi melihat kenyataan di server:
#
#   1. membaca halaman status Kuma lewat API publiknya (tanpa kunci) dan
#      menampilkan status terakhir tiap monitor,
#   2. membaca topik ntfy dan mencari pesan yang benar-benar berasal dari
#      Kuma (judulnya berakhiran "[Uptime-Kuma]"),
#   3. bila belum ada, memberi tahu bahwa tombol Test di panel Kuma perlu
#      ditekan dulu - bukan berpura-pura kanalnya sehat.
#
# Kanal ini SENGAJA terpisah dari kanal router (mikrotik-ntfy/), supaya
# gangguan router dan gangguan layanan tidak tercampur. Untuk router,
# pakai `uji-ntfy.py` di akar repo.
#
# Pakai
# -----
#   python zima-hosting/uji-kuma-ntfy.py
#   python zima-hosting/uji-kuma-ntfy.py --jam 24
#   python zima-hosting/uji-kuma-ntfy.py --kirim      # kirim probe sendiri
#
# Opsi
# ----
#   --kuma URL    dasar Kuma            (bawaan https://kuma.clusternet.my.id)
#   --hal SLUG    slug halaman status   (bawaan mesh)
#   --server URL  server ntfy           (bawaan https://ntfy.adminforge.de)
#   --topik NAMA  nama topik            (bawaan kuma-7m3xq9dt2v)
#   --jam N       jendela pencarian     (bawaan 12 jam)
#   --kirim       kirim satu pesan probe dari skrip ini, lalu baca kembali
#                 (membuktikan sisi ntfy hidup; BUKAN bukti Kuma mengirim)
#
# Lingkungan
# ----------
#   UJI_TLS_INSECURE  "1" mematikan verifikasi TLS (hanya untuk diagnosis)
#
# Hasil: LULUS bila topik terbaca DAN ada pesan asli dari Kuma; selain itu
# GAGAL (kode keluar 1).
# ============================================================

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BAWAAN_KUMA = "https://kuma.clusternet.my.id"
BAWAAN_HAL = "mesh"
BAWAAN_SERVER = "https://ntfy.adminforge.de"
BAWAAN_TOPIK = "kuma-7m3xq9dt2v"
PENANDA_KUMA = "[Uptime-Kuma]"

# Status heartbeat Kuma. Ditulis teks, bukan emoji: konsol Windows (cp1252)
# tidak bisa mencetak emoji dan akan berhenti dengan UnicodeEncodeError.
NAMA_STATUS = {0: "DOWN", 1: "UP", 2: "PENDING", 3: "MAINT"}

LOLOS = 0
GAGAL = 0


def lolos(pesan):
    global LOLOS
    LOLOS += 1
    print("  [LULUS]      %s" % pesan)


def gagal(pesan):
    global GAGAL
    GAGAL += 1
    print("  [GAGAL]      %s" % pesan)


def info(pesan):
    print("               -> %s" % pesan)


def pembuka_tls():
    if os.environ.get("UJI_TLS_INSECURE") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def minta(url, ctx, metode="GET", data=None, header=None, timeout=20):
    """Kembalikan (teks, galat). Salah satu selalu None."""
    req = urllib.request.Request(url, data=data, method=metode)
    for k, v in (header or {}).items():
        req.add_header(k, v)
    req.add_header("User-Agent", "uji-kuma-ntfy/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read().decode("utf-8", "replace"), None
    except urllib.error.HTTPError as e:
        return None, "HTTP %d dari %s" % (e.code, url)
    except urllib.error.URLError as e:
        return None, "tidak bisa menghubungi %s (%s)" % (url, e)


def json_dari(url, ctx):
    teks, galat = minta(url, ctx)
    if galat:
        return None, galat
    try:
        return json.loads(teks), None
    except json.JSONDecodeError:
        return None, "balasan bukan JSON (mungkin tertahan halaman login/Cloudflare)"


def daftar_monitor(kuma, hal, ctx):
    """Kembalikan [(id, nama)] dari halaman status publik."""
    konf, galat = json_dari("%s/api/status-page/%s" % (kuma.rstrip("/"), urllib.parse.quote(hal)), ctx)
    if galat:
        return None, galat
    hasil = []
    for grup in konf.get("publicGroupList") or []:
        for mon in grup.get("monitorList") or []:
            hasil.append((mon.get("id"), mon.get("name") or "(tanpa nama)"))
    return hasil, None


def status_terakhir(kuma, hal, ctx):
    """Kembalikan {id_monitor: (status, pesan, waktu)} untuk heartbeat terakhir."""
    hb, galat = json_dari(
        "%s/api/status-page/heartbeat/%s" % (kuma.rstrip("/"), urllib.parse.quote(hal)), ctx
    )
    if galat:
        return None, galat
    keluaran = {}
    for kunci, deret in (hb.get("heartbeatList") or {}).items():
        if not deret:
            continue
        akhir = deret[-1]
        try:
            kunci_int = int(kunci)
        except (TypeError, ValueError):
            kunci_int = kunci
        keluaran[kunci_int] = (akhir.get("status"), akhir.get("msg") or "", akhir.get("time"))
    return keluaran, None


def pesan_topik(server, topik, jam, ctx):
    """Baca pesan topik selama `jam` terakhir. Kembalikan (daftar, galat)."""
    url = "%s/%s/json?poll=1&since=%dh" % (
        server.rstrip("/"), urllib.parse.quote(topik), jam
    )
    teks, galat = minta(url, ctx)
    if galat:
        return None, galat
    daftar = []
    for baris in teks.splitlines():
        baris = baris.strip()
        if not baris:
            continue
        try:
            daftar.append(json.loads(baris))
        except json.JSONDecodeError:
            continue
    return daftar, None


def kirim_probe(server, topik, ctx):
    """Kirim satu pesan uji ke topik (membuktikan sisi ntfy bisa ditulisi)."""
    url = "%s/%s" % (server.rstrip("/"), urllib.parse.quote(topik))
    penanda = "PROBE-%d" % (int(time.time()) % 100000000)
    isi = ("Probe dari uji-kuma-ntfy.py (%s). Ini BUKAN pesan dari Kuma - "
           "hanya membuktikan topik bisa ditulisi." % penanda).encode("utf-8")
    teks, galat = minta(
        url,
        ctx,
        metode="POST",
        data=isi,
        header={"Title": "PROBE TOPIK KUMA", "Tags": "test_tube", "Priority": "3"},
    )
    return penanda, galat or teks


def main(argv):
    args = list(argv)
    kuma = BAWAAN_KUMA
    hal = BAWAAN_HAL
    server = BAWAAN_SERVER
    topik = BAWAAN_TOPIK
    jam = 12
    kirim = False

    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--kuma", "--hal", "--server", "--topik", "--jam") and i + 1 < len(args):
            nilai = args[i + 1]
            if a == "--kuma":
                kuma = nilai
            elif a == "--hal":
                hal = nilai
            elif a == "--server":
                server = nilai
            elif a == "--topik":
                topik = nilai
            else:
                jam = int(nilai)
            i += 2
            continue
        if a == "--kirim":
            kirim = True
            i += 1
            continue
        if a in ("-h", "--help"):
            print(__doc__ or "")
            return 0
        print("Opsi tidak dikenal: %s" % a, file=sys.stderr)
        return 2

    ctx = pembuka_tls()

    print("=" * 60)
    print(" UJI KANAL NOTIFIKASI: Uptime Kuma -> ntfy")
    print("=" * 60)
    print("Kuma   : %s (halaman %s)" % (kuma, hal))
    print("ntfy   : %s" % server)
    print("Topik  : %s" % topik)
    print("Jendela: %d jam terakhir" % jam)
    print()

    # --- 1. Halaman status Kuma terbaca? ---
    monitor, galat = daftar_monitor(kuma, hal, ctx)
    if galat:
        gagal("halaman status Kuma tidak bisa dibaca")
        info(galat)
        monitor = []
    else:
        lolos("halaman status Kuma terbaca (%d monitor di halaman '%s')" % (len(monitor), hal))

    if monitor:
        status, galat_st = status_terakhir(kuma, hal, ctx)
        if galat_st:
            info("heartbeat tidak terbaca: %s" % galat_st)
        else:
            urut = {idm: nama for idm, nama in monitor}
            turun = 0
            for idm, nama in monitor:
                st = status.get(idm)
                if not st:
                    continue
                label = NAMA_STATUS.get(st[0], "?%s" % st[0])
                if st[0] == 0:
                    turun += 1
                info("%-8s %s" % (label, nama))
            if turun:
                info("CATATAN: %d monitor sedang DOWN saat pemeriksaan ini." % turun)
    print()

    # --- 2. Topik ntfy terbaca? ---
    daftar, galat = pesan_topik(server, topik, jam, ctx)
    if galat:
        gagal("topik ntfy tidak bisa dibaca")
        info(galat)
        return ringkasan()
    lolos("topik ntfy terbaca (%d pesan dalam %d jam terakhir)" % (len(daftar), jam))

    # --- 3. Ada pesan yang benar-benar dari Kuma? ---
    dari_kuma = [p for p in daftar if PENANDA_KUMA in (p.get("title") or "")]
    if dari_kuma:
        akhir = dari_kuma[-1]
        lolos("ada pesan ASLI dari Kuma di topik ini")
        info("judul  : %s" % (akhir.get("title") or "(tanpa judul)"))
        info("waktu  : %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(akhir.get("time", 0))))
        info("prioritas: %s   tag: %s" % (akhir.get("priority"), ", ".join(akhir.get("tags") or [])))
    else:
        gagal("belum ada pesan asli dari Kuma dalam %d jam terakhir" % jam)
        info("buka https://kuma.clusternet.my.id/settings/notifications")
        info("-> Edit 'ntfy Kuma (adminforge)' -> tombol Test -> lalu jalankan ulang skrip ini")
        info("kanal bisa saja sudah benar tetapi belum pernah dipakai sejak lama")

    # --- 4. Opsional: probe tulis ke topik ---
    if kirim:
        print()
        penanda, balasan = kirim_probe(server, topik, ctx)
        if balasan and balasan.startswith("{"):
            lolos("probe %s berhasil ditulis ke topik (sisi ntfy hidup)" % penanda)
        else:
            gagal("probe gagal ditulis ke topik")
            info(str(balasan))

    return ringkasan()


def ringkasan():
    print()
    print("=" * 60)
    print(" Lolos: %d | GAGAL: %d" % (LOLOS, GAGAL))
    if GAGAL:
        print(" HASIL: kanal Kuma -> ntfy BELUM terbukti hidup.")
    else:
        print(" HASIL: kanal Kuma -> ntfy terbukti hidup ujung-ke-ujung.")
    print("=" * 60)
    return 0 if GAGAL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
