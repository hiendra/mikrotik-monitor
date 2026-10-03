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
#   meshtastic_exporter_gateway_cadangan            1 bila exporter sedang membaca
#     gateway cadangan (lihat MESH_HOST_CADANGAN di bawah)
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
#   MESH_HOST_CADANGAN alamat gateway cadangan, boleh lebih dari satu dipisah
#                      koma (bawaan: kosong = tanpa cadangan). Bila gateway
#                      utama tidak bisa dihubungi, exporter pindah ke cadangan
#                      lalu kembali mencoba yang utama di putaran berikutnya,
#                      sehingga gateway utama yang pulih dipakai lagi sendiri.
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
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from pubsub import pub
from meshtastic.tcp_interface import TCPInterface

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


def _alamat(host):
    """Alamat gateway yang sedang dipakai.

    `host` boleh berupa teks (pemakaian lama, termasuk oleh uji) atau callable
    yang mengembalikan alamat terkini (SumberGateway.host_aktif). Dengan begitu
    halaman web dan /data.json selalu menunjuk gateway yang BENAR-BENAR sedang
    dibaca, walaupun exporter sudah berpindah ke cadangan setelah start.
    """
    return host() if callable(host) else host


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

    def ganti(self, nodes, gateway=None):
        with self._kunci:
            self._nodes = nodes
            self._gateway = dict(gateway or {})
            self._sekarang = time.time()

    def baca(self):
        with self._kunci:
            return dict(self._nodes), dict(self._gateway), self._sekarang


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
            "lat": pos.get("latitude"),
            "lon": pos.get("longitude"),
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

# Menyala 1 saat exporter sedang memakai gateway CADANGAN (MESH_HOST_CADANGAN)
# karena gateway utama tidak bisa dihubungi. Aturan alert memakai ini supaya
# berpindahnya sumber data tidak berlalu tanpa kabar.
EXPORTER_CADANGAN = Gauge(
    "meshtastic_exporter_gateway_cadangan",
    "1 bila exporter sedang membaca dari gateway cadangan")
# Cermin sederhana untuk halaman web ("utama"/"cadangan"): dibaca dari thread
# permintaan HTTP, diperbarui SumberGateway.pindah saat sumber berpindah.
_SUMBER_CADANGAN = False


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


def data_json(cuplikan, offline, host, port):
    nodes, gateway, sekarang = cuplikan.baca()
    lantai = gateway.get("lantai_snr") or BAWAAN_LANTAI_SNR
    daftar = []
    for node_id, r in sorted(nodes.items()):
        last = r.get("last")
        usia = (sekarang - last) if last else None
        item = dict(r)
        item["node_id"] = node_id
        item["last_heard_seconds"] = usia
        item["online"] = bool(last and usia <= offline)
        # Tingkat mutu sinyal 0-3 (None bila node bukan jalur radio gateway):
        # angkanya bisa dipakai dasbor/alert tanpa menghitung ulang sendiri.
        item["mutu_sinyal"] = (None if (r.get("via") or "").lower() == "mqtt"
                               else mutu_sinyal(r.get("snr"), lantai))
        daftar.append(item)
    return {
        "gateway": {"host": _alamat(host), "port": port,
                    "cadangan": _SUMBER_CADANGAN},
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
        ))


# ------------------------------------------------------------
# Tab "Peta" & halaman lacak per node
# ------------------------------------------------------------
# Halaman utama bisa dibaca dua cara: TABEL (seperti semula) atau PETA.
# Peta memakai data yang sudah ada di /data.json, jadi tidak ada sumber data
# baru yang perlu dirawat. Pustaka peta (Leaflet) dan basemap (OpenStreetMap)
# dimuat dari internet dan hanya saat tab Peta benar-benar dibuka - halaman
# tabel yang menyegar tiap 5 detik tidak ikut mengunduhnya.
#
# Halaman ini menyegar sendiri lewat <meta http-equiv="refresh">. Itu justru
# MERUSAK peta: setiap 5 detik peta dibangun ulang dan posisi/zoom yang sedang
# dilihat hilang. Karena itu di tab Peta penyegaran halaman DIMATIKAN dan
# diganti penyegaran data lewat /data.json (skrip di bawah).
#
# Klik penanda membuka popup berisi data node, dan di dalamnya ada TAUTAN
# OTOMATIS ke halaman lacak node itu: /lacak/<node_id> (mis.
# /lacak/!c483e00a). Halaman itulah yang dibangun oleh halaman_lacak().
GAYA_PETA = """
/* ===== Tab menu & panel ===== */
.tab{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0 0;border-bottom:1px solid #24303c}
.tab-tombol{background:none;border:none;border-bottom:2px solid transparent;color:#8b98a8;font:inherit;font-size:13.5px;padding:9px 15px;cursor:pointer;border-radius:8px 8px 0 0}
.tab-tombol:hover{color:#79c0ff;background:#1a212b}
.tab-tombol.aktif{color:#e6edf3;border-bottom-color:#58a6ff;background:#1a212b}
.panel[hidden]{display:none}
/* ===== Peta ===== */
.peta-alat{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:12px 0}
.peta-alat button,.tombol-tengah,.tombol-lacak{background:#1a212b;border:1px solid #2a3340;color:#e6edf3;border-radius:8px;padding:6px 12px;font:inherit;font-size:12.5px;cursor:pointer;text-decoration:none;display:inline-block}
.peta-alat button:hover,.tombol-tengah:hover,.tombol-lacak:hover{border-color:#3d5a80}
.tombol-lacak{background:#1d3557;color:#79c0ff;border-color:#2c4a6e;font-weight:600}
#peta-kanvas{height:70vh;min-height:420px;border:1px solid #232c38;border-radius:10px;background:#0b0f14}
.peta-kunci{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:12px;color:#8b98a8;margin:10px 0}
.peta-kunci i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px;vertical-align:-1px}
.w-hijau{background:#3fb950}.w-biru{background:#58a6ff}.w-abu{background:#8b98a8}.w-merah{background:#f85149}
.peta-galat{background:#3d1d1d;border:1px solid #f85149;color:#ffb3ad;padding:10px 14px;border-radius:8px;margin:10px 0}
/* ===== Popup node (latar putih bawaan Leaflet) ===== */
.leaflet-popup-content{margin:12px 14px;font:13px/1.5 system-ui,Segoe UI,Roboto,sans-serif;min-width:220px}
.popup-judul{font-weight:600;font-size:14px;color:#1f2328;margin-bottom:1px}
.popup-id{color:#57606a;font-family:ui-monospace,Consolas,monospace;font-size:11.5px;margin-bottom:6px}
.popup-tabel{border-collapse:collapse;margin:8px 0;font-size:12.5px}
.popup-tabel td{padding:2px 12px 2px 0;border:none;white-space:nowrap;color:#1f2328}
.popup-tabel td:first-child{color:#57606a}
.popup-tabel .dim,.popup-lacak .dim{color:#57606a}
.popup-lacak{border-top:1px solid #d0d7de;padding-top:9px;margin-top:9px}
.popup-lacak .mono{font-size:11px;color:#57606a;margin-top:5px;word-break:break-all}
/* ===== Panel rincian (halaman lacak) ===== */
.rincian{background:#1a212b;border:1px solid #2a3340;border-radius:10px;padding:2px 16px;margin:12px 0}
.rincian .baris{display:grid;grid-template-columns:200px 1fr;gap:2px 16px;padding:8px 0;border-top:1px solid #232c38}
.rincian .baris:first-child{border-top:none}
.rincian b{color:#9fb0c3;font-weight:600}
@media (max-width:760px){.rincian .baris{grid-template-columns:1fr}}
"""

# Panel peta di halaman utama. Sengaja berupa rangkaian HTML polos (bukan di
# dalam template berformat persen) supaya tanda persen di CSS/JS di bawah tidak
# perlu ditulis ganda.
PANEL_PETA = """<div id="panel-peta" class="panel" hidden>
<div class="peta-alat">
  <button type="button" id="peta-pas">Pas ke semua node</button>
  <button type="button" id="peta-segar">Segarkan sekarang</button>
  <span class="dim" id="peta-ringkas">memuat data node...</span>
</div>
<div id="peta-galat" class="peta-galat" hidden></div>
<div id="peta-kanvas"></div>
<div class="peta-kunci">
  <span><i class="w-hijau"></i>online, lewat radio</span>
  <span><i class="w-biru"></i>gateway</span>
  <span><i class="w-abu"></i>online, lewat MQTT</span>
  <span><i class="w-merah"></i>offline</span>
  <span class="dim">Klik penanda untuk data node &amp; tautan lacaknya.</span>
</div>
<div class="dim">Peta menyegar sendiri tiap 5 detik <b>tanpa memuat ulang halaman</b>, jadi posisi dan zoom yang Anda pilih tidak hilang. Pustaka peta &amp; basemap diambil dari internet (unpkg &amp; OpenStreetMap); tanpa internet peta tidak tampil, tetapi tab tabel tetap berfungsi.</div>
</div>
"""

# Skrip peta & rincian node. Dipakai DUA halaman supaya tidak ada dua
# salinan logika yang bisa berbeda diam-diam:
#   - halaman utama, di dalam tab "Peta" (window.PETA_SOROT tidak diisi);
#   - halaman /lacak/<id>, satu node disorot & difokuskan (PETA_SOROT diisi,
#     PETA_AUTO=1 supaya peta langsung jalan tanpa tab).
SKRIP_PETA = """<script>
(function(){
  var PETA=null, LAPISAN=null, TIMER=null, SUDAH_PAS=false, SIBUK=false;
  var SOROT=(typeof window.PETA_SOROT==='string')?window.PETA_SOROT:'';
  var POSISI={};
  // Penanda disimpan per id node supaya tiap penyegaran hanya MEMPERBARUI yang
  // sudah ada, bukan menghapus lalu menggambar ulang semuanya.
  var PENANDA={};

  function el(id){ return document.getElementById(id); }
  function esc(s){
    return String(s==null?'':s).replace(/[&<>"']/g, function(c){
      if(c==='&'){ return '&amp;'; }
      if(c==='<'){ return '&lt;'; }
      if(c==='>'){ return '&gt;'; }
      if(c==='"'){ return '&quot;'; }
      return '&#39;';
    });
  }
  function angka(v,digit,satuan){
    if(v===null||v===undefined||v===''){ return '-'; }
    var x=parseFloat(v);
    if(!isFinite(x)){ return '-'; }
    return x.toFixed(digit)+(satuan||'');
  }
  function durasi(d){
    if(d===null||d===undefined){ return '-'; }
    d=Math.max(0,Math.round(d));
    if(d<60){ return d+' detik'; }
    var m=Math.floor(d/60), j=Math.floor(m/60), h=Math.floor(j/24);
    if(j<1){ return m+' menit'; }
    if(h<1){ return j+' jam '+(m%60)+' menit'; }
    return h+' hari '+(j%24)+' jam';
  }
  function baterai(v){
    if(v===null||v===undefined||v===''){ return '-'; }
    var x=parseFloat(v);
    if(!isFinite(x)){ return '-'; }
    if(x>100){ return 'charge &mdash; tersambung listrik/USB'; }
    return x.toFixed(0)+'%';
  }
  function tegangan(v){
    if(v===null||v===undefined||v===''){ return ''; }
    var x=parseFloat(v);
    if(!isFinite(x)||Math.abs(x)<0.05){ return ''; }
    return x.toFixed(2)+' V';
  }
  function mutuKata(m){
    var label=['Nihil','Buruk','Cukup','Baik'];
    if(m===null||m===undefined){ return ''; }
    return label[m]||'';
  }
  function sinyal(n){
    if((n.via||'').toLowerCase()==='mqtt'){ return '<span class="dim">lewat internet (bukan radio gateway)</span>'; }
    if(n.snr===null||n.snr===undefined){ return '-'; }
    var m=mutuKata(n.mutu_sinyal);
    return esc(angka(n.snr,1,' dB'))+(m?(' <span class="dim">&middot; '+m+'</span>'):'');
  }
  function hop(n){
    if(n.hops===null||n.hops===undefined){ return '-'; }
    var h=parseFloat(n.hops), k='';
    if(h===0){ k='langsung ke gateway'; }
    else if(h<=2){ k='dekat'; }
    else if(h<=4){ k='jauh'; }
    else { k='sangat jauh'; }
    return h.toFixed(0)+' <span class="dim">&middot; '+k+'</span>';
  }
  // /data.json mengirim waktu sebagai epoch detik (angka), sedangkan halaman
  // yang dirender server memakai teks "YYYY-MM-DD HH:MM:SS". Formatnya dibuat
  // sama di sini supaya kolom "diperbarui" tidak berubah bentuk setelah peta
  // menyegar sendiri.
  function stempel(epoch){
    if(!epoch){ return '-'; }
    try{
      var d=new Date(parseFloat(epoch)*1000);
      if(isNaN(d.getTime())){ return '-'; }
      function p(n){ return (n<10?'0':'')+n; }
      return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())
        +' '+p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds());
    }catch(e){ return '-'; }
  }
  function viaLencana(via){
    var v=(via||'').toLowerCase();
    if(v==='diri'){ return '<span class="via via-diri">DIRI</span>'; }
    if(v==='lora'){ return '<span class="via via-lora">LORA</span>'; }
    return '<span class="via via-mqtt">MQTT</span>';
  }
  function status(n){
    return n.online ? '<span class="on">ONLINE</span>' : '<span class="off">OFFLINE</span>';
  }
  function warna(n){
    if(!n.online){ return '#f85149'; }
    if(n.via==='diri'){ return '#58a6ff'; }
    if(n.via==='mqtt'){ return '#8b98a8'; }
    return '#3fb950';
  }
  function baris(label,nilai){
    return '<div class="baris"><b>'+label+'</b><span>'+nilai+'</span></div>';
  }
  function namaNode(n){
    var nama=esc(n.long_name||'(tanpa nama)');
    if(n.favorite){ nama='<span class="favorit">&#9733;</span> '+nama; }
    return nama;
  }
  function rincian(n){
    var daya=baterai(n.battery), t=tegangan(n.voltage);
    if(t){ daya+=' <span class="dim">&middot; '+t+'</span>'; }
    if(n.uptime){ daya+=' <span class="dim">&middot; up '+durasi(n.uptime)+'</span>'; }
    var pos=angka(n.lat,5,'')+' / '+angka(n.lon,5,'');
    if(n.alt!==null&&n.alt!==undefined){ pos+=' <span class="dim">&middot; '+angka(n.alt,0,' m')+'</span>'; }
    var env=angka(n.temp,1,' &deg;C');
    if(n.hum!==null&&n.hum!==undefined){ env+=' <span class="dim">&middot; '+angka(n.hum,1,' % RH')+'</span>'; }
    if(n.press!==null&&n.press!==undefined){ env+=' <span class="dim">&middot; '+angka(n.press,0,' hPa')+'</span>'; }
    return baris('Nama', namaNode(n))
      +baris('Node ID', '<span class="mono">'+esc(n.node_id)+'</span>')
      +baris('Status', status(n)+' <span class="dim">&middot; terakhir '+durasi(n.last_heard_seconds)+' lalu ('+stempel(n.last)+')</span>')
      +baris('Jalur paket terakhir', viaLencana(n.via))
      +baris('Sinyal (SNR)', sinyal(n))
      +baris('Hop', hop(n))
      +baris('Baterai / Daya', daya)
      +baris('Kanal / Air TX', angka(n.chan_util,1,'%')+' <span class="dim">&middot; air TX '+angka(n.air_tx,1,'%')+'</span>')
      +baris('Posisi (lat / lon / alt)', pos)
      +baris('Suhu / RH / hPa', env)
      +baris('Perangkat / Peran', esc(n.hw_model||'-')+' <span class="dim">&middot; '+(n.role?esc(n.role):'-')+'</span>')
      +baris('Favorite', n.favorite?'ya &mdash; lebih terlindungi saat daftar node penuh':'tidak');
  }
  function tautanLacak(n){
    var u='/lacak/'+encodeURIComponent(n.node_id);
    return '<div class="popup-lacak"><a class="tombol-lacak" href="'+esc(u)+'">Lacak node ini &rarr;</a>'
      +'<div class="mono">'+esc(u)+'</div></div>';
  }
  function popup(n){
    return '<div class="popup-judul">'+namaNode(n)+'</div>'
      +'<div class="popup-id">'+esc(n.node_id)+'</div>'
      +'<div>'+status(n)+' '+viaLencana(n.via)+'</div>'
      +'<table class="popup-tabel"><tbody>'
      +'<tr><td>Terakhir</td><td>'+durasi(n.last_heard_seconds)+' lalu</td></tr>'
      +'<tr><td>Sinyal</td><td>'+sinyal(n)+'</td></tr>'
      +'<tr><td>Hop</td><td>'+hop(n)+'</td></tr>'
      +'<tr><td>Baterai</td><td>'+baterai(n.battery)+'</td></tr>'
      +'<tr><td>Posisi</td><td>'+angka(n.lat,5,'')+', '+angka(n.lon,5,'')+'</td></tr>'
      +'<tr><td>Ketinggian</td><td>'+(n.alt===null||n.alt===undefined?'-':angka(n.alt,0,' m'))+'</td></tr>'
      +'<tr><td>Perangkat</td><td>'+esc(n.hw_model||'-')+'</td></tr>'
      +'</tbody></table>'
      +'<button type="button" class="tombol-tengah" data-node="'+esc(n.node_id)+'">Tengahin ke peta</button>'
      +tautanLacak(n);
  }

  var leafletDiminta=false, tunggu=[];
  function pakaiLeaflet(fn){
    if(window.L){ fn(); return; }
    tunggu.push(fn);
    if(leafletDiminta){ return; }
    leafletDiminta=true;
    var css=document.createElement('link');
    css.rel='stylesheet';
    css.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);
    var js=document.createElement('script');
    js.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload=function(){ var q=tunggu; tunggu=[]; for(var i=0;i<q.length;i++){ q[i](); } };
    js.onerror=function(){ galatPeta('Pustaka peta (Leaflet) gagal dimuat - butuh sambungan internet ke unpkg.com. Tab tabel tetap berfungsi.'); };
    document.head.appendChild(js);
  }
  function galatPeta(pesan){
    var g=el('peta-galat');
    if(g){ g.textContent=pesan; g.hidden=false; }
  }

  // Tombol "Tengahin ke peta" didengar lewat SATU pendengar di pembungkus
  // popup, bukan onclick per tombol: isi popup diganti tiap 5 detik oleh
  // setPopupContent(), dan kalau tombolnya memakai onclick, penggantian itu
  // membuat tombolnya berhenti bekerja. Pembungkus popup sendiri TIDAK ikut
  // diganti, jadi pendengar di sini tetap hidup. (Pendengar tidak boleh
  // ditaruh di wadah peta: Leaflet menghentikan rambatan klik di dalam popup.)
  function pasangTengahPopup(mar){
    mar.on('popupopen', function(ev){
      var wadah=ev.popup.getElement();
      if(!wadah || wadah.__tengahAda){ return; }
      wadah.__tengahAda=true;
      wadah.addEventListener('click', function(e){
        var t=e.target;
        if(t && t.className && (' '+t.className+' ').indexOf(' tombol-tengah ')>=0){
          var id=t.getAttribute('data-node');
          if(id && POSISI[id]){ PETA.setView(POSISI[id], Math.max(PETA.getZoom(),14)); }
        }
      });
    });
  }

  function gambarPeta(d){
    var nodes=d.node||[];
    var batas=[], tampil=0, tanpa=0, online=0;
    var dilihat={};
    // Penting: JANGAN membersihkan lapisan peta di sini. Membersihkan lalu
    // menggambar ulang tiap 5 detik ikut MENUTUP popup yang sedang dibuka -
    // itulah sebabnya tautan "Lacak node ini" di popup tampak "hilang"
    // sendiri beberapa detik setelah node diklik. Penanda yang sudah ada
    // diperbarui di tempat (posisi, warna, isi popup), jadi popup tetap
    // terbuka dan isinya malah ikut segar. Uji 12d menjaga ini.
    for(var i=0;i<nodes.length;i++){
      var n=nodes[i];
      var lat=parseFloat(n.lat), lon=parseFloat(n.lon);
      if(!isFinite(lat)||!isFinite(lon)||(lat===0&&lon===0)){ tanpa++; continue; }
      dilihat[n.node_id]=true;
      tampil++;
      if(n.online){ online++; }
      POSISI[n.node_id]=[lat,lon];
      batas.push([lat,lon]);
      var jari=(SOROT&&SOROT===n.node_id)?11:7;
      var mar=PENANDA[n.node_id];
      if(mar){
        mar.setLatLng([lat,lon]);
        mar.setStyle({radius:jari, fillColor:warna(n)});
        mar.setTooltipContent(esc(n.long_name||n.node_id));
        mar.setPopupContent(popup(n));
      } else {
        mar=window.L.circleMarker([lat,lon],{
          radius:jari,
          color:'#0f1319', weight:1, fillColor:warna(n), fillOpacity:0.95});
        mar.bindTooltip(esc(n.long_name||n.node_id),{direction:'top'});
        mar.bindPopup(popup(n),{maxWidth:340});
        pasangTengahPopup(mar);
        mar.addTo(LAPISAN);
        PENANDA[n.node_id]=mar;
      }
    }
    // Penanda untuk node yang sudah tidak ada lagi (mis. tergeser keluar
    // NodeDB, atau kehilangan koordinat) baru dibuang di sini.
    for(var id in PENANDA){
      if(!dilihat[id]){
        LAPISAN.removeLayer(PENANDA[id]);
        delete PENANDA[id];
        delete POSISI[id];
      }
    }
    var ringkas=el('peta-ringkas');
    if(ringkas){
      ringkas.textContent=tampil+' node di peta ('+online+' online)'
        +(tanpa?(' - '+tanpa+' node tanpa koordinat tidak dipetakan'):'');
    }
    if(SOROT&&POSISI[SOROT]){
      if(!SUDAH_PAS){ PETA.setView(POSISI[SOROT],14); SUDAH_PAS=true; }
    } else if(!SUDAH_PAS&&batas.length){
      PETA.fitBounds(batas,{padding:[30,30],maxZoom:14});
      SUDAH_PAS=true;
    }
    perbaruiLacak(d);
    var w=el('peta-diperbarui');
    if(w&&d.waktu){ w.textContent=stempel(d.waktu); }
  }

  function perbaruiLacak(d){
    var kotak=el('lacak-rincian');
    if(!kotak||!SOROT){ return; }
    var nodes=d.node||[], n=null;
    for(var i=0;i<nodes.length;i++){ if(nodes[i].node_id===SOROT){ n=nodes[i]; break; } }
    if(!n){
      kotak.innerHTML=baris('Node','<span class="mono">'+esc(SOROT)+'</span> sudah tidak ada di database gateway saat ini.');
      return;
    }
    kotak.innerHTML=rincian(n)+baris('Tautan tetap','<span class="mono">'+esc('/lacak/'+n.node_id)+'</span>');
  }

  function muatPeta(){
    if(SIBUK||!LAPISAN){ return; }
    SIBUK=true;
    var x=new XMLHttpRequest();
    x.open('GET','/data.json?peta=1',true);
    x.onload=function(){
      SIBUK=false;
      if(x.status!==200){ galatPeta('Gagal membaca /data.json (status '+x.status+').'); return; }
      var d;
      try{ d=JSON.parse(x.responseText); }catch(e){ galatPeta('Data /data.json tidak bisa dibaca.'); return; }
      var g=el('peta-galat'); if(g){ g.hidden=true; }
      gambarPeta(d);
    };
    x.onerror=function(){ SIBUK=false; galatPeta('Tidak bisa menyambung ke exporter untuk menyegarkan peta.'); };
    x.send();
  }

  function mulaiPeta(){
    if(!el('peta-kanvas')){ return; }
    pakaiLeaflet(function(){
      if(!PETA){
        PETA=window.L.map('peta-kanvas',{scrollWheelZoom:true}).setView([-2.2,118.0],5);
        window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
          maxZoom:19, attribution:'&copy; OpenStreetMap'}).addTo(PETA);
        LAPISAN=window.L.layerGroup().addTo(PETA);
        var pas=el('peta-pas');
        if(pas){ pas.onclick=function(){ SUDAH_PAS=false; if(SOROT&&POSISI[SOROT]){ PETA.setView(POSISI[SOROT],14); SUDAH_PAS=true; } else { muatPeta(); } }; }
        var seg=el('peta-segar');
        if(seg){ seg.onclick=function(){ muatPeta(); }; }
      }
      PETA.invalidateSize();
      muatPeta();
      if(!TIMER){ TIMER=setInterval(muatPeta,5000); }
    });
  }

  window.mulaiPeta=mulaiPeta;
  if(window.PETA_AUTO){
    if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded',mulaiPeta); }
    else { mulaiPeta(); }
  }
})();
</script>
"""

# Skrip menu tab (halaman utama). Dipasang SESUDAH SKRIP_PETA supaya
# window.mulaiPeta sudah ada saat tab Peta dibuka.
SKRIP_TAB = """<script>
// Menu tab "Tabel" / "Peta". Tab yang dipakai disimpan di localStorage supaya
// penyegaran halaman (meta refresh tiap 5 detik) tidak mengembalikannya ke
// Tabel. Di tab Peta penyegaran halaman itu dimatikan - kalau tidak, peta
// dibangun ulang tiap 5 detik dan posisi/zoom yang sedang dilihat hilang.
(function(){
  var KUNCI='meshid-tab-1';
  var panel={tabel:document.getElementById('panel-tabel'),peta:document.getElementById('panel-peta')};
  var tombol=document.querySelectorAll('[data-tab]');
  var aktif=null;
  function baca(){ try{ return localStorage.getItem(KUNCI)||'tabel'; }catch(e){ return 'tabel'; } }
  function simpan(n){ try{ localStorage.setItem(KUNCI,n); }catch(e){} }
  function matikanSegar(){
    var m=document.querySelector('meta[http-equiv="refresh"]');
    if(m&&m.parentNode){ m.parentNode.removeChild(m); }
  }
  function tampilkan(n){
    if(!panel[n]){ n='tabel'; }
    aktif=n;
    for(var t in panel){ if(panel[t]){ panel[t].hidden=(t!==n); } }
    for(var i=0;i<tombol.length;i++){
      var ini=tombol[i].getAttribute('data-tab')===n;
      tombol[i].className='tab-tombol'+(ini?' aktif':'');
      tombol[i].setAttribute('aria-selected', ini?'true':'false');
    }
    simpan(n);
    if(n==='peta'){
      matikanSegar();
      if(window.mulaiPeta){ window.mulaiPeta(); }
    }
  }
  for(var i=0;i<tombol.length;i++){
    tombol[i].addEventListener('click', function(){
      var n=this.getAttribute('data-tab');
      if(n===aktif){ return; }
      if(n==='tabel'){
        // Kembali ke tabel: muat ulang supaya penyegaran 5 detik hidup lagi.
        simpan('tabel');
        location.reload();
        return;
      }
      tampilkan(n);
    });
  }
  tampilkan(baca());
})();
</script>
"""


def _esc(teks):
    """Escape HTML untuk masukan dari URL (id node pada /lacak/).

    Id node datang dari alamat yang diketik pengunjung, jadi TIDAK boleh
    ditempel mentah ke halaman - itu jalan masuk HTML/script injection.
    """
    return (str(teks if teks is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;").replace("'", "&#39;"))


def halaman_lacak(cuplikan, offline, host, port, node_id, exporter_up, logo=True):
    """Halaman pelacakan satu node: /lacak/<node_id>.

    Inilah tujuan tautan otomatis di popup peta. Mengembalikan None bila node
    tidak ada di database gateway saat ini - pemanggil yang memutuskan 404.
    """
    nodes, gateway, sekarang = cuplikan.baca()
    r = nodes.get(node_id)
    if r is None:
        return None
    last = r.get("last")
    usia = (sekarang - last) if last else None
    online = bool(last and usia <= offline)
    lencana = ("<span class='on'>ONLINE</span>" if online
               else "<span class='off'>OFFLINE</span>")
    via = (r.get("via") or "").lower()
    kelas_via = {"diri": "via-diri", "lora": "via-lora"}.get(via, "via-mqtt")
    nama_polos = r.get("long_name") or ("(tanpa nama)")
    ikon = ('<link rel="icon" type="image/png" href="/favicon.png">'
            '<link rel="apple-touch-icon" href="/logo.png">') if logo else ""
    gambar_kepala = ('<img class="logo" src="/logo.png" width="42" height="42"'
                     ' alt="Logo MeshNode ID">') if logo else ""
    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lacak %(nama_polos)s - Meshnode-ID Monitor</title>
%(ikon)s
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{background:#0f1319;color:#e6edf3;font:13.5px/1.5 system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:18px 20px 44px;max-width:1750px}
h1{font-size:19px;margin:0 0 3px}
a{color:#58a6ff}
.dim{color:#8b98a8;font-size:12px}
.mono{font-family:ui-monospace,Consolas,monospace}
.on{color:#3fb950;font-weight:600}.off{color:#f85149;font-weight:600}
.favorit{color:#e3b341}
.via{display:inline-block;border-radius:4px;padding:1px 7px;font-size:10.5px;font-weight:600;letter-spacing:.04em}
.via-diri{background:#1d3557;color:#79c0ff}
.via-lora{background:#173a24;color:#56d364}
.via-mqtt{background:#2b3038;color:#9fb0c3}
.kepala{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;justify-content:space-between;border-bottom:1px solid #24303c;padding-bottom:12px}
.merek{display:flex;align-items:center;gap:12px}
.logo{width:42px;height:42px;flex:0 0 auto;display:block}
.kaki{margin-top:22px;padding-top:12px;border-top:1px solid #24303c}
.kaki a{display:inline-block;background:#1a212b;border:1px solid #2a3340;border-radius:8px;padding:5px 11px;font-size:12px;text-decoration:none;margin-right:8px}
%(gaya_peta)s
</style></head><body>
<div class="kepala">
  <div class="merek">%(gambar)s
    <div>
      <h1>Lacak node: %(nama)s</h1>
      <div class="dim"><span class="mono">%(node_id)s</span> &middot; <span id="lacak-status">%(lencana)s <span class="via %(kelas_via)s">%(via_teks)s</span></span> &middot; diperbarui <span class="mono" id="peta-diperbarui">%(waktu)s</span></div>
    </div>
  </div>
  <div class="dim">gateway <span class="mono">%(host)s:%(port)s</span> &middot; sumber <b>%(sumber)s</b> &middot; exporter %(teks_up)s</div>
</div>
<div id="peta-galat" class="peta-galat" hidden></div>
<div id="peta-kanvas"></div>
<div class="peta-kunci">
  <span><i class="w-hijau"></i>online, lewat radio</span>
  <span><i class="w-biru"></i>gateway</span>
  <span><i class="w-abu"></i>online, lewat MQTT</span>
  <span><i class="w-merah"></i>offline</span>
  <span class="dim">Node yang dilacak disorot lebih besar. Klik penanda lain untuk membuka datanya.</span>
</div>
<div id="lacak-rincian" class="rincian"><div class="baris"><b>Memuat</b><span class="dim">mengambil data dari /data.json...</span></div></div>
<noscript><div class="peta-galat">Halaman ini butuh JavaScript untuk peta dan data live. Daftar lengkap semua node tetap tersedia di <a href="/">halaman utama</a>.</div></noscript>
<div class="kaki dim"><a href="/">&#8592; Kembali ke monitor node</a><a href="/data.json">/data.json</a><a href="/metrics">/metrics</a> &nbsp;Peta &amp; data menyegar sendiri tiap 5 detik.</div>
<script>window.PETA_SOROT=%(sorot_js)s; window.PETA_AUTO=true;</script>
%(skrip_peta)s
</body></html>""" % {
        "nama": _esc(nama_polos), "nama_polos": _esc(nama_polos),
        "node_id": _esc(node_id), "sorot_js": json.dumps(node_id),
        "lencana": lencana, "kelas_via": kelas_via,
        "via_teks": (r.get("via") or "").upper(),
        "host": _esc(_alamat(host)), "port": port,
        "sumber": "cadangan" if _SUMBER_CADANGAN else "utama",
        "waktu": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(sekarang)),
        "ikon": ikon, "gambar": gambar_kepala,
        "teks_up": "terhubung" if exporter_up else "terputus",
        "gaya_peta": GAYA_PETA, "skrip_peta": SKRIP_PETA,
    }


def halaman_tidak_ada(node_id):
    """Halaman 404 untuk /lacak/<id> yang tidak ada di database gateway."""
    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Node tidak ditemukan - Meshnode-ID Monitor</title>
<style>
:root{color-scheme:dark}
body{background:#0f1319;color:#e6edf3;font:13.5px/1.5 system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:40px 20px;max-width:900px}
h1{font-size:19px}
a{color:#58a6ff}
.dim{color:#8b98a8;font-size:12.5px}
.mono{font-family:ui-monospace,Consolas,monospace}
.kaki{margin-top:22px;padding-top:12px;border-top:1px solid #24303c}
</style></head><body>
<h1>Node tidak ditemukan</h1>
<div class="dim">Node <span class="mono">%(node)s</span> tidak ada di database gateway saat ini. Node bisa saja baru saja tergeser keluar dari daftar (lihat tabel di halaman utama), belum pernah terdengar, atau id-nya salah ketik.</div>
<div class="kaki dim"><a href="/">Kembali ke monitor node</a></div>
</body></html>""" % {"node": _esc(node_id)}


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
        baris_diri = "<tr><td colspan='12' class='dim'>-</td></tr>"
    if not baris_lora:
        baris_lora = ("<tr><td colspan='12' class='dim'>Belum ada node yang "
                      "terbukti tersambung langsung ke gateway.</td></tr>")
    if not baris_ragu:
        baris_ragu = "<tr><td colspan='12' class='dim'>-</td></tr>"
    if not baris_mqtt:
        baris_mqtt = ("<tr><td colspan='12' class='dim'>Tidak ada node dari MQTT "
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
        "<th>Lat / Lon / Alt</th></tr>")

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
<title>Meshnode-ID Monitor</title>
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
%(gaya_peta)s
</style></head><body>
<div class="kepala">
  <div class="merek">%(gambar)s
    <div>
      <h1>Meshnode-ID Monitor</h1>
      <div class="dim">Gateway <span class="mono">%(host)s:%(port)s</span> &middot; sumber <b>%(sumber)s</b> &middot; preset <span class="mono">%(preset_gw)s</span> &middot; diperbarui <span class="mono" id="peta-diperbarui">%(waktu)s</span></div>
    </div>
  </div>
  <div class="status %(kelas_up)s"><span class="titik"></span> exporter %(teks_up)s</div>
</div>

<div class="tab" role="tablist">
  <button type="button" class="tab-tombol aktif" data-tab="tabel" role="tab" aria-selected="true">Tabel node</button>
  <button type="button" class="tab-tombol" data-tab="peta" role="tab" aria-selected="false">Peta langsung</button>
</div>

<div id="panel-tabel" class="panel">
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
<div class="kaki dim">Halaman menyegar otomatis tiap 5 detik.&nbsp; <a href="/data.json">/data.json</a><a href="/metrics">/metrics</a></div>
</div>
%(panel_peta)s
%(skrip_peta)s
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
</script>
%(skrip_tab)s
</body></html>""" % {
        "peringatan": peringatan,
        "host": _alamat(host), "port": port,
        "sumber": "cadangan" if _SUMBER_CADANGAN else "utama",
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
        "gaya_peta": GAYA_PETA,
        "panel_peta": PANEL_PETA,
        "skrip_peta": SKRIP_PETA,
        "skrip_tab": SKRIP_TAB,
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
                elif jalur == "/lacak" or jalur.startswith("/lacak/"):
                    # Tujuan tautan otomatis di popup peta: /lacak/<node_id>.
                    # Node yang tidak ada dijawab 404 dengan halaman sendiri,
                    # bukan halaman utama - supaya tautan yang rusak terlihat
                    # rusak, bukan diam-diam menampilkan data lain.
                    node_id = unquote(jalur[len("/lacak"):]).strip("/").strip()
                    hlm = halaman_lacak(cuplikan, offline, host, port, node_id,
                                        EXPORTER_UP._value.get(), bool(lampiran))
                    if hlm is None:
                        self._kirim(404, "text/html; charset=utf-8",
                                    halaman_tidak_ada(node_id))
                    else:
                        self._kirim(200, "text/html; charset=utf-8", hlm)
                else:
                    self._kirim(200, "text/html; charset=utf-8",
                                halaman_html(cuplikan, offline, host, port,
                                             EXPORTER_UP._value.get(),
                                             bool(lampiran)))
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                LOG.debug("gagal melayani permintaan %s", self.path, exc_info=True)

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


def daftar_tujuan(utama, cadangan):
    """Urutan tujuan koneksi: utama dulu, lalu cadangan (dipisah koma/spasi).

    Daftar dipakai bergilir: bila gateway utama mati, exporter pindah ke
    cadangan; bila cadangan pun mati, ia kembali mencoba yang utama. Jadi
    begitu gateway utama pulih, exporter kembali ke sana tanpa perlu di-restart.
    """
    hasil = [utama]
    for bagian in (cadangan or "").replace(",", " ").split():
        if bagian and bagian not in hasil:
            hasil.append(bagian)
    return hasil


class SumberGateway:
    """Alamat gateway yang SEDANG dibaca; bisa berpindah ke cadangan.

    Halaman web dan /data.json harus menampilkan gateway yang BENAR-BENAR
    sedang dibaca, bukan yang dikonfigurasi. Karena isinya bisa berpindah saat
    loop koneksi berganti host, objek ini diserahkan ke bagian tampilan lewat
    `host_aktif` (dibaca _alamat) supaya tiap permintaan membaca alamat terkini.
    """

    def __init__(self, utama, cadangan=()):
        self._kunci = threading.Lock()
        self._utama = utama
        self._host = utama
        self._cadangan = list(cadangan)

    def pindah(self, host):
        global _SUMBER_CADANGAN
        with self._kunci:
            self._host = host
        _SUMBER_CADANGAN = host != self._utama
        EXPORTER_CADANGAN.set(1 if _SUMBER_CADANGAN else 0)

    def host_aktif(self):
        with self._kunci:
            return self._host


def sambung(host, port, interval, cuplikan):
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
            jumlah = kumpulkan(iface, cuplikan)
            LOG.debug("memperbarui %d node", jumlah)

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
            time.sleep(interval)
    finally:
        try:
            iface.close()
        except Exception:
            LOG.debug("gagal menutup interface", exc_info=True)


def main():
    host = _env("MESH_HOST", "192.168.20.31")
    cadangan = _env("MESH_HOST_CADANGAN", "")
    tujuan = daftar_tujuan(host, cadangan)
    sumber = SumberGateway(host, tujuan[1:])
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

    gambar = baca_gambar()
    LOG.info("gambar halaman: %s", ", ".join(sorted(gambar)) or "tidak ada")
    # host_aktif (bukan host) supaya halaman menampilkan gateway yang sedang
    # dibaca - penting saat exporter sudah berpindah ke cadangan.
    jalankan_web(listen, exp_port, cuplikan, offline, sumber.host_aktif, port,
                 gambar)
    LOG.info("tampilan web di http://%s:%d/  (metrik: /metrics, json: /data.json)",
             listen, exp_port)
    LOG.info("node gateway %s:%d", host, port)
    if len(tujuan) > 1:
        LOG.info("gateway cadangan: %s", ", ".join(tujuan[1:]))

    # Bergilir antar tujuan: utama dulu, lalu cadangan. Kegagalan memindahkan
    # sasaran ke tujuan berikutnya, jadi begitu gateway utama pulih exporter
    # kembali ke sana sendiri tanpa perlu di-restart.
    idx = 0
    jeda = 5
    while True:
        kini = tujuan[idx]
        sumber.pindah(kini)
        try:
            sambung(kini, port, interval, cuplikan)
        except KeyboardInterrupt:
            LOG.info("dihentikan")
            return 0
        except Exception as e:
            EXPORTER_UP.set(0)
            if len(tujuan) > 1:
                idx = (idx + 1) % len(tujuan)
                LOG.warning("gateway %s gagal (%s); pindah ke %s",
                            kini, e, tujuan[idx])
                time.sleep(min(jeda, 15))
            else:
                LOG.warning("koneksi ke node gagal (%s); coba lagi dalam %ds",
                            e, jeda)
                time.sleep(jeda)
                jeda = min(jeda * 2, 60)


if __name__ == "__main__":
    sys.exit(main())
