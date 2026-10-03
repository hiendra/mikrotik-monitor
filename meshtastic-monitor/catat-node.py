#!/usr/bin/env python3
# ============================================================
# catat-node.py - rekam data node RF Meshtastic untuk mengkalibrasi ambang alert
# ============================================================
# MASALAH yang dipecahkan: node berperan ROUTER hanya memancarkan telemetry
# sendiri sekitar tiap 12 jam. Bila ambang "offline" (MESH_OFFLINE_SECS) di
# exporter lebih pendek dari irama alami node itu, Anda akan mendapat alert
# offline PALSU setiap hari.
#
# ALAT ini menyampel data dari exporter (atau langsung dari node) selama
# beberapa jam, mencatat setiap perubahan `last_heard`, lalu menghitung irama
# asli tiap node radio dan MEREKOMENDASIKAN nilai ambang yang aman
# (sekitar 2x interval terpanjang yang teramati).
#
# Pakai
# -----
#   # cara 1 (disarankan): baca dari exporter yang sudah jalan
#   python catat-node.py --durasi 24
#
#   # cara 2: ambil sendiri dari node (butuh pustaka meshtastic)
#   ./venv/Scripts/python catat-node.py --langsung --durasi 24
#
#   # cepat: satu sampel saja, tanpa berkas
#   python catat-node.py --sekali
#
# Opsi
# ----
#   --data URL     alamat /data.json exporter (bawaan http://127.0.0.1:9208/data.json)
#   --langsung     ambil langsung dari node via TCP (abaikan --data)
#   --host / --port   alamat node untuk --langsung (bawaan 192.168.20.31:4403)
#   --durasi JAM   lama pencatatan (bawaan 24; 0 = tanpa batas)
#   --interval DET jeda antar sampel (bawaan 60)
#   --csv BERKAS   tempat menyimpan sampel (bawaan catat-node.csv)
#   --sekali       ambil satu sampel, tampilkan, lalu keluar
#   --laporan      jangan mencatat; hanya baca --csv yang ada lalu laporkan
#
# Aman: hanya MEMBACA. Tidak mengubah setelan node.
# ============================================================

import csv
import json
import os
import sys
import time
import urllib.request

AKAR = os.path.dirname(os.path.abspath(__file__))
KOLOM = ["waktu_epoch", "waktu", "node_id", "nama", "via", "online",
         "last_heard_seconds", "snr", "hops", "battery", "favorite"]


def angka_atau_kosong(nilai):
    return "" if nilai is None else nilai


def ambil_dari_exporter(url, timeout=15):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "catat-node/1.0")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def siapkan_langsung(host, port):
    """Sambung ke node via TCP dan bungkus agar mirip data.json exporter."""
    from meshtastic.tcp_interface import TCPInterface
    iface = TCPInterface(hostname=host, portNumber=port)
    batas = time.time() + 25
    while time.time() < batas and not iface.nodes:
        time.sleep(1)
    return iface


def dari_iface(iface):
    """Ubah iface.nodes menjadi bentuk data.json yang dipakai alat ini."""
    try:
        diri_id = ((iface.getMyNodeInfo() or {}).get("user") or {}).get("id")
    except Exception:
        diri_id = None
    sekarang = time.time()
    daftar = []
    for node_id, n in (iface.nodes or {}).items():
        n = n or {}
        user = n.get("user") or {}
        dm = n.get("deviceMetrics") or {}
        last = n.get("lastHeard")
        if node_id == diri_id:
            via = "diri"
        elif n.get("viaMqtt"):
            via = "mqtt"
        else:
            via = "lora"
        daftar.append({
            "node_id": node_id,
            "long_name": user.get("longName") or "",
            "via": via,
            "online": bool(last),
            "last_heard_seconds": (sekarang - last) if last else None,
            "snr": n.get("snr"),
            "hops": n.get("hopsAway"),
            "battery": dm.get("batteryLevel"),
            "favorite": bool(n.get("isFavorite")),
        })
    return {"node": daftar}


def tulis_sampel(penulis, data):
    sekarang = time.time()
    stempel = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sekarang))
    jumlah = 0
    for item in data.get("node", []):
        if item.get("via") != "lora":
            continue          # hanya node radio yang perlu dikalibrasi
        if item.get("last_heard_seconds") is None:
            continue
        penulis.writerow([
            int(sekarang), stempel, item.get("node_id"),
            item.get("long_name") or "", item.get("via"),
            1 if item.get("online") else 0,
            round(item.get("last_heard_seconds") or 0, 1),
            angka_atau_kosong(item.get("snr")),
            angka_atau_kosong(item.get("hops")),
            angka_atau_kosong(item.get("battery")),
            1 if item.get("favorite") else 0,
        ])
        jumlah += 1
    return jumlah


def baca_sampel(berkas):
    """Kumpulkan deret per node: [(waktu_epoch, last_heard_seconds), ...]."""
    per_node = {}
    nama = {}
    if not os.path.exists(berkas):
        return per_node, nama
    with open(berkas, newline="", encoding="utf-8") as f:
        for baris in csv.DictReader(f):
            nid = baris.get("node_id")
            try:
                waktu = float(baris["waktu_epoch"])
                usia = float(baris["last_heard_seconds"])
            except (KeyError, TypeError, ValueError):
                continue
            per_node.setdefault(nid, []).append((waktu, usia))
            nama[nid] = baris.get("nama") or nid
    return per_node, nama


def laporan(berkas):
    per_node, nama = baca_sampel(berkas)
    if not per_node:
        print("Belum ada sampel di %s. Jalankan pencatatan dulu." % berkas)
        return 1

    print("=" * 68)
    print(" LAPORAN IRAMA NODE RADIO (dari %s)" % berkas)
    print("=" * 68)
    print(" File ini merekam kapan tiap node MENGIRIM paket baru. Yang dicari")
    print(" bukan rata-ratanya, melainkan JEDA TERPANJANG - karena ambang offline")
    print(" harus lebih panjang dari itu agar tidak salah alarm.")
    print()

    kesimpulan = []
    for nid in sorted(per_node):
        deret = sorted(per_node[nid])
        # Deteksi pemancaran baru: nilai last_heard_seconds MENGECIL berarti ada
        # paket baru dari node itu (umur sejak terakhir terdengar menyegar).
        kejadian = []
        sebelumnya = None
        for waktu, usia in deret:
            if sebelumnya is None or usia < sebelumnya - 0.5:
                kejadian.append(waktu)
            sebelumnya = usia
        durasi_amati = (deret[-1][0] - deret[0][0]) if len(deret) > 1 else 0
        print("- %s  (%s)" % (nid, nama.get(nid, "?")))
        print("    sampel: %d | lama pengamatan: %s | paket baru terdeteksi: %d"
              % (len(deret), jam_teks(durasi_amati), len(kejadian)))
        if len(kejadian) < 3:
            print("    -> data belum cukup untuk menilai irama (butuh >=3 paket baru).")
            print("       Perpanjang pencatatan, terutama untuk node ROUTER yang")
            print("       memang jarang memancar.")
            print()
            continue
        jeda = [kejadian[i + 1] - kejadian[i] for i in range(len(kejadian) - 1)]
        jeda.sort()
        terpanjang = jeda[-1]
        median = jeda[len(jeda) // 2]
        saran = int(max(terpanjang * 2, 1800))
        print("    jeda antar paket: terpendek %s | median %s | TERPANJANG %s"
              % (jam_teks(jeda[0]), jam_teks(median), jam_teks(terpanjang)))
        print("    -> saran MESH_OFFLINE_SECS = %d (%s), yaitu 2x jeda terpanjang"
              % (saran, jam_teks(saran)))
        kesimpulan.append((nid, saran))
        print()

    print("=" * 68)
    print(" RINGKASAN")
    print("=" * 68)
    if not kesimpulan:
        print(" Belum ada node dengan data cukup. Jalankan lebih lama (mis. 24 jam),")
        print(" karena node ROUTER bisa hanya memancar beberapa kali sehari.")
    else:
        paling_aman = max(saran for _, saran in kesimpulan)
        for nid, saran in kesimpulan:
            print("   %-10s -> MESH_OFFLINE_SECS >= %d (%s)" % (nid, saran, jam_teks(saran)))
        print()
        print(" Supaya SEMUA node radio aman, pakai nilai terbesar:")
        print("   MESH_OFFLINE_SECS=%d" % paling_aman)
        print(" Setel di exporter (Environment= pada meshtastic-exporter.service atau")
        print(" variabel lingkungan), lalu notifier memakai nilai yang sama.")
        print(" Catatan: makin panjang ambang, makin lambat Anda tahu node benar-benar")
        print(" mati - itu pertukaran yang disengaja untuk menghindari alarm palsu.")
    print("=" * 68)
    return 0


def jam_teks(detik):
    if detik is None:
        return "-"
    detik = int(max(0, detik))
    jam, sisa = divmod(detik, 3600)
    menit, sisa = divmod(sisa, 60)
    if jam >= 24:
        return "%dh %dj" % (jam // 24, jam % 24)
    if jam:
        return "%dj %dm" % (jam, menit)
    if menit:
        return "%dm" % menit
    return "%ds" % sisa


def baca_opsi(argv):
    opsi = {
        "data": os.environ.get("MESH_DATA", "http://127.0.0.1:9208/data.json"),
        "langsung": False,
        "host": os.environ.get("MESH_HOST", "192.168.20.31"),
        "port": int(os.environ.get("MESH_PORT", "4403")),
        "durasi": 24.0,
        "interval": 60,
        "csv": os.path.join(AKAR, "catat-node.csv"),
        "sekali": False,
        "laporan": False,
    }
    kunci_int = {"--interval": "interval", "--port": "port"}
    kunci_num = {"--durasi": "durasi"}
    kunci_str = {"--data": "data", "--host": "host", "--csv": "csv"}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(__doc__ or "catat-node.py - kalibrasi ambang offline node Meshtastic")
            return None
        if a == "--langsung":
            opsi["langsung"] = True; i += 1; continue
        if a == "--sekali":
            opsi["sekali"] = True; i += 1; continue
        if a == "--laporan":
            opsi["laporan"] = True; i += 1; continue
        if a in kunci_int or a in kunci_num or a in kunci_str:
            if i + 1 >= len(argv):
                print("Opsi %s butuh nilai." % a, file=sys.stderr)
                raise SystemExit(2)
            nilai = argv[i + 1]
            if a in kunci_int:
                opsi[kunci_int[a]] = int(nilai)
            elif a in kunci_num:
                opsi[kunci_num[a]] = float(nilai)
            else:
                opsi[kunci_str[a]] = nilai
            i += 2; continue
        print("Opsi tidak dikenal: %s" % a, file=sys.stderr)
        raise SystemExit(2)
    return opsi


def main(argv):
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    opsi = baca_opsi(argv)
    if opsi is None:
        return 0

    if opsi["laporan"]:
        return laporan(opsi["csv"])

    iface = None
    if opsi["langsung"]:
        print("Menyambung langsung ke node %s:%d ..." % (opsi["host"], opsi["port"]))
        try:
            iface = siapkan_langsung(opsi["host"], opsi["port"])
        except Exception as e:
            print("Gagal menyambung langsung: %s" % e, file=sys.stderr)
            print("Alternatif: jalankan exporter lalu pakai mode --data.", file=sys.stderr)
            return 1
    else:
        print("Membaca dari exporter: %s" % opsi["data"])

    print("Mencatat tiap %ds selama %s (Ctrl+C untuk berhenti lebih awal)."
          % (opsi["interval"], "tanpa batas" if opsi["durasi"] <= 0 else jam_teks(opsi["durasi"] * 3600)))
    print()

    baru = not os.path.exists(opsi["csv"])
    berkas = open(opsi["csv"], "a", newline="", encoding="utf-8")
    penulis = csv.writer(berkas)
    if baru:
        penulis.writerow(KOLOM)
        berkas.flush()

    akhir = None if opsi["durasi"] <= 0 else time.time() + opsi["durasi"] * 3600
    jumlah_sampel = 0
    try:
        while True:
            try:
                data = dari_iface(iface) if iface is not None else ambil_dari_exporter(opsi["data"])
            except Exception as e:
                print("  sampel gagal: %s" % e, file=sys.stderr)
                data = None
            if data is not None:
                jumlah = tulis_sampel(penulis, data)
                berkas.flush()
                jumlah_sampel += 1
                print("  %s  sampel #%d (%d node radio)"
                      % (time.strftime("%H:%M:%S"), jumlah_sampel, jumlah))
            if opsi["sekali"]:
                break
            if akhir is not None and time.time() >= akhir:
                print("\nPencatatan selesai.")
                break
            time.sleep(opsi["interval"])
    except KeyboardInterrupt:
        print("\nDihentikan oleh pengguna.")
    finally:
        berkas.close()
        if iface is not None:
            try:
                iface.close()
            except Exception:
                pass

    print()
    return laporan(opsi["csv"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
