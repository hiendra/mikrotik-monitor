#!/usr/bin/env python3
# ============================================================
# mqtt-downlink.py - matikan DOWNLINK MQTT di gateway Meshtastic
# ============================================================
# Ini PENYEMBUH, bukan obat. Menjawab akar masalah dari reset-node.py:
# gateway menarik paket dari broker MQTT publik, dan tiap pengirim yang
# lewat MQTT ikut masuk ke daftar node. Hasilnya NodeDB penuh oleh node
# internet (195 dari 200) sehingga node RF sendiri terancam tergeser keluar.
#
# Alat ini mematikan hanya ARUS MASUK dari MQTT (downlink), sementara
# uplink tetap hidup - jadi node Anda masih bisa melapor ke MQTT/map.
#
# Tombol yang dipakai
# -------------------
#   * ChannelSettings.downlink_enabled  (per kanal) - gate utama: bila mati,
#     paket yang datang dari MQTT untuk kanal itu tidak diolah lagi, sehingga
#     pengirimnya tidak ditambahkan ke NodeDB.
#   * MQTTConfig.proxy_to_client_enabled (opsional, --matikan-proxy).
#     KOREKSI 28 Sep 2026: ini BUKAN "meneruskan trafik MQTT ke klien API".
#     Dokumentasi resmi Meshtastic: "If true, let the device use the client's
#     (e.g. your phone's) network connection to connect to the MQTT server."
#     Jadi arahnya kebalikan - node memakai internet MILIK KLIEN. Untuk node
#     yang internetnya dari WiFi sendiri (kasus gateway ini), proxy harus MATI;
#     membiarkannya hidup tanpa klien yang menyediakan koneksi bisa mengganggu
#     uplink MQTT node itu sendiri. Uji lapangan 28 Sep 2026: dengan proxy
#     hidup, selama 2,5 menit 0 paket MQTT sampai ke klien API - jadi tombol ini
#     memang tidak ada gunanya untuk bot yang membaca broker.
#
# Pakai
# -----
#   ./venv/Scripts/python mqtt-downlink.py                 # PERIKSA SAJA
#   ./venv/Scripts/python mqtt-downlink.py --ya            # matikan downlink
#   ./venv/Scripts/python mqtt-downlink.py --ya --kanal 0
#   ./venv/Scripts/python mqtt-downlink.py --ya --matikan-proxy
#   ./venv/Scripts/python mqtt-downlink.py --ya --nyalakan  # kembalikan
#
# Opsi
# ----
#   --host / --port            alamat gateway (bawaan 192.168.20.31:4403)
#   --ya                       benar-benar tulis (tanpa ini hanya periksa)
#   --kanal N[,M]              batasi ke kanal tertentu (bawaan: semua kanal
#                              aktif yang downlink-nya masih hidup)
#   --matikan-proxy            matikan juga proxy_to_client_enabled pada MQTT
#   --nyalakan                 kebalikannya: hidupkan lagi downlink (rollback)
#   --tanpa-notif              jangan kirim kabar ke ntfy
#
# Lingkungan: MESH_HOST, MESH_PORT, NTFY_SERVER, NTFY_TOPIK, NTFY_LOKAL,
#             NTFY_TOKEN
#
# Catatan: menulis setelan kanal/modul membuat gateway memuat ulang setelannya
# (biasanya disertai reboot singkat). Notifier tidak akan menganggap itu
# masalah, tetapi penghitung reboot gateway akan naik satu.
# ============================================================

import importlib.util
import os
import sys
import time

AKAR = os.path.dirname(os.path.abspath(__file__))
BAWAAN_HOST = os.environ.get("MESH_HOST", "192.168.20.31")
BAWAAN_PORT = int(os.environ.get("MESH_PORT", "4403"))
ROLE = {0: "DISABLED", 1: "PRIMARY", 2: "SECONDARY"}

USAGE = """mqtt-downlink.py - matikan downlink MQTT di gateway Meshtastic

  mqtt-downlink.py                     periksa saja (bawaan, tidak mengubah)
  mqtt-downlink.py --ya                matikan downlink pada kanal aktif
  mqtt-downlink.py --ya --kanal 0
  mqtt-downlink.py --ya --matikan-proxy
  mqtt-downlink.py --ya --nyalakan     kembalikan (rollback)

  --host H --port P    alamat gateway (bawaan 192.168.20.31:4403)
  --tanpa-notif        jangan kirim kabar ke ntfy
"""


def muat_notifier():
    jalur = os.path.join(AKAR, "notif-meshtastic.py")
    if not os.path.exists(jalur):
        return None
    spec = importlib.util.spec_from_file_location("notif_meshtastic", jalur)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def kabarkan(judul, pesan, prioritas="default", tag="electric_plug"):
    modul = muat_notifier()
    if modul is None:
        print("  (notif-meshtastic.py tidak ada, kabar ntfy dilewati)")
        return
    kanal, galat = modul.kirim(
        judul, pesan, prioritas, tag,
        os.environ.get("NTFY_SERVER", modul.BAWAAN_SERVER),
        os.environ.get("NTFY_TOPIK", modul.BAWAAN_TOPIK),
        os.environ.get("NTFY_TOKEN") or None,
        os.environ.get("NTFY_LOKAL", modul.BAWAAN_LOKAL))
    if kanal:
        print("  Kabar terkirim via %s" % kanal)
    else:
        print("  Kabar GAGAL terkirim: %s" % galat, file=sys.stderr)


def sambung(host, port, tunggu=25):
    from meshtastic.tcp_interface import TCPInterface
    iface = TCPInterface(hostname=host, portNumber=port)
    batas = time.time() + tunggu
    while time.time() < batas:
        ln = getattr(iface, "localNode", None)
        if ln is not None and getattr(ln, "channels", None):
            break
        time.sleep(1)
    return iface


def daftar_kanal(iface):
    ln = iface.localNode
    keluaran = []
    for pos, ch in enumerate(ln.channels or []):
        s = getattr(ch, "settings", None)
        if s is None:
            continue
        keluaran.append({
            "pos": pos,
            "nomor": getattr(s, "channel_num", pos),
            "nama": getattr(s, "name", "") or "",
            "role": ROLE.get(int(getattr(ch, "role", 0)), "?"),
            "uplink": bool(getattr(s, "uplink_enabled", False)),
            "downlink": bool(getattr(s, "downlink_enabled", False)),
            "psk": bool(getattr(s, "psk", b"")),
        })
    return keluaran


def tampilkan(kanal):
    print("  %-4s %-10s %-14s %-7s %-9s %s"
          % ("pos", "kanal", "nama", "role", "uplink", "downlink"))
    for k in kanal:
        print("  %-4d %-10s %-14s %-7s %-9s %s"
              % (k["pos"], k["nomor"], (k["nama"] or "(tanpa nama)")[:14],
                 k["role"], "hidup" if k["uplink"] else "mati",
                 "HIDUP" if k["downlink"] else "mati"))


def kondisi_mqtt(iface):
    try:
        m = iface.localNode.moduleConfig.mqtt
    except Exception:
        return None
    return {
        "enabled": bool(getattr(m, "enabled", False)),
        "proxy": bool(getattr(m, "proxy_to_client_enabled", False)),
        "json": bool(getattr(m, "json_enabled", False)),
        "address": getattr(m, "address", "") or "",
        "root": getattr(m, "root", "") or "",
    }


def baca_opsi(argv):
    opsi = {"host": BAWAAN_HOST, "port": BAWAAN_PORT, "ya": False,
            "kanal": None, "matikan_proxy": False, "nyalakan": False,
            "notif": True}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(USAGE)
            return None
        if a == "--ya":
            opsi["ya"] = True; i += 1; continue
        if a == "--matikan-proxy":
            opsi["matikan_proxy"] = True; i += 1; continue
        if a == "--nyalakan":
            opsi["nyalakan"] = True; i += 1; continue
        if a == "--tanpa-notif":
            opsi["notif"] = False; i += 1; continue
        if a in ("--host", "--port", "--kanal"):
            if i + 1 >= len(argv):
                print("%s butuh nilai." % a, file=sys.stderr)
                return 2
            nilai = argv[i + 1]
            if a == "--host":
                opsi["host"] = nilai
            elif a == "--port":
                opsi["port"] = int(nilai)
            else:
                opsi["kanal"] = {int(x) for x in nilai.replace(",", " ").split() if x}
            i += 2; continue
        print("Opsi tidak dikenal: %s" % a, file=sys.stderr)
        return 2
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

    sasaran_kata = "HIDUPKAN kembali" if opsi["nyalakan"] else "MATIKAN"
    print("=" * 62)
    print(" KENDALI DOWNLINK MQTT GATEWAY MESHTASTIC")
    print("=" * 62)
    print(" Mode: %s%s\n" % (
        "TULIS SETELAN -> " if opsi["ya"] else "PERIKSA SAJA (tidak mengubah apa pun) -> ",
        sasaran_kata))

    try:
        iface = sambung(opsi["host"], opsi["port"])
    except Exception as e:
        print("Gagal menyambung ke %s:%d (%s)" % (opsi["host"], opsi["port"], e),
              file=sys.stderr)
        return 1

    try:
        kanal = daftar_kanal(iface)
        if not kanal:
            print("Tidak bisa membaca daftar kanal dari gateway.", file=sys.stderr)
            return 1
        print("Kanal gateway:")
        tampilkan(kanal)
        print()

        mq = kondisi_mqtt(iface)
        if mq:
            print("Modul MQTT:")
            print("  aktif (enabled)   : %s" % ("hidup" if mq["enabled"] else "mati"))
            print("  proxy ke klien    : %s" % ("hidup" if mq["proxy"] else "mati"))
            print("  alamat server     : %s" % (mq["address"] or "-"))
            print("  root/topik        : %s" % (mq["root"] or "-"))
            print()

        # --- tentukan sasaran ---
        # Keadaan downlink yang DIINGINKAN: mati saat normal, hidup saat --nyalakan.
        ingin_hidup = opsi["nyalakan"]
        sasaran = []
        for k in kanal:
            if k["role"] == "DISABLED":
                continue
            if opsi["kanal"] is not None and k["nomor"] not in opsi["kanal"] \
                    and k["pos"] not in opsi["kanal"]:
                continue
            if k["downlink"] != ingin_hidup:
                sasaran.append(k)

        mau_proxy = (not ingin_hidup) and opsi["matikan_proxy"] and bool(mq) and mq["proxy"]
        if not sasaran and not mau_proxy:
            print("Tidak ada yang perlu diubah (setelan sudah sesuai keinginan).")
            return 0

        print("Rencana perubahan:")
        for k in sasaran:
            print("  kanal %s (%s): downlink %s -> %s"
                  % (k["nomor"], k["nama"] or "tanpa nama",
                     "HIDUP" if k["downlink"] else "mati",
                     "HIDUP" if ingin_hidup else "mati"))
        if mau_proxy:
            print("  modul MQTT: proxy_to_client_enabled hidup -> mati")
        print()

        if not opsi["ya"]:
            print("TIDAK ada perubahan dilakukan. Untuk menerapkan tambahkan --ya.")
            print()
            print("Setelah diterapkan, pantau isi database gateway beberapa jam:")
            print("  ./venv/Scripts/python reset-node.py      # lihat isi NodeDB")
            print("Bila jumlahnya berhenti naik, downlink memang gerbangnya.")
            return 0

        # --- terapkan ---
        berubah = []
        for k in sasaran:
            ch = iface.localNode.channels[k["pos"]]
            ch.settings.downlink_enabled = ingin_hidup
            iface.localNode.writeChannel(k["pos"])
            berubah.append("kanal %s (%s)" % (k["nomor"], k["nama"] or "tanpa nama"))
            time.sleep(1.5)

        if mau_proxy:
            iface.localNode.moduleConfig.mqtt.proxy_to_client_enabled = False
            iface.localNode.writeConfig("mqtt")
            berubah.append("proxy_to_client_enabled")
            time.sleep(1.5)

        print("Dikirim: %s" % ", ".join(berubah))
        time.sleep(8)

        try:
            iface.close()
        except Exception:
            pass
        iface = sambung(opsi["host"], opsi["port"])
        sesudah = daftar_kanal(iface)
        print("\nKanal setelah perubahan:")
        tampilkan(sesudah)

        if opsi["notif"]:
            aksi = "dihidupkan lagi" if opsi["nyalakan"] else "dimatikan"
            kabarkan(
                "Downlink MQTT gateway %s" % aksi,
                ("Kanal %s: downlink %s.\nUplink tetap seperti semula.\n\n"
                 "Pantau isi NodeDB beberapa jam; bila berhenti naik, sumber node "
                 "internet sudah tertutup."
                 % (", ".join(berubah), aksi)),
                prioritas="default")
        return 0
    finally:
        try:
            iface.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
