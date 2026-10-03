#!/usr/bin/env python3
"""Uji lokal cepat: halaman tetap dirender, skrip posisi terpasang, dan titik
GPS sampah di sekitar (0,0) - penyebab peta "kembali ke posisi awal" - tersaring,
baik pada data baru maupun riwayat lama yang tersimpan sebelum pembersihan
penulisan (28 Sep 2026).

Jalankan dari folder meshtastic-monitor:
    venv/Scripts/python.exe uji-layar-lokal.py
"""
import importlib.util
import json
import os
import sys
import time
import urllib.request

AKAR = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(AKAR, "lacak-kerja")
sys.path.insert(0, DIR)

spec = importlib.util.spec_from_file_location(
    "exporter_meshtastic", os.path.join(DIR, "exporter-meshtastic.py"))
expl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(expl)

expl.lacak_node.init()


def node(via, lat, lon, nama, detik=60, snr=None, hops=None):
    return {
        "via": via, "favorite": False, "long_name": nama, "short_name": nama[:4],
        "hw_model": "SEEED_XIAO_S3", "role": "CLIENT", "battery": 80,
        "voltage": 4.1, "chan_util": 12.0, "air_tx": 2.4, "uptime": 5000,
        "snr": snr, "hops": hops, "last": time.time() - detik,
        "lat": lat, "lon": lon, "alt": 20, "temp": 29.5, "hum": 71.0,
        "press": 1009.0,
    }


nodes = {
    "!c483e00a": node("diri", -6.2088, 106.8456, "GATEWAY-JKT", 2),
    "!da5a16f8": node("lora", -6.9175, 107.6191, "ROUTER-BDG", 300, 8.0, 0),
    "!02ee76d0": node("lora", -7.2575, 112.7521, "MOB-SBY", 1200, 2.5, 2),
    "!1a2b3c4d": node("mqtt", -0.9471, 100.4172, "MQTT-PADANG", 600),
    # Node tanpa kunci GPS: nilai sisa bit yang dulu membuat fitBounds melebar
    # ke seluruh dunia dan zoom jatuh ke 3.
    "!49b70fe8": node("mqtt", 0.0016384, 0.0016384, "N-14-TANPA-GPS", 400),
    "!0a8ef54c": node("mqtt", 0.0262144, 0.0262144, "N-16-TANPA-GPS", 400),
    # Nilai di luar rentang bumi dan teks sampah: harus ikut tersaring.
    "!aaaa0001": node("mqtt", 91.0, 200.0, "LUAR-RENTANG", 400),
    "!aaaa0002": node("mqtt", "bukan-angka", "x", "BUKAN-ANGKA", 400),
}
gateway = {
    "node_id": "!c483e00a", "uptime": 120000, "reboot_count": 12,
    "nodedb_count": 118, "firmware": "2.7.15.567b8ea", "role": "ROUTER",
    "hw_model": "HELTEC_V3", "jumlah_node": len(nodes), "jumlah_lora": 2,
    "jumlah_mqtt": 1, "preset": "LONG_FAST", "kustom": False,
    "spread_factor": 11, "bandwidth": 250, "lantai_snr": -17.5,
}

cuplikan = expl.Cuplikan()
cuplikan.ganti(nodes, gateway)

# Riwayat: titik sampah tidak boleh masuk database, karena satu baris saja
# membuat peta /lacak/<id> melompat ke Teluk Guinea.
bersih = dict(nodes)
bersih["!aaaa0001"] = node("mqtt", 45.0, 45.0, "DI-RIWAYAT", 400)
tulis = expl.lacak_node.catat_snapshot(bersih)
print("baris riwayat ditulis: %d (dari %d node)" % (tulis, len(bersih)))

# Data LAMA: baris dengan sisa bit disuntikkan langsung ke database,
# meniru baris yang tersimpan sebelum pembersihan penulisan (28 Sep
# 2026). Jalur baca harus menyaringnya lagi supaya garis rute tidak
# menyebrang seluruh peta. Baris lama untuk node uji dibuang dulu
# supaya uji bersifat deterministik walau dijalankan berulang kali.
penyimpan = expl.lacak_node._penyimpan()
t0 = time.time() - 3600.0
with penyimpan.kunci:
    konek = penyimpan._konek()
    konek.execute("DELETE FROM posisi WHERE node_id IN (?,?)",
                  ("!c483e00a", "!0f1e2d3c"))
    baris_lama = [
        # !c483e00a: tiga titik sah diselipi dua sisa bit.
        ("!c483e00a", t0, -6.2088, 106.8456, 20),
        ("!c483e00a", t0 + 60, 0.0016384, 0.0016384, 20),
        ("!c483e00a", t0 + 120, -6.2090, 106.8460, 20),
        ("!c483e00a", t0 + 180, 0.0262144, 0.0262144, 20),
        ("!c483e00a", t0 + 240, -6.2092, 106.8462, 20),
        # !0f1e2d3c: perjalanan jauh yang SAH (Jakarta -> Padang,
        # ~900 km) tidak boleh dihapus oleh pembersihan.
        ("!0f1e2d3c", t0, -6.2088, 106.8456, 20),
        ("!0f1e2d3c", t0 + 700, -0.9471, 100.4172, 20),
    ]
    for n_id, t, la, lo, al in baris_lama:
        konek.execute(
            "INSERT OR REPLACE INTO posisi (node_id,t,lat,lon,alt)"
            " VALUES (?,?,?,?,?)", (n_id, t, la, lo, al))
    konek.commit()
print("baris lama disuntikkan: %d" % len(baris_lama))

srv = expl.jalankan_web("127.0.0.1", 9219, cuplikan, 10800, "192.168.20.31",
                        4403, None)
gagal = []
try:
    for jalur, tanda in (("/", "meshid-layar-1"),
                         ("/peta", "meshid-peta-view-1"),
                         ("/lacak", "Tracking"),
                         ("/metrics", "meshtastic")):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9219" + jalur,
                                        timeout=15) as r:
                isi = r.read().decode("utf-8", "replace")
            print("%-10s %s  %7d byte   penanda '%s': %s"
                  % (jalur, r.status, len(isi), tanda, tanda in isi))
            if tanda not in isi:
                gagal.append("%s tidak memuat %s" % (jalur, tanda))
            if jalur == "/peta":
                for sampah in ("0.0016384", "0.0262144", "0.0016", "0.0262"):
                    if sampah in isi:
                        gagal.append("/peta masih memuat titik sampah %s" % sampah)
                # 4 node berkoordinat sah: gateway, router, mobile, padang.
                if isi.count('"lat":') != 4:
                    gagal.append("/peta memuat %d titik, seharusnya 4"
                                 % isi.count('"lat":'))
                if "<b>4</b><span>tanpa koordinat</span>" not in isi:
                    gagal.append("kartu 'tanpa koordinat' tidak menghitung "
                                 "4 node tanpa GPS/luar rentang")
                # Label nama node menempel di peta, bukan cuma di popup.
                if isi.count('"nama":') != 4:
                    gagal.append("label nama tidak ikut dikirim ke peta")
                for nama in ("GATEWAY-JKT", "ROUTER-BDG"):
                    if nama not in isi:
                        gagal.append("nama %s tidak ada di data peta" % nama)
                if "bindTooltip" not in isi or "label-node" not in isi:
                    gagal.append("skrip label nama node tidak terpasang")
                if "saklar-nama" not in isi or "peta-tanpa-nama" not in isi:
                    gagal.append("saklar sembunyikan nama tidak terpasang")
                # Telemetri di popup.
                for medan in ("Suhu", "Kelembapan", "Tekanan", "Kanal",
                              "Udara TX", "Uptime"):
                    if medan not in isi:
                        gagal.append("popup tidak memuat telemetri %s" % medan)
                # Satuan di dalam nilai popup harus karakter sungguhan ("\u00b0C"),
                # bukan entitas HTML: nilai itu di-escape sekali lagi, sehingga
                # entitas tadi berakhir sebagai tulisan "&amp;deg;" di layar.
                if "&amp;deg;" in isi or "&amp;middot;" in isi:
                    gagal.append("satuan popup ter-escape dua kali")
                if "\u00b0C" not in isi:
                    gagal.append("satuan derajat tidak muncul sebagai karakter")
        except Exception as e:  # noqa: BLE001
            print("%-10s GAGAL: %s" % (jalur, e))
            gagal.append("%s error: %s" % (jalur, e))

    # Halaman detail /lacak/<node_id>: nama node harus muncul di peta
    # riwayat (balon penanda posisi + popup titik singgah), bukan cuma
    # di judul halaman. `catat_snapshot` di atas sudah menulis riwayat
    # untuk node berkoordinat sah, jadi !c483e00a pasti punya paket.
    try:
        with urllib.request.urlopen("http://127.0.0.1:9219/lacak/!c483e00a",
                                    timeout=15) as r:
            isi = r.read().decode("utf-8", "replace")
        print("%-10s %s  %7d byte" % ("/lacak/id", r.status, len(isi)))
        if "Tracking Node" not in isi:
            gagal.append("/lacak/<id> bukan halaman Tracking Node")
        for tanda, pesan in (
                ('"nama": "GATEWAY-JKT"',
                 "data JSON tidak memuat nama node"),
                ('"node_id": "!c483e00a"',
                 "data JSON tidak memuat node_id"),
                ("function escHtml",
                 "helper escape nama node tidak ada di skrip"),
                ("const NAMA_NODE",
                 "nama node tidak disiapkan untuk tooltip/popup"),
                ("class=\"b-nama\"",
                 "balon penanda posisi tidak menampilkan nama"),
                ("pop-judul",
                 "popup titik singgah tanpa judul nama node"),
                ("class=\"pop-id\"",
                 "popup titik singgah tanpa ID node")):
            if tanda not in isi:
                gagal.append("/lacak/<id>: %s" % pesan)
    except Exception as e:  # noqa: BLE001
        print("/lacak/id GAGAL: %s" % e)
        gagal.append("/lacak/<id> error: %s" % e)

    # Riwayat lama: sisa bit harus dibuang dari rute sehingga garis
    # terbentuk rapi (tanpa lompatan 12.000 km ke Null Island).
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:9219/lacak/!c483e00a.json",
                timeout=15) as r:
            isi_json = r.read().decode("utf-8", "replace")
        data = json.loads(isi_json)
        rute = data["route"]
        print("%-14s %s  %7d byte   titik rute: %d"
              % ("/lacak/id.json", r.status, len(isi_json),
                 len(rute)))
        for sampah in ("0.0016384", "0.0262144", "0.0016",
                       "0.0262"):
            if sampah in isi_json:
                gagal.append("riwayat lama: rute masih memuat %s"
                             % sampah)
        if len(rute) != 3:
            gagal.append("riwayat lama: rute %d titik, seharusnya 3"
                         % len(rute))
        if data["stats"]["points"] != 3:
            gagal.append("riwayat lama: stats.points=%d, seharusnya 3"
                         % data["stats"]["points"])
        for la, lo in rute:
            if abs(la) < 0.1 and abs(lo) < 0.1:
                gagal.append("riwayat lama: titik Null Island %s,%s "
                             "lolos" % (la, lo))
        if data["bounds"][0][0] > -1.0:
            gagal.append("riwayat lama: bounds rusak (lat_min=%s)"
                         % data["bounds"][0][0])
        lompat = max((l["dist_m"] for l in data["legs"]),
                     default=0.0)
        if lompat > 200.0:
            gagal.append("riwayat lama: kaki %d m, seharusnya < 200 m"
                         % lompat)
    except Exception as e:  # noqa: BLE001
        print("/lacak/id.json GAGAL: %s" % e)
        gagal.append("/lacak/<id>.json error: %s" % e)

    # Lompatan jauh yang sah (Jakarta -> Padang) harus tetap menjadi
    # garis rute: pembersihan tidak boleh menghapus perjalanan nyata.
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:9219/lacak/!0f1e2d3c.json",
                timeout=15) as r:
            isi_json = r.read().decode("utf-8", "replace")
        data = json.loads(isi_json)
        rute = data["route"]
        if len(rute) != 2:
            gagal.append("lompatan jauh: rute %d titik, seharusnya 2"
                         % len(rute))
        elif (rute[0] != [-6.2088, 106.8456]
                or rute[-1] != [-0.9471, 100.4172]):
            gagal.append("lompatan jauh: ujung rute berubah: %s" % rute)
        jauh = expl.lacak_node.jarak_m(-6.2088, 106.8456,
                                       -0.9471, 100.4172)
        # stats.dist_km dibulatkan ke 0,1 km, jadi bandingkan
        # dengan nilai harapan yang dibulatkan dengan cara sama.
        if abs(data["stats"]["dist_km"]
               - round(jauh / 1000.0, 1)) > 0.05:
            gagal.append("lompatan jauh: dist %s km, seharusnya ~%.1f km"
                         % (data["stats"]["dist_km"], jauh / 1000.0))
    except Exception as e:  # noqa: BLE001
        print("/lompatan-jauh GAGAL: %s" % e)
        gagal.append("lompatan jauh error: %s" % e)
finally:
    srv.shutdown()

print()
if gagal:
    for m in gagal:
        print("GAGAL:", m)
    sys.exit(1)
print("SEMUA LULUS")
