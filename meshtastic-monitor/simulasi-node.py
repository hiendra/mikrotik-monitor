#!/usr/bin/env python3
# ============================================================
# simulasi-node.py - node Meshtastic tiruan (uji tanpa radio, tanpa hardware)
# ============================================================
# Modul bersama: berbicara protokol PhoneAPI Meshtastic yang asli (bingkai
# 0x94 0xC3 + protobuf ToRadio/FromRadio) persis seperti meshtasticd, hanya
# radionya yang tidak ada. Dipakai oleh uji yang menjalankan klien produksi
# (exporter) terhadap node tiruan ini.
#
# Isi:
#   * NodeSimulasi  - node tiruan: jabat tangan, NodeDB, bongkar suntikan
#                     dari suntik-paket.py, teruskan paket ke klien;
#   * muat/porta_bebas - memuat modul ber-tanda hubung di folder ini;
#   * ambil/tunggu_http/tunggu - pemeriksa HTTP kecil untuk uji.
#
# Posisi gateway simulasi (GW) harus sama dengan --gw penyuntik, sebab jarak
# tiap kontak dihitung dari posisi gateway di NodeDB.
# ============================================================

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

AKAR = os.path.dirname(os.path.abspath(__file__))
AWAL1, AWAL2 = 0x94, 0xC3

# Posisi gateway simulasi. Harus sama dengan --gw yang dipakai penyuntik,
# sebab jarak tiap kontak dihitung dari posisi gateway di NodeDB.
GW = (-6.2, 106.8)

# Node "gateway" tiruan (klien menyambung ke node ini).
DIRI_NUM = 0x00ABC123

def muat(nama):
    path = os.path.join(AKAR, nama)
    if not os.path.exists(path):
        print("ERROR: %s tidak ada di %s" % (nama, AKAR), file=sys.stderr)
        raise SystemExit(2)
    spec = importlib.util.spec_from_file_location(nama.replace("-", "_").replace(".py", ""), path)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def porta_bebas():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


# ------------------------------------------------------------
# Node Meshtastic tiruan - cukup untuk melayani PhoneAPI
# ------------------------------------------------------------

class NodeSimulasi:
    """Node tiruan: menjawab jabat tangan, membongkar suntikan, meneruskan paket.

    Yang ditiru dari firmware:
      * MeshService::handleToRadio -> SimRadio::unpackAndReceive() untuk paket
        ber-portnum SIMULATOR_APP (dibongkar dengan modul suntik-paket.py);
      * pengiriman ke klien lewat FromRadio (sendToPhone);
      * NodeDB yang menyimpan user.id + position, lalu disiarkan sebagai node_info.
    """

    def __init__(self, mesh_pb2, portnums_pb2, channel_pb2, module_config_pb2, bongkar,
                 porta=0, firmware="2.7.15.simulasi"):
        # `porta` bawaan 0 = pilih porta acak (perilaku lama). Uji yang perlu
        # mematikan lalu menghidupkan node di ALAMAT YANG SAMA - mis. membuktikan
        # klien kembali menyambung - mengisi porta tetap di sini, sebab klien
        # ke alamat yang ditentukan di baris perintah.
        self.firmware = firmware
        self.mesh_pb2 = mesh_pb2
        self.portnums_pb2 = portnums_pb2
        self.channel_pb2 = channel_pb2
        self.module_config_pb2 = module_config_pb2
        self.bongkar = bongkar

        self.soket = socket.socket()
        self.soket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soket.bind(("127.0.0.1", int(porta)))
        self.soket.listen(4)
        self.port = self.soket.getsockname()[1]

        self.berhenti = threading.Event()
        self.kunci = threading.Lock()
        self.koneksi = []
        self.balasan = []      # pesan teks yang dipancarkan klien (bukan kita)
        self.suntikan = []     # paket yang disuntikkan, sudah dibongkar
        self.node_db = {}      # num -> {"nama":..., "posisi":...}
        self.galat_jabat = []
        # Dipakai kontrol negatif: paket tetap diterima & dibongkar, tapi sengaja
        # TIDAK diteruskan ke klien. Kalau uji tetap hijau dalam keadaan ini,
        # ujinya tidak benar-benar menguji apa pun.
        self.jangan_teruskan = False

        threading.Thread(target=self._layani, name="node-sim", daemon=True).start()

    # ---- jaringan ----

    def _layani(self):
        self.soket.settimeout(0.5)
        while not self.berhenti.is_set():
            try:
                conn, _ = self.soket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self.kunci:
                self.koneksi.append(conn)
            threading.Thread(target=self._baca, args=(conn,), daemon=True).start()

    def _baca(self, conn):
        buf = b""
        conn.settimeout(0.5)
        while not self.berhenti.is_set():
            try:
                keping = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not keping:
                break
            buf += keping
            while True:
                i = buf.find(bytes([AWAL1, AWAL2]))
                if i < 0:
                    buf = b""
                    break
                if len(buf) < i + 4:
                    buf = buf[i:]
                    break
                panjang = (buf[i + 2] << 8) | buf[i + 3]
                if len(buf) < i + 4 + panjang:
                    buf = buf[i:]
                    break
                muatan = buf[i + 4:i + 4 + panjang]
                buf = buf[i + 4 + panjang:]
                try:
                    self._tangani(conn, muatan)
                except Exception as e:      # jangan matikan node karena satu paket
                    self.galat_jabat.append("%s: %s" % (type(e).__name__, e))
        try:
            conn.close()
        except OSError:
            pass
        with self.kunci:
            if conn in self.koneksi:
                self.koneksi.remove(conn)

    def _kirim(self, conn, pesan):
        muatan = pesan.SerializeToString()
        try:
            conn.sendall(bytes([AWAL1, AWAL2, (len(muatan) >> 8) & 0xFF,
                                len(muatan) & 0xFF]) + muatan)
        except OSError:
            pass

    def _siarkan(self, pesan, kecuali=None):
        with self.kunci:
            daftar = [k for k in self.koneksi if k is not kecuali]
        for k in daftar:
            self._kirim(k, pesan)

    # ---- protokol ----

    def _jabat_tangan(self, conn, config_id):
        """Urutan yang ditunggu pustaka meshtastic sebelum 'tersambung'."""
        fr = self.mesh_pb2.FromRadio()
        fr.my_info.my_node_num = DIRI_NUM
        # Versi firmware TIDAK di sini: MyNodeInfo tidak punya field itu di
        # pustaka 2.7 (ada di DeviceMetadata). Menyetelnya melempar AttributeError
        # dan seluruh jabat tangan gagal - ini sempat terjadi saat uji ini dibuat.
        fr.my_info.pio_env = "simulasi"
        # Jumlah isi NodeDB & jumlah reboot dipakai halaman exporter untuk
        # menilai kesehatan gateway. Kirim angka yang masuk akal, bukan nol -
        # nol terbaca sebagai "database kosong" dan mengalihkan perhatian.
        fr.my_info.nodedb_count = len(self.node_db) + 1
        fr.my_info.reboot_count = 12
        self._kirim(conn, fr)

        # Metadata perangkat: versi firmware tampil di kepala halaman exporter,
        # dan peran/perangkat ikut dikirim supaya kepala itu tidak kosong.
        meta = self.mesh_pb2.FromRadio()
        meta.metadata.firmware_version = self.firmware
        self._setel_enum(meta.metadata, "role", "ROUTER")
        meta.metadata.hw_model = self.mesh_pb2.HELTEC_V3
        self._kirim(conn, meta)

        # PENTING: posisi gateway ikut dikirim, sebab klien menghitung jarak tiap
        # kontak dari posisi gateway di NodeDB. Tanpa ini semua jarak kosong.
        diri = self.node_db.get(DIRI_NUM) or {}
        self._kirim(conn, self._pesan_node_info(
            DIRI_NUM, diri.get("nama") or "GATEWAY-SIM",
            diri.get("posisi") or {"lat": GW[0], "lon": GW[1], "alt": 12}))

        # NodeDB yang sudah kita pelajari dikirim ulang ke klien baru. Syaratnya
        # punya NAMA atau posisi: node yang baru mengumumkan namanya pun sudah
        # berguna (mis. halaman exporter menampilkannya sebagai node jalur MQTT).
        for num, simpul in list(self.node_db.items()):
            if num == DIRI_NUM:
                continue
            if simpul.get("posisi") or simpul.get("nama"):
                self._kirim(conn, self._pesan_node_info(num, simpul.get("nama"),
                                                        simpul.get("posisi")))

        # Setelan radio gateway. Halaman exporter menghitung LANTAI DEMODULASI
        # meter sinyal dari preset ini; tanpa config ini setelan radio terbaca
        # kosong dan halaman menandai lantainya "diasumsikan". Preset LONG_FAST
        # dipilih karena itu bawaan pabrik Meshtastic (lantai SNR -17.5 dB).
        try:
            from meshtastic.protobuf import config_pb2
            cfg = self.mesh_pb2.FromRadio()
            cfg.config.lora.use_preset = True
            cfg.config.lora.modem_preset = (
                config_pb2.Config.LoRaConfig.ModemPreset.LONG_FAST)
            cfg.config.lora.hop_limit = 3
            self._kirim(conn, cfg)
        except Exception:
            pass

        # Modul MQTT dimatikan supaya klien tidak menghubungi broker sungguhan.
        mc = self.mesh_pb2.FromRadio()
        mc.moduleConfig.mqtt.enabled = False
        self._kirim(conn, mc)

        ch = self.mesh_pb2.FromRadio()
        ch.channel.role = self.channel_pb2.Channel.Role.PRIMARY
        ch.channel.settings.channel_num = 0
        ch.channel.settings.name = "LongFast"
        ch.channel.settings.uplink_enabled = True
        ch.channel.settings.downlink_enabled = False
        self._kirim(conn, ch)

        akhir = self.mesh_pb2.FromRadio()
        akhir.config_complete_id = config_id
        self._kirim(conn, akhir)

    def _setel_enum(self, pesan, nama_field, nama_nilai):
        """Setel field enum dari NAMANYA; diam bila nama itu tidak dikenal.

        Nama perangkat dan peran berbeda antar versi pustaka, jadi node simulasi
        tidak boleh gagal hanya karena satu nama enum tidak ada. Peran (Role)
        bukan enum milik mesh_pb2 melainkan milik config_pb2, karena itu dicoba
        di dua tempat.
        """
        if not nama_nilai:
            return
        nilai = getattr(self.mesh_pb2, nama_nilai, None)
        if nilai is None:
            try:
                from meshtastic.protobuf import config_pb2
                nilai = config_pb2.Config.DeviceConfig.Role.Value(nama_nilai)
            except Exception:
                return
        try:
            setattr(pesan, nama_field, nilai)
        except Exception:
            pass

    def semai_node(self, daftar):
        """Isi NodeDB dengan node virtual lengkap SEBELUM klien menyambung.

        Dipakai agar halaman exporter punya jaringan yang masuk
        akal sejak detik pertama: nama, posisi, SNR, hop, baterai, tegangan,
        kanal, udara TX, perangkat, peran, dan kapan terakhir terdengar.
        """
        for simpul in daftar:
            self.node_db[int(simpul["num"])] = dict(simpul)

    def _pesan_node_info(self, num, nama, posisi):
        """NodeInfo selengkap yang kita ketahui tentang satu node.

        Pustaka meshtastic menyimpan SELURUH isi NodeInfo ke dict node di klien
        (node.update(asDict["nodeInfo"])), lalu halaman exporter membacanya:
        snr, hopsAway, lastHeard, deviceMetrics, user.hwModel, user.role. Jadi
        satu NodeInfo yang lengkap sudah membuat satu baris tabel terisi penuh -
        tidak perlu paket tambahan untuk itu.
        """
        info = self.node_db.get(num) or {}
        ni = self.mesh_pb2.NodeInfo(num=num)
        ni.user.id = "!%08x" % num        # wajib: pustaka mengindeks nodes[user.id]
        if nama:
            ni.user.long_name = nama[:39]
            ni.user.short_name = nama[:4].upper()
        if info.get("nama_singkat"):
            ni.user.short_name = info["nama_singkat"][:4]
        self._setel_enum(ni.user, "hw_model", info.get("hw"))
        self._setel_enum(ni.user, "role", info.get("role"))
        if posisi:
            ni.position.latitude_i = int(round(posisi["lat"] * 1e7))
            ni.position.longitude_i = int(round(posisi["lon"] * 1e7))
            ni.position.altitude = int(posisi.get("alt") or 0)
        # snr bertipe float di NodeInfo, sisanya uint32.
        for kunci, nilai in (("snr", info.get("snr")),
                             ("hops_away", info.get("hop")),
                             ("channel", info.get("kanal")),
                             ("last_heard", info.get("terakhir"))):
            if nilai is not None:
                setattr(ni, kunci, nilai)
        if info.get("favorit"):
            ni.is_favorite = True
        if info.get("via_mqtt"):
            ni.via_mqtt = True
        dm = info.get("device")
        if dm:
            from meshtastic.protobuf import telemetry_pb2
            m = telemetry_pb2.DeviceMetrics()
            for kunci, nilai in (("battery_level", dm.get("baterai")),
                                 ("voltage", dm.get("tegangan")),
                                 ("channel_utilization", dm.get("kanal")),
                                 ("air_util_tx", dm.get("udara")),
                                 ("uptime_seconds", dm.get("uptime"))):
                if nilai is not None:
                    setattr(m, kunci, nilai)
            ni.device_metrics.CopyFrom(m)
        fr = self.mesh_pb2.FromRadio()
        fr.node_info.CopyFrom(ni)
        return fr

    def _tangani(self, conn, muatan):
        tr = self.mesh_pb2.ToRadio()
        tr.ParseFromString(muatan)

        if tr.want_config_id:
            self._jabat_tangan(conn, tr.want_config_id)
            return
        if tr.disconnect:
            return
        if not tr.HasField("packet"):
            return

        p = tr.packet
        if p.WhichOneof("payload_variant") == "decoded" and \
                p.decoded.portnum == self.portnums_pb2.PortNum.SIMULATOR_APP:
            self._suntikan(conn, p)
            return

        # Bukan suntikan: ini pesan yang dipancarkan klien ke udara.
        decoded = p.decoded if p.WhichOneof("payload_variant") == "decoded" else None
        if decoded is not None and decoded.portnum == self.portnums_pb2.PortNum.TEXT_MESSAGE_APP:
            self.balasan.append({
                "dari": getattr(p, "from"), "ke": p.to, "kanal": p.channel,
                "teks": decoded.payload.decode("utf-8", "replace")})

    def _suntikan(self, conn, p):
        """Cermin SimRadio::unpackAndReceive + sendToPhone."""
        tr = self.mesh_pb2.ToRadio()
        tr.packet.CopyFrom(p)
        hasil = self.bongkar(tr)
        self.suntikan.append(hasil)

        num = hasil["dari"]
        simpul = self.node_db.setdefault(num, {"nama": None, "posisi": None})
        if hasil["batin"] == self.portnums_pb2.PortNum.POSITION_APP and hasil["posisi"]:
            simpul["posisi"] = hasil["posisi"]
        elif hasil["batin"] == self.portnums_pb2.PortNum.NODEINFO_APP and hasil["nama"]:
            simpul["nama"] = hasil["nama"][0]

        if self.jangan_teruskan:
            return

        # node_info DIDAHULUKAN: klien butuh posisi di NodeDB-nya sebelum paket
        # teks tiba, sebab jarak dihitung saat kontak dicatat.
        if simpul.get("posisi"):
            self._siarkan(self._pesan_node_info(num, simpul.get("nama"),
                                                simpul["posisi"]), kecuali=conn)

        # Paket yang sudah dibongkar, dikirim ke klien lain (kecuali penyuntik).
        z = self.mesh_pb2.MeshPacket()
        z.CopyFrom(p)
        z.decoded.portnum = hasil["batin"]
        z.decoded.payload = hasil["muatan"]
        fr = self.mesh_pb2.FromRadio()
        fr.packet.CopyFrom(z)
        self._siarkan(fr, kecuali=conn)

    def tutup(self):
        self.berhenti.set()
        try:
            self.soket.close()
        except OSError:
            pass
        with self.kunci:
            for k in list(self.koneksi):
                try:
                    k.close()
                except OSError:
                    pass
            self.koneksi = []


# ------------------------------------------------------------
# HTTP kecil
# ------------------------------------------------------------

def ambil(alamat, batas=5):
    try:
        with urllib.request.urlopen(alamat, timeout=batas) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def tunggu_http(alamat, detik=25):
    batas = time.time() + detik
    while time.time() < batas:
        kode, _ = ambil(alamat, batas=2)
        if kode == 200:
            return True
        time.sleep(0.4)
    return False


def tunggu(syarat, detik=15, jeda=0.3):
    batas = time.time() + detik
    while time.time() < batas:
        if syarat():
            return True
        time.sleep(jeda)
    return False


