#!/usr/bin/env python3
# ============================================================
# bersih-node.py - hapus node yang sudah lama tidak terdengar dari NodeDB gateway
# ============================================================
# Menjawab masalah yang sama dengan reset-node.py, tetapi dengan pisau yang
# lebih tajam: alih-alih mengosongkan SELURUH daftar node (yang ikut membuang
# node RF Anda dan menghapus semua tanda Favorite), alat ini hanya meminta
# gateway MENGHAPUS satu per satu node yang sudah lama tidak terdengar - jadi
# slot NodeDB kembali lega tanpa menyentuh node yang masih hidup.
#
# Kenapa ini perlu: NodeDB gateway punya batas (lihat ambang 190 di halaman
# pemantau). Begitu penuh, firmware membuang node "paling lama dan paling
# tidak menarik" menurut perhitungannya sendiri - kita tidak memilih apa yang
# dibuang. Membersihkan lebih dulu berarti KITA yang memilih.
#
# Cara menentukan "lama tidak terdengar"
# --------------------------------------
# Patokan utamanya `lastHeard` dari NodeDB gateway: waktu paket terakhir yang
# membuat node itu tercatat (baik lewat radio maupun lewat MQTT). Bawaan ambang
# di sini **5 hari**.
#
# Pengaman yang menyala SECARA BAWAAN (semua bisa dibuka lewat opsi)
# -----------------------------------------------------------------
#   1. TANPA --ya tidak ada apa pun yang diubah; alat hanya memeriksa.
#   2. Node gateway sendiri tidak pernah diusulkan untuk dihapus.
#   3. Node **Favorite** dilewati - justru inilah tanda perlindungan yang kita
#      pakai; membuangnya berarti membatalkan perlindungan yang sudah disiapkan.
#   4. Node **jalur radio** (bukan MQTT) dilewati. Node RF yang jarang memancar
#      (ROUTER bisa hanya beberapa paket sehari) gampang lewat 5 hari padahal
#      baik-baik saja. Node MQTT-lah yang membanjiri daftar, jadi itu sasaran
#      bawaannya. Pakai --termasuk-radio bila memang ingin ikut menghapusnya.
#   5. Node TANPA `lastHeard` dilewati: umur yang tidak diketahui tidak boleh
#      diterjemahkan menjadi "lama tidak terdengar".
#   6. Ada batas jumlah per sekali jalan (--batas, bawaan 200) sebagai jaring
#      pengaman bila ambangnya salah setel.
#
# Peringatan yang jujur
# ---------------------
# Selama **downlink MQTT** masih hidup di gateway, node internet yang baru
# dihapus akan masuk kembali begitu ada paket berikutnya. Jadi alat ini
# merapikan, bukan menutup keran. Yang menutup keran: `mqtt-downlink.py`.
#
# Saat alat ini berjalan, ia memakai koneksi TCP ke gateway - dan API node
# Meshtastic hanya melayani SATU klien, jadi exporter akan tergeser keluar dan
# menyambung ulang sendiri setelah selesai (halaman pemantau bisa basi 1-2
# menit). Itu normal dan sudah terjadi pada reset-node.py juga.
#
# Pakai
# -----
#   ./venv/Scripts/python bersih-node.py                     # PERIKSA SAJA
#   ./venv/Scripts/python bersih-node.py --hari 5            # ambang lain
#   ./venv/Scripts/python bersih-node.py --ya                # benar-benar hapus
#   ./venv/Scripts/python bersih-node.py --ya --termasuk-radio
#   ./venv/Scripts/python bersih-node.py --ya --kecuali !da5a16f8,!02ee76d0
#
# Opsi
# ----
#   --host / --port          alamat gateway (bawaan 192.168.20.31:4403)
#   --hari N                 ambang tidak terdengar (bawaan 5)
#   --ya                     benar-benar hapus (tanpa ini hanya periksa)
#   --termasuk-favorit       ikut hapus node yang ditandai Favorite
#   --termasuk-radio         ikut hapus node jalur radio, bukan hanya MQTT
#   --kecuali ID[,ID]        node yang tidak boleh dihapus (boleh diulang)
#   --batas N                maksimum node dihapus sekali jalan (bawaan 200)
#   --jeda DETIK             jeda antar perintah admin (bawaan 1.0)
#   --jeda-min-jam JAM       lewati jalan bila jalan terakhir < JAM yang lalu
#                            (timer harian memakai 20 supaya tidak dobel)
#   --tanpa-notif            jangan kirim kabar ke ntfy
#
# Penjadwalan: meshtastic-bersih.timer (systemd) - lihat README.
#
# Lingkungan: MESH_HOST, MESH_PORT, MESH_HAPUS_HARI, MESH_HAPUS_BATAS,
#             NTFY_SERVER, NTFY_TOPIK, NTFY_LOKAL, NTFY_TOKEN
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
BAWAAN_HARI = float(os.environ.get("MESH_HAPUS_HARI", "5"))
BAWAAN_BATAS = int(os.environ.get("MESH_HAPUS_BATAS", "200"))
BAWAAN_JEDA = 1.0
MARKER = os.path.join(AKAR, "bersih-terakhir.json")
SEHARI = 86400.0

USAGE = """bersih-node.py - hapus node lama dari NodeDB gateway Meshtastic

  bersih-node.py                              periksa saja (bawaan, tidak mengubah)
  bersih-node.py --hari 5                     ambang tidak terdengar 5 hari
  bersih-node.py --ya                         benar-benar hapus (hanya MQTT)
  bersih-node.py --ya --termasuk-radio        ikut hapus node jalur radio
  bersih-node.py --ya --kecuali !da5a16f8     lindungi node tertentu

  --host H --port P       alamat gateway (bawaan 192.168.20.31:4403)
  --termasuk-favorit      ikut hapus node Favorite
  --batas N               maksimum dihapus sekali jalan (bawaan 200)
  --jeda DETIK            jeda antar perintah admin (bawaan 1.0)
  --jeda-min-jam JAM      lewati bila jalan terakhir < JAM yang lalu
  --tanpa-notif           jangan kirim kabar ke ntfy
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


def hari_teks(detik):
    """Umur dalam bentuk yang mudah dibaca: 5h 3j, 12j 4m, 40m."""
    if detik is None:
        return "-"
    detik = int(max(0, detik))
    hari, sisa = divmod(detik, 86400)
    jam, sisa2 = divmod(sisa, 3600)
    menit, _ = divmod(sisa2, 60)
    if hari:
        return "%dh %dj" % (hari, jam)
    if jam:
        return "%dj %dm" % (jam, menit)
    return "%dm" % menit


def nama_node(n):
    """Nama yang enak dibaca dari satu entri NodeDB."""
    user = (n or {}).get("user") or {}
    return user.get("longName") or user.get("shortName") or ""


def pilih_kandidat(nodes, diri_id, sekarang, hari=BAWAAN_HARI,
                   termasuk_favorit=False, termasuk_radio=False,
                   kecuali=(), batas=None):
    """Tentukan node mana yang layak dihapus. Fungsi murni, tanpa jaringan.

    Kembalikan (kandidat, dilewati):
      kandidat : daftar dict {id, nama, umur, via, favorit}, paling lama dulu
      dilewati : dict alasan -> daftar id, supaya keputusan bisa diaudit
    """
    ambang = float(hari) * SEHARI
    kecuali = set(kecuali or ())
    kandidat = []
    dilewati = {"diri": [], "kecuali": [], "tanpa_waktu": [], "masih_aktif": [],
                "favorit": [], "radio": [], "batas": []}

    for nid, n in sorted((nodes or {}).items()):
        n = n or {}
        if nid == diri_id:
            dilewati["diri"].append(nid)
            continue
        if nid in kecuali:
            dilewati["kecuali"].append(nid)
            continue
        # Umur yang tidak diketahui TIDAK boleh dibaca sebagai "lama".
        last = n.get("lastHeard")
        if not last or float(last) <= 0:
            dilewati["tanpa_waktu"].append(nid)
            continue
        umur = sekarang - float(last)
        # Ambang dibaca "lebih dari N hari", jadi tepat 5 hari masih dihitung
        # aktif - batas yang lebih longgar, bukan lebih galak.
        if umur <= ambang:
            dilewati["masih_aktif"].append(nid)
            continue
        favorit = bool(n.get("isFavorite"))
        radio = not n.get("viaMqtt")
        if favorit and not termasuk_favorit:
            dilewati["favorit"].append(nid)
            continue
        if radio and not termasuk_radio:
            dilewati["radio"].append(nid)
            continue
        kandidat.append({"id": nid, "nama": nama_node(n), "umur": umur,
                         "via": "radio" if radio else "mqtt",
                         "favorit": favorit})

    kandidat.sort(key=lambda k: -k["umur"])
    if batas is not None and len(kandidat) > batas:
        dilewati["batas"] = [k["id"] for k in kandidat[batas:]]
        kandidat = kandidat[:batas]
    return kandidat, dilewati


def baca_kondisi(iface):
    """Ringkasan isi NodeDB seperti reset-node.py, ditambah jumlah kandidat."""
    nodes = iface.nodes or {}
    lora = [n for n, d in nodes.items() if not (d or {}).get("viaMqtt")]
    mqtt = [n for n, d in nodes.items() if (d or {}).get("viaMqtt")]
    fav = [n for n, d in nodes.items() if (d or {}).get("isFavorite")]
    mi = getattr(iface, "myInfo", None)
    diri = field(mi, "myNodeNum", "my_node_num")
    return {
        "jumlah": len(nodes),
        "lora": lora,
        "mqtt": mqtt,
        "favorit": fav,
        "nodedb": field(mi, "nodedbCount", "nodedb_count"),
        "reboot": field(mi, "rebootCount", "reboot_count"),
        "diri_id": ("!%08x" % diri) if diri else None,
    }


def id_diri(iface):
    """Nomor node gateway sendiri dalam bentuk id (mis. !8f4c1354)."""
    mi = getattr(iface, "myInfo", None)
    num = field(mi, "myNodeNum", "my_node_num")
    if num:
        return "!%08x" % int(num)
    # Cadangan: node yang ditandai sebagai dirinya sendiri oleh pustaka.
    try:
        ln = iface.localNode
        return "!%08x" % int(ln.nodeNum)
    except Exception:
        return None


def muat_notifier():
    """Pakai fungsi kirim() dari notif-meshtastic.py agar kanal sama."""
    jalur = os.path.join(AKAR, "notif-meshtastic.py")
    if not os.path.exists(jalur):
        return None
    spec = importlib.util.spec_from_file_location("notif_meshtastic", jalur)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def kabarkan(judul, pesan, prioritas="default", tag="wastebasket"):
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


def tutup(iface):
    try:
        iface.close()
    except Exception:
        pass


def tampilkan_ringkas(judul, kandidat, dilewati, batas_baris=40):
    print(judul)
    if not kandidat:
        print("  (tidak ada node yang memenuhi syarat)")
    for k in kandidat[:batas_baris]:
        tanda = " [favorit]" if k["favorit"] else ""
        print("  %-11s %-8s %-11s %-26s%s"
              % (k["id"], k["via"].upper(), hari_teks(k["umur"]),
                 k["nama"][:26], tanda))
    if len(kandidat) > batas_baris:
        print("  ... dan %d node lain" % (len(kandidat) - batas_baris))
    # Yang dilewati dilaporkan sebagai angka, kecuali yang perlu dilihat orang:
    # node jalur radio (calon yang paling mungkin ingin diputuskan manual).
    print("  Dilewati: %d masih aktif | %d jalur radio | %d favorit | %d tanpa waktu"
          " | %d dikecualikan"
          % (len(dilewati["masih_aktif"]), len(dilewati["radio"]),
             len(dilewati["favorit"]), len(dilewati["tanpa_waktu"]),
             len(dilewati["kecuali"])))
    if dilewati["radio"]:
        print("    (jalur radio yang umurnya sudah lewat ambang: %s)"
              % ", ".join(dilewati["radio"][:10]))


def baca_opsi(argv):
    opsi = {"host": BAWAAN_HOST, "port": BAWAAN_PORT, "hari": BAWAAN_HARI,
            "ya": False, "termasuk_favorit": False, "termasuk_radio": False,
            "kecuali": [], "batas": BAWAAN_BATAS, "jeda": BAWAAN_JEDA,
            "jeda_min": 0.0, "notif": True}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(USAGE)
            return None
        if a == "--ya":
            opsi["ya"] = True; i += 1; continue
        if a == "--termasuk-favorit":
            opsi["termasuk_favorit"] = True; i += 1; continue
        if a == "--termasuk-radio":
            opsi["termasuk_radio"] = True; i += 1; continue
        if a == "--tanpa-notif":
            opsi["notif"] = False; i += 1; continue
        if a in ("--host", "--port", "--hari", "--kecuali", "--batas",
                 "--jeda", "--jeda-min-jam"):
            if i + 1 >= len(argv):
                print("%s butuh nilai." % a, file=sys.stderr)
                return 2
            nilai = argv[i + 1]
            try:
                if a == "--host":
                    opsi["host"] = nilai
                elif a == "--port":
                    opsi["port"] = int(nilai)
                elif a == "--hari":
                    opsi["hari"] = float(nilai)
                elif a == "--batas":
                    opsi["batas"] = int(nilai)
                elif a == "--jeda":
                    opsi["jeda"] = float(nilai)
                elif a == "--jeda-min-jam":
                    opsi["jeda_min"] = float(nilai)
                else:
                    opsi["kecuali"] += [x.strip() for x in nilai.split(",") if x.strip()]
            except ValueError:
                print("%s butuh angka, bukan '%s'." % (a, nilai), file=sys.stderr)
                return 2
            i += 2; continue
        print("Opsi tidak dikenal: %s" % a, file=sys.stderr)
        return 2
    return opsi


def main(argv):
    # Konsol Windows memakai cp1252 dan tidak bisa mencetak emoji/karakter
    # lebar; tanpa ini seluruh laporan gagal dengan UnicodeEncodeError.
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    opsi = baca_opsi(argv)
    if opsi is None:
        return 0

    print("=" * 66)
    print(" BERSIHKAN NODEDB - HAPUS NODE YANG LAMA TIDAK TERDENGAR")
    print("=" * 66)
    print(" Gateway        : %s:%s" % (opsi["host"], opsi["port"]))
    print(" Ambang         : %s (%s detik) tidak terdengar"
          % (hari_teks(opsi["hari"] * SEHARI), int(opsi["hari"] * SEHARI)))
    print(" Lingkup bawaan : jalur MQTT saja%s"
          % (", plus jalur RADIO" if opsi["termasuk_radio"] else ""))
    if opsi["termasuk_favorit"]:
        print(" PERINGATAN     : node FAVORITE ikut dihapus (--termasuk-favorit)")
    print(" Mode           : %s"
          % ("HAPUS SUNGGUHAN" if opsi["ya"]
             else "PERIKSA SAJA (tidak mengubah apa pun)"))
    if opsi["kecuali"]:
        print(" Dikecualikan   : %s" % ", ".join(opsi["kecuali"]))
    print()

    # --- riwayat jalan terakhir & pengaman jeda ---
    usia_jalan = None
    if os.path.exists(MARKER):
        try:
            with open(MARKER, encoding="utf-8") as f:
                lama = json.load(f)
            usia_jalan = time.time() - lama.get("waktu", 0)
            print(" Jalan terakhir : %s lalu (%s), %s node dihapus"
                  % (hari_teks(usia_jalan),
                     time.strftime("%d %b %Y %H:%M", time.localtime(lama.get("waktu", 0))),
                     lama.get("dihapus", "?")))
            print()
        except (OSError, json.JSONDecodeError):
            pass

    if (opsi["ya"] and opsi["jeda_min"] > 0 and usia_jalan is not None
            and usia_jalan < opsi["jeda_min"] * 3600):
        print("Dilewati: jalan terakhir baru %s lalu, di bawah jeda minimum %s."
              % (hari_teks(usia_jalan), hari_teks(opsi["jeda_min"] * 3600)))
        return 0

    try:
        iface = sambung(opsi["host"], opsi["port"])
    except Exception as e:
        print("Gagal menyambung ke %s:%d (%s)"
              % (opsi["host"], opsi["port"], e), file=sys.stderr)
        return 1

    try:
        sebelum = baca_kondisi(iface)
        diri = sebelum["diri_id"] or id_diri(iface)
        sekarang = time.time()
        kandidat, dilewati = pilih_kandidat(
            iface.nodes, diri, sekarang, opsi["hari"],
            opsi["termasuk_favorit"], opsi["termasuk_radio"],
            opsi["kecuali"], opsi["batas"])

        print("Isi NodeDB sekarang:")
        print("  total %s entri (dilaporkan node: %s) | jalur radio %d | jalur MQTT %d"
              " | Favorite %d"
              % (sebelum["jumlah"], sebelum["nodedb"], len(sebelum["lora"]),
                 len(sebelum["mqtt"]), len(sebelum["favorit"])))
        print("  gateway sendiri: %s" % (diri or "?"))
        print()
        tampilkan_ringkas("Calon dihapus (paling lama dulu):", kandidat, dilewati)
        print()

        if not kandidat:
            print("Tidak ada yang perlu dihapus. NodeDB sudah bersih dari node lama.")
            return 0

        if not opsi["ya"]:
            print("Menguji jalur admin (permintaan metadata, tidak mengubah apa pun) ...")
            try:
                iface.localNode.getMetadata()
                print("  -> jalur admin OK: penghapusan akan bisa dikirim saat")
                print("     dijalankan dengan --ya.")
            except Exception as e:
                print("  -> jalur admin GAGAL: %s" % e, file=sys.stderr)
            print()
            print("TIDAK ada perubahan dilakukan.")
            print("Untuk benar-benar menghapus %d node: tambahkan --ya" % len(kandidat))
            return 0

        # --- benar-benar menghapus ------------------------------------------
        print("Menghapus %d node (jeda %.1f s antar perintah admin) ..."
              % (len(kandidat), opsi["jeda"]))
        gagal = []
        for k in kandidat:
            try:
                iface.localNode.removeNode(k["id"])
                print("  hapus %-11s %-26s (%s tidak terdengar)"
                      % (k["id"], k["nama"][:26], hari_teks(k["umur"])))
            except Exception as e:
                gagal.append((k["id"], str(e)))
                print("  GAGAL %-11s %s" % (k["id"], e), file=sys.stderr)
            time.sleep(max(0.0, opsi["jeda"]))

        # --- buktikan dengan membaca ulang, bukan dengan percaya diri --------
        print()
        print("Menyambung ulang untuk memeriksa hasilnya ...")
        tutup(iface)
        time.sleep(3)
        try:
            iface = sambung(opsi["host"], opsi["port"])
            sesudah = baca_kondisi(iface)
        except Exception as e:
            print("Gagal menyambung ulang (%s) - hasil belum bisa dipastikan." % e,
                  file=sys.stderr)
            return 1

        tertinggal = [k for k in kandidat if k["id"] in (iface.nodes or {})]
        hilang = [k for k in kandidat if k["id"] not in (iface.nodes or {})]
        print("  NodeDB: %d entri -> %d entri" % (sebelum["jumlah"], sesudah["jumlah"]))
        print("  Benar-benar hilang : %d" % len(hilang))
        if tertinggal:
            print("  Masih tercatat      : %d (%s)"
                  % (len(tertinggal), ", ".join(k["id"] for k in tertinggal[:8])))
            print("  Catatan: firmware bisa menolak sementara bila NodeDB sedang sibuk;")
            print("  ulangi sekali lagi dalam beberapa menit.")
        if gagal:
            print("  Perintah yang gagal  : %d" % len(gagal))

        with open(MARKER, "w", encoding="utf-8") as f:
            json.dump({"waktu": time.time(), "host": opsi["host"],
                       "hari": opsi["hari"], "dihapus": len(hilang),
                       "kandidat": [k["id"] for k in kandidat],
                       "tertinggal": [k["id"] for k in tertinggal],
                       "sebelum": sebelum["jumlah"], "sesudah": sesudah["jumlah"]},
                      f, indent=2, ensure_ascii=False)
        print()
        print("Penanda ditulis: %s" % MARKER)

        if opsi["notif"]:
            contoh = ", ".join("%s (%s)" % (k["nama"][:18] or k["id"], k["id"])
                               for k in hilang[:5]) or "-"
            kabarkan(
                "NodeDB dibersihkan: %d node lama dihapus" % len(hilang),
                ("Dihapus %d node yang tidak terdengar > %s.\n"
                 "NodeDB: %d -> %d entri.\n"
                 "Contoh: %s\n%s\n\n"
                 "Rincian: %s"
                 % (len(hilang), hari_teks(opsi["hari"] * SEHARI),
                    sebelum["jumlah"], sesudah["jumlah"], contoh,
                    ("Tertinggal %d (ulangi nanti)." % len(tertinggal))
                    if tertinggal else "Semua kandidat berhasil dibuang.",
                    MARKER)),
                prioritas="low", tag="wastebasket")
        return 0
    finally:
        tutup(iface)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
