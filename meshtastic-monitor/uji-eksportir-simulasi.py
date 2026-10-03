#!/usr/bin/env python3
# ============================================================
# uji-eksportir-simulasi.py - halaman monitor node utama (:9208) tanpa hardware
# ============================================================
# Menguji jawaban atas satu pertanyaan: bisakah HALAMAN EXPORTER yang dipakai
# memantau jaringan sungguhan terisi tanpa satu pun radio?
#
# Rantai yang diuji persis seperti produksi, hanya radionya yang dipalsukan:
#
#   1. NodeSimulasi (dari simulasi-node.py) berbicara PhoneAPI Meshtastic
#      yang asli di 127.0.0.1 - protokol yang sama dengan meshtasticd;
#   2. NodeDB-nya DISEMAI lebih dulu dengan jaringan yang masuk akal: gateway,
#      dua tower router, dan sebuah tracker - lengkap dengan peran, perangkat,
#      baterai, tegangan, SNR, hop, dan posisi;
#   3. exporter-meshtastic.py dijalankan sebagai PROSES TERPISAH, menunjuk ke
#      node itu lewat MESH_HOST/MESH_PORT - jalur yang sama dengan produksi;
#   4. uji ini membaca halaman /, /data.json, dan /metrics yang sungguhan
#      lewat HTTP, lalu memeriksa nama, SNR, hop, peran, preset radio, dan
#      lantai SNR meter sinyal.
#
# Kontrol negatif (bagian 5) menjalankan rantai yang sama TANPA menyemai. Yang
# diperiksa justru kebalikannya: halaman HARUS hanya berisi node gateway, dan
# nama tower semaian HARUS tidak ada. Bila bagian itu tetap hijau, maka hijau
# di bagian utama tidak membuktikan apa pun - karena itu kontrol ini ikut
# dijalankan sebagai bagian wajib uji ini.
#
# Pakai
# -----
#   ./venv/Scripts/python uji-eksportir-simulasi.py
#
# Hasil: LULUS bila seluruh rangkaian terbukti; selain itu GAGAL (kode keluar 1).
# Tidak menyentuh radio, tidak memakai airtime, tidak menghubungi broker.
# ============================================================

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

AKAR = os.path.dirname(os.path.abspath(__file__))

LOLOS = 0
GAGAL = 0
SEMENTARA = None


def lolos(pesan):
    global LOLOS
    LOLOS += 1
    print("  [LULUS] %s" % pesan, flush=True)


def gagal(pesan):
    global GAGAL
    GAGAL += 1
    print("  [GAGAL] %s" % pesan, flush=True)


def info(pesan):
    print("          -> %s" % pesan, flush=True)


def bagian(judul):
    print("\n%s" % judul, flush=True)


def muat(nama):
    path = os.path.join(AKAR, nama)
    if not os.path.exists(path):
        print("ERROR: %s tidak ada di %s" % (nama, AKAR), file=sys.stderr)
        raise SystemExit(2)
    spec = importlib.util.spec_from_file_location(
        nama.replace("-", "_").replace(".py", ""), path)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def porta_bebas():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def ambil(alamat, batas=5):
    try:
        with urllib.request.urlopen(alamat, timeout=batas) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def tunggu(syarat, detik=25, jeda=0.3):
    batas = time.time() + detik
    while time.time() < batas:
        if syarat():
            return True
        time.sleep(jeda)
    return False


# ------------------------------------------------------------
# Jaringan yang disemai: apa yang biasa dilihat operator
# ------------------------------------------------------------

def semaian(simulasi):
    """NodeDB awal: gateway, dua tower router, dan satu tracker.

    Angka SNR sengaja dibuat beragam terhadap lantai LONG_FAST (-17.5 dB),
    supaya meter sinyal di halaman benar-benar teruji: tower dekat => \"Baik\",
    sensor jauh => \"Cukup\". Nama dan perangkat pun nyata supaya halaman bisa
    dibandingkan dengan jaringan sungguhan tanpa merasa sedang melihat mockup.
    """
    gw = simulasi.GW
    return [
        {"num": simulasi.DIRI_NUM, "nama": "GATEWAY-SIM", "nama_singkat": "GWSI",
         "posisi": {"lat": gw[0], "lon": gw[1], "alt": 12}, "hw": "HELTEC_V3",
         "role": "ROUTER", "kanal": 0,
         "device": {"kanal": 4.2, "udara": 1.1, "uptime": 86400}},
        {"num": 0x11AA0001, "nama": "TOWER-UTARA", "nama_singkat": "TWRN",
         "posisi": {"lat": gw[0] + 0.02, "lon": gw[1] + 0.01, "alt": 40},
         "hw": "HELTEC_V3", "role": "ROUTER", "kanal": 0, "snr": 7.0, "hop": 0,
         "device": {"baterai": 100, "tegangan": 4.10, "kanal": 3.1,
                    "udara": 0.9, "uptime": 604800}},
        {"num": 0x11AA0002, "nama": "SENSOR-KEBUN", "nama_singkat": "SNSK",
         "posisi": {"lat": gw[0] - 0.03, "lon": gw[1] + 0.04, "alt": 8},
         "hw": "SEEED_XIAO_S3", "role": "SENSOR", "kanal": 0, "snr": -21.0,
         "hop": 1, "device": {"baterai": 62, "tegangan": 3.72, "kanal": 1.2,
                              "udara": 0.3, "uptime": 43200}},
        {"num": 0x11AA0003, "nama": "TRACKER-01", "nama_singkat": "TRK1",
         "posisi": {"lat": gw[0] - 0.004, "lon": gw[1] + 0.007, "alt": 15},
         "hw": "SEEED_XIAO_S3", "role": "TRACKER", "kanal": 0, "snr": 1.5,
         "hop": 0, "device": {"baterai": 74, "tegangan": 3.81, "kanal": 1.8,
                              "udara": 0.5, "uptime": 21600}},
    ]


JUMLAH_SEMAIAN = 4


# ------------------------------------------------------------
# Menjalankan exporter ke node simulasi
# ------------------------------------------------------------

def mulai_exporter(node_port, cara):
    """Popen exporter menunjuk ke node simulasi; kembalikan (proses, alamat)."""
    exp_port = porta_bebas()
    env = dict(os.environ)
    env.update(cara)
    env.update({
        "MESH_HOST": "127.0.0.1", "MESH_PORT": str(node_port),
        "MESH_EXPORTER_PORT": str(exp_port), "MESH_LISTEN": "127.0.0.1",
        "MESH_INTERVAL": "5", "MESH_TUNGGU_AWAL": "15", "MESH_LOG": "WARNING",
    })
    log = open(os.path.join(SEMENTARA, "exporter-%d.log" % exp_port), "wb")
    proses = subprocess.Popen(
        [sys.executable, os.path.join(AKAR, "exporter-meshtastic.py")],
        stdout=log, stderr=subprocess.STDOUT, cwd=SEMENTARA, env=env)
    alamat = "http://127.0.0.1:%d" % exp_port
    ok = tunggu(lambda: ambil("%s/data.json" % alamat, batas=3)[0] == 200,
                detik=30)
    return proses, alamat, ok


def henti(proses):
    if proses is None or proses.poll() is not None:
        return
    proses.terminate()
    try:
        proses.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proses.kill()


def data_json(alamat):
    kode, isi = ambil("%s/data.json" % alamat, batas=5)
    if kode != 200:
        return None
    try:
        return json.loads(isi)
    except ValueError:
        return None


# ------------------------------------------------------------
# Uji
# ------------------------------------------------------------

def uji():
    global LOLOS, GAGAL
    LOLOS = GAGAL = 0

    print("=" * 62)
    print(" UJI HALAMAN EXPORTER :9208 TANPA HARDWARE")
    print("=" * 62, flush=True)

    mesh_pb2 = __import__("meshtastic.protobuf.mesh_pb2", fromlist=["x"])
    portnums_pb2 = __import__("meshtastic.protobuf.portnums_pb2", fromlist=["x"])
    channel_pb2 = __import__("meshtastic.protobuf.channel_pb2", fromlist=["x"])
    module_config_pb2 = __import__("meshtastic.protobuf.module_config_pb2",
                                   fromlist=["x"])
    simulasi = muat("simulasi-node.py")
    suntik = muat("suntik-paket.py")

    bagian("1. Node simulasi disemai dengan jaringan yang masuk akal")
    node = simulasi.NodeSimulasi(mesh_pb2, portnums_pb2, channel_pb2,
                                 module_config_pb2, suntik.bongkar)
    node.semai_node(semaian(simulasi))
    info("node simulasi PhoneAPI di 127.0.0.1:%d, %d node disemai"
         % (node.port, JUMLAH_SEMAIAN))
    if len(node.node_db) == JUMLAH_SEMAIAN:
        lolos("NodeDB node simulasi berisi %d node sebelum klien menyambung"
              % len(node.node_db))
    else:
        gagal("NodeDB berisi %d node, diharapkan %d"
              % (len(node.node_db), JUMLAH_SEMAIAN))

    proses = None
    try:
        bagian("2. Exporter membaca node simulasi lewat MESH_HOST/MESH_PORT")
        proses, alamat, ok = mulai_exporter(node.port, {})
        if not ok:
            gagal("exporter tidak menjawab /data.json di %s" % alamat)
            return akhir(node, proses)
        lolos("exporter hidup dan melayani %s/data.json" % alamat)

        terisi = tunggu(lambda: (data_json(alamat) or {}).get("jumlah_node",
                                                             0) >= JUMLAH_SEMAIAN,
                        detik=25)
        d = data_json(alamat) or {}
        if terisi:
            lolos("halaman exporter melihat semua %d node semaian" % JUMLAH_SEMAIAN)
        else:
            gagal("hanya %r dari %d node semaian terlihat"
                  % (d.get("jumlah_node"), JUMLAH_SEMAIAN))
            return akhir(node, proses)

        nama = {n.get("long_name") for n in (d.get("node") or [])}
        perlu = {"GATEWAY-SIM", "TOWER-UTARA", "SENSOR-KEBUN", "TRACKER-01"}
        if perlu <= nama:
            lolos("nama node tampil apa adanya: %s" % ", ".join(sorted(nama)))
        else:
            gagal("nama node hilang: %s" % ", ".join(sorted(perlu - nama)))

        bagian("3. Isi node benar, bukan sekadar ada")
        per = {n.get("long_name"): n for n in (d.get("node") or [])}
        twr = per.get("TOWER-UTARA") or {}
        if twr.get("snr") == 7.0 and twr.get("hops") == 0 and twr.get("via") == "lora":
            lolos("TOWER-UTARA: SNR 7.0 dB, 0 hop, jalur lora - persis yang disemai")
        else:
            gagal("TOWER-UTARA salah: snr=%r hop=%r via=%r"
                  % (twr.get("snr"), twr.get("hops"), twr.get("via")))
        if twr.get("role") == "ROUTER" and twr.get("hw_model") == "HELTEC_V3":
            lolos("peran & perangkat terbaca dari NodeInfo semaian: %s / %s"
                  % (twr.get("role"), twr.get("hw_model")))
        else:
            gagal("peran/perangkat TOWER-UTARA salah: %r / %r"
                  % (twr.get("role"), twr.get("hw_model")))
        if twr.get("mutu_sinyal") == 3:
            lolos("meter sinyal menilai TOWER-UTARA \"Baik\" (mutu 3) terhadap "
                  "lantai LONG_FAST")
        else:
            gagal("mutu sinyal TOWER-UTARA = %r, diharapkan 3" % twr.get("mutu_sinyal"))
        sen = per.get("SENSOR-KEBUN") or {}
        if sen.get("mutu_sinyal") == 2:
            lolos("meter sinyal membedakan SENSOR-KEBUN sebagai \"Cukup\" "
                  "(mutu 2, SNR -21 dB terhadap lantai -17.5 dB)")
        else:
            gagal("mutu sinyal SENSOR-KEBUN = %r, diharapkan 2" % sen.get("mutu_sinyal"))

        bagian("4. Kesehatan gateway & preset radio")
        gk = d.get("kesehatan_gateway") or {}
        # Versi firmware yang dikirim node simulasi di metadata handshake.
        if gk.get("firmware") == "2.7.15.simulasi":
            lolos("versi firmware gateway terbaca dari metadata: %s" % gk.get("firmware"))
        else:
            gagal("firmware gateway salah: %r" % gk.get("firmware"))
        if gk.get("preset") == "LONG_FAST" and abs(float(gk.get("lantai_snr")) + 17.5) < 0.01:
            lolos("preset radio LONG_FAST => lantai SNR -17.5 dB (angka nyata, "
                  "bukan asumsi)")
        else:
            gagal("preset/lantai gateway salah: preset=%r lantai=%r"
                  % (gk.get("preset"), gk.get("lantai_snr")))
        if gk.get("role") == "ROUTER":
            lolos("peran gateway dari metadata: %s" % gk.get("role"))
        else:
            gagal("peran gateway salah: %r" % gk.get("role"))

        bagian("5. Halaman HTML & metrik Prometheus yang dilihat operator")
        kode, html = ambil("%s/" % alamat)
        kurang = [p for p in ("GATEWAY-SIM", "TOWER-UTARA", "SENSOR-KEBUN",
                              "LONG_FAST", "ONLINE")
                  if kode != 200 or p not in html]
        if not kurang:
            lolos("halaman / memuat nama node, preset LONG_FAST, dan lencana ONLINE")
        else:
            gagal("halaman / kehilangan: %r (HTTP %s)" % (kurang, kode))
        kode, isi = ambil("%s/metrics" % alamat)
        perlu_metrik = ["meshtastic_node_info", "meshtastic_node_snr_db",
                        'node_id="!11aa0001"', "meshtastic_device_battery_level_percent"]
        kurang = [p for p in perlu_metrik if kode != 200 or p not in isi]
        if not kurang:
            lolos("metrik Prometheus memuat node_id semaian & baterainya")
        else:
            gagal("metrik kehilangan: %r (HTTP %s)" % (kurang, kode))

        bagian("6. Kontrol negatif: tanpa semaian, hanya gateway yang muncul")
        henti(proses)
        proses = None
        kosong = simulasi.NodeSimulasi(mesh_pb2, portnums_pb2, channel_pb2,
                                       module_config_pb2, suntik.bongkar)
        try:
            proses, alamat2, ok = mulai_exporter(kosong.port, {})
            if not ok:
                gagal("exporter kontrol negatif tidak menjawab")
            else:
                # Tunggu jabat tangan selesai (gateway minimal sudah muncul)
                # sebelum menilai: membaca terlalu cepat menghasilkan 0 node
                # dan kontrol negatif gagal palsu.
                tunggu(lambda: ((data_json(alamat2) or {}).get("jumlah_node")
                                or 0) >= 1, detik=10)
                d2 = data_json(alamat2) or {}
                nama2 = {n.get("long_name") for n in (d2.get("node") or [])}
                if d2.get("jumlah_node") == 1 and "TOWER-UTARA" not in nama2:
                    lolos("tanpa semaian halaman hanya berisi 1 node gateway - "
                          "jadi %d node di bagian utama memang datang dari semaian, "
                          "bukan dikarang halaman" % JUMLAH_SEMAIAN)
                else:
                    gagal("kontrol negatif tidak sah: jumlah=%r nama=%r"
                          % (d2.get("jumlah_node"), nama2))
        finally:
            henti(proses)
            proses = None
            kosong.tutup()

        return akhir(node, proses)

    finally:
        henti(proses)
        node.tutup()


def akhir(node, proses):
    print("\n" + "=" * 62)
    print(" HASIL: %d lulus, %d gagal" % (LOLOS, GAGAL))
    print("=" * 62)
    if GAGAL:
        print(" Halaman exporter TIDAK terbukti bisa diisi tanpa hardware.")
        return 1
    print(" Halaman monitor node utama (:9208) terbukti terisi dari node simulasi.")
    print(" Yang TIDAK dibuktikan: perilaku radio sungguhan (lantai derau, airtime).")
    return 0


def main(argv):
    global SEMENTARA
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    for a in argv:
        if a in ("-h", "--help"):
            print(__doc__ or "uji-eksportir-simulasi.py")
            return 0
        print("Opsi tidak dikenal: %s" % a, file=sys.stderr)
        return 2

    SEMENTARA = tempfile.mkdtemp(prefix="uji-eksportir-")
    try:
        return uji()
    finally:
        for nama in os.listdir(SEMENTARA):
            try:
                os.remove(os.path.join(SEMENTARA, nama))
            except OSError:
                pass
        try:
            os.rmdir(SEMENTARA)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
