#!/usr/bin/env python3
# ============================================================
# exporter-meshtastic.py - Prometheus exporter + tampilan data node Meshtastic
# ============================================================
# Terhubung ke SATU node Meshtastic lewat API TCP (bawaan port 4403), lalu:
#   1. mengekspos metrik Prometheus di  http://<host>:9208/metrics
#   Node MQTT ikut terbaca, jadi metrik meshtastic_node_direct dipakai untuk
#   menyorot hanya node yang benar-benar ada di jaringan RF Anda.
#   2. menyajikan halaman web semua data node di
#      http://<host>:9208/            (HTML, auto-refresh)
#      http://<host>:9208/data.json   (JSON, untuk integrasi lain)
#   3. menerima perintah tombol halaman web di
#      http://<host>:9208/aksi        (POST {"aksi", "node_id"})
#      aksi: "hapus" (keluarkan node dari database gateway), "unfavorit"
#      (lepas tanda Favorite), atau "favorit" (tandai node sebagai Favorite).
#      Perintah DIANTRIKAN lalu dijalankan oleh thread
#      collector yang memegang interface, bukan oleh thread HTTP.
#
# Halaman web menampilkan SEMUA data yang diketahui node gateway: setiap node
# yang pernah ia dengar (nama, role, baterai, tegangan, utilisasi kanal,
# airtime TX, uptime, SNR, hop, posisi, sensor lingkungan) dan umpan paket
# terakhir yang masuk ke node gateway.
#
# Karena satu node Meshtastic menyimpan database SEMUA node yang pernah ia
# dengar, satu koneksi cukup untuk memantau node tower (ROUTER) sekaligus
# node client di bawahnya - asalkan node router memang terdengar lewat LoRa.
#
# Metrik Prometheus (label node_id selalu ada):
#   meshtastic_node_info                            metadata (selalu 1)
#     label via = lora (jalur radio langsung) / mqtt (lewat internet) / diri (gateway)
#   meshtastic_node_direct                          1 bila node terdengar LANGSUNG lewat LoRa
#   meshtastic_node_online                          1 bila baru terdengar
#   meshtastic_node_last_heard_seconds              detik sejak terakhir terdengar
#   meshtastic_node_last_heard_timestamp_seconds    waktu paket terakhir (epoch, konvensi Prometheus)
#   meshtastic_device_battery_level_percent         level baterai (%)
#   meshtastic_device_voltage_volts                 tegangan (V)
#   meshtastic_device_channel_utilization_percent   utilisasi kanal (%)
#   meshtastic_device_air_tx_utilization_percent    airtime TX (%)
#   meshtastic_device_uptime_seconds                uptime perangkat (detik)
#   meshtastic_node_snr_db                          SNR terakhir (dB)
#   meshtastic_node_hops_away                       jumlah hop
#   meshtastic_node_latitude / _longitude / _altitude_meters
#   meshtastic_environment_temperature_celsius      suhu (bila ada sensor)
#   meshtastic_environment_humidity_percent         kelembapan
#   meshtastic_environment_pressure_hpa             tekanan
#   meshtastic_packets_received_total               jumlah paket per node & tipe
#   meshtastic_cuplikan_umur_seconds                umur data node terakhir yang dikumpulkan
#   meshtastic_exporter_up                          1 bila exporter terhubung DAN datanya segar
#     (turun ke 0 bila umur data melewati MESH_BASI_MAKS, bawaan 3x interval)
#
# Pakai
# -----
#   pip install -r requirements.txt
#   MESH_HOST=192.168.20.31 python exporter-meshtastic.py
#   buka http://<ip-mesin-exporter>:9208/
#
# Lingkungan
# ----------
#   MESH_HOST          alamat node Meshtastic (bawaan 192.168.20.31)
#   MESH_PORT          port API TCP node (bawaan 4403)
#   MESH_EXPORTER_PORT port HTTP exporter (bawaan 9208)
#   MESH_LISTEN        alamat bind exporter (bawaan 0.0.0.0)
#   MESH_INTERVAL      detik antar penyegaran data (bawaan 30)
#   MESH_OFFLINE_SECS  ambang "online"; di atas ini dianggap offline
#                      (bawaan 10800 = 3 jam, agar node ROUTER yang jarang
#                      memancarkan telemetry tetap terbaca online)
#   MESH_PAKET_BUFFER  banyak paket terakhir yang disimpan di umpan (bawaan 200)
#   MESH_DB_AMBANG     ambang peringatan isi database gateway (bawaan 190)
#   MESH_LOG           level log: DEBUG/INFO/WARNING (bawaan INFO)
#
# Tampilan yang dibaca manusia
# -----------------------------
# Dua nilai perangkat tidak ditampilkan apa adanya karena menyesatkan:
#   - batteryLevel > 100 (firmware memakai 101 = tersambung listrik/USB)
#     ditulis "charge", bukan "101%";
#   - tegangan yang membulat ke nol (derau ADC tanpa penginderaan baterai)
#     ditulis "-", bukan "-0.00 V".
# Nilai MENTAH tetap utuh di /metrics dan /data.json untuk alert dan skrip.
#
# Ambang yang dipakai halaman
# ---------------------------
# Angka di kolom Kanal, Air TX, dan Hop diberi warna menurut pedoman
# operasional Meshtastic (lihat TANGGA_* di bawah). Pedoman itu dipakai juga
# oleh dasbor komunitas, jadi angkanya bisa dibandingkan antarperkakas.
#
# Catatan penting
# ---------------
# Node berperan ROUTER hanya memancarkan telemetry sendiri sekitar tiap 12
# jam, jadi battery/utilisasi node tower akan jarang diperbarui. Node CLIENT
# normal mengirim jauh lebih sering. Ubah ke ROUTER_CLIENT bila ingin
# telemetry router lebih rapat.
# ============================================================

import json
import logging
import os
import re
import sys
import threading
import time
import urllib.parse

# Modul lacakan (tab Tracking Node) dimuat di sini dengan import biasa, bukan
# di dalam main(): kalau modulnya hilang, exporter harus gagal NYATA saat
# start, bukan gagal diam-diam setiap kali ada yang membuka /lacak.
import lacak_halaman
import lacak_node
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pubsub import pub
from meshtastic.tcp_interface import TCPInterface
from meshtastic import mesh_pb2, portnums_pb2
from google.protobuf import json_format

from prometheus_client import Gauge, CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.core import REGISTRY, GaugeMetricFamily

LOG = logging.getLogger("meshtastic-exporter")


def _env(nama, bawaan):
    return os.environ.get(nama, bawaan)


def _env_int(nama, bawaan):
    try:
        return int(os.environ.get(nama, str(bawaan)))
    except (TypeError, ValueError):
        return bawaan


BATAS_PAKET = max(10, _env_int("MESH_PAKET_BUFFER", 200))
# Ambang peringatan isi database node gateway. Saat database penuh, Meshtastic
# membuang node "terlama dan paling tidak menarik", sehingga node RF yang jarang
# memancar (mis. router tower) berisiko tergeser keluar.
AMBANG_DB_PENUH = _env_int("MESH_DB_AMBANG", 190)


def nama_enum(nilai):
    """Enum protobuf bisa datang sebagai int atau nama; normalisasi ke teks."""
    if nilai is None:
        return ""
    return str(nilai)


# Urutan Role di firmware Meshtastic. Dipakai untuk menerjemahkan angka yang
# datang dari metadata gateway (di sana role masih berupa enum mentah).
ROLE = {0: "CLIENT", 1: "CLIENT_MUTE", 2: "ROUTER", 3: "ROUTER_CLIENT",
        4: "REPEATER", 5: "TRACKER", 6: "SENSOR", 7: "TAK", 8: "CLIENT_HIDDEN",
        9: "LOST_AND_FOUND", 10: "TAK_TRACKER", 11: "ROUTER_LATE", 12: "CLIENT_BASE"}


def nama_role(nilai):
    if isinstance(nilai, int):
        return ROLE.get(nilai, str(nilai))
    return nama_enum(nilai)


def ambil_field(obj, *nama):
    """Ambil field protobuf dengan toleransi camelCase maupun snake_case.

    Dict node dari pustaka meshtastic memakai camelCase ("hwModel"), sedangkan
    objek protobuf seperti myInfo/metadata memakai snake_case ("firmware_version").
    """
    if obj is None:
        return None
    for n in nama:
        try:
            nilai = getattr(obj, n)
        except Exception:
            continue
        if nilai is not None:
            return nilai
    return None


class Cuplikan:
    """Salinan data node yang aman dibaca oleh collector tanpa race."""

    def __init__(self):
        self._kunci = threading.Lock()
        self._nodes = {}
        self._gateway = {}
        self._sekarang = time.time()
        # Antrian perintah dari halaman web (hapus/unfavorit node). HTTP berjalan
        # di thread terpisah dari collector, jadi satu-satunya cara aman keduanya
        # bertukar perintah adalah lewat objek Cuplikan milik bersama ini.
        self._antrian = deque()
        self._sinyal = threading.Event()
        self._kunci_antrian = threading.Lock()

    def ganti(self, nodes, gateway=None):
        with self._kunci:
            self._nodes = nodes
            self._gateway = dict(gateway or {})
            self._sekarang = time.time()

    def baca(self):
        with self._kunci:
            return dict(self._nodes), dict(self._gateway), self._sekarang

    def taruh_perintah(self, aksi, sasaran):
        """Simpan satu perintah untuk collector; balikkan penanda hasilnya.

        Collector mengeksekusi lewat threadnya sendiri dan mengisi perintah
        ["hasil"], lalu menyalakan event "selesai" - HTTP menunggu event itu.
        """
        perintah = {
            "aksi": aksi,
            "sasaran": sasaran,
            "hasil": None,
            "selesai": threading.Event(),
        }
        with self._kunci_antrian:
            self._antrian.append(perintah)
        self._sinyal.set()
        return perintah

    def ambil_perintah(self):
        """Ambil SEMUA perintah yang menunggu; kosong bila tidak ada."""
        with self._kunci_antrian:
            if not self._antrian:
                return []
            daftar = list(self._antrian)
            self._antrian.clear()
        return daftar

    def tunggu_sinyal(self, batas):
        """Tidur sampai `batas` detik; bangun lebih cepat bila ada perintah."""
        if self._sinyal.wait(batas):
            self._sinyal.clear()


# Waktu paket terakhir per node (dari callback pubsub), dipakai sebagai
# pelengkap bila field lastHeard tidak tersedia di versi firmware tertentu.
_PAKET_TERAKHIR = {}
_PAKET = deque(maxlen=BATAS_PAKET)
_HITUNG = {}  # (node_id, portnum) -> jumlah paket
_PAKET_KUNCI = threading.Lock()


def _hitung_hop(packet):
    awal = packet.get("hopStart")
    sisa = packet.get("hopLimit")
    if awal is None or sisa is None:
        return None
    return max(0, int(awal) - int(sisa))


def saat_menerima(packet, interface=None):
    """Callback tiap paket masuk: catat waktu, hitung, dan simpan di umpan."""
    try:
        asal = packet.get("from")
        node_id = "!%08x" % asal if asal is not None else "?"
        decoded = packet.get("decoded") or {}
        portnum = str(decoded.get("portnum") or "UNKNOWN")
        tujuan = packet.get("to")
        rek = {
            "waktu": time.time(),
            "dari": node_id,
            "ke": ("!%08x" % tujuan) if tujuan else "",
            "portnum": portnum,
            "snr": packet.get("rxSnr"),
            "rssi": packet.get("rxRssi"),
            "hop": _hitung_hop(packet),
        }
        with _PAKET_KUNCI:
            _PAKET.append(rek)
            if asal is not None:
                _PAKET_TERAKHIR[node_id] = rek["waktu"]
                _HITUNG[(node_id, portnum)] = _HITUNG.get((node_id, portnum), 0) + 1
    except Exception:  # jangan pernah matikan thread library karena callback
        LOG.debug("gagal mencatat paket masuk", exc_info=True)


def ambil_paket_terakhir(node_id):
    with _PAKET_KUNCI:
        return _PAKET_TERAKHIR.get(node_id)


def ambil_umpan_paket():
    with _PAKET_KUNCI:
        return list(_PAKET)


def ambil_hitungan():
    with _PAKET_KUNCI:
        return dict(_HITUNG)


def kumpulkan(iface, cuplikan):
    """Baca database node dari interface dan simpan sebagai cuplikan."""
    sekarang = time.time()
    hasil = {}
    try:
        diri_id = ((iface.getMyNodeInfo() or {}).get("user") or {}).get("id")
    except Exception:
        diri_id = None

    # Kesehatan node gateway: jumlah reboot, isi database, versi firmware.
    # nodedb_count penting: database node punya batas, dan bila penuh node
    # yang jarang terdengar (mis. router tower) bisa tergeser keluar.
    reboot_count = nodedb_count = firmware = gw_role = gw_hw = None
    preset = lantai = None
    sf = bw = None
    kustom = False
    try:
        mi = iface.myInfo
        reboot_count = ambil_field(mi, "rebootCount", "reboot_count")
        nodedb_count = ambil_field(mi, "nodedbCount", "nodedb_count")
    except Exception:
        LOG.debug("info gateway tidak terbaca", exc_info=True)
    # Setelan radio gateway menentukan LANTAI DEMODULASI yang dipakai meter
    # sinyal: SNR yang sama bisa berarti "baik" pada satu preset dan "nihil"
    # pada preset lain. Karena itu preset dibaca di sini, bukan ditebak.
    try:
        lora = iface.localNode.localConfig.lora
        sf = ambil_field(lora, "spreadFactor", "spread_factor")
        bw = ambil_field(lora, "bandwidth", "bandwidth")
        pakai_preset = ambil_field(lora, "usePreset", "use_preset")
        preset = nama_preset(ambil_field(lora, "modemPreset", "modem_preset"))
        if pakai_preset is False:
            # Setelan kustom: nama presetnya tidak berlaku, lantainya ditaksir
            # dari spread factor/bandwidth yang benar-benar dipakai.
            kustom = True
            lantai = lantai_snr(sf=sf, bw=bw)
        else:
            lantai = lantai_snr(preset=preset)
    except Exception:
        LOG.debug("konfigurasi LoRa gateway tidak terbaca", exc_info=True)
    if lantai is None:
        lantai = BAWAAN_LANTAI_SNR
    try:
        meta = iface.metadata
        firmware = ambil_field(meta, "firmwareVersion", "firmware_version")
        gw_role = nama_role(ambil_field(meta, "role"))
        # metadata.hw_model berupa angka enum; pakai nama dari daftar node bila ada.
        gw_hw = nama_enum(ambil_field(meta, "hwModel", "hw_model"))
    except Exception:
        LOG.debug("metadata gateway tidak terbaca", exc_info=True)

    for node_id, n in list((iface.nodes or {}).items()):
        n = n or {}
        user = n.get("user") or {}
        dm = n.get("deviceMetrics") or {}
        pos = n.get("position") or {}
        env = n.get("environmentMetrics") or {}

        last = n.get("lastHeard")
        last_paket = ambil_paket_terakhir(node_id)
        if last_paket and (not last or last_paket > last):
            last = last_paket

        # Asal paket terakhir node ini: "mqtt" bila datang lewat internet,
        # "lora" bila terdengar langsung lewat radio, "diri" untuk node gateway
        # sendiri. Protobuf menghilangkan nilai bawaan, jadi viaMqtt yang tidak
        # ada berarti False -> jalur radio.
        if node_id == diri_id:
            via = "diri"
        elif n.get("viaMqtt"):
            via = "mqtt"
        else:
            via = "lora"

        # Koordinat dibersihkan DI SINI, satu tempat, supaya semua yang membaca
        # cuplikan ini (daftar Monitoring, /data.json, Live Map, penyimpan
        # riwayat) sepakat soal node mana yang punya posisi. Node yang belum
        # mengunci GPS melaporkan sisa bit di sekitar (0,0) - lihat
        # lacak_node.posisi_bersih().
        lat, lon = lacak_node.posisi_bersih(pos.get("latitude"),
                                           pos.get("longitude"))

        hasil[node_id] = {
            "via": via,
            "favorite": bool(n.get("isFavorite")),
            "long_name": user.get("longName") or "",
            "short_name": user.get("shortName") or "",
            "hw_model": nama_enum(user.get("hwModel")),
            "role": nama_enum(user.get("role")),
            "battery": dm.get("batteryLevel"),
            "voltage": dm.get("voltage"),
            "chan_util": dm.get("channelUtilization"),
            "air_tx": dm.get("airUtilTx"),
            "uptime": dm.get("uptimeSeconds"),
            "snr": n.get("snr"),
            "hops": n.get("hopsAway"),
            "last": last,
            "lat": lat,
            "lon": lon,
            "alt": pos.get("altitude"),
            "temp": env.get("temperature"),
            "hum": env.get("relativeHumidity"),
            "press": env.get("barometricPressure"),
        }
    if diri_id and (hasil.get(diri_id) or {}).get("hw_model"):
        gw_hw = hasil[diri_id]["hw_model"]

    jumlah_lora = sum(1 for r in hasil.values() if r["via"] == "lora")
    jumlah_mqtt = sum(1 for r in hasil.values() if r["via"] == "mqtt")
    gateway = {
        "node_id": diri_id,
        "uptime": (hasil.get(diri_id) or {}).get("uptime") if diri_id else None,
        "reboot_count": reboot_count,
        "nodedb_count": nodedb_count,
        "firmware": firmware,
        "role": gw_role,
        "hw_model": gw_hw,
        "jumlah_node": len(hasil),
        "jumlah_lora": jumlah_lora,
        "jumlah_mqtt": jumlah_mqtt,
        # Setelan radio gateway + lantai demodulasi yang dipakai meter sinyal.
        "preset": preset,
        "kustom": kustom,
        "spread_factor": sf,
        "bandwidth": bw,
        "lantai_snr": lantai,
    }
    cuplikan.ganti(hasil, gateway)
    return len(hasil)


class PengumpulMesh:
    """Custom collector: membangun metrik dari cuplikan saat di-scrape."""

    def __init__(self, cuplikan, offline_secs, basi_secs=0):
        self._cuplikan = cuplikan
        self._offline = offline_secs
        # Umur cuplikan yang dianggap basi. Scrape datang dari thread HTTP yang
        # TERPISAH dari loop pengumpul, jadi bila loop itu tersangkut atau mati,
        # penanda up di sini tetap turun dan alert MeshtasticExporterDown
        # berbunyi - tidak lagi "hidup tetapi buta" yang senyap.
        self._basi = basi_secs

    def collect(self):
        nodes, gateway, sekarang = self._cuplikan.baca()
        umur = max(0.0, time.time() - sekarang)
        if self._basi:
            EXPORTER_UP.set(0 if umur > self._basi else 1)
        umur_cuplikan = GaugeMetricFamily(
            "meshtastic_cuplikan_umur_seconds",
            "Umur data node terakhir yang dikumpulkan (detik); membesar berarti loop pengumpul tersangkut")
        umur_cuplikan.add_metric([], umur)

        favorite = GaugeMetricFamily(
            "meshtastic_node_favorite",
            "1 bila node ditandai Favorite (lebih terlindung dari penggusuran database)",
            labels=["node_id"])
        gw_uptime = GaugeMetricFamily(
            "meshtastic_gateway_uptime_seconds", "Uptime node gateway (detik)")
        gw_reboot = GaugeMetricFamily(
            "meshtastic_gateway_reboot_count", "Jumlah reboot yang dicatat node gateway")
        gw_nodedb = GaugeMetricFamily(
            "meshtastic_gateway_nodedb_count", "Jumlah entri di database node gateway")
        gw_lora = GaugeMetricFamily(
            "meshtastic_gateway_nodes_lora", "Jumlah node yang terdengar langsung lewat LoRa")
        gw_mqtt = GaugeMetricFamily(
            "meshtastic_gateway_nodes_mqtt", "Jumlah node yang masuk lewat MQTT")
        gw_info = GaugeMetricFamily(
            "meshtastic_gateway_info", "Metadata node gateway (selalu 1)",
            labels=["node_id", "firmware", "role", "hw_model"])

        info = GaugeMetricFamily(
            "meshtastic_node_info", "Metadata node Meshtastic (selalu 1)",
            labels=["node_id", "long_name", "short_name", "hw_model", "role", "via"])
        direct = GaugeMetricFamily(
            "meshtastic_node_direct",
            "1 bila node terdengar LANGSUNG lewat radio LoRa, 0 bila lewat MQTT/node gateway",
            labels=["node_id"])
        online = GaugeMetricFamily(
            "meshtastic_node_online", "1 bila node terdengar dalam ambang waktu",
            labels=["node_id"])
        heard = GaugeMetricFamily(
            "meshtastic_node_last_heard_seconds", "Detik sejak terakhir terdengar",
            labels=["node_id"])
        # Versi epoch dari metrik di atas. Sebagian dasbor & alert komunitas
        # memakai bentuk timestamp, bukan umur, jadi keduanya disediakan.
        heard_ts = GaugeMetricFamily(
            "meshtastic_node_last_heard_timestamp_seconds",
            "Waktu paket terakhir node ini terdengar (epoch detik)",
            labels=["node_id"])
        batt = GaugeMetricFamily(
            "meshtastic_device_battery_level_percent", "Level baterai (%)",
            labels=["node_id"])
        volt = GaugeMetricFamily(
            "meshtastic_device_voltage_volts", "Tegangan (V)", labels=["node_id"])
        chutil = GaugeMetricFamily(
            "meshtastic_device_channel_utilization_percent", "Utilisasi kanal (%)",
            labels=["node_id"])
        airtx = GaugeMetricFamily(
            "meshtastic_device_air_tx_utilization_percent", "Airtime TX (%)",
            labels=["node_id"])
        uptime = GaugeMetricFamily(
            "meshtastic_device_uptime_seconds", "Uptime perangkat (detik)",
            labels=["node_id"])
        snr = GaugeMetricFamily(
            "meshtastic_node_snr_db", "SNR terakhir (dB)", labels=["node_id"])
        hops = GaugeMetricFamily(
            "meshtastic_node_hops_away", "Jumlah hop dari node gateway",
            labels=["node_id"])
        lat = GaugeMetricFamily("meshtastic_node_latitude", "Garis lintang", labels=["node_id"])
        lon = GaugeMetricFamily("meshtastic_node_longitude", "Garis bujur", labels=["node_id"])
        alt = GaugeMetricFamily("meshtastic_node_altitude_meters", "Ketinggian (m)", labels=["node_id"])
        temp = GaugeMetricFamily("meshtastic_environment_temperature_celsius", "Suhu (C)", labels=["node_id"])
        hum = GaugeMetricFamily("meshtastic_environment_humidity_percent", "Kelembapan (%)", labels=["node_id"])
        press = GaugeMetricFamily("meshtastic_environment_pressure_hpa", "Tekanan (hPa)", labels=["node_id"])
        paket = GaugeMetricFamily(
            "meshtastic_packets_received_total", "Jumlah paket diterima per node & tipe",
            labels=["node_id", "portnum"])

        for node_id, r in nodes.items():
            info.add_metric(
                [node_id, r["long_name"], r["short_name"], r["hw_model"], r["role"],
                 r.get("via", "")], 1)
            direct.add_metric([node_id], 1 if r.get("via") == "lora" else 0)
            favorite.add_metric([node_id], 1 if r.get("favorite") else 0)

            last = r.get("last")
            if last:
                usia = max(0.0, sekarang - last)
                heard.add_metric([node_id], usia)
                heard_ts.add_metric([node_id], float(last))
                online.add_metric([node_id], 1 if usia <= self._offline else 0)
            else:
                online.add_metric([node_id], 0)

            def tambah(famili, kunci):
                nilai = r.get(kunci)
                if nilai is not None:
                    famili.add_metric([node_id], float(nilai))

            tambah(batt, "battery")
            tambah(volt, "voltage")
            tambah(chutil, "chan_util")
            tambah(airtx, "air_tx")
            tambah(uptime, "uptime")
            tambah(snr, "snr")
            tambah(hops, "hops")
            tambah(lat, "lat")
            tambah(lon, "lon")
            tambah(alt, "alt")
            tambah(temp, "temp")
            tambah(hum, "hum")
            tambah(press, "press")

        for (node_id, portnum), jumlah in ambil_hitungan().items():
            paket.add_metric([node_id, portnum], jumlah)

        # --- kesehatan node gateway ---
        for famili, kunci in ((gw_uptime, "uptime"), (gw_reboot, "reboot_count"),
                              (gw_nodedb, "nodedb_count"), (gw_lora, "jumlah_lora"),
                              (gw_mqtt, "jumlah_mqtt")):
            nilai = gateway.get(kunci)
            if isinstance(nilai, (int, float)):
                famili.add_metric([], nilai)
        if gateway.get("node_id"):
            gw_info.add_metric([gateway["node_id"], gateway.get("firmware") or "",
                                gateway.get("role") or "", gateway.get("hw_model") or ""], 1)

        for famili in (info, online, heard, heard_ts, batt, volt, chutil, airtx, uptime,
                       snr, hops, lat, lon, alt, temp, hum, press, paket, direct,
                       favorite, gw_uptime, gw_reboot, gw_nodedb, gw_lora, gw_mqtt,
                       gw_info, umur_cuplikan):
            yield famili


EXPORTER_UP = Gauge(
    "meshtastic_exporter_up", "1 bila exporter berhasil terhubung ke node")


# Gambar halaman: logo di samping judul dan ikon pada tab peramban.
#
# Gambar TIDAK disisipkan ke dalam HTML (mis. sebagai base64) justru karena
# halaman ini menyegar sendiri tiap 5 detik - kalau disisipkan, setiap
# penyegaran mengunduh ulang seluruh gambar dan halaman membengkak. Jadi
# gambar dilayani sebagai berkas terpisah di URL tetap, dengan header cache,
# dan hanya dibaca sekali saat start.
#
# Berkasnya dihasilkan oleh siapkan-logo.ps1 (memangkas pinggiran transparan,
# lalu mengecilkan logo asli 2048x2048 / 3,1 MB menjadi dua berkas kecil).
GAMBAR = {
    "/logo.png": ("meshnodeid-256.png", "image/png"),
    "/favicon.png": ("meshnodeid-64.png", "image/png"),
}

# Leaflet 1.9.4 (MIT) disajikan sendiri, bukan dari CDN. Alasannya praktis:
# exporter ini sering dibuka dari jaringan lokal yang tidak punya akses
# internet, dan peta yang gagal dimuat karena CDN tidak terjangkau membuat
# seluruh tab Tracking Node tidak berguna.
LEAFLET_TIPE = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
}


def _tipe_berkas(nama):
    return LEAFLET_TIPE.get(os.path.splitext(nama)[1].lower(),
                            "application/octet-stream")


def baca_gambar():
    """Baca berkas gambar dari folder skrip ini sekali saat start.

    Berkas yang tidak ada hanya dilewati dengan peringatan: halaman tetap
    hidup tanpa logo, bukan menampilkan ikon gambar rusak.
    """
    hasil = {}
    folder = os.path.dirname(os.path.abspath(__file__))
    for url, (nama, tipe) in GAMBAR.items():
        jalur = os.path.join(folder, nama)
        try:
            with open(jalur, "rb") as f:
                hasil[url] = (f.read(), tipe)
        except OSError:
            LOG.warning("gambar %s tidak ada (%s) - halaman jalan tanpa logo",
                        nama, jalur)
    hasil.update(baca_leaflet(os.path.join(folder, "leaflet")))
    return hasil


def baca_leaflet(folder):
    """Baca folder leaflet/ (js, css, images) untuk disajikan di /leaflet/...

    Disajikan lewat dict lampiran yang sama dengan logo, jadi cache-nya
    tidak perlu diulang: handler sudah memasang header Cache-Control untuk
    isi dict itu.
    """
    hasil = {}
    if not os.path.isdir(folder):
        LOG.warning("folder leaflet tidak ada (%s) - tab Tracking Node "
                    "akan tampil tanpa peta", folder)
        return hasil
    for akar, _, berkasnya in os.walk(folder):
        for nama in berkasnya:
            penuh = os.path.join(akar, nama)
            relatif = os.path.relpath(penuh, folder).replace(os.sep, "/")
            try:
                with open(penuh, "rb") as f:
                    hasil["/leaflet/" + relatif] = (f.read(), _tipe_berkas(nama))
            except OSError as exc:
                LOG.warning("berkas leaflet %s tidak terbaca: %s", penuh, exc)
    return hasil


# ------------------------------------------------------------
# Tampilan web: HTML & JSON dari data node + umpan paket
# ------------------------------------------------------------

def _fmt(nilai, satuan="", digit=1):
    """Format angka dengan pembulatan.

    Sengaja memakai str.format, BUKAN %-formatting: satuan di sini sering
    berupa "%" (persen), dan lewat %-formatting karakter itu dianggap awal
    penentu format sehingga formatting kedua gagal dengan ValueError.
    Akibatnya dulu fungsi ini jatuh ke cabang cadangan dan mengembalikan nilai
    MENTAH tanpa dibulatkan (mis. "4.939833%" alih-alih "4.9%").
    """
    if nilai is None or nilai == "":
        return "-"
    try:
        # Kurung kurawal di satuan diamankan supaya tidak dibaca sebagai medan.
        aman = satuan.replace("{", "{{").replace("}", "}}")
        return ("{:." + str(int(digit)) + "f}" + aman).format(float(nilai))
    except (TypeError, ValueError):
        return "%s%s" % (nilai, satuan)


def _durasi(detik):
    if detik is None:
        return "-"
    detik = int(max(0, detik))
    hari, sisa = divmod(detik, 86400)
    jam, sisa = divmod(sisa, 3600)
    menit, detik = divmod(sisa, 60)
    if hari:
        return "%dh %dj %dm" % (hari, jam, menit)
    if jam:
        return "%dj %dm" % (jam, menit)
    if menit:
        return "%dm %ds" % (menit, detik)
    return "%ds" % detik


# ------------------------------------------------------------
# Ambang operasional
# ------------------------------------------------------------
# Angka-angka ini bukan karangan sendiri, melainkan pedoman operasional yang
# dipakai juga oleh dasbor komunitas Meshtastic:
#   - utilisasi kanal di atas 25% mulai menahan pengiriman; di atas 40%
#     pembaruan GPS dikurangi; di atas 50% kanal dianggap padat.
#   - airtime TX di atas 8% berarti node terlalu banyak memancar sehingga
#     membebani kanal bersama.
#   - hop: 0 = terdengar langsung, makin besar makin jauh dari gateway.
# Tiap tangga berisi (batas atas, kelas warna, label) dan diakhiri satu entri
# berbatas None yang berarti "di atas semua batas di atasnya".
TANGGA_CHUTIL = ((25, "a-aman", "sehat"), (40, "a-sedang", "sedang"),
                 (50, "a-tinggi", "tinggi"), (None, "a-padat", "padat"))
TANGGA_AIRTX = ((5, "a-aman", "bagus"), (8, "a-sedang", "wajar"),
                (None, "a-padat", "kelebihan"))
TANGGA_HOP = ((1, "hop-0", "langsung"), (3, "hop-1", "dekat"),
              (5, "hop-2", "jauh"), (None, "hop-3", "sangat jauh"))


def _tingkat(nilai, tangga):
    """Pilih (kelas warna, label) menurut tangga ambang; None bila tak ada."""
    try:
        angka = float(nilai)
    except (TypeError, ValueError):
        return None
    for batas, kelas, label in tangga:
        if batas is None or angka < batas:
            return kelas, label
    return tangga[-1][1:]


def _sel_baterai(nilai):
    """Kolom baterai.

    Firmware Meshtastic mengirim batteryLevel dalam skala 0-101 dan nilai 101
    berarti **tersambung listrik/USB**, bukan "baterai 101%" (lihat
    meshtastic/firmware#4158: "a percentage from 0-101 with 101 meaning
    powered"). Menampilkan "101%" karena itu menyesatkan, jadi di halaman
    ditulis "charge". Nilai mentahnya TIDAK diubah di /metrics dan /data.json,
    supaya alert dan skrip lama tetap membaca angka aslinya.
    """
    if nilai is None or nilai == "":
        return "-"
    try:
        angka = float(nilai)
    except (TypeError, ValueError):
        return _fmt(nilai, "%", 0)
    if angka > 100:
        return ("<span class='charge' title='Tersambung listrik/USB - firmware "
                "mengirim kode %d untuk itu, bukan persentase'>charge</span>"
                % int(angka))
    return _fmt(angka, "%", 0)


def _sel_tegangan(nilai):
    """Kolom tegangan.

    Perangkat bertenaga listrik tanpa penginderaan baterai melaporkan tegangan
    di lantai derau ADC (biasanya -0.001 V). Dibulatkan dua angka menjadi
    "-0.00 V" yang terbaca seperti kerusakan, jadi nilai yang membulat ke nol
    ditulis "-" dengan keterangan. Tegangan sungguhan (mis. 4.14 V) apa adanya.
    """
    if nilai is None or nilai == "":
        return "-"
    try:
        angka = float(nilai)
    except (TypeError, ValueError):
        return _fmt(nilai, " V", 2)
    if abs(angka) < 0.05:
        return ("<span class='dim' title='Tidak ada pengukuran baterai - "
                "perangkat bertenaga listrik'>&ndash;</span>")
    return _fmt(angka, " V", 2)


def _sel_ambang(nilai, satuan, digit, tangga):
    """Isi sel: angkanya diberi warna + keterangan tingkatannya."""
    teks = _fmt(nilai, satuan, digit)
    tingkat = _tingkat(nilai, tangga)
    if not tingkat:
        return teks
    kelas, label = tingkat
    return "<span class='%s' title='%s'>%s</span>" % (kelas, label, teks)


def _sel_hop(nilai):
    """Kolom hop: angka diberi warna, jaraknya ditulis kecil di sampingnya."""
    teks = _fmt(nilai, "", 0)
    tingkat = _tingkat(nilai, TANGGA_HOP)
    if not tingkat:
        return teks
    kelas, label = tingkat
    return ("<span class='%s' title='%s'>%s</span> <span class='dim'>%s</span>"
            % (kelas, label, teks, label))


# ------------------------------------------------------------
# Meter sinyal (mengikuti meter sinyal resmi Meshtastic)
# ------------------------------------------------------------
# Aplikasi resmi Meshtastic TIDAK menilai sinyal dari kuatnya pancaran, tetapi
# dari "keterbacaan": seberapa jauh SNR sebuah paket berada DI ATAS LANTAI
# DEMODULASI preset radio yang sedang dipakai (dokumentasi: "How the Meshtastic
# Signal Meter Works", Apple & Android). Karena radio LoRa bisa mendengar di
# bawah lantai derau, SNR negatif itu normal - yang penting jaraknya ke lantai.
#
# Ambangnya diambil apa adanya dari tabel lintas-platform yang dipakai aplikasi
# Android & Apple (Meshtastic-Android: ChannelOption.kt; Meshtastic-Apple:
# ModemPresetSnrLimitTests.swift). Catatan penting dari sana: lantai LONG_SLOW
# adalah -20 dB (SF12), bukan -7.5 dB - nilai itu pernah salah di kedua aplikasi
# (issue #2041/#5446) dan berakibat tautan LongSlow yang sehat dinilai buruk.
#
# Untuk setelan CUSTOM (use_preset mati) tidak ada nama preset yang bisa
# ditabelkan; lantai ditaksir dari spread factor yang benar-benar dilaporkan
# gateway, dengan tambahan +5 dB bila bandwidth 500 kHz (karena lantai derau
# naik seiring lebar pita). Angka taksiran itu ditandai "kustom" di halaman
# supaya tidak dibaca sebagai angka yang pasti.
LANTAI_SNR_PRESET = {
    "SHORT_TURBO": -7.5, "SHORT_FAST": -7.5, "SHORT_SLOW": -10.0,
    "MEDIUM_FAST": -12.5, "MEDIUM_SLOW": -15.0,
    "LONG_TURBO": -12.5, "LONG_FAST": -17.5, "LONG_MODERATE": -17.5,
    "LONG_SLOW": -20.0, "VERY_LONG_SLOW": -20.0,
}
# Urutan enum LoRaConfig.ModemPreset di protobuf Meshtastic.
PRESET_NOMOR = {0: "LONG_FAST", 1: "LONG_SLOW", 2: "VERY_LONG_SLOW",
                3: "MEDIUM_SLOW", 4: "MEDIUM_FAST", 5: "SHORT_SLOW",
                6: "SHORT_FAST", 7: "LONG_MODERATE", 8: "SHORT_TURBO",
                9: "LONG_TURBO"}
BAWAAN_LANTAI_SNR = -17.5  # LONG_FAST, preset bawaan pabrik Meshtastic

# Tingkat mutu -> (kelas warna, kata di halaman, keterangan ambang).
SINYAL_TINGKAT = {
    3: ("m-baik", "Baik", "SNR di atas lantai demodulasi"),
    2: ("m-cukup", "Cukup", "sampai 5.5 dB di bawah lantai"),
    1: ("m-buruk", "Buruk", "sampai 7.5 dB di bawah lantai"),
    0: ("m-nihil", "Nihil", "lebih dalam dari 7.5 dB di bawah lantai"),
}


def nama_preset(nilai):
    """Nama preset dari enum mentah (int) maupun teks."""
    if nilai is None or nilai == "":
        return ""
    if isinstance(nilai, bool):
        return ""
    if isinstance(nilai, int):
        return PRESET_NOMOR.get(nilai, "PRESET_%d" % nilai)
    return str(nilai).strip().upper()


def lantai_snr(preset=None, sf=None, bw=None):
    """Lantai demodulasi SNR (dB) untuk preset, atau taksiran dari SF/BW."""
    nama = nama_preset(preset)
    if nama in LANTAI_SNR_PRESET:
        return LANTAI_SNR_PRESET[nama]
    try:
        angka_sf = int(sf)
    except (TypeError, ValueError):
        return BAWAAN_LANTAI_SNR
    if not 5 <= angka_sf <= 12:
        return BAWAAN_LANTAI_SNR
    # Taksiran untuk setelan kustom: -7.5 dB di SF7 dan turun 2.5 dB tiap
    # kenaikan spread factor (kecenderungan yang sama dengan tabel preset di
    # atas), lalu +5 dB bila lebar pitanya 500 kHz.
    lantai = -7.5 - 2.5 * (angka_sf - 7)
    try:
        if float(bw) >= 500:
            lantai += 5.0
    except (TypeError, ValueError):
        pass
    return lantai


def mutu_sinyal(snr, lantai=BAWAAN_LANTAI_SNR):
    """Tingkat mutu sinyal 0-3 dari SNR, mengikuti aturan aplikasi resmi.

        margin >  0 dB           -> 3 batang, Baik
        margin = 0 .. -5.5 dB    -> 2 batang, Cukup
        margin = -5.5 .. -7.5 dB -> 1 batang, Buruk
        margin < -7.5 dB         -> 0 batang, Nihil

    Kembalikan None bila SNR-nya tidak ada (bukan dianggap buruk).
    """
    if snr is None or snr == "":
        return None
    try:
        margin = float(snr) - float(lantai)
    except (TypeError, ValueError):
        return None
    if margin > 0:
        return 3
    if margin > -5.5:
        return 2
    if margin >= -7.5:
        return 1
    return 0


def _meter_sinyal(tingkat, kelas, teks, judul="", ekor=""):
    """Tiga batang naik + kata mutunya + angka pendamping, seperti di aplikasi.

    Batang yang menyala memakai currentColor, jadi warnanya cukup diatur sekali
    lewat kelas .m-* di induknya - tidak ada warna yang perlu disalin ke sini.

    `ekor` (di halaman: angka SNR) ikut masuk KE DALAM pembungkus .meter supaya
    jaraknya diatur oleh gap yang sama; dulu angka itu ditempel di luar sehingga
    hasilnya terbaca "Baik6.2 dB" yang rapat dan sulit dipisah mata.
    """
    batang = "".join("<i%s></i>" % (" class='nyala'" if i < tingkat else "")
                     for i in range(3))
    tambahan = ("<span class='db'>%s</span>" % ekor) if ekor else ""
    return ("<span class='meter %s' title=\"%s\"><span class='batang'>%s</span>"
            "<span class='mutu'>%s</span>%s</span>"
            % (kelas, judul, batang, teks, tambahan))


def _sel_sinyal(snr, via, lantai=BAWAAN_LANTAI_SNR):
    """Sel "Sinyal (SNR)": meter + kata mutu + angka SNR apa adanya."""
    if (via or "").lower() == "mqtt":
        # Node jalur MQTT tidak didengar radio gateway sama sekali. SNR yang
        # tersimpan untuknya datang dari radio ORANG LAIN di internet, jadi
        # menggambarnya sebagai meter sinyal kita akan menyesatkan.
        return ("<span class='meter m-internet' title='Tidak didengar radio "
                "gateway Anda - paket terakhir datang lewat internet (MQTT), "
                "jadi tidak ada ukuran keterbacaan dari tempat Anda'>"
                "<span class='mutu'>&ndash;</span>"
                "<span class='db'>lewat internet</span></span>")
    tingkat = mutu_sinyal(snr, lantai)
    if tingkat is None:
        return "-"
    kelas, kata, aturan = SINYAL_TINGKAT[tingkat]
    judul = "%s (%s). SNR %s vs lantai preset %+.1f dB" % (kata, aturan, snr, float(lantai))
    return _meter_sinyal(tingkat, kelas, kata, judul, _fmt(snr, " dB", 1))


def node_dengan_status(cuplikan, offline):
    """Peta {node_id: {...}} dengan node_id dan status online ikut di dalam.

    cuplikan.baca() mengembalikan peta mentah yang kuncinya adalah node_id tapi
    isninya sendiri tidak memuat node_id maupun penanda online; data_json()
    menambahkannya saat serialize. Lacakan butuh keduanya juga: /lacak
    menampilkan status online, dan snapshot yang direkam harus sama dengan
    yang terlihat di /data.json. Penambahan itu karena itu dikumpulkan di
    sini, lalu dipakai data_json(), routes /lacak, dan perekaman histori -
    bukan ditulis ulang di tiap tempat.
    """
    nodes, _gateway, sekarang = cuplikan.baca()
    hasil = {}
    for node_id, r in nodes.items():
        item = dict(r)
        item["node_id"] = node_id
        item["online"] = _online(r, sekarang, offline)
        hasil[node_id] = item
    return hasil


def data_json(cuplikan, offline, host, port):
    gateway = cuplikan.baca()[1]
    sekarang = cuplikan.baca()[2]
    lantai = gateway.get("lantai_snr") or BAWAAN_LANTAI_SNR
    daftar = []
    for node_id, item in sorted(node_dengan_status(cuplikan, offline).items()):
        last = item.get("last")
        item["last_heard_seconds"] = (sekarang - last) if last else None
        # Tingkat mutu sinyal 0-3 (None bila node bukan jalur radio gateway):
        # angkanya bisa dipakai dasbor/alert tanpa menghitung ulang sendiri.
        item["mutu_sinyal"] = (None if (item.get("via") or "").lower() == "mqtt"
                               else mutu_sinyal(item.get("snr"), lantai))
        daftar.append(item)
    return {
        "gateway": {"host": host, "port": port},
        "kesehatan_gateway": gateway,
        "waktu": sekarang,
        # Umur data: 0 berarti baru saja dibaca. Angka yang terus membesar
        # menandakan loop pengumpul tersangkut walau halamannya tetap hidup.
        "umur_data_seconds": max(0.0, time.time() - sekarang),
        "jumlah_node": len(daftar),
        "node": daftar,
        "paket_terakhir": list(reversed([dict(p, waktu=time.strftime(
            "%Y-%m-%d %H:%M:%S", time.localtime(p["waktu"]))) for p in ambil_umpan_paket()])),
    }


def _online(r, sekarang, offline):
    """True bila node terdengar dalam ambang waktu.

    Dipakai DUA tempat: pewarnaan di _baris_node() dan pengurutan tabel. Dulu
    syaratnya ditulis ulang di tiap tempat sehingga mudah berbeda diam-diam.
    """
    last = r.get("last")
    return bool(last and (sekarang - last) <= offline)


def _baris_node(node_id, r, offline, sekarang, tanda="", lantai=BAWAAN_LANTAI_SNR):
    """Satu <tr> tabel node. Dipakai bersama oleh semua tabel.

    `lantai` adalah lantai demodulasi SNR preset gateway - dibawa lewat argumen
    (bukan dibaca dari global) supaya halaman dan uji selalu memakai angka yang
    sama dengan yang tertulis di legenda.
    """
    last = r.get("last")
    usia = (sekarang - last) if last else None
    online = _online(r, sekarang, offline)
    lencana = ("<span class='on'>ONLINE</span>" if online
               else "<span class='off'>OFFLINE</span>")
    # Tanda bintang untuk Favorite: ini yang melindungi node dari penggusuran
    # saat NodeDB penuh.
    nama = r["long_name"] or "(tanpa nama)"
    if r.get("favorite"):
        nama = "<span class='favorit'>&#9733;</span> " + nama
    # Node jalur MQTT yang masih menyimpan SNR berarti gateway pernah
    # mendengarnya lewat radio - jadi kemungkinan besar itu node lokal juga.
    catatan = (" <span class='tag'>%s</span>" % tanda) if tanda else ""
    if r.get("via") == "mqtt" and r.get("snr") is not None:
        catatan += " <span class='tag'>pernah lewat radio</span>"
    # Lencana jalur: lebih cepat dibaca daripada teks polos, dan warnanya
    # sejalan dengan kotak pembungkus tabelnya (hijau = radio, abu = internet).
    via = (r.get("via") or "").lower()
    kelas_via = {"diri": "via-diri", "lora": "via-lora"}.get(via, "via-mqtt")
    # Kelas .num membuat kolom angka rata kanan dan TIDAK terpotong dua baris
    # (dulu "6.5 dB" pecah jadi "6.5" / "dB" sehingga baris jadi tinggi).
    # Baris sekunder di bawah nama memuat hal-hal yang jarang dibutuhkan
    # sekilas (nama pendek, peran, jenis perangkat). Dulu ketiganya masing-masing
    # memakai kolom sendiri sehingga tabel lebih lebar dari layar; digabung di
    # sini, jumlah kolom turun dari 14 ke 12 tanpa ada data yang hilang.
    ciri = " &middot; ".join(x for x in (r["short_name"], r["role"], r["hw_model"]) if x)
    # Tegangan ikut ke bawah angka baterai: keduanya selalu dibaca bersamaan,
    # dan sebagian besar node tidak melaporkannya. Hanya tegangan SUNGGUHAN
    # yang ditulis; derau ADC (-0.001 V) dilewati, supaya selnya tidak berisi
    # tanda "-" bertumpuk yang cuma menambah ramai.
    daya = _sel_baterai(r["battery"])
    teg = r.get("voltage")
    try:
        if teg is not None and abs(float(teg)) >= 0.05:
            daya += "<br><span class='dim'>%s</span>" % _sel_tegangan(teg)
    except (TypeError, ValueError):
        pass
    # Uptime perangkat melengkapi sel daya: sama-sama isi deviceMetrics, dan
    # praktis untuk melihat node yang baru saja reboot (mis. gateway yang
    # reboot_count-nya naik terus).
    if r.get("uptime"):
        daya += "<br><span class='dim'>up %s</span>" % _durasi(r["uptime"])
    # Sel lingkungan: telemetri sensor ditulis HANYA bila perangkat memang
    # mengirimkannya. Kebanyakan node di jaringan kita tidak punya pengindera
    # suhu/kelembapan/tekanan, dan kolom berisi tanda "-" bertumpuk cuma
    # menambah ramai tanpa memberi keterangan apa pun.
    lingkungan = _fmt(r["temp"], " \u00b0C", 1)
    if r.get("hum") is not None:
        lingkungan += "<br><span class='dim'>%s</span>" % _fmt(r["hum"], " % RH", 1)
    if r.get("press") is not None:
        lingkungan += "<br><span class='dim'>%s</span>" % _fmt(r["press"], " hPa", 0)
    # Ketinggian menempel pada sel posisi: sama-sama dari posisi perangkat.
    posisi = _fmt(r["lat"], "", 5) + " / " + _fmt(r["lon"], "", 5)
    if r.get("alt") is not None:
        posisi += "<br><span class='dim'>%s</span>" % _fmt(r["alt"], " m", 0)
    # Kolom Aksi: tombol untuk node YANG BUKAN gateway sendiri. Menghapus node
    # gateway dari database-nya sendiri tidak masuk akal, jadi baris itu tidak
    # diberi tombol. Pesan konfirmasi memakai nama node supaya pengguna tahu
    # benar yang mana yang akan disentuh.
    if via == "diri":
        aksi = "<td class='aksi'><span class='dim'>-</span></td>"
    elif r.get("favorite"):
        aksi = (
            "<td class='aksi'>"
            "<button class='aksi' data-aksi='hapus' data-node='%s'>hapus</button>"
            "<button class='aksi' data-aksi='unfavorit' data-node='%s'>unfavorit</button>"
            "<button class='aksi' data-aksi='trace' data-node='%s'>trace</button>"
            "</td>" % (node_id, node_id, node_id))
    else:
        aksi = (
            "<td class='aksi'>"
            "<button class='aksi' data-aksi='hapus' data-node='%s'>hapus</button>"
            "<button class='aksi' data-aksi='favorit' data-node='%s'>favorit</button>"
            "<button class='aksi' data-aksi='trace' data-node='%s'>trace</button>"
            "</td>" % (node_id, node_id, node_id))
    return (
        "<tr>"
        "<td class='mono'>%s</td>"
        "<td class='nama'><b>%s</b>%s<br><span class='dim'>%s</span></td>"
        "<td><span class='via %s'>%s</span></td>"
        "<td>%s</td>"
        "<td class='num'>%s</td>"
        "<td class='num'>%s</td>"
        "<td class='num'>%s</td>"
        "<td class='num'>%s</td>"
        "<td class='sinyal'>%s</td>"
        "<td class='num'>%s</td>"
        "<td class='num'>%s</td>"
        "<td class='mono'>%s</td>"
        "%s"
        "</tr>" % (
            node_id,
            nama, catatan, ciri,
            kelas_via, (r.get("via") or "").upper(),
            lencana,
            _durasi(usia),
            daya,
            _sel_ambang(r["chan_util"], "%", 1, TANGGA_CHUTIL),
            _sel_ambang(r["air_tx"], "%", 1, TANGGA_AIRTX),
            _sel_sinyal(r["snr"], r.get("via"), lantai),
            _sel_hop(r["hops"]),
            lingkungan,
            posisi,
            aksi,
        ))


# ------------------------------------------------------------------
# Posisi gulir yang diingat saat halaman menyegar sendiri
# ------------------------------------------------------------------
# Halaman ini memuat ulang dirinya tiap 5 detik lewat
# <meta http-equiv="refresh" content="5">, dan muat ulang SELALU memulai dari
# paling atas. Membaca tabel MQTT yang panjang jadi menyiksa: baru sampai
# bawah, sudah dilempar ke atas lagi.
#
# Perbaikan ini sengaja TIDAK bergantung pada kejadian 'beforeunload' - tidak
# semua peramban menjalankannya untuk penyegaran meta, dan yang paling penting:
# kalau hanya mengandalkan unload, gulir orang yang sedang berhenti (tidak
# digulir lagi) bisa tidak tercatat. Sebagai gantinya posisi dicatat SETIAP kali
# orang menggulir, dengan jeda 120 ms supaya tidak menulis ke penyimpanan terus
# menerus, lalu dipasang kembali sesudah halaman selesai dimuat.
#
# Kuncinya per alamat (location.pathname): gulir di halaman Monitoring tidak
# boleh terbawa ke halaman /peta atau /lacak.
SKRIP_LAYAR = """<script>
(function(){
  var KUNCI='meshid-layar-1:'+(location.pathname||'/');
  var jeda=null;
  // Pemulihan bawaan peramban dimatikan: halaman ini memulihkan sendiri, dan
  // dua-duanya jalan bersamaan bisa saling tarik-menarik.
  try{ if('scrollRestoration' in history){ history.scrollRestoration='manual'; } }catch(e){}
  function baca(){
    try{ return JSON.parse(sessionStorage.getItem(KUNCI)||'null'); }catch(e){ return null; }
  }
  function tulis(o){ try{ sessionStorage.setItem(KUNCI, JSON.stringify(o)); }catch(e){} }
  function kotakGulir(){ return document.querySelectorAll('.gulir'); }
  function keadaanSekarang(){
    var kotak=kotakGulir(), g=[];
    for(var i=0;i<kotak.length;i++){ g.push([kotak[i].scrollTop, kotak[i].scrollLeft]); }
    return {y: window.scrollY || window.pageYOffset || 0, g: g};
  }
  function simpan(){
    if(jeda){ return; }
    jeda=setTimeout(function(){ jeda=null; tulis(keadaanSekarang()); }, 120);
  }
  function pulihkan(){
    var s=baca();
    if(!s){ return; }
    var kotak=kotakGulir();
    if(s.g){
      for(var i=0;i<kotak.length && i<s.g.length;i++){
        kotak[i].scrollTop=s.g[i][0];
        kotak[i].scrollLeft=s.g[i][1];
      }
    }
    if(s.y){ window.scrollTo(0, s.y); }
  }
  // Panggil dua kali: begitu DOM siap, lalu lagi setelah semua gambar/gaya
  // selesai dimuat - tata letak masih bergeser di antara kedua waktu itu,
  // dan tinggi tabel yang belum final membuat tujuannya meleset.
  function pulihkanMenyusul(){ pulihkan(); setTimeout(pulihkan, 80); }
  // capture:true supaya kejadian gulir dari kotak .gulir (yang tidak naik ke
  // window) ikut tertangkap oleh satu pendengar saja.
  window.addEventListener('scroll', simpan, true);
  window.addEventListener('beforeunload', function(){ tulis(keadaanSekarang()); });
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded', pulihkanMenyusul);
    window.addEventListener('load', pulihkanMenyusul);
  } else {
    pulihkanMenyusul();
  }
})();
</script>
"""


def halaman_html(cuplikan, offline, host, port, exporter_up, logo=True):
    nodes, gateway, sekarang = cuplikan.baca()

    # Lantai demodulasi SNR: setelan radio gateway yang sedang dipakai. Meter
    # sinyal di tiap baris node menilai SNR terhadap angka ini, jadi angkanya
    # ditulis terbuka di legenda - pembaca halaman harus bisa memeriksa sendiri
    # kenapa sebuah node disebut "Baik" atau "Nihil".
    lantai = gateway.get("lantai_snr")
    if lantai is None:
        lantai = BAWAAN_LANTAI_SNR
    try:
        lantai = float(lantai)
    except (TypeError, ValueError):
        lantai = BAWAAN_LANTAI_SNR
    preset_gw = gateway.get("preset") or "tidak terbaca"
    # Setelan radio yang tidak terbaca JANGAN disembunyikan: lantai bawaannya
    # tetap dipakai supaya halaman tidak kosong, tetapi pembaca harus tahu
    # bahwa angkanya asumsi, bukan hasil membaca perangkat.
    catatan_lantai = (" <span class='dim'>(diasumsikan, setelan radio gateway "
                      "belum terbaca)</span>") if not gateway.get("preset") else ""
    if gateway.get("kustom"):
        preset_gw = "kustom (SF %s / %s kHz)" % (
            gateway.get("spread_factor") or "?", gateway.get("bandwidth") or "?")
    # Contoh meter untuk legenda: keempat tingkat, berurutan dari terbaik.
    contoh_meter = " &middot; ".join(
        "%s <span class='dim'>%s</span>"
        % (_meter_sinyal(t, SINYAL_TINGKAT[t][0], SINYAL_TINGKAT[t][1],
                         SINYAL_TINGKAT[t][2]), SINYAL_TINGKAT[t][2])
        for t in (3, 2, 1, 0))

    # Pisahkan berdasarkan BUKTI, bukan tebakan. Dua nilai yang dipakai:
    #   via  = jalur paket TERAKHIR yang dicatat gateway (diri/lora/mqtt)
    #   snr  = hasil pengukuran radio gateway SENDIRI terhadap node itu
    #
    # SNR hanya terisi bila gateway benar-benar menerima paket node itu lewat
    # udara. Jadi SNR yang ada + hop 0 = bukti gateway tersambung LANGSUNG ke
    # node itu. Tanpa SNR, kita tidak punya bukti apa pun soal koneksi langsung
    # - walau node itu bukan node MQTT.
    milik_diri, milik_lora, milik_mqtt, milik_ragu = [], [], [], []
    for node_id, r in sorted(nodes.items()):
        via = r.get("via")
        punya_snr = r.get("snr") is not None
        langsung = punya_snr and r.get("hops") in (None, 0)
        if via == "diri": 
            milik_diri.append((node_id, r))
        elif via == "mqtt":
            milik_mqtt.append((node_id, r))
        elif langsung:
            milik_lora.append((node_id, r))
        else:
            milik_ragu.append((node_id, r))

    # Urutan tiap tabel: node yang ONLINE lebih dulu (paling baru terdengar di
    # atas), baru yang OFFLINE di bawahnya. Node gateway tetap paling atas
    # karena ia memang tabelnya sendiri. Pemutus seri memakai node_id supaya
    # urutannya stabil, tidak melompat-lompat tiap halaman menyegar sendiri.
    def urut(daftar):
        return sorted(daftar, key=lambda nr: (
            not _online(nr[1], sekarang, offline),
            -(nr[1].get("last") or 0),
            nr[0]))

    def render(daftar, tanda=""):
        return "".join(_baris_node(n, r, offline, sekarang, tanda, lantai)
                       for n, r in daftar)

    baris_diri = render(milik_diri, "gateway")
    baris_lora = render(urut(milik_lora), "langsung ke gateway")
    baris_ragu = render(urut(milik_ragu), "belum ada bukti langsung")
    baris_mqtt = render(urut(milik_mqtt))
    if not baris_diri:
        baris_diri = "<tr><td colspan='13' class='dim'>-</td></tr>"
    if not baris_lora:
        baris_lora = ("<tr><td colspan='13' class='dim'>Belum ada node yang "
                      "terbukti tersambung langsung ke gateway.</td></tr>")
    if not baris_ragu:
        baris_ragu = "<tr><td colspan='13' class='dim'>-</td></tr>"
    if not baris_mqtt:
        baris_mqtt = ("<tr><td colspan='13' class='dim'>Tidak ada node dari MQTT "
                      "- downlink mungkin sedang mati. Bagus.</td></tr>")

    # Kepala tabel disusun SEKALI lalu dipakai ketiga tabel node. Dengan begitu
    # jumlah kolom di ketiga tabel tidak mungkin berbeda karena salah ketik,
    # dan kelas .num (rata kanan) dijamin sejajar dengan barisnya di
    # _baris_node().
    kepala_node = (
        "<tr><th>ID</th><th>Nama &amp; Perangkat</th><th>Via</th>"
        "<th>Status</th>"
        "<th class='num'>Terakhir</th><th class='num'>Baterai / Daya</th>"
        "<th class='num'>Kanal</th><th class='num'>Air TX</th><th class='sinyal'>Sinyal (SNR)</th>"
        "<th class='num'>Hop</th><th class='num'>Suhu / RH / hPa</th>"
        "<th>Lat / Lon / Alt</th><th>Aksi</th></tr>")

    umpan = ambil_umpan_paket()
    paket_baris = []
    for p in reversed(umpan):
        paket_baris.append(
            "<tr><td class='mono'>%s</td><td class='mono'>%s</td>"
            "<td>%s</td><td class='num'>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td></tr>" % (
                time.strftime("%H:%M:%S", time.localtime(p["waktu"])),
                p["dari"], p["portnum"],
                _fmt(p.get("snr"), " dB", 1),
                _fmt(p.get("rssi"), " dBm", 0),
                _fmt(p.get("hop"), "", 0),
            ))

    jumlah_online = sum(
        1 for r in nodes.values()
        if r.get("last") and (sekarang - r["last"]) <= offline)

    nodedb = gateway.get("nodedb_count")
    peringatan = ""
    if isinstance(nodedb, int) and nodedb >= AMBANG_DB_PENUH:
        peringatan = ("<div class='peringatan'>PERHATIAN: database node gateway hampir penuh "
                      "(%d entri). Node yang jarang terdengar bisa tergeser keluar - "
                      "tandai node RF Anda sebagai <b>Favorite</b> dan kurangi downlink MQTT."
                      "</div>" % nodedb)

    # Logo di samping judul dan ikon pada tab peramban. Keduanya hanya
    # disertakan bila berkasnya benar-benar ada, supaya pemasangan tanpa logo
    # tidak menampilkan ikon gambar rusak.
    ikon = ('<link rel="icon" type="image/png" href="/favicon.png">\n'
            '<link rel="apple-touch-icon" href="/logo.png">') if logo else ""
    gambar_kepala = ('<img class="logo" src="/logo.png" width="42" height="42"'
                     ' alt="Logo MeshNode ID">') if logo else ""

    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta http-equiv="refresh" content="5">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meshnode-ID Monitor (Mtl-Cbt Site)</title>
%(ikon)s
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{background:#0f1319;color:#e6edf3;font:13.5px/1.5 system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:18px 20px 44px;max-width:1750px}
h1{font-size:19px;margin:0 0 3px}
h2{font-size:14px;margin:26px 0 10px;border-bottom:1px solid #24303c;padding-bottom:7px;text-transform:uppercase;letter-spacing:.06em;color:#9fb0c3}
a{color:#58a6ff}
.dim{color:#8b98a8;font-size:12px}
.mono{font-family:ui-monospace,Consolas,monospace}
/* Kepala halaman: judul di kiri, keadaan sambungan di kanan. Titik warnanya
   memakai currentColor, jadi warnanya ikut kelas .hidup/.mati di bawah. */
.kepala{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;justify-content:space-between;border-bottom:1px solid #24303c;padding-bottom:12px}
/* Logo di samping judul; ukurannya dipatok di HTML (width/height) supaya tata
   letak tidak melompat saat gambar selesai dimuat. */
.merek{display:flex;align-items:center;gap:12px}
.logo{width:42px;height:42px;flex:0 0 auto;display:block}
.status{display:flex;align-items:center;gap:8px;background:#1a212b;border:1px solid #2a3340;border-radius:999px;padding:6px 14px;font-size:12.5px;white-space:nowrap}
.titik{width:9px;height:9px;border-radius:50%%;background:currentColor;flex:0 0 auto}
.kartu{display:grid;grid-template-columns:repeat(auto-fit,minmax(134px,1fr));gap:10px;margin:14px 0 4px}
.kotak{background:#1a212b;border:1px solid #2a3340;border-radius:10px;padding:10px 14px}
.kotak b{display:block;font-size:22px;line-height:1.25;font-variant-numeric:tabular-nums}
.kotak span{color:#8b98a8;font-size:11.5px}
/* Tiap tabel duduk di kotak yang bisa digulir SENDIRI. Sebelumnya tabel yang
   lebih lebar dari jendela menyeret seluruh halaman ke kanan, sehingga judul
   dan kotak ringkasan ikut hilang saat orang membaca kolom paling kanan. */
.gulir{overflow:auto;max-height:78vh;background:#1a212b;border:1px solid #232c38;border-radius:10px}
table{width:100%%;border-collapse:separate;border-spacing:0;font-size:12.5px}
td.mono{font-size:12px}
th,td{padding:6px 9px;text-align:left;border-bottom:1px solid #232c38;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
/* Nama kolom lengket: saat tabel MQTT yang panjang digulir, judulnya tetap
   terbaca tanpa perlu naik ke atas dulu. */
thead th{position:sticky;top:0;z-index:2;background:#202836;color:#9fb0c3;font-size:11px;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #2f3b4a}
tbody tr:nth-child(even){background:#1d252e}
tbody tr:hover{background:#26303c}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
td.nama{white-space:normal;min-width:150px;max-width:250px;overflow-wrap:anywhere}
.on{color:#3fb950;font-weight:600}.off{color:#f85149;font-weight:600}
.hidup{color:#3fb950}.mati{color:#f85149}
.peringatan{background:#3d1d1d;border:1px solid #f85149;color:#ffb3ad;padding:10px 14px;border-radius:8px;margin:12px 0}
.favorit{color:#e3b341}
.tag{background:#21323f;color:#79c0ff;border-radius:4px;padding:1px 6px;font-size:11px;white-space:nowrap}
/* Lencana jalur paket: biru = node gateway sendiri, hijau = lewat radio,
   abu-abu = lewat internet (MQTT). */
.via{display:inline-block;border-radius:4px;padding:1px 7px;font-size:10.5px;font-weight:600;letter-spacing:.04em}
.via-diri{background:#1d3557;color:#79c0ff}
.via-lora{background:#173a24;color:#56d364}
.via-mqtt{background:#2b3038;color:#9fb0c3}
.lok{border-left:3px solid #3fb950;padding-left:0}
.ragu{border-left:3px solid #e3b341;padding-left:0}
.internet{border-left:3px solid #6e7681;padding-left:0}
/* Kotak satu bagian (details) supaya penjelasan, tabel, dan judulnya terlihat
   sebagai satu kesatuan, bukan tiga blok yang terapung. */
.kotak-bagian{background:#161d25;border:1px solid #232c38;border-radius:10px;margin:14px 0;overflow:hidden}
.kotak-bagian .isi{padding:0 14px 14px}
/* Warna ambang operasional (lihat TANGGA_* di kode): hijau aman, kuning
   mulai terasa, oranye tinggi, merah bahaya. Dipakai di kolom Kanal, Air TX,
   dan Hop supaya masalah terlihat sebelum angka besar menyadarkannya. */
.a-aman{color:#3fb950}.a-sedang{color:#e3b341}.a-tinggi{color:#f0883e}
.a-padat{color:#f85149;font-weight:600}
.hop-0{color:#3fb950}.hop-1{color:#58a6ff}.hop-2{color:#e3b341}.hop-3{color:#f85149}
/* Meter sinyal: tiga batang yang naik, meniru indikator di aplikasi resmi
   Meshtastic. Batang yang menyala memakai currentColor, jadi cukup satu kelas
   warna (.m-*) untuk mewarnai batang sekaligus kata mutunya. Batang yang mati
   tetap terlihat samar (opacity) supaya orang bisa melihat "2 dari 3". */
.meter{display:inline-flex;align-items:center;gap:9px;white-space:nowrap}
.batang{display:inline-flex;align-items:flex-end;gap:3px;height:14px}
.batang i{display:block;width:4px;border-radius:1px;background:currentColor;opacity:.22}
.batang i:nth-child(1){height:6px}
.batang i:nth-child(2){height:10px}
.batang i:nth-child(3){height:14px}
.batang i.nyala{opacity:1}
.meter .mutu{font-weight:600}
/* Angka SNR dipisah titik tengah: tanpa itu "Baik" dan "6.2 dB" terbaca
   sebagai satu kata yang rapat. Titiknya dipasang lewat CSS supaya pemisah
   tidak ikut tersalin saat teks selnya di-copy. */
.meter .db{color:#8b98a8;font-variant-numeric:tabular-nums}
.meter .db::before{content:"\\00b7";color:#5a6675;margin-right:9px}
/* Kolom sinyal rata kiri (bukan .num): isinya meter, bukan angka - dan jarak
   kanannya dilebihkan supaya tidak menempel ke kolom Hop di sebelahnya. */
td.sinyal{white-space:nowrap;padding-right:20px}
th.sinyal{white-space:nowrap}
.m-baik{color:#3fb950}.m-cukup{color:#e3b341}.m-buruk{color:#f0883e}.m-nihil{color:#f85149}
.m-internet{color:#8b98a8}
/* Lencana "charge": penanda perangkat bertenaga listrik/USB (kode 101 dari
   firmware), dipakai sebagai ganti angka 101 persen yang menyesatkan.
   Catatan: di dalam template ini tanda persen HARUS ditulis ganda (%%), karena
   seluruh halaman dirakit lewat pemformatan persen. */
.charge{background:#21323f;color:#79c0ff;border-radius:4px;padding:1px 6px;font-size:11px;white-space:nowrap}
/* Penjelasan ambang: label di kiri, artinya di kanan, satu baris per aturan -
   supaya tidak lagi menjadi satu paragraf panjang yang sulit dipindai. */
.tangga{background:#1a212b;border:1px solid #2a3340;border-radius:10px;padding:12px 16px;margin:14px 0;font-size:12.5px}
.tangga b{color:#9fb0c3;font-weight:600}
.tangga-judul{font-size:11.5px;text-transform:uppercase;letter-spacing:.06em;color:#9fb0c3;margin-bottom:5px}
.tangga-baris{display:grid;grid-template-columns:150px 1fr;gap:2px 14px;padding:5px 0;border-top:1px solid #232c38}
.tangga-baris:first-of-type{border-top:none}
.tangga .dim{margin-bottom:4px}
@media (max-width:760px){.tangga-baris{grid-template-columns:1fr}}
/* Panah penanda bagian yang bisa dibuka/tutup. Penanda bawaan browser disembunyikan
   supaya bentuk dan posisinya seragam di semua peramban, lalu diganti panah sendiri
   yang berubah arah: menunjuk kanan saat tertutup, ke bawah saat terbuka.
   Catatan: escape CSS memakai kode hex LANGSUNG (\\25b6), bukan gaya \\u25b6 -
   CSS tidak mengenal awalan \"u\", jadi salah bentuk akan tampil sebagai teks. */
summary{cursor:pointer;font-size:16px;font-weight:600;margin:28px 0 8px;list-style:none}
summary::-webkit-details-marker{display:none}
summary::marker{content:""}
summary::before{content:"\\25b6";color:#58a6ff;font-size:12px;margin-right:8px;display:inline-block}
details[open]>summary::before{content:"\\25bc"}
summary:hover{color:#79c0ff}
details[open] summary{margin-bottom:8px}
/* Alat saring: satu baris bersama hasilnya, bukan kolom input yang menggantung
   sendirian di tengah halaman. Ada DUA kotak yang berbagi satu saringan - satu
   di atas semua tabel, satu lagi tepat di atas tabel MQTT yang panjang -, jadi
   keduanya memakai gaya yang sama; .alat-tabel hanya merapikan jaraknya di
   dalam kotak bagian. */
.alat{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:16px 0 6px}
.alat-tabel{margin:10px 0 10px}
input{background:#1a212b;border:1px solid #2a3340;color:#e6edf3;border-radius:8px;padding:8px 12px;width:280px;font:inherit}
input:focus{outline:none;border-color:#3d5a80}
.hasil{font-size:12px;color:#8b98a8}
.kaki{margin-top:22px;padding-top:12px;border-top:1px solid #24303c}
.kaki a{display:inline-block;background:#1a212b;border:1px solid #2a3340;border-radius:8px;padding:5px 11px;font-size:12px;text-decoration:none;margin-right:8px}
.kaki a:hover{border-color:#3d5a80}
/* Tombol Aksi (hapus / favorit / unfavorit) di kolom terakhir tiap tabel node.
   Dipakai tanpa kunci - jadi tombolnya dibuat kecil dan samar supaya tidak
   menonjol, dan halaman meminta konfirmasi sebelum mengeksekusi lewat skrip. */
button.aksi{background:#1a212b;border:1px solid #2c3641;color:#8b98a8;border-radius:6px;padding:3px 8px;font-size:11px;cursor:pointer;white-space:nowrap}
button.aksi:hover{border-color:#f0883e;color:#e6edf3}
button.aksi:disabled{opacity:.45;cursor:not-allowed}
td.aksi{white-space:nowrap}
/* Tab navigasi Monitoring / Tracking Node. Gaya .tabbar di sini sengaja
   sama dengan yang dipakai lacak_halaman.py, jadi perpindahan tab terasa
   seperti satu aplikasi dan bukan seperti menuju situs lain. */
.tabbar{display:flex;gap:4px;border-bottom:1px solid #24303c;margin:0 0 16px;
        overflow-x:auto;-webkit-overflow-scrolling:touch}
.tabbar a{display:block;padding:9px 14px;color:#8b98a8;text-decoration:none;
          font-size:13.5px;white-space:nowrap;border-bottom:2px solid transparent}
.tabbar a:hover{color:#e6edf3}
.tabbar a.aktif{color:#e6edf3;border-bottom-color:#58a6ff;font-weight:600}
</style></head><body>
<nav class="tabbar">
<a href="/" class="aktif">&#127968; Monitoring</a>
<a href="/peta">&#128205; Live Map</a>
<a href="/lacak">&#128205; Tracking Node</a>
</nav>
<div class="kepala">
  <div class="merek">%(gambar)s
    <div>
      <h1>Meshnode-ID Monitor (Mtl-Cbt Site)</h1>
      <div class="dim">Gateway <span class="mono">%(host)s:%(port)s</span> &middot; preset <span class="mono">%(preset_gw)s</span> &middot; diperbarui <span class="mono">%(waktu)s</span></div>
    </div>
  </div>
  <div class="status %(kelas_up)s"><span class="titik"></span> exporter %(teks_up)s</div>
</div>
%(peringatan)s
<div class="kartu">
  <div class="kotak"><b>%(jml_langsung)s</b><span>langsung ke gateway</span></div>
  <div class="kotak"><b>%(jml_lora)s</b><span>radio, ada bukti SNR</span></div>
  <div class="kotak"><b>%(jml_ragu)s</b><span>radio, belum ada bukti</span></div>
  <div class="kotak"><b>%(jml_mqtt)s</b><span>lewat MQTT (internet)</span></div>
  <div class="kotak"><b>%(jml_online)s</b><span>online</span></div>
  <div class="kotak"><b>%(jml_total)s</b><span>total node</span></div>
  <div class="kotak"><b>%(uptime)s</b><span>uptime gateway</span></div>
  <div class="kotak"><b>%(db)s</b><span>database node</span></div>
</div>

<div class="tangga">
<div class="tangga-judul">Ambang yang dipakai halaman ini</div>
<div class="dim">Angka di kolom Kanal, Air TX, dan Hop diwarnai mengikuti pedoman operasional Meshtastic &mdash; pedoman yang sama dipakai dasbor komunitas, jadi hasilnya bisa dibandingkan antarperkakas.</div>
<div class="tangga-baris"><b>Utilisasi kanal</b><span><span class="a-aman">&lt;25%%</span> sehat &middot; <span class="a-sedang">25&ndash;40%%</span> sedang, pengiriman mulai tertahan &middot; <span class="a-tinggi">40&ndash;50%%</span> tinggi, pembaruan GPS dikurangi &middot; <span class="a-padat">&gt;50%%</span> padat, kanal kelebihan beban</span></div>
<div class="tangga-baris"><b>Airtime TX</b><span><span class="a-aman">&lt;5%%</span> bagus &middot; <span class="a-sedang">5&ndash;8%%</span> wajar &middot; <span class="a-padat">&gt;8%%</span> kelebihan, kurangi pancaran</span></div>
<div class="tangga-baris"><b>Hop</b><span><span class="hop-0">0</span> langsung ke gateway &middot; <span class="hop-1">1&ndash;2</span> dekat &middot; <span class="hop-2">3&ndash;4</span> jauh &middot; <span class="hop-3">&ge;5</span> sangat jauh</span></div>
<div class="tangga-baris"><b>Baterai</b><span><span class="charge">charge</span> tersambung listrik/USB &middot; angka persen = memakai baterai &middot; <span class="dim">&ndash;</span> perangkat tidak melaporkan baterai</span></div>
<div class="tangga-baris"><b>Meter sinyal</b><span>%(contoh_meter)s</span></div>
<div class="tangga-baris"><b>Cara membacanya</b><span>Meter ini menilai <b>keterbacaan</b>, bukan kuat-lemah: yang diukur jarak SNR paket terakhir dari <b>lantai demodulasi</b> preset radio gateway (<span class="mono">%(preset_gw)s</span> &rarr; lantai <b>%(lantai_teks)s dB</b>%(catatan_lantai)s). Radio LoRa memang bisa mendengar di bawah lantai derau, jadi SNR negatif itu normal &mdash; dan SNR &minus;10 dB bisa "Baik" di satu preset tetapi "Nihil" di preset lain. Angka SNR mentahnya tetap dicetak di sebelah meter. Node jalur MQTT tidak diberi meter karena gateway tidak mendengarnya lewat udara.</span></div>
<div class="tangga-baris"><b>Tanda lain</b><span><span class="via via-lora">LORA</span> lewat radio &middot; <span class="via via-mqtt">MQTT</span> lewat internet &middot; <span class="favorit">&#9733;</span> Favorite (terlindungi saat daftar node penuh)</span></div>
</div>

<div class="alat">
  <input id="saring" data-saring placeholder="saring: nama atau ID, mis. ROUTER, MOB, !da5a16f8">
  <span class="dim">saringan tetap tersimpan saat halaman menyegar</span>
  <span class="hasil"></span>
</div>

<div class="kotak-bagian lok">
<details open class="bagian" id="bagian-gateway"><summary>GATEWAY &amp; NODE YANG TERSAMBUNG LANGSUNG &mdash; %(jml_langsung)s node</summary>
<div class="isi">
<div class="dim">Baris pertama adalah gateway itu sendiri. Sisanya node yang <b>terbukti</b> tersambung langsung ke gateway: gateway <b>mengukur sendiri</b> SNR-nya lewat udara dan jaraknya <b>0 hop</b>. Jadi buktinya bukan label dari internet, melainkan hasil pengukuran radio di tempat Anda. <span class="favorit">&#9733;</span> = Favorite (lebih terlindungi saat daftar node penuh).</div>
<div class="gulir"><table class="data"><thead>%(kepala_node)s</thead>
<tbody>%(baris_diri)s%(baris_lora)s</tbody></table></div>
</div>
</details>
</div>

<div class="kotak-bagian ragu">
<details class="bagian" id="bagian-ragu"><summary>NODE JALUR RADIO TANPA BUKTI KONEKSI LANGSUNG &mdash; %(jml_ragu)s node</summary>
<div class="isi">
<div class="dim">Node ini <b>bukan</b> node MQTT, tetapi gateway <b>belum pernah mengukur SNR-nya</b> dan jaraknya belum diketahui. Artinya belum ada bukti ia tersambung langsung ke gateway &mdash; bisa jadi terakhir terdengar lewat perantara, atau entri lamanya masih tersimpan. Begitu gateway menangkap paketnya lewat udara, ia akan pindah sendiri ke tabel di atas.</div>
<div class="gulir"><table class="data"><thead>%(kepala_node)s</thead>
<tbody>%(baris_ragu)s</tbody></table></div>
</div>
</details>
</div>

<div class="kotak-bagian internet">
<details class="bagian" id="bagian-mqtt"><summary>NODE LEWAT MQTT (INTERNET) &mdash; %(jml_mqtt)s node, BUKAN jaringan radio lokal Anda</summary>
<div class="isi">
<div class="dim">Node dari broker publik <span class="mono">msh</span>. Mereka muncul karena gateway ikut menarik MQTT, dan bisa memenuhi daftar node. Tanda <span class="tag">pernah lewat radio</span> berarti gateway <b>juga</b> pernah mendengarnya lewat udara &mdash; kemungkinan itu node lokal yang paket terakhirnya kebetulan datang dari internet.</div>
<div class="alat alat-tabel">
  <input id="saring-mqtt" data-saring placeholder="saring %(jml_mqtt)s node MQTT: nama atau ID, mis. !da5a16f8">
  <span class="dim">kotak ini menyaring tabel node &amp; katanya ikut tersimpan saat halaman menyegar</span>
  <span class="hasil"></span>
</div>
<div class="gulir"><table class="data"><thead>%(kepala_node)s</thead>
<tbody>%(baris_mqtt)s</tbody></table></div>
</div>
</details>
</div>

<h2>Data yang masuk ke node (paket terakhir)</h2>
<div class="dim" style="margin-bottom:8px">%(jml_paket)s paket terakhir yang tercatat di gateway.</div>
<div class="gulir"><table><thead><tr>
<th>Waktu</th><th>Dari</th><th>Tipe</th><th class="num">SNR</th><th class="num">RSSI</th><th class="num">Hop</th>
</tr></thead><tbody>%(baris_paket)s</tbody></table></div>
<div class="kaki dim">Halaman menyegar otomatis tiap 5 detik.&nbsp; <a href="/data.json">/data.json</a><a href="/metrics">/metrics</a><a href="/lacak">/lacak</a> &mdash; peta dan riwayat pergerakan node yang punya koordinat</div>
<script>
// Status BUKA/TUTUP tiap bagian diingat di peramban. Halaman ini menyegar
// sendiri tiap 5 detik, dan tanpa diingat setiap penyegaran akan menutup lagi
// bagian yang baru saja dibuka - menjengkelkan saat sedang membaca tabel MQTT.
// Yang disimpan hanya status bukanya (bukan isi halaman), per bagian.
var bagian=document.querySelectorAll('details.bagian');
var KUNCI_BUKA='meshid-buka-1';
function bacaSimpanan(){
  try{ return JSON.parse(localStorage.getItem(KUNCI_BUKA) || '{}'); }catch(e){ return {}; }
}
function tulisSimpanan(objek){
  try{ localStorage.setItem(KUNCI_BUKA, JSON.stringify(objek)); }catch(e){}
}
var simpanan=bacaSimpanan();
for(var b=0;b<bagian.length;b++){
  var el=bagian[b];
  // Simpanan menang atas keadaan bawaan di HTML; kalau belum ada simpanan,
  // bagian pertama tetap terbuka seperti bawaannya.
  if(el.id && Object.prototype.hasOwnProperty.call(simpanan, el.id)){
    el.open = simpanan[el.id];
  }
  el.addEventListener('toggle', function(ev){
    var s=bacaSimpanan();
    s[ev.currentTarget.id]=ev.currentTarget.open;
    tulisSimpanan(s);
  });
}

// Saringan node. Dua kotak (satu di atas semua tabel, satu tepat di atas tabel
// MQTT) memakai satu kata saringan yang sama, jadi mengetik di salah satunya
// langsung mengisi yang lain.
//
// Kata saringannya diingat di tiga tempat, dari yang paling kuat:
//   1. localStorage - bertahan walau alamat halaman dibuka ulang dari awal,
//      dan tidak bergantung pada peramban yang mempertahankan #hash. Inilah
//      yang membuat saringan tetap tersimpan saat halaman menyegar sendiri.
//   2. #hash alamat - supaya tautan hasil saringan bisa dibagikan apa adanya.
//   3. Kotak yang terakhir dipakai dicatat di sessionStorage, supaya
//      penyegaran tiap 5 detik mengembalikan fokus ke kotak yang BENAR (tidak
//      selalu kotak paling atas).
var KUNCI_SARING='meshid-saring-1';
var KUNCI_FOKUS='meshid-saring-fokus';
var kotak=document.querySelectorAll('input[data-saring]');
var semuaHasil=document.querySelectorAll('.hasil');
function bacaSaring(){
  try{ return localStorage.getItem(KUNCI_SARING) || ''; }catch(e){ return ''; }
}
function simpanSaring(nilai){
  try{ localStorage.setItem(KUNCI_SARING, nilai); }catch(e){}
}
function terapkan(sumber){
  var teks=sumber ? sumber.value : '';
  var q=teks.toLowerCase();
  // Samakan isi kotak lainnya (tanpa menyentuh kotak yang sedang dipakai,
  // supaya posisi kursor orang yang mengetik tidak melompat).
  for(var j=0;j<kotak.length;j++){
    if(kotak[j]!==sumber && kotak[j].value!==teks){ kotak[j].value=teks; }
  }
  var tr=document.querySelectorAll('table.data tbody tr');
  var tampil=0;
  for(var i=0;i<tr.length;i++){
    var cocok = tr[i].textContent.toLowerCase().indexOf(q)>=0;
    tr[i].style.display = cocok ? '' : 'none';
    if(cocok){ tampil++; }
  }
  var ringkas = q ? (tampil + ' node cocok') : '';
  for(var k=0;k<semuaHasil.length;k++){ semuaHasil[k].textContent=ringkas; }
  simpanSaring(teks);
  try{ history.replaceState(null,'','#'+encodeURIComponent(teks)); }catch(e){}
}
function fokusTerakhir(){
  try{ return sessionStorage.getItem(KUNCI_FOKUS) || ''; }catch(e){ return ''; }
}
for(var m=0;m<kotak.length;m++){
  (function(el){
    // Kotak yang sedang dipakai dicatat dari dua kejadian: 'input' (pasti
    // sedang mengetik) dan 'focus'. Peramban tidak mengirim kejadian 'focus'
    // bila jendelanya sendiri sedang tidak aktif, jadi 'input' yang jadi
    // andalan - dan kejadian itulah yang penting supaya fokus dikembalikan ke
    // kotak yang benar setelah penyegaran berikutnya.
    el.addEventListener('input', function(){
      try{ sessionStorage.setItem(KUNCI_FOKUS, el.id); }catch(e){}
      terapkan(el);
    });
    el.addEventListener('focus', function(){
      try{ sessionStorage.setItem(KUNCI_FOKUS, el.id); }catch(e){}
    });
  })(kotak[m]);
}
if(kotak.length){
  // #hash menang atas simpanan: tautan yang dibagikan harus membuka saringan
  // yang dimaksud pengirimnya, bukan saringan lama penerima.
  var awal=decodeURIComponent((location.hash||'').slice(1)) || bacaSaring();
  for(var n=0;n<kotak.length;n++){ kotak[n].value=awal; }
  if(awal){
    terapkan(kotak[0]);
    // Penyegaran tiap 5 detik membuang fokus dan menaruh kursor di awal kata.
    // Keduanya dikembalikan supaya bisa langsung melanjutkan mengetik.
    var aktif=document.getElementById(fokusTerakhir()) || kotak[0];
    aktif.focus();
    try{ aktif.setSelectionRange(aktif.value.length, aktif.value.length); }catch(e){}
  }
}

// Tombol Aksi: hapus node dari database gateway / lepas tanda Favorite.
// Perintah dikirim ke /aksi, hasilnya ditampilkan, lalu halaman dimuat ulang
// sendiri (biasanya penyegaran tiap 5 detik sudah cukup, tapi tindakan ini
// memakai muat ulang cepat supaya tabel segera menunjukkan keadaan baru).
//
// PENTING: halaman memuat ulang sendiri tiap 5 detik. Traceroute bisa
// mengambil waktu lebih lama (bahkan puluhan detik), dan konfirmasi pun bisa
// terbuka beberapa detik. Kalau refresh berjalan saat itu, semua JavaScript
// yang menunggu hasil ikut hilang dan tombol tampak "tidak berfungsi". Karena
// itu refresh dijeda sejak tombol diklik, lalu tampilan dimuat ulang manual
// setelah hasil (atau kegagalan) ditampilkan.
function jedaAutoRefresh(){
  var m=document.querySelector('meta[http-equiv="refresh"]');
  if(m){ m.setAttribute('content','3600'); }
}
function aksi(btn){
  jedaAutoRefresh();
  var node=btn.getAttribute('data-node');
  var perintah=btn.getAttribute('data-aksi');
  var kata = perintah==='hapus' ? 'hapus node '+node+' dari database gateway'
                                : perintah==='favorit' ? 'tandai node '+node+' sebagai Favorite'
                                : perintah==='trace' ? 'telusuri jalur ke node '+node
                                                       : 'lepas Favorite node '+node;
  if(!window.confirm(kata+'?')){ pulihkanAutoRefresh(); return; }
  var semua=document.querySelectorAll('button.aksi');
  for(var i=0;i<semua.length;i++){ semua[i].disabled=true; }
  btn.textContent = perintah==='hapus' ? 'menghapus...'
                  : perintah==='favorit' ? 'menandai...'
                  : perintah==='trace' ? 'melacak...' : 'melepas...';
  fetch('/aksi',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({aksi:perintah,node_id:node})
  }).then(function(r){return r.json();}).then(function(j){
    window.alert(j.pesan || (j.ok ? 'ok' : 'gagal'));
    location.reload();
  }).catch(function(){
    window.alert('Gagal menghubungi exporter.');
    location.reload();
  });
}
function pulihkanAutoRefresh(){
  var m=document.querySelector('meta[http-equiv="refresh"]');
  if(m){ m.setAttribute('content','5'); }
}
var tombol=document.querySelectorAll('button.aksi');
for(var t=0;t<tombol.length;t++){
  tombol[t].addEventListener('click', function(){ aksi(this); });
}
</script>
%(skrip_layar)s
</body></html>""" % {
        "peringatan": peringatan,
        "host": host, "port": port,
        "waktu": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sekarang)),
        "ikon": ikon, "gambar": gambar_kepala,
        "kelas_up": "hidup" if exporter_up else "mati",
        "teks_up": "terhubung" if exporter_up else "terputus",
        "jml_lora": len(milik_lora),
        "jml_langsung": len(milik_lora) + len(milik_diri),
        "jml_ragu": len(milik_ragu),
        "jml_mqtt": len(milik_mqtt),
        "jml_online": jumlah_online,
        "jml_total": len(nodes),
        "jml_paket": len(umpan),
        "uptime": _durasi(gateway.get("uptime")),
        "db": "%s / %s" % (nodedb if nodedb is not None else "-", AMBANG_DB_PENUH),
        "baris_lora": baris_lora,
        "baris_ragu": baris_ragu,
        "baris_mqtt": baris_mqtt,
        "baris_diri": baris_diri,
        "kepala_node": kepala_node,
        "preset_gw": preset_gw,
        "contoh_meter": contoh_meter,
        "lantai_teks": "%+.1f" % lantai,
        "catatan_lantai": catatan_lantai,
        "baris_paket": "".join(paket_baris) or "<tr><td colspan='6' class='dim'>Belum ada paket.</td></tr>",
        "skrip_layar": SKRIP_LAYAR,
    }


def buat_handler(cuplikan, offline, host, port, gambar=None):
    lampiran = gambar or {}

    class Handler(BaseHTTPRequestHandler):
        def _kirim(self, status, tipe, isi, tahan=False):
            badan = isi if isinstance(isi, bytes) else isi.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", tipe)
            self.send_header("Content-Length", str(len(badan)))
            if tahan:
                # Gambar tidak berubah selama proses hidup, sedangkan halaman
                # menyegar sendiri tiap 5 detik: tanpa header ini peramban
                # mengunduh ulang logo di setiap penyegaran.
                self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(badan)

        def do_GET(self):
            # Kueri dibuang lebih dulu supaya "/logo.png?v=2" tetap dilayani.
            jalur = self.path.split("?")[0]
            try:
                if jalur in lampiran:
                    isi, tipe = lampiran[jalur]
                    self._kirim(200, tipe, isi, tahan=True)
                elif jalur.startswith("/metrics"):
                    self._kirim(200, CONTENT_TYPE_LATEST, generate_latest())
                elif jalur.startswith("/data.json"):
                    self._kirim(200, "application/json; charset=utf-8",
                                json.dumps(data_json(cuplikan, offline, host, port),
                                           indent=2, ensure_ascii=False))
                elif jalur == "/peta" or jalur == "/peta/":
                    # Tab Live Map: satu peta berisi semua node yang punya
                    # koordinat. Sumbernya snapshot gateway yang sama dengan
                    # /data.json, jadi nama/status di peta tidak bisa beda
                    # dengan tabel monitoring.
                    nodes = node_dengan_status(cuplikan, offline)
                    self._kirim(200, "text/html; charset=utf-8",
                                lacak_halaman.halaman_peta(
                                    list(nodes.values()),
                                    time.time(), bool(lampiran)))
                elif jalur == "/lacak" or jalur == "/lacak/":
                    self._kirim(200, "text/html; charset=utf-8",
                                lacak_halaman.halaman_daftar(
                                    lacak_node.node_berriwayat(
                                        node_dengan_status(cuplikan, offline)),
                                    lacak_node.statistik_db(), bool(lampiran)))
                elif jalur.startswith("/lacak/"):
                    # /lacak/<node_id>       -> halaman peta
                    # /lacak/<node_id>.json  -> paket data yang sama, untuk skrip
                    self._lacak(jalur[len("/lacak/"):])
                else:
                    self._kirim(200, "text/html; charset=utf-8",
                                halaman_html(cuplikan, offline, host, port,
                                             EXPORTER_UP._value.get(),
                                             bool(lampiran)))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                LOG.debug("gagal melayani permintaan %s", self.path, exc_info=True)

        def _lacak(self, sisa):
            """Layani /lacak/<node_id>[.json].

            node_id divalidasi dengan pola yang sama seperti /aksi: isinya
            masuk ke jalur filesystem (nama berkas database) dan ke SQL, jadi
            bentuknya harus dibatasi ketat, bukan sekadar di-escape.
            """
            mau_json = sisa.endswith(".json")
            if mau_json:
                sisa = sisa[:-len(".json")]
            node_id = urllib.parse.unquote(sisa)
            if re.fullmatch(r"![0-9a-fA-F]{8}", node_id) is None:
                return self._kirim(404, "text/plain; charset=utf-8",
                                   "node_id tidak sah (format !xxxxxxxx)")
            meta = node_dengan_status(cuplikan, offline).get(node_id) or {}
            nama = (meta.get("long_name") or meta.get("short_name")
                    or lacak_node.node_nama(node_id) or node_id)
            paket = lacak_node.paket_node(node_id)
            db = lacak_node.statistik_db()
            if mau_json:
                # node_id dan nama ikut disertakan supaya JSON standalone
                # tidak perlu lookup terpisah; None berarti node belum punya
                # histori sama sekali.
                if paket:
                    paket["node_id"] = node_id
                    paket["nama"] = nama
                return self._kirim(200, "application/json; charset=utf-8",
                                   json.dumps(paket, ensure_ascii=False,
                                              allow_nan=False))
            return self._kirim(200, "text/html; charset=utf-8",
                               lacak_halaman.halaman_node(node_id, paket, nama,
                                                           bool(lampiran), db))

        def do_POST(self):
            """Terima perintah dari tombol halaman: {'aksi', 'node_id'}.

            Perintah diterima lalu DIANTRIKAN; thread collector yang
            menjalankannya (sesuai kesepakatan: hanya collector yang memegang
            interface). Permintaan ini menunggu hasil dengan tenggat, sehingga
            halaman bisa menampilkan pesan sukses/gagal ke pemakai.
            """
            jalur = self.path.split("?")[0]
            if jalur != "/aksi":
                return self._kirim(404, "application/json; charset=utf-8",
                                   json.dumps({"ok": False,
                                               "pesan": "rute tidak dikenal"}))
            try:
                panjang = int(self.headers.get("Content-Length") or 0)
                if panjang > 65536:
                    raise ValueError("badan terlalu besar")
                isi = json.loads(self.rfile.read(panjang).decode("utf-8"))
            except Exception:
                return self._kirim(400, "application/json; charset=utf-8",
                                   json.dumps({"ok": False,
                                               "pesan": "permintaan bukan JSON yang sah"}))
            aksi = str(isi.get("aksi") or "").strip().lower()
            node_id = str(isi.get("node_id") or "").strip()
            valid_aksi = aksi in ("hapus", "unfavorit", "favorit", "trace")
            valid_id = re.fullmatch(r"![0-9a-fA-F]{8}", node_id) is not None
            if not valid_aksi:
                return self._kirim(400, "application/json; charset=utf-8",
                                   json.dumps({"ok": False,
                                               "pesan": "aksi harus 'hapus', 'unfavorit', 'favorit', atau 'trace'"}))
            if not valid_id:
                return self._kirim(400, "application/json; charset=utf-8",
                                   json.dumps({"ok": False,
                                               "pesan": "node_id tidak sah (format !xxxxxxxx)"}))
            perintah = cuplikan.taruh_perintah(aksi, node_id)
            menunggu = 40 if aksi == "trace" else 20
            if perintah["selesai"].wait(menunggu):
                hasil = perintah["hasil"] or {"ok": False, "pesan": "hasil tidak tersedia"}
            else:
                hasil = {"ok": False, "pesan": "gateway belum selesai memproses (antisipasi keterlambatan)"}
            return self._kirim(200, "application/json; charset=utf-8",
                               json.dumps(hasil))

        def log_message(self, *args):  # redam log akses
            pass

    return Handler


def jalankan_web(listen, exp_port, cuplikan, offline, host, port, gambar=None):
    httpd = ThreadingHTTPServer(
        (listen, exp_port), buat_handler(cuplikan, offline, host, port, gambar))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# ------------------------------------------------------------
# Koneksi ke node
# ------------------------------------------------------------

# Penjaga sambungan (lihat kendala yang terbukti 28 Sep 2026).
#
# GEJALA: halaman web dan /data.json menampilkan 0 node selamanya, tetapi
# meshtastic_exporter_up tetap 1 dan tidak satu pun alert berbunyi. Terjadi
# ketika gateway memuat ulang setelannya (mis. sesudah menulis setelan MQTT)
# atau reboot: socket lama mati tanpa memberi tahu pembaca, sementara pustaka
# meshtastic TIDAK membersihkan penanda isConnected-nya saat socket putus.
# Akibatnya exporter "hidup" tetapi buta - dan karena up=1, alert
# MeshtasticExporterDown diam.
#
# SEBAB: loop di sini hanya menunggu `time.sleep`, tanpa pernah memeriksa
# apakah data datang. `kumpulkan()` mengembalikan 0 node, dicatat sebagai
# debug, lalu diulang selamanya dengan 0 node.
#
# SOLUSI: dua penjaga. (1) saat pertama menyambung, tunggu database node
# benar-benar terisi; (2) bila database kosong berulang kali padahal
# sebelumnya ada isinya, turunkan penanda up dan keluar supaya main()
# menyambung ulang dengan jeda bertingkat.
#
# TAMBAHAN 28 Sep 2026 sore (gejala yang sama terulang di halaman produksi):
# penjaga (2) bergantung pada penanda "pernah ada isi". Bila pembacaan
# PERTAMA sudah kosong - persis yang terjadi di host ZimaOS setelah socket
# mati pada 18:22 - penanda itu tidak pernah menyala, sehingga penjaga diam
# selamanya: halaman terus kosong, up tetap 1, dan alert tidak berbunyi.
# Karena itu isi handshake dipakai untuk menyalakan penjaga, dan ada tenggat
# tambahan (MESH_BUTA_TUNGGU) supaya gelandangan tanpa isi pun akhirnya
# menyambung ulang, bukan diam menunggu keajaiban.
BAWAAN_TUNGGU_AWAL = 30    # detik menunggu database node terisi saat pertama sambung
BAWAAN_KOSONG_MAKS = 3     # berapa kali "0 node" berturut-turut sebelum dianggap mati
BAWAAN_BUTA_TUNGGU = 120   # detik: setelah ini, "0 node" dihitung walau belum pernah ada isi

# Perintah dari tombol halaman web (hapus node / lepas Favorite) DIJALANKAN oleh
# thread collector - bukan oleh thread HTTP - karena hanya collector yang
# memegang interface ke gateway. Bahaya yang dihindari: HTTP dibuka tanpa kunci,
# jadi toh ia tidak punya hak istimewa lewat API admin; bedanya di sini hanya
# akses ke interface yang diizinkan dari satu thread yang jelas.
def _buang_dari_cache(iface, sasaran):
    """Radio menghapus node dari nodedb-nya sendiri, tetapi pustaka klien tidak
    diberitahu (tidak ada pesan 'node dihapus'). Biarkan saja, entri basi di
    iface.nodes / iface.nodesByNum akan terus ditampilkan sampai restart. Jadi
    hapus sendiri entri itu agar halaman dan metrik ikut menyesuaikan."""
    try:
        if getattr(iface, "nodesByNum", None) is not None and sasaran.startswith("!"):
            iface.nodesByNum.pop(int(sasaran[1:], 16), None)
        if getattr(iface, "nodes", None) is not None:
            iface.nodes.pop(sasaran, None)
    except Exception:
        LOG.debug("cache tak ikut dibersihkan", exc_info=True)


def _ubah_favorit_di_cache(iface, sasaran, tanda):
    """Setelah setFavorite/removeFavorite, ikut mengubah isFavorite di cache
    pustaka agar halaman langsung mencerminkan tanpa menunggu radio mengirim
    ulang. Entri bisa ada di iface.nodes (kunci id) dan/atau nodesByNum
    (kunci angka), jadi keduanya dijangkau."""
    try:
        angka = int(sasaran[1:], 16) if sasaran.startswith("!") else None
        for kumpulan in (getattr(iface, "nodes", None),
                         getattr(iface, "nodesByNum", None)):
            if not kumpulan:
                continue
            kunci = sasaran if kumpulan is getattr(iface, "nodes", None) else angka
            if kunci is None or kunci not in kumpulan:
                continue
            entri = kumpulan[kunci]
            if isinstance(entri, dict):
                entri["isFavorite"] = tanda
    except Exception:
        LOG.debug("cache favorit tak ikut diubah", exc_info=True)


def _lepas_favorit_di_cache(iface, sasaran):
    _ubah_favorit_di_cache(iface, sasaran, False)


def _tandai_favorit_di_cache(iface, sasaran):
    _ubah_favorit_di_cache(iface, sasaran, True)


def _bentuk_jalur_trace(iface, p, asDict):
    """Buat baris teks jalur (maju dan, bila ada, kembali) dari RouteDiscovery."""
    UNK = -128

    def nama(num):
        if num is None:
            return None
        if hasattr(iface, "_nodeNumToId"):
            try:
                return iface._nodeNumToId(num, False) or "%08x" % num
            except Exception:
                pass
        return "%08x" % num

    def snr(isi, i, sah):
        if not sah or isi[i] == UNK:
            return "?"
        return "%.1f" % (isi[i] / 4)

    garis = []
    rute = asDict.get("route") or []
    snr_t = asDict.get("snrTowards") or []
    sah_t = len(snr_t) == len(rute) + 1
    s = nama(p.get("to"))
    for i, n in enumerate(rute):
        s += " --> %s (%s)" % (nama(n), snr(snr_t, i, sah_t))
    s += " --> %s (%s)" % (nama(p.get("from")), snr(snr_t, len(rute), sah_t))
    garis.append("maju: " + s)
    if "hopStart" in p and "snrBack" in asDict:
        balik = asDict.get("routeBack") or []
        snr_b = asDict.get("snrBack") or []
        sah_b = len(snr_b) == len(balik) + 1
        t = nama(p.get("from"))
        for i, n in enumerate(balik):
            t += " --> %s (%s)" % (nama(n), snr(snr_b, i, sah_b))
        t += " --> %s (%s)" % (nama(p.get("to")), snr(snr_b, len(balik), sah_b))
        garis.append("balik: " + t)
    return garis or ["jalur kosong"]


def _laksana_trace(iface, sasaran, tenggat=35.0):
    """Kirim traceroute ke node dan tangkap jalurnya sebagai nilai.

    Tidak seperti meshtastic.sendTraceRoute - yang mencetak ke stdout dan
    memblokir tanpa hasil - di sini respon RouteDiscovery ditangkap oleh
    handler dan disusun jadi baris teks untuk popup halaman web."""
    kantong = {}
    terima = threading.Event()

    def pada_respon(p):
        try:
            decoded = p.get("decoded") or {}
            nama_port = decoded.get("portnum")
            if nama_port == "ROUTING_APP":
                err = (decoded.get("routing") or {}).get("errorReason")
                if err and err != "NONE":
                    kantong["rute"] = ["gagal: %s" % err]
            else:
                rd = mesh_pb2.RouteDiscovery()
                rd.ParseFromString(decoded["payload"])
                kantong["rute"] = _bentuk_jalur_trace(iface, p,
                                                      json_format.MessageToDict(rd))
        except Exception as e:
            kantong["rute"] = ["gagal memproses balasan: %s" % e]
        finally:
            terima.set()

    try:
        hop_limit = 3
        try:
            hop_limit = int(iface.localNode.localConfig.lora.hop_limit)
        except Exception:
            pass
        iface.sendData(
            mesh_pb2.RouteDiscovery(),
            destinationId=sasaran,
            portNum=portnums_pb2.PortNum.TRACEROUTE_APP,
            wantResponse=True,
            onResponse=pada_respon,
            channelIndex=0,
            hopLimit=hop_limit,
        )
    except Exception as e:
        return {"ok": False, "pesan": "traceroute gagal dikirim: %s" % e}

    if not terima.wait(tenggat):
        return {"ok": False,
                "pesan": "traceroute tidak membalas dalam %.0f detik" % tenggat}
    jalur = kantong.get("rute")
    if not jalur:
        return {"ok": False, "pesan": "traceroute selesai tanpa jalur"}
    return {"ok": True,
            "pesan": "jalur menuju %s:\n%s" % (sasaran, "\n".join(jalur)),
            "rute": jalur}


def laksana_perintah(iface, perintah):
    """Jalankan SATU perintah admin; balikkan dict hasil {ok, pesan}.

    Buffer socket ke gateway bisa penuh bila perintah beruntun dikirim serempak,
    jadi metode pustaka ini TIDAK dijamin cepat selesai - HTTP menanti hasilnya
    dengan tenggat sendiri lewat perintah["selesai"].
    """
    aksi = perintah.get("aksi")
    sasaran = perintah.get("sasaran")
    if not iface or not getattr(iface, "localNode", None):
        return {"ok": False, "pesan": "gateway belum tersambung"}
    try:
        # Pesan admin dikirim PKI-encrypted dan MEWAJIBKAN session_passkey.
        # ensureSessionKey() hanya MENGIRIM permintaan kunci (async) lalu balik
        # seketika; kalau pesan dikirim sebelum kunci tiba, radio membuangnya
        # tanpa jejak. Jadi tunggu sampai passkey sungguh masuk ke cache dulu.
        node = iface.localNode
        if not getattr(node, "noProto", False):
            if iface._getOrCreateByNum(node.nodeNum).get("adminSessionPassKey") is None:
                node.ensureSessionKey()
                for _ in range(200):  # maksimal ~20 detik menunggu kunci sesi
                    if iface._getOrCreateByNum(node.nodeNum).get("adminSessionPassKey") is not None:
                        break
                    time.sleep(0.1)
        if aksi == "hapus":
            iface.localNode.removeNode(sasaran)
            _buang_dari_cache(iface, sasaran)
            hasil = {"ok": True, "pesan": "perintah hapus node %s terkirim" % sasaran}
        elif aksi == "unfavorit":
            iface.localNode.removeFavorite(sasaran)
            _lepas_favorit_di_cache(iface, sasaran)
            hasil = {"ok": True, "pesan": "node %s dilepas dari Favorite" % sasaran}
        elif aksi == "favorit":
            iface.localNode.setFavorite(sasaran)
            _tandai_favorit_di_cache(iface, sasaran)
            hasil = {"ok": True, "pesan": "node %s ditandai sebagai Favorite" % sasaran}
        elif aksi == "trace":
            hasil = _laksana_trace(iface, sasaran)
        else:
            hasil = {"ok": False, "pesan": "aksi tidak dikenal: %s" % aksi}
    except Exception as e:
        LOG.warning("gagal menjalankan perintah %s %s: %s", aksi, sasaran, e)
        hasil = {"ok": False, "pesan": "%s: %s" % (type(e).__name__, e)}
    perintah["hasil"] = hasil
    perintah["selesai"].set()
    return hasil


def sambung(host, port, interval, cuplikan, offline):
    """Satu siklus hidup koneksi: sambung, lalu perbarui sampai gagal."""
    LOG.info("menyambung ke node Meshtastic %s:%d ...", host, port)
    iface = TCPInterface(hostname=host, portNumber=port)
    kosong = 0
    mula = time.time()
    pernah_ada = False
    tunggu = float(os.environ.get("MESH_TUNGGU_AWAL", BAWAAN_TUNGGU_AWAL) or 0)
    kosong_maks = int(os.environ.get("MESH_KOSONG_MAKS", BAWAAN_KOSONG_MAKS) or 0)
    buta_tunggu = float(os.environ.get("MESH_BUTA_TUNGGU", BAWAAN_BUTA_TUNGGU) or 0)
    try:
        # (1) Handshake: jangan mengaku "up" sebelum database node benar-benar
        # terbaca. Tanpa ini, sambungan yang gagal di tengah handshake akan
        # tampak sehat selamanya (persis gejala yang terjadi).
        batas = time.time() + tunggu
        while tunggu and not (iface.nodes or {}) and time.time() < batas:
            time.sleep(1)
        if tunggu and not (iface.nodes or {}):
            EXPORTER_UP.set(0)
            raise RuntimeError(
                "database node belum terbaca setelah %.0f detik" % tunggu)

        EXPORTER_UP.set(1)
        # Handshake di atas sudah MEMBUKTIKAN database node terbaca, jadi
        # penjaga di bawah langsung aktif. Tanpa baris ini, pembacaan pertama
        # yang kosong mematikan penjaga untuk selamanya (lihat catatan di atas).
        pernah_ada = bool(iface.nodes or {})
        while True:
            # Jalankan perintah admin yang menunggu dari halaman web. Di sini,
            # bukan di handler HTTP, karena hanya thread inilah yang memegang
            # interface gateway. Cuplikan sesudahnya tetap segar: perintah
            # berjalan sebelum pembacaan kumpulkan() berikutnya.
            for perintah in cuplikan.ambil_perintah():
                laksana_perintah(iface, perintah)
            jumlah = kumpulkan(iface, cuplikan)
            LOG.debug("memperbarui %d node", jumlah)
            # Rekam posisi ke histori lacak. Sengaja SESUDAH kumpulkan() dan
            # tidak pernah menggagalkan poll: kehabisan ruang disk atau tabel
            # SQLite yang bermasalah tidak boleh menghentikan pemantau node.
            # Parameter `offline` diteruskan dari main() karena penanda online
            # perlu ikut tersimpan di snapshot.
            try:
                lacak_node.catat_snapshot(node_dengan_status(cuplikan, offline))
            except Exception:  # noqa: BLE001
                LOG.debug("lacak: perekaman posisi gagal", exc_info=True)

            # (2) Penjaga "hidup tetapi buta". Pembacaan kosong baru dihitung
            # sebagai kegagalan bila database pernah berisi, atau bila
            # sambungan sudah berjalan lebih lama dari tenggat MESH_BUTA_TUNGGU.
            if jumlah:
                pernah_ada = True
                kosong = 0
            elif pernah_ada or (buta_tunggu and time.time() - mula >= buta_tunggu):
                kosong += 1
                LOG.warning("tidak ada data dari gateway (%d kali berturut-turut)",
                            kosong)
                if kosong_maks and kosong >= kosong_maks:
                    EXPORTER_UP.set(0)
                    raise RuntimeError("gateway berhenti mengirim data")
            # Tidur antar pembaruan, tetapi PERMUKAAN lebih cepat bila halaman
            # web menaruh perintah baru (jangan menunggu interval penuh tiap
            # klik tombol - bisa terasa "layar beku").
            cuplikan.tunggu_sinyal(interval)
    finally:
        try:
            iface.close()
        except Exception:
            LOG.debug("gagal menutup interface", exc_info=True)


def main():
    host = _env("MESH_HOST", "192.168.20.31")
    port = _env_int("MESH_PORT", 4403)
    exp_port = _env_int("MESH_EXPORTER_PORT", 9208)
    listen = _env("MESH_LISTEN", "0.0.0.0")
    interval = max(5, _env_int("MESH_INTERVAL", 30))
    offline = _env_int("MESH_OFFLINE_SECS", 10800)
    logging.basicConfig(
        level=_env("MESH_LOG", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s")

    cuplikan = Cuplikan()
    # Batas umur cuplikan sebelum dianggap basi. Tiga kali interval (minimal 90
    # detik) memberi ruang bagi satu putaran yang lambat tanpa alarm palsu.
    basi = _env_int("MESH_BASI_MAKS", max(3 * interval, 90))
    REGISTRY.register(PengumpulMesh(cuplikan, offline, basi))
    pub.subscribe(saat_menerima, "meshtastic.receive")

    # Penyimpanan histori posisi untuk tab Tracking Node. Gagal membuka
    # database TIDAK menghentikan exporter: modul ini mencatat sendiri
    # kesalahannya dan halaman /lacak menjelaskannya ke pembaca.
    lacak_node.init()
    if not lacak_node.statistik_db().get("aktif"):
        LOG.warning("lacak: riwayat lokasi tidak aktif (%s); tab Tracking Node "
                    "menampilkan penjelasan, sisanya tetap jalan",
                    lacak_node.statistik_db().get("pesan"))

    gambar = baca_gambar()
    LOG.info("gambar halaman: %s", ", ".join(sorted(gambar)) or "tidak ada")
    jalankan_web(listen, exp_port, cuplikan, offline, host, port, gambar)
    LOG.info("tampilan web di http://%s:%d/  (metrik: /metrics, json: /data.json)",
             listen, exp_port)
    LOG.info("node gateway %s:%d", host, port)

    jeda = 5
    while True:
        try:
            sambung(host, port, interval, cuplikan, offline)
        except KeyboardInterrupt:
            LOG.info("dihentikan")
            return 0
        except Exception as e:
            EXPORTER_UP.set(0)
            LOG.warning("koneksi ke node gagal (%s); coba lagi dalam %ds", e, jeda)
            time.sleep(jeda)
            jeda = min(jeda * 2, 60)


if __name__ == "__main__":
    sys.exit(main())
