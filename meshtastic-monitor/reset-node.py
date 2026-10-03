#!/usr/bin/env python3
# ============================================================
# reset-node.py - kosongkan daftar node (NodeDB) gateway Meshtastic
# ============================================================
# Menjawab masalah: daftar node gateway penuh oleh node yang masuk lewat MQTT
# (mesh publik), sehingga node RF sendiri terancam tergeser keluar. Alat ini
# memerintahkan gateway mengosongkan daftar itu.
#
# !! BACA DULU - INI OBAT SEMENTARA !!
# Selama *downlink MQTT* masih hidup di gateway, ratusan node internet akan
# masuk kembali dalam hitungan jam. Jadi reset berkala memberi manfaat singkat,
# tetapi TIDAK menghilangkan sebabnya. Perbaikan yang benar: matikan downlink
# MQTT, pakai broker sendiri, atau channel privat.
#
# Efek samping yang perlu disadari:
#   * daftar node jadi KOSONG, termasuk node RF Anda - mereka akan terdaftar
#     ulang begitu terdengar lagi (bisa beberapa jam untuk node yang jarang
#     memancar seperti ROUTER);
#   * tanda **Favorite** ikut hilang bersama entri node, jadi perlu ditandai
#     ulang setelah node terdengar kembali;
#   * ada jeda singkat saat node belum mengenal siapa pun di sekitarnya.
#
# Pakai
# -----
#   ./venv/Scripts/python reset-node.py                 # PERIKSA SAJA (bawaan)
#   ./venv/Scripts/python reset-node.py --ya            # benar-benar reset
#   ./venv/Scripts/python reset-node.py --ya --hanya-jika-penuh 190
#   ./venv/Scripts/python reset-node.py --ya --abaikan-ambang
#
# Opsi
# ----
#   --host / --port          alamat node gateway (bawaan 192.168.20.31:4403)
#   --ya                     benar-benar jalankan reset (tanpa ini hanya periksa)
#   --hanya-jika-penuh N     reset hanya bila isi database >= N (bawaan 190)
#   --abaikan-ambang         jalankan tanpa memeriksa ambang
#   --jendela-notif DETIK    lama notifier menahan alarm "node hilang" setelah
#                            reset (bawaan 1800), karena reset MEMANG
#                            mengosongkan daftar
#   --jeda-min-jam JAM       lewati reset bila reset terakhir < JAM yang lalu
#                            (bawaan 0 = nonaktif). Scheduler 2 harian memakai
#                            36 agar tidak dobel saat layanan di-restart.
#   --tanpa-notif            jangan kirim kabar ke ntfy setelah reset
#
# Penjadwalan: pakai meshtastic-reset.timer (systemd) - lihat README.
#
# Lingkungan: MESH_HOST, MESH_PORT, NTFY_SERVER, NTFY_TOPIK, NTFY_LOKAL,
#             NTFY_TOKEN
#
# Aman secara bawaan: tanpa --ya, alat ini hanya MEMBACA dan menguji jalur
# admin (permintaan metadata), tidak mengubah apa pun.
# ============================================================

import importlib.util
import json
import os
import sys
import time

AKAR = os.path.dirname(os.path.abspath(__file__))
BAWAAN_HOST = os.environ.get("MESH_HOST", "192.168.20.31")
BAWAAN_PORT = int(os.environ.get("MESH_PORT", "4403"))
BAWAAN_AMBANG = 190
BAWAAN_JENDELA = 1800
BAWAAN_JEDA_MIN = 0
MARKER = os.path.join(AKAR, "reset-terakhir.json")

USAGE = """reset-node.py - kosongkan daftar node (NodeDB) gateway Meshtastic

  reset-node.py                          periksa saja (bawaan, tidak mengubah)
  reset-node.py --ya                     benar-benar reset
  reset-node.py --ya --hanya-jika-penuh 190
  reset-node.py --ya --jeda-min-jam 36   lewati bila reset terakhir < 36 jam

  --host H --port P         alamat gateway (bawaan 192.168.20.31:4403)
  --abaikan-ambang          jalankan tanpa memeriksa ambang isi database
  --jendela-notif DETIK     lama notifier menahan alarm "node hilang" (1800)
  --tanpa-notif             jangan kirim kabar ke ntfy setelah reset
"""


def field(obj, *nama):
    """Ambil field protobuf; terima camelCase maupun snake_case."""
    if obj is None:
        return None
    for n in nama:
        try:
            nilai = getattr(obj, n)
        except AttributeError:
            continue
        if nilai is not None:
            return nilai
    return None


def jam_teks(detik):
    if detik is None:
        return "-"
    detik = int(max(0, detik))
    jam, sisa = divmod(detik, 3600)
    menit, _ = divmod(sisa, 60)
    if jam >= 24:
        return "%d hari %d jam" % (jam // 24, jam % 24)
    if jam:
        return "%d jam %d menit" % (jam, menit)
    if menit:
        return "%d menit" % menit
    return "%d detik" % detik


def baca_kondisi(iface):
    nodes = iface.nodes or {}
    lora, mqtt, fav = [], [], []
    for nid, n in nodes.items():
        n = n or {}
        if n.get("viaMqtt"):
            mqtt.append(nid)
        else:
            lora.append(nid)
        if n.get("isFavorite"):
            fav.append(nid)
    mi = getattr(iface, "myInfo", None)
    return {
        "jumlah": len(nodes),
        "lora": lora,
        "mqtt": len(mqtt),
        "favorit": fav,
        "nodedb": field(mi, "nodedbCount", "nodedb_count"),
        "reboot": field(mi, "rebootCount", "reboot_count"),
    }


def nama_dari(iface, nid):
    return ((iface.nodes or {}).get(nid) or {}).get("user", {}).get("longName") or nid


def tampilkan(kondisi, iface):
    print("  Isi database      : %s entri (dilaporkan node: %s)"
          % (kondisi["jumlah"], kondisi["nodedb"]))
    print("  Node jalur radio  : %d %s"
          % (len(kondisi["lora"]),
             ", ".join(nama_dari(iface, x) for x in kondisi["lora"][:8]) or ""))
    print("  Node jalur MQTT   : %d" % kondisi["mqtt"])
    fav = kondisi["favorit"]
    print("  Node ditandai Fav : %d %s"
          % (len(fav), ", ".join(nama_dari(iface, x) for x in fav[:8]) or ""))
    # Peringatan: reset menghapus Favorite, jadi sorot node RF yang ditandai.
    fav_lora = [x for x in fav if x in kondisi["lora"]]
    kurang = [x for x in kondisi["lora"] if x not in fav]
    if fav_lora:
        print("    (favorit jalur radio: %s)"
              % ", ".join(nama_dari(iface, x) for x in fav_lora))
    if kurang:
        print("    (belum Favorite: %s)"
              % ", ".join(nama_dari(iface, x) for x in kurang))
        print("    -> RESET akan menghapus Favorite yang ada. Tandai ulang setelah")
        print("       node terdengar kembali (lihat README).")


def muat_notifier():
    """Pakai fungsi kirim() dari notif-meshtastic.py agar kanal sama."""
    jalur = os.path.join(AKAR, "notif-meshtastic.py")
    if not os.path.exists(jalur):
        return None
    spec = importlib.util.spec_from_file_location("notif_meshtastic", jalur)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def kabarkan(judul, pesan, prioritas="default", tag="recycle"):
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
    while time.time() < batas and not iface.nodes:
        time.sleep(1)
    return iface


def baca_opsi(argv):
    opsi = {"host": BAWAAN_HOST, "port": BAWAAN_PORT, "ya": False,
            "hanya_jika_penuh": BAWAAN_AMBANG, "abaikan_ambang": False,
            "jendela": BAWAAN_JENDELA, "jeda_min": BAWAAN_JEDA_MIN,
            "notif": True}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(USAGE)
            return None
        if a == "--ya":
            opsi["ya"] = True; i += 1; continue
        if a == "--abaikan-ambang":
            opsi["abaikan_ambang"] = True; i += 1; continue
        if a == "--tanpa-notif":
            opsi["notif"] = False; i += 1; continue
        if a in ("--host", "--port", "--hanya-jika-penuh", "--jendela-notif",
                 "--jeda-min-jam"):
            if i + 1 >= len(argv):
                print("%s butuh nilai." % a, file=sys.stderr)
                return 2
            nilai = argv[i + 1]
            if a == "--host":
                opsi["host"] = nilai
            elif a == "--port":
                opsi["port"] = int(nilai)
            elif a == "--hanya-jika-penuh":
                opsi["hanya_jika_penuh"] = int(nilai)
            elif a == "--jeda-min-jam":
                opsi["jeda_min"] = float(nilai)
            else:
                opsi["jendela"] = int(nilai)
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

    print("=" * 62)
    print(" RESET NODEDB GATEWAY MESHTASTIC")
    print("=" * 62)
    print(" Mode: %s\n" % ("JALANKAN RESET" if opsi["ya"] else "PERIKSA SAJA (tidak mengubah apa pun)"))

    # --- riwayat reset terakhir ---
    usia_reset = None
    if os.path.exists(MARKER):
        try:
            with open(MARKER, encoding="utf-8") as f:
                lama = json.load(f)
            usia_reset = time.time() - lama.get("waktu", 0)
            print(" Reset terakhir : %s lalu (%s)" % (
                jam_teks(usia_reset),
                time.strftime("%d %b %Y %H:%M", time.localtime(lama.get("waktu", 0)))))
        except (OSError, json.JSONDecodeError):
            pass
    print()

    # --- pengaman ganda: jangan reset terlalu sering ---
    if (opsi["ya"] and opsi["jeda_min"] > 0
            and usia_reset is not None and usia_reset < opsi["jeda_min"] * 3600):
        print("Dilewati: reset terakhir baru %s lalu, di bawah jeda minimum %s."
              % (jam_teks(usia_reset), jam_teks(opsi["jeda_min"] * 3600)))
        return 0

    try:
        iface = sambung(opsi["host"], opsi["port"])
    except Exception as e:
        print("Gagal menyambung ke %s:%d (%s)" % (opsi["host"], opsi["port"], e), file=sys.stderr)
        return 1

    try:
        sebelum = baca_kondisi(iface)
        print("Kondisi sekarang:")
        tampilkan(sebelum, iface)
        print()

        if not opsi["ya"]:
            print("Menguji jalur admin (permintaan metadata, tidak mengubah apa pun) ...")
            try:
                iface.localNode.getMetadata()
                print("  -> jalur admin OK: node menjawab permintaan admin.")
                print("     Artinya reset NodeDB akan bisa dikirim saat dijalankan dengan --ya.")
            except Exception as e:
                print("  -> jalur admin GAGAL: %s" % e, file=sys.stderr)
            print()
            print("TIDAK ada perubahan dilakukan. Untuk menjalankan sungguhan tambahkan --ya.")
            return 0

        if sebelum["favorit"]:
            print("Catatan: %d node Favorite akan kehilangan tanda itu setelah reset."
                  % len(sebelum["favorit"]))
            print()

        if not opsi["abaikan_ambang"]:
            isi = sebelum["nodedb"] if sebelum["nodedb"] is not None else sebelum["jumlah"]
            if isi < opsi["hanya_jika_penuh"]:
                print("Dilewati: isi database %s masih di bawah ambang %s."
                      % (isi, opsi["hanya_jika_penuh"]))
                print("(pakai --abaikan-ambang bila tetap ingin menjalankan)")
                return 0

        print("Mengirim perintah reset NodeDB ...")
        try:
            iface.localNode.resetNodeDb()
        except Exception as e:
            print("GAGAL mengirim perintah reset: %s" % e, file=sys.stderr)
            return 1
        time.sleep(6)

        try:
            iface.close()
        except Exception:
            pass
        iface = sambung(opsi["host"], opsi["port"])
        sesudah = baca_kondisi(iface)
        print("Kondisi setelah reset:")
        tampilkan(sesudah, iface)
        print()

        with open(MARKER, "w", encoding="utf-8") as f:
            json.dump({"waktu": time.time(), "node_id": opsi["host"],
                       "sebelum": {k: v for k, v in sebelum.items()},
                       "sesudah": {k: v for k, v in sesudah.items()}},
                      f, indent=2, ensure_ascii=False)
        print("Penanda ditulis: %s" % MARKER)
        print("Notifier akan menahan alarm \"node hilang\" selama %s."
              % jam_teks(opsi["jendela"]))

        if opsi["notif"]:
            kabarkan(
                "NodeDB gateway dikosongkan",
                ("Daftar node %s dikosongkan.\n"
                 "Sebelum: %s entri (%d jalur radio, %d MQTT, %d Favorite)\n"
                 "Sesudah: %s entri\n\n"
                 "Node RF akan terdaftar ulang saat terdengar; tandai Favorite lagi "
                 "bila perlu. Ingat: selama downlink MQTT hidup, node internet akan "
                 "kembali dalam hitungan jam."
                 % (opsi["host"], sebelum["jumlah"], len(sebelum["lora"]),
                    sebelum["mqtt"], len(sebelum["favorit"]), sesudah["jumlah"])),
                prioritas="default", tag="recycle")
        return 0
    finally:
        try:
            iface.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
