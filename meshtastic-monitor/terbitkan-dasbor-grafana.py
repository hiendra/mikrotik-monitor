#!/usr/bin/env python3
# ============================================================
# terbitkan-dasbor-grafana.py - terbitkan dasbor Mesh ID ke Grafana
# ============================================================
# Membaca dashboard-grafana.json (yang sengaja tetap PORTABEL: datasource-nya
# ditulis sebagai ${DS_PROMETHEUS} supaya bisa diimpor lewat antarmuka Grafana
# di pemasangan mana pun), lalu menerbitkannya lewat API Grafana dengan
# datasource itu SUDAH DIISI uid yang benar.
#
# Mengapa lewat API, bukan impor manual:
#
#   * impor lewat antarmuka selalu meminta pemilihan datasource, dan salah pilih
#     menghasilkan dasbor yang SEMUA panelnya kosong tanpa satu pun pesan galat -
#     persis kegagalan senyap yang paling lama tidak disadari;
#   * menerbitkan ulang setelah dasbor diperbaiki jadi satu perintah, dan
#     idempoten: uid dasbor dipertahankan sehingga tautan/penanda buku yang ada
#     tetap hidup.
#
# Aman: hanya berbicara dengan API Grafana (baca daftar datasource, tulis SATU
# dasbor). Tidak menyentuh datasource, pengguna, atau pengaturan lain.
#
# Pakai
# -----
#   python terbitkan-dasbor-grafana.py                 # terbitkan
#   python terbitkan-dasbor-grafana.py --kering        # hanya melaporkan
#   python terbitkan-dasbor-grafana.py --periksa       # jalankan kueri tiap panel
#   python terbitkan-dasbor-grafana.py --uid-ds prom-mikrotik --kering
#
# --periksa adalah yang membedakan "dasbor sudah terbit" dari "dasbor benar-
# benar menampilkan angka". Ia menjalankan SETIAP kueri panel lewat datasource
# Grafana (bukan langsung ke Prometheus) supaya jalur yang benar-benar dipakai
# dasbor itulah yang diuji, lalu melaporkan panel mana yang masih kosong.
#
# Lingkungan
# ----------
#   GRAFANA_URL   bawaan http://127.0.0.1:3003
#   GRAFANA_USER  bawaan admin
#   GRAFANA_PASS  bawaan admin123  (bawaan alat lain di repo ini, lihat
#                                  zima-hosting/tautan-balik-grafana.mjs)
#   GRAFANA_DS    nama datasource yang dicari, bawaan Prometheus
#
# Kode keluar: 0 bila berhasil (atau laporan --kering), 1 bila gagal.
# ============================================================

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

AKAR = os.path.dirname(os.path.abspath(__file__))
BERKAS_DASBOR = os.path.join(AKAR, "dashboard-grafana.json")
VARIABEL_DS = "${DS_PROMETHEUS}"


def rapi_pesan(galat):
    """Uraikan galat HTTP Grafana menjadi satu baris yang berguna."""
    if isinstance(galat, urllib.error.HTTPError):
        try:
            isi = galat.read().decode("utf-8", "replace")
        except Exception:
            isi = ""
        return "HTTP %s: %s" % (galat.code, isi[:300])
    return str(galat)


class Grafana:
    def __init__(self, base, user, sandi):
        self.base = base.rstrip("/")
        self.kepala = {
            "Authorization": "Basic " + base64.b64encode(
                ("%s:%s" % (user, sandi)).encode("utf-8")).decode("ascii"),
            "Content-Type": "application/json",
            "User-Agent": "terbitkan-dasbor-grafana/1.0",
        }

    def minta(self, jalur, metode="GET", muatan=None, timeout=30):
        data = json.dumps(muatan).encode("utf-8") if muatan is not None else None
        req = urllib.request.Request(self.base + jalur, data=data, method=metode)
        for k, v in self.kepala.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                badan = r.read().decode("utf-8", "replace")
                return (json.loads(badan) if badan.strip() else None), None
        except urllib.error.HTTPError as e:
            return None, rapi_pesan(e)
        except (urllib.error.URLError, OSError) as e:
            return None, rapi_pesan(e)


def ganti(isi, lama, baru):
    """Ganti SEMUA nilai string persis `lama` di dalam struktur JSON.

    Diganti lewat penelusuran struktur, bukan penyuntingan teks berkas, supaya
    tidak ada kemungkinan merusak JSON (mis. koma/kurung) - dan supaya jumlah
    penggantiannya bisa dilaporkan sebagai bukti.
    """
    jumlah = 0

    def telusuri(x):
        nonlocal jumlah
        if isinstance(x, str):
            if x == lama:
                jumlah += 1
                return baru
            return x
        if isinstance(x, list):
            return [telusuri(v) for v in x]
        if isinstance(x, dict):
            return {k: telusuri(v) for k, v in x.items()}
        return x

    return telusuri(isi), jumlah


def main(argv):
    p = argparse.ArgumentParser(add_help=True, description="Terbitkan dasbor Mesh ID ke Grafana.")
    p.add_argument("--url", default=os.environ.get("GRAFANA_URL", "http://127.0.0.1:3003"))
    p.add_argument("--user", default=os.environ.get("GRAFANA_USER", "admin"))
    p.add_argument("--sandi", default=os.environ.get("GRAFANA_PASS", "admin123"))
    p.add_argument("--ds", default=os.environ.get("GRAFANA_DS", "Prometheus"),
                   help="nama datasource yang dicari (bawaan Prometheus)")
    p.add_argument("--uid-ds", default=None,
                   help="pakai uid datasource ini langsung, tanpa bertanya ke Grafana")
    p.add_argument("--berkas", default=BERKAS_DASBOR, help="berkas dasbor sumber")
    p.add_argument("--kering", action="store_true", help="jangan menulis apa pun")
    p.add_argument("--periksa", action="store_true",
                   help="jalankan kueri tiap panel lewat datasource dan laporkan yang kosong")
    o = p.parse_args(argv)

    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    if not os.path.exists(o.berkas):
        print("ERROR: berkas dasbor tidak ada: %s" % o.berkas, file=sys.stderr)
        return 1
    with open(o.berkas, encoding="utf-8") as f:
        dasbor = json.load(f)

    uid_dasbor = dasbor.get("uid") or "(tanpa uid)"
    print("Dasbor   : %s (uid %s, %d panel)"
          % (dasbor.get("title"), uid_dasbor, len(dasbor.get("panels") or [])))
    print("Grafana  : %s" % o.url)

    # --- 1. tentukan datasource ---
    g = Grafana(o.url, o.user, o.sandi)
    if o.uid_ds:
        uid_ds = o.uid_ds
        print("Datasource: %s (diberikan lewat --uid-ds, tanpa bertanya ke Grafana)" % uid_ds)
    else:
        daftar, galat = g.minta("/api/datasources")
        if galat:
            print("GAGAL membaca daftar datasource: %s" % galat, file=sys.stderr)
            print("       periksa GRAFANA_URL / GRAFANA_USER / GRAFANA_PASS", file=sys.stderr)
            return 1
        cocok = [d for d in (daftar or []) if d.get("name") == o.ds]
        if not cocok:
            nama = ", ".join(sorted(d.get("name", "?") for d in (daftar or [])))
            print("GAGAL: datasource bernama %r tidak ada. Yang ada: %s" % (o.ds, nama),
                  file=sys.stderr)
            print("       sebut uid-nya langsung: --uid-ds <uid>", file=sys.stderr)
            return 1
        ds = cocok[0]
        uid_ds = ds.get("uid")
        print("Datasource: %s (uid %s, tipe %s, url %s)"
              % (ds.get("name"), uid_ds, ds.get("type"), ds.get("url")))
        if ds.get("type") != "prometheus":
            print("GAGAL: datasource %r bertipe %r, bukan prometheus."
                  % (o.ds, ds.get("type")), file=sys.stderr)
            return 1

    # --- 2. isi datasource di seluruh panel ---
    dasbor, jumlah = ganti(dasbor, VARIABEL_DS, uid_ds)
    print("Penggantian %s -> %s : %d tempat" % (VARIABEL_DS, uid_ds, jumlah))
    if jumlah == 0:
        print("PERINGATAN: tidak ada %s yang ditemukan. Dasbor mungkin sudah berisi uid"
              % VARIABEL_DS)
    # Variabel templating-nya ikut diisi supaya pemilih datasource tidak
    # menampilkan pilihan kosong saat dasbor dibuka.
    for v in ((dasbor.get("templating") or {}).get("list") or []):
        if v.get("name") == "DS_PROMETHEUS":
            v["current"] = {"selected": True, "text": o.ds, "value": uid_ds}
            v["hide"] = 2   # tetap ada agar rujukan ${DS_PROMETHEUS} sah, tapi tidak mencolok

    if o.periksa:
        print()
        kosong = periksa_panel(g, uid_ds, dasbor)
        if o.kering:
            return 1 if kosong else 0
        # Teruskan menerbitkan walau ada panel kosong: dasbor yang sebagian
        # kosong tetap lebih berguna daripada tidak ada. Kode keluarnya yang
        # memberi tahu bahwa masih ada yang perlu ditengok.
        hasil_kosong = kosong
    else:
        hasil_kosong = 0

    if o.kering:
        print("\n--kering: tidak ada yang ditulis ke Grafana.")
        print("Hasilnya akan diterbitkan sebagai uid %s." % uid_dasbor)
        # Tetap laporkan dasbor yang sudah ada di Grafana (bila ada), supaya
        # perbedaan versi kelihatan sebelum menimpa.
        ada, galat = g.minta("/api/dashboards/uid/%s" % uid_dasbor)
        if galat:
            print("Di Grafana: belum ada atau tidak terbaca (%s)" % galat)
        else:
            print("Di Grafana: sudah ada, versi %s" % (ada.get("dashboard") or {}).get("version"))
        return 0

    # --- 3. terbitkan ---
    # Grafana menolak (HTTP 412) bila nomor versi yang dikirim lebih tua daripada
    # yang tersimpan. Berkas dasbor di repo menyimpan `version` dari saat ia
    # dibuat, jadi versi yang DIPAKAI harus diambil dari Grafana lebih dulu -
    # kalau tidak, penerbitan kedua kali bisa gagal hanya karena berkas lokalnya
    # "tertinggal", tanpa hubungan apa pun dengan isi dasbornya.
    ada, galat_ada = g.minta("/api/dashboards/uid/%s" % uid_dasbor)
    if not galat_ada:
        tersimpan = (ada or {}).get("dashboard") or {}
        dasbor["version"] = tersimpan.get("version") or 0
        if tersimpan.get("id"):
            dasbor["id"] = tersimpan["id"]
        print("Versi tersimpan di Grafana: %s -> dikirim sebagai %s"
              % (tersimpan.get("version"), dasbor["version"]))
    muatan = {
        "dashboard": dasbor,
        "overwrite": True,
        "message": "terbitkan-dasbor-grafana.py: dasbor Mesh ID",
    }
    hasil, galat = g.minta("/api/dashboards/db", metode="POST", muatan=muatan)
    if galat:
        print("GAGAL menerbitkan: %s" % galat, file=sys.stderr)
        return 1
    print("TERBIT: status=%s uid=%s versi=%s url=%s"
          % ((hasil or {}).get("status"), (hasil or {}).get("uid"),
             (hasil or {}).get("version"), (hasil or {}).get("url")))

    # --- 4. buktikan hasilnya benar-benar tersimpan (bukan sekadar 200) ---
    verifikasi, galat = g.minta("/api/dashboards/uid/%s" % ((hasil or {}).get("uid") or uid_dasbor))
    if galat:
        print("PERINGATAN: terbit sukses tetapi pembacaan ulang gagal: %s" % galat,
              file=sys.stderr)
        return 1
    d_ulang = (verifikasi or {}).get("dashboard") or {}
    panel = d_ulang.get("panels") or []
    sisa = json.dumps(panel).count(VARIABEL_DS)
    print("Terbaca ulang: %d panel, versi %s, sisa %s = %d"
          % (len(panel), d_ulang.get("version"), VARIABEL_DS, sisa))
    if sisa:
        print("GAGAL: masih ada panel yang memakai %s - panel itu akan kosong." % VARIABEL_DS,
              file=sys.stderr)
        return 1
    print("Bukti akhir: %s" % ("https://grafana.clusternet.my.id/d/%s" % d_ulang.get("uid")))
    if o.periksa and hasil_kosong:
        print("\nPERHATIAN: %d panel belum mengembalikan data (lihat daftar di atas)" % hasil_kosong)
        return 1
    return 0


def periksa_panel(g, uid_ds, dasbor):
    """Jalankan kueri tiap panel lewat datasource; laporkan yang kosong.

    Lewat datasource Grafana, BUKAN langsung ke Prometheus: kalau uid datasource
    salah, kueri langsung ke Prometheus tetap berhasil sementara dasbornya tetap
    kosong - persis kasus yang ingin dicegah di sini.
    """
    print("Pemeriksaan panel: menjalankan %d kueri lewat datasource %s" % (
        sum(len(p.get("targets") or []) for p in (dasbor.get("panels") or [])), uid_ds))
    kosong = []
    for p in (dasbor.get("panels") or []):
        if p.get("type") in ("row", "text"):
            continue
        total = 0
        ada_galat = None
        punya_kueri = False
        for t in (p.get("targets") or []):
            ekspresi = t.get("expr")
            if not ekspresi:
                continue
            punya_kueri = True
            jalur = "/api/datasources/proxy/uid/%s/api/v1/query?query=%s" % (
                uid_ds, urllib.parse.quote(ekspresi))
            hasil, galat = g.minta(jalur)
            if galat:
                ada_galat = galat
                continue
            data = ((hasil or {}).get("data") or {})
            total = max(total, len(data.get("result") or []))
        if not punya_kueri:
            continue
        judul = (p.get("title") or "?")[:42]
        if ada_galat:
            print("  [GALAT]  %-42s %s" % (judul, ada_galat))
            kosong.append(p.get("title") or "?")
        elif total:
            print("  [OK]     %-42s %d seri" % (judul, total))
        else:
            print("  [KOSONG] %-42s tidak ada data" % judul)
            kosong.append(p.get("title") or "?")
    print("Panel kosong/bermasalah: %d" % len(kosong))
    return len(kosong)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
