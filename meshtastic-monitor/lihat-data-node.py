#!/usr/bin/env python3
# ============================================================
# lihat-data-node.py - tarik sekali data live dari node Meshtastic (TCP API)
# ============================================================
# Alat periksa cepat: menyambung ke SATU node Meshtastic lewat API TCP
# (bawaan port 4403), lalu menampilkan daftar SEMUA node yang diketahui node
# itu - baik yang datang lewat LoRa maupun yang lewat MQTT.
#
# Berguna untuk menjawab "node saya kelihatan tidak?" tanpa menyalakan
# Prometheus/Grafana dulu. Untuk pemantauan terus-menerus, pakai
# exporter-meshtastic.py.
#
# Pakai
# -----
#   ./venv/Scripts/python lihat-data-node.py
#   ./venv/Scripts/python lihat-data-node.py 192.168.20.31
#   ./venv/Scripts/python lihat-data-node.py --json          # JSON mentah
#   ./venv/Scripts/python lihat-data-node.py --lama 30       # tunggu lebih lama
#   ./venv/Scripts/python lihat-data-node.py --lora          # hanya jalur radio
#   ./venv/Scripts/python lihat-data-node.py --mqtt          # hanya jalur internet
#
# Pemisahan jalur: kolom VIA dihitung dari paket TERAKHIR yang dicatat gateway,
# jadi LoRa = terdengar langsung lewat radio (jaringan lokal Anda) dan
# MQTT = datang dari broker internet. Inilah pembeda yang benar-benar diketahui
# perangkat, bukan tebakan.
#
# Lingkungan
# ----------
#   MESH_HOST   alamat node gateway (bawaan 192.168.20.31)
#   MESH_PORT   port API TCP       (bawaan 4403)
#
# Aman: hanya MEMBACA. Tidak mengubah satu pun setelan node.
# ============================================================

import json
import logging
import os
import sys
import time

from meshtastic.tcp_interface import TCPInterface

BAWAAN_HOST = os.environ.get("MESH_HOST", "192.168.20.31")
BAWAAN_PORT = int(os.environ.get("MESH_PORT", "4403"))


def durasi(detik):
    if detik is None:
        return "-"
    detik = int(max(0, detik))
    hari, sisa = divmod(detik, 86400)
    jam, sisa = divmod(sisa, 3600)
    menit, _ = divmod(sisa, 60)
    if hari:
        return "%dh%dj" % (hari, jam)
    if jam:
        return "%dj%dm" % (jam, menit)
    if menit:
        return "%dm" % menit
    return "%ds" % detik


def angka(nilai, satuan="", digit=1):
    if nilai is None:
        return "-"
    try:
        return ("%%.%df%%s" % digit) % (float(nilai), satuan)
    except (TypeError, ValueError):
        return "%s%s" % (nilai, satuan)


def tunggu_node(iface, batas_detik):
    batas = time.time() + batas_detik
    while time.time() < batas:
        if iface.nodes:
            return True
        time.sleep(1)
    return bool(iface.nodes)


def tampilkan(iface, sekarang, lingkup="semua"):
    info = iface.getMyNodeInfo() or {}
    user = info.get("user") or {}
    print("Gateway : %s (%s)" % (user.get("longName") or "?", user.get("id") or "?"))
    print("Perangkat: %s" % (user.get("hwModel") or "-"))
    print("Node di database: %d" % len(iface.nodes or {}))
    print()

    judul = ["ID", "NAMA", "VIA", "ROLE", "BATT", "VOLT", "KANAL", "AIRTX",
             "SNR", "HOP", "TERAKHIR", "LAT/LON", "SUHU"]
    baris = []
    for node_id, n in sorted((iface.nodes or {}).items()):
        n = n or {}
        u = n.get("user") or {}
        dm = n.get("deviceMetrics") or {}
        pos = n.get("position") or {}
        env = n.get("environmentMetrics") or {}
        last = n.get("lastHeard")
        usia = (sekarang - last) if last else None
        latlon = ("%s/%s" % (angka(pos.get("latitude"), "", 4),
                             angka(pos.get("longitude"), "", 4))
                  if pos.get("latitude") is not None else "-")
        # viaMqtt: True = paket terakhir node ini datang lewat internet/MQTT.
        # Bila tidak ada / False, artinya bukan lewat MQTT -> jalur radio (LoRa).
        # Protobuf menghilangkan nilai bawaan, jadi "tidak ada" = False = LoRa.
        via_txt = ("DIRI" if node_id == user.get("id")
                   else ("MQTT" if n.get("viaMqtt") else "LoRa"))
        baris.append([
            node_id,
            (u.get("longName") or "(tanpa nama)")[:22],
            via_txt,
            str(u.get("role") or "-")[:14],
            angka(dm.get("batteryLevel"), "%", 0),
            angka(dm.get("voltage"), "V", 2),
            angka(dm.get("channelUtilization"), "%", 0),
            angka(dm.get("airUtilTx"), "%", 1),
            angka(n.get("snr"), "dB", 1),
            angka(n.get("hopsAway"), "", 0),
            durasi(usia),
            latlon,
            angka(env.get("temperature"), "C", 0),
        ])

    # --- pemisahan jalur: LoRa lokal vs MQTT internet ---
    # VIA dihitung dari paket TERAKHIR yang dicatat gateway, jadi inilah pembeda
    # yang benar-benar diketahui perangkat.
    semua = baris
    if lingkup == "lora":
        baris = [r for r in semua if r[2] == "LoRa"]
        print("Hanya node jalur RADIO (LoRa) - jaringan lokal Anda.")
    elif lingkup == "mqtt":
        baris = [r for r in semua if r[2] == "MQTT"]
        print("Hanya node jalur MQTT - berasal dari internet, bukan radio lokal.")
    print()

    if not baris:
        print("(tidak ada node pada lingkup ini)")
        print()
    else:
        lebar = [max(len(str(r[i])) for r in ([judul] + baris)) for i in range(len(judul))]
        cetak = lambda r: "  ".join(str(v).ljust(lebar[i]) for i, v in enumerate(r))
        print(cetak(judul))
        print("  ".join("-" * w for w in lebar))
        for r in baris:
            print(cetak(r))
        print()

    lora = sum(1 for r in semua if r[2] == "LoRa")
    mqtt = sum(1 for r in semua if r[2] == "MQTT")
    diri = sum(1 for r in semua if r[2] == "DIRI")
    # Bukti koneksi LANGSUNG: SNR terisi (indeks 8) berarti gateway sendiri
    # yang mengukur link radio itu; hop kosong/0 berarti tidak lewat perantara.
    bukti = sum(1 for r in semua
                if r[2] == "LoRa" and r[8] != "-" and r[9] in ("-", "0"))
    print("Total %d node: %d jalur radio (di antaranya %d TERBUKTI tersambung "
          "langsung ke gateway lewat SNR), %d MQTT (internet), %d diri."
          % (len(semua), lora, bukti, mqtt, diri))
    if lingkup != "semua":
        print("Ditampilkan %d baris (lingkup=%s)." % (len(baris), lingkup))
    return baris


def main(argv):
    # Konsol Windows (cp1252) tidak bisa mencetak emoji yang dipakai sebagian
    # nama node; paksa UTF-8 dengan pengganti agar tidak berhenti di tengah.
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    # Pustaka meshtastic mencetak jejak galat saat soket ditutup; redam agar
    # keluaran alat ini tetap bersih.
    logging.getLogger("meshtastic").setLevel(logging.CRITICAL)

    host, port, batas, keluarkan_json = BAWAAN_HOST, BAWAAN_PORT, 25, False
    lingkup = "semua"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            keluarkan_json = True; i += 1; continue
        if a == "--lora":
            lingkup = "lora"; i += 1; continue
        if a == "--mqtt":
            lingkup = "mqtt"; i += 1; continue
        if a in ("-h", "--help"):
            print(__doc__ or "lihat-data-node.py [host] [--port N] [--json] [--lama DET]")
            print("  --lora | --mqtt | --lingkup lora|mqtt|semua")
            return 0
        if a in ("--port", "--lama", "--lingkup"):
            if i + 1 >= len(argv):
                print("Opsi %s butuh nilai." % a, file=sys.stderr)
                return 2
            if a == "--port":
                port = int(argv[i + 1])
            elif a == "--lama":
                batas = int(argv[i + 1])
            else:
                lingkup = argv[i + 1].strip().lower()
                if lingkup not in ("lora", "mqtt", "semua"):
                    print("--lingkup harus lora, mqtt, atau semua.", file=sys.stderr)
                    return 2
            i += 2; continue
        if a.startswith("-"):
            print("Opsi tidak dikenal: %s" % a, file=sys.stderr)
            return 2
        host = a; i += 1

    print("Menyambung ke %s:%d ..." % (host, port))
    iface = TCPInterface(hostname=host, portNumber=port)
    try:
        if not tunggu_node(iface, batas):
            print("Tidak ada node yang terbaca dalam %ds." % batas, file=sys.stderr)
            print("Periksa: node menyala? TCP API aktif? satu jaringan?", file=sys.stderr)
            return 1
        sekarang = time.time()
        if keluarkan_json:
            print(json.dumps(iface.nodes, indent=2, ensure_ascii=False, default=str))
        else:
            tampilkan(iface, sekarang, lingkup)
    finally:
        try:
            iface.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
