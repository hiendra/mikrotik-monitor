#!/usr/bin/env python3
# ============================================================
# traceroute-node.py - baca data traceroute Meshtastic secara terstruktur
# ============================================================
# Traceroute menjawab pertanyaan yang tidak bisa dijawab daftar node: "lewat
# node APA saja paket saya sampai ke tujuan, dan seberapa kuat sinyal tiap hop?"
#
# Pustaka meshtastic bawaan hanya MENCETAK hasilnya dan tidak mengembalikan
# data, jadi alat ini menangkap balasan traceroute sendiri (portnum
# TRACEROUTE_APP), mengurai RouteDiscovery, lalu menyajikannya sebagai rantai
# hop + SNR per hop - lengkap dengan nama node, bukan hanya nomor.
#
# PERHATIAN: traceroute MEMANCARKAN paket ke udara (bukan sekadar membaca).
# Satu permintaan = satu paket siaran + balasan, jadi hematlah pemakaiannya.
# Tidak ada setelan node yang diubah.
#
# Pakai
# -----
#   ./venv/Scripts/python traceroute-node.py '!da5a16f8'
#   ./venv/Scripts/python traceroute-node.py ROUTER          # cari dari nama
#   ./venv/Scripts/python traceroute-node.py --semua         # semua node LoRa
#   ./venv/Scripts/python traceroute-node.py '!da5a16f8' --hop-limit 7
#
# Opsi
# ----
#   --host / --port   alamat node gateway (bawaan 192.168.20.31:4403)
#   --hop-limit N     batas hop yang dijelajahi (bawaan 3; hop di luar ini tidak
#                     akan muncul di hasil)
#   --channel N       indeks kanal (bawaan 0)
#   --timeout DET     batas tunggu balasan per tujuan (bawaan 25)
#   --semua           traceroute ke SEMUA node yang terdengar langsung lewat LoRa
#   --mentah          tampilkan angka mentah RouteDiscovery (untuk verifikasi)
#
# Lingkungan: MESH_HOST, MESH_PORT
# ============================================================

import os
import sys
import threading
import time

from pubsub import pub

from meshtastic.protobuf import mesh_pb2, portnums_pb2
from meshtastic.tcp_interface import TCPInterface

BAWAAN_HOST = os.environ.get("MESH_HOST", "192.168.20.31")
BAWAAN_PORT = int(os.environ.get("MESH_PORT", "4403"))
SNR_TIDAK_DIKETAHUI = -128

_balasan = []
_kunci = threading.Lock()


def saat_menerima(packet, interface=None):
    decoded = (packet or {}).get("decoded") or {}
    portnum = str(decoded.get("portnum") or "")
    if portnum not in ("TRACEROUTE_APP", "ROUTING_APP"):
        return
    with _kunci:
        _balasan.append(packet)


def nama_node(iface, num):
    """Ubah nomor node menjadi '!id Nama' bila dikenal."""
    node_id = "!%08x" % num if isinstance(num, int) else str(num)
    n = (iface.nodes or {}).get(node_id) or {}
    nama = (n.get("user") or {}).get("longName")
    return "%s %s" % (node_id, nama) if nama else node_id


def field(msg, *nama):
    """Ambil field protobuf; terima snake_case (protobuf) maupun camelCase."""
    for n in nama:
        try:
            nilai = getattr(msg, n)
        except AttributeError:
            continue
        return list(nilai)
    return []


def snr_teks(nilai):
    if nilai is None or nilai == SNR_TIDAK_DIKETAHUI:
        return "?"
    return "%.1f dB" % (nilai / 4.0)


def urai(packet, iface):
    """Kembalikan dict rincian dari satu balasan traceroute."""
    decoded = packet.get("decoded") or {}
    if str(decoded.get("portnum")) == "ROUTING_APP":
        err = ((decoded.get("routing") or {}).get("errorReason")) or "?"
        return {"galat": err}
    rd = mesh_pb2.RouteDiscovery()
    rd.ParseFromString(decoded.get("payload") or b"")

    asal = packet.get("from")
    tujuan_kita = packet.get("to")
    # Nama field protobuf memakai snake_case (snr_towards); camelCase disiapkan
    # sebagai cadangan agar alat ini tetap jalan di versi pustaka lain.
    rute = field(rd, "route")
    snr_maju = field(rd, "snr_towards", "snrTowards")
    rute_balik = field(rd, "route_back", "routeBack")
    snr_balik = field(rd, "snr_back", "snrBack")

    # Rantai pergi: kita -> [hop perantara...] -> tujuan
    # snrTowards punya satu entri per hop yang MENERIMA paket, jadi
    # snrTowards[i] adalah SNR saat node ke-(i+1) menerima paket.
    rantai = [tujuan_kita] + rute + [asal]
    snr_rantai = []
    for i in range(1, len(rantai)):
        idx = i - 1
        snr_rantai.append(snr_maju[idx] if idx < len(snr_maju) else None)

    ada_balik = "hopStart" in packet and len(snr_balik) == len(rute_balik) + 1
    rantai_balik = ([asal] + rute_balik + [tujuan_kita]) if ada_balik else []
    snr_balik_rantai = []
    if ada_balik:
        for i in range(1, len(rantai_balik)):
            idx = i - 1
            snr_balik_rantai.append(snr_balik[idx] if idx < len(snr_balik) else None)

    return {
        "mentah": {
            "route": list(rute),
            "snr_towards_raw": list(snr_maju),
            "route_back": list(rute_balik),
            "snr_back_raw": list(snr_balik),
            "hopStart": packet.get("hopStart"),
            "hopLimit": packet.get("hopLimit"),
            "rxSnr": packet.get("rxSnr"),
        },
        "asal": asal,
        "kita": tujuan_kita,
        "rute": rute,
        "rantai": rantai,
        "snr_rantai": snr_rantai,
        "ada_balik": ada_balik,
        "rantai_balik": rantai_balik,
        "snr_balik_rantai": snr_balik_rantai,
        "hop": len(rute),
    }


def cetak_rantai(iface, rantai, snr_rantai, label):
    print("    %-12s: %s" % (label, nama_node(iface, rantai[0])))
    for i in range(1, len(rantai)):
        print("    %-12s  -> %-28s %s" % ("", nama_node(iface, rantai[i]),
                                          snr_teks(snr_rantai[i - 1])))


def jalankan(iface, tujuan, opsi):
    _balasan.clear()
    print("Traceroute ke %s (hop limit %d) ..." % (nama_node(iface, tujuan), opsi["hop_limit"]))
    iface.sendData(
        mesh_pb2.RouteDiscovery(),
        destinationId=tujuan,
        portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
        wantResponse=True,
        channelIndex=opsi["channel"],
        hopLimit=opsi["hop_limit"],
    )

    batas = time.time() + opsi["timeout"]
    jawab = None
    while time.time() < batas:
        with _kunci:
            for p in _balasan:
                if p.get("from") == tujuan or (p.get("decoded") or {}).get("portnum") == "TRACEROUTE_APP":
                    jawab = p
        if jawab:
            break
        time.sleep(0.5)

    if jawab is None:
        print("    TIDAK ADA BALASAN dalam %ds." % opsi["timeout"])
        print("    Artinya: node tidak terjangkau, tidur, atau hop limit terlalu kecil.")
        print()
        return None

    r = urai(jawab, iface)
    if "galat" in r:
        print("    GAGAL: router menjawab error '%s'." % r["galat"])
        print()
        return {"tujuan": tujuan, "galat": r["galat"]}

    if opsi.get("mentah"):
        print("    MENTAH     : %s" % r["mentah"])
    cetak_rantai(iface, r["rantai"], r["snr_rantai"], "Rute pergi")
    if r["ada_balik"]:
        cetak_rantai(iface, r["rantai_balik"], r["snr_balik_rantai"], "Rute balik")
    else:
        print("    %-12s: (tidak tersedia)" % "Rute balik")

    if r["hop"] == 0:
        print("    Kesimpulan : LANGSUNG lewat radio, tanpa node perantara.")
    else:
        perantara = ", ".join(nama_node(iface, x) for x in r["rute"])
        print("    Kesimpulan : lewat %d node perantara: %s" % (r["hop"], perantara))
    sah = [s for s in r["snr_rantai"] if s is not None and s != SNR_TIDAK_DIKETAHUI]
    if sah:
        terlemah = min(sah)
        print("    Hop terlemah: %s" % snr_teks(terlemah))
    print()
    return {"tujuan": tujuan, "hop": r["hop"],
            "snr_terlemah": min(sah) if sah else None}


def pilih_target(iface, pilihan):
    """Cari nomor node dari '!id', potongan nama, atau angka."""
    nodes = iface.nodes or {}
    if pilihan.startswith("!"):
        return int(pilihan[1:], 16) if pilihan[1:] else None
    if pilihan.isdigit():
        return int(pilihan)
    cocok = [(nid, n) for nid, n in nodes.items()
             if pilihan.lower() in ((n.get("user") or {}).get("longName") or "").lower()]
    if len(cocok) == 1:
        return int(cocok[0][0][1:], 16)
    if len(cocok) > 1:
        print("Nama '%s' cocok dengan beberapa node:" % pilihan)
        for nid, n in cocok:
            print("   %s %s" % (nid, (n.get("user") or {}).get("longName")))
        return None
    return None


def daftar_lora(iface):
    """Semua node yang terdengar langsung lewat LoRa (punya lastHeard, bukan diri)."""
    try:
        diri = ((iface.getMyNodeInfo() or {}).get("user") or {}).get("id")
    except Exception:
        diri = None
    hasil = []
    for nid, n in (iface.nodes or {}).items():
        if nid == diri or n.get("viaMqtt") or n.get("lastHeard") is None:
            continue
        hasil.append((int(nid[1:], 16), (n.get("user") or {}).get("longName") or nid))
    return hasil


def main(argv):
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    opsi = {"host": BAWAAN_HOST, "port": BAWAAN_PORT, "hop_limit": 3,
            "channel": 0, "timeout": 25, "semua": False, "mentah": False}
    pilihan = None
    i = 0
    kunci_int = {"--port": "port", "--hop-limit": "hop_limit",
                 "--channel": "channel", "--timeout": "timeout"}
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(__doc__ or "traceroute-node.py [tujuan] [--semua]")
            return 0
        if a == "--semua":
            opsi["semua"] = True; i += 1; continue
        if a == "--mentah":
            opsi["mentah"] = True; i += 1; continue
        if a == "--host":
            if i + 1 >= len(argv):
                print("--host butuh nilai.", file=sys.stderr); return 2
            opsi["host"] = argv[i + 1]; i += 2; continue
        if a in kunci_int:
            if i + 1 >= len(argv):
                print("%s butuh nilai." % a, file=sys.stderr); return 2
            opsi[kunci_int[a]] = int(argv[i + 1]); i += 2; continue
        if a.startswith("-"):
            print("Opsi tidak dikenal: %s" % a, file=sys.stderr); return 2
        pilihan = a; i += 1

    if not opsi["semua"] and not pilihan:
        print("Sebutkan tujuan, atau pakai --semua.", file=sys.stderr)
        return 2

    print("Menyambung ke %s:%d ..." % (opsi["host"], opsi["port"]))
    iface = TCPInterface(hostname=opsi["host"], portNumber=opsi["port"])
    pub.subscribe(saat_menerima, "meshtastic.receive")
    try:
        batas = time.time() + 25
        while time.time() < batas and not iface.nodes:
            time.sleep(1)

        if opsi["semua"]:
            target = daftar_lora(iface)
            print("Traceroute ke %d node LoRa langsung.\n" % len(target))
        else:
            num = pilih_target(iface, pilihan)
            if num is None:
                print("Tujuan '%s' tidak ditemukan di daftar node." % pilihan, file=sys.stderr)
                return 1
            target = [(num, None)]

        ringkasan = []
        for num, _ in target:
            hasil = jalankan(iface, num, opsi)
            if hasil:
                ringkasan.append(hasil)

        if len(ringkasan) > 1:
            print("=" * 62)
            print(" RINGKASAN")
            print("=" * 62)
            for h in ringkasan:
                if "galat" in h:
                    print(" %-30s GAGAL: %s" % (nama_node(iface, h["tujuan"]), h["galat"]))
                else:
                    print(" %-30s %d hop | SNR terlemah %s"
                          % (nama_node(iface, h["tujuan"]), h["hop"],
                             snr_teks(h["snr_terlemah"])))
    finally:
        try:
            iface.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
