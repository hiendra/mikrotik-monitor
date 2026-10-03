#!/usr/bin/env python3
# ============================================================
# favorite-node.py - tandai node RF langsung sebagai Favorite di gateway
# ============================================================
# Kenapa ini penting: NodeDB gateway punya batas, dan saat penuh Meshtastic
# membuang node "terlama dan paling tidak menarik". Node yang ditandai
# **Favorite** lebih terlindungi dari penggusuran. Jadi sebelum melakukan
# apa pun yang mengosongkan/menekan daftar (mis. reset-node.py), node RF
# Anda sebaiknya sudah Favorite.
#
# Lingkup bawaan: hanya node yang terdengar LANGSUNG lewat radio (viaMqtt
# kosong) dan bukan node gateway sendiri. Ratusan node MQTT di daftar Anda
# TIDAK ikut ditandai - menandainya justru menghabiskan slot yang kita
# berusaha lindungi.
#
# Pakai
# -----
#   ./venv/Scripts/python favorite-node.py                 # PERIKSA SAJA
#   ./venv/Scripts/python favorite-node.py --ya            # tandai semua node RF
#   ./venv/Scripts/python favorite-node.py --ya --node !da5a16f8,!02ee76d0
#   ./venv/Scripts/python favorite-node.py --ya --lepas    # rollback
#
# Opsi
# ----
#   --host / --port     alamat gateway (bawaan 192.168.20.31:4403)
#   --ya                benar-benar tulis (tanpa ini hanya periksa)
#   --node ID[,ID]      batasi ke node tertentu (bawaan: semua node RF langsung)
#   --lepas             kebalikannya: lepas tanda Favorite (rollback)
#   --tanpa-notif       jangan kirim kabar ke ntfy
#
# Mode jaga (untuk dipakai SETELAH reset NodeDB)
# ----------------------------------------------
# Reset mengosongkan daftar - termasuk tanda Favorite - dan node RF baru
# terdaftar ulang beberapa saat kemudian (ROUTER bisa perlu jam-an). Mode jaga
# menyambung berulang, menandai tiap node sasaran begitu ia muncul, lalu
# berhenti sendiri ketika semuanya sudah tertandai:
#
#   ./venv/Scripts/python favorite-node.py --ya --jaga 240 \
#       --node !da5a16f8,!02ee76d0,!8f4c228c,!4f98c3ae
#
#   --jaga MENIT        lamanya berjaga (0 = nonaktif, bawaan)
#   --jeda DETIK        jeda antar putaran (bawaan 120)
#
# Lingkungan: MESH_HOST, MESH_PORT, NTFY_SERVER, NTFY_TOPIK, NTFY_LOKAL,
#             NTFY_TOKEN
#
# Aman secara bawaan: tanpa --ya, alat ini hanya MEMBACA, tidak mengubah apa pun.
# ============================================================

import importlib.util
import os
import sys
import time

AKAR = os.path.dirname(os.path.abspath(__file__))
BAWAAN_HOST = os.environ.get("MESH_HOST", "192.168.20.31")
BAWAAN_PORT = int(os.environ.get("MESH_PORT", "4403"))

USAGE = """favorite-node.py - tandai node RF langsung sebagai Favorite

  favorite-node.py                    periksa saja (bawaan, tidak mengubah)
  favorite-node.py --ya               tandai semua node jalur radio
  favorite-node.py --ya --node !da5a16f8,!02ee76d0
  favorite-node.py --ya --lepas       lepas tanda Favorite (rollback)

  --host H --port P    alamat gateway (bawaan 192.168.20.31:4403)
  --tanpa-notif        jangan kirim kabar ke ntfy
  --jaga MENIT         berjaga setelah reset: tandai node begitu muncul
  --jeda DETIK         jeda antar putaran saat berjaga (bawaan 120)
"""


def muat_notifier():
    jalur = os.path.join(AKAR, "notif-meshtastic.py")
    if not os.path.exists(jalur):
        return None
    spec = importlib.util.spec_from_file_location("notif_meshtastic", jalur)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def kabarkan(judul, pesan, prioritas="default", tag="star"):
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


def jam_teks(detik):
    if detik is None:
        return "-"
    detik = int(max(0, detik))
    jam, sisa = divmod(detik, 3600)
    menit, _ = divmod(sisa, 60)
    if jam >= 24:
        return "%dhari" % (jam // 24)
    if jam:
        return "%dj%dm" % (jam, menit)
    return "%dm" % menit


def kumpulkan(iface):
    """Node jalur radio langsung (bukan MQTT, bukan gateway sendiri)."""
    # my_node_num berupa angka; id node berupa string "!xxxxxxxx", jadi perlu
    # disamakan bentuknya sebelum dibandingkan.
    diri = None
    try:
        num = iface.myInfo.my_node_num
        if num:
            diri = "!%08x" % int(num)
    except Exception:
        pass
    sekarang = time.time()
    keluaran = []
    for node_id, n in (iface.nodes or {}).items():
        n = n or {}
        if node_id == diri:
            continue
        if n.get("viaMqtt"):
            continue
        user = n.get("user") or {}
        last = n.get("lastHeard")
        keluaran.append({
            "id": node_id,
            "nama": user.get("longName") or user.get("shortName") or node_id,
            "role": user.get("role"),
            "snr": n.get("snr"),
            "hops": n.get("hopsAway"),
            "favorit": bool(n.get("isFavorite")),
            "umur": (sekarang - last) if last else None,
        })
    keluaran.sort(key=lambda r: r["id"])
    return diri, keluaran


def tampilkan(baris):
    print("  %-12s %-30s %-9s %-7s %-6s %s"
          % ("id", "nama", "favorit", "snr", "hop", "terakhir"))
    for r in baris:
        print("  %-12s %-30s %-9s %-7s %-6s %s"
              % (r["id"], (r["nama"] or "")[:30],
                 "ya" if r["favorit"] else "TIDAK",
                 "-" if r["snr"] is None else "%.1f" % r["snr"],
                 "-" if r["hops"] is None else r["hops"],
                 jam_teks(r["umur"])))


def mode_jaga(opsi):
    """Mode jaga: tandai node sasaran begitu muncul (dipakai sesudah reset).

    Reset NodeDB mengosongkan daftar beserta tanda Favorite, lalu node RF
    terdaftar ulang secara bertahap. Fungsi ini menyambung berulang dan
    menandai tiap node sasaran begitu terlihat, lalu berhenti sendiri.
    """
    batas = time.time() + opsi["jaga"] * 60
    target = set(opsi["node"] or [])
    ditandai = {}
    putaran = 0
    kosong_berturut = 0

    print("Berjaga %s menit, jeda %d detik." % (opsi["jaga"], opsi["jeda"]))
    if target:
        print("Sasaran (%d): %s" % (len(target), ", ".join(sorted(target))))
    else:
        print("Sasaran: semua node jalur radio yang belum Favorite.")
    if not opsi["ya"]:
        print("CATATAN: tanpa --ya, mode jaga hanya melapor, tidak menulis.")
    print()

    while True:
        putaran += 1
        sasaran = []
        baris = []
        iface = None
        try:
            iface = sambung(opsi["host"], opsi["port"])
        except Exception as e:
            print("  putaran %d: gagal menyambung (%s), dicoba lagi." % (putaran, e))
        if iface is not None:
            try:
                _, baris = kumpulkan(iface)
                if target:
                    sasaran = [r for r in baris
                               if r["id"] in target and not r["favorit"]]
                else:
                    sasaran = [r for r in baris if not r["favorit"]]
                print("  putaran %d %s: %d node RF terlihat, %d perlu ditandai."
                      % (putaran, time.strftime("%H:%M:%S"), len(baris), len(sasaran)))
                if opsi["ya"]:
                    for r in sasaran:
                        try:
                            iface.localNode.setFavorite(r["id"])
                            ditandai[r["id"]] = r["nama"]
                            print("     + Favorite %s  %s" % (r["id"], r["nama"]))
                        except Exception as e:
                            print("     GAGAL %s: %s" % (r["id"], e), file=sys.stderr)
                        time.sleep(1.0)
            finally:
                try:
                    iface.close()
                except Exception:
                    pass

        if target:
            if not (target - set(ditandai)):
                print("\nSemua %d node sasaran sudah tertandai Favorite."
                      % len(target))
                break
        elif sasaran:
            kosong_berturut = 0
        else:
            kosong_berturut += 1
            if kosong_berturut >= 3:
                print("\nTidak ada node RF yang perlu ditandai selama 3 putaran;"
                      " berhenti.")
                break

        if time.time() + opsi["jeda"] >= batas:
            print("\nWaktu berjaga habis (%s menit)." % opsi["jaga"])
            break
        time.sleep(opsi["jeda"])

    if opsi["notif"] and ditandai:
        kabarkan(
            "Favorite node RF dipulihkan setelah reset",
            ("%d node ditandai ulang:\n%s\n\n%s"
             % (len(ditandai),
                "\n".join("  %s %s" % (k, v) for k, v in ditandai.items()),
                ("Belum tertandai: %s" % ", ".join(sorted(target - set(ditandai))))
                if target and (target - set(ditandai)) else
                "Semua sasaran sudah tertandai.")),
            prioritas="default", tag="star")
    return 0


def baca_opsi(argv):
    opsi = {"host": BAWAAN_HOST, "port": BAWAAN_PORT, "ya": False,
            "node": None, "lepas": False, "notif": True,
            "jaga": 0, "jeda": 120}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(USAGE)
            return None
        if a == "--ya":
            opsi["ya"] = True; i += 1; continue
        if a == "--lepas":
            opsi["lepas"] = True; i += 1; continue
        if a == "--tanpa-notif":
            opsi["notif"] = False; i += 1; continue
        if a in ("--host", "--port", "--node", "--jaga", "--jeda"):
            if i + 1 >= len(argv):
                print("%s butuh nilai." % a, file=sys.stderr)
                return 2
            nilai = argv[i + 1]
            if a == "--host":
                opsi["host"] = nilai
            elif a == "--port":
                opsi["port"] = int(nilai)
            elif a == "--jaga":
                opsi["jaga"] = float(nilai)
            elif a == "--jeda":
                opsi["jeda"] = max(15, int(nilai))
            else:
                opsi["node"] = {x.strip() for x in nilai.replace(",", " ").split() if x.strip()}
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

    tujuan = "LEPAS tanda Favorite" if opsi["lepas"] else "TANDAI Favorite"
    print("=" * 62)
    print(" FAVORITE NODE RF LANGSUNG")
    print("=" * 62)
    print(" Mode: %s%s\n" % (
        "TULIS -> " if opsi["ya"] else "PERIKSA SAJA (tidak mengubah apa pun) -> ",
        "BERJAGA (auto-Favorite setelah reset)" if opsi["jaga"] > 0 else tujuan))

    if opsi["jaga"] > 0:
        return mode_jaga(opsi)

    try:
        iface = sambung(opsi["host"], opsi["port"])
    except Exception as e:
        print("Gagal menyambung ke %s:%d (%s)" % (opsi["host"], opsi["port"], e),
              file=sys.stderr)
        return 1

    try:
        diri, baris = kumpulkan(iface)
        print("Node jalur radio langsung (%d) - gateway sendiri tidak dihitung:"
              % len(baris))
        tampilkan(baris)
        print()

        if opsi["node"] is not None:
            ada = {r["id"] for r in baris}
            kurang = opsi["node"] - ada
            if kurang:
                print("PERINGATAN: node berikut tidak ada di jalur radio langsung:")
                print("  %s" % ", ".join(sorted(kurang)))
                print("(periksa ejaan id, atau node belum terdengar sama sekali)")
                print()
            baris = [r for r in baris if r["id"] in opsi["node"]]

        # Sasaran: yang keadaannya belum sesuai keinginan.
        sasaran = [r for r in baris if r["favorit"] == opsi["lepas"]]

        if not sasaran:
            print("Tidak ada yang perlu diubah (sudah sesuai keinginan).")
            return 0

        print("Rencana perubahan:")
        for r in sasaran:
            print("  %-12s %-30s -> %s"
                  % (r["id"], (r["nama"] or "")[:30],
                     "lepas Favorite" if opsi["lepas"] else "Favorite"))
        print()

        if not opsi["ya"]:
            print("TIDAK ada perubahan dilakukan. Untuk menerapkan tambahkan --ya.")
            print()
            print("Menandai Favorite adalah langkah perlindungan termurah, dan")
            print("sebaiknya dilakukan SEBELUM reset NodeDB (lihat README).")
            return 0

        berhasil, gagal = [], []
        for r in sasaran:
            try:
                if opsi["lepas"]:
                    iface.localNode.removeFavorite(r["id"])
                else:
                    iface.localNode.setFavorite(r["id"])
                berhasil.append(r)
            except Exception as e:
                gagal.append((r, e))
                print("  GAGAL %s: %s" % (r["id"], e), file=sys.stderr)
            time.sleep(1.0)

        print("Berhasil: %d%s"
              % (len(berhasil), (", gagal: %d" % len(gagal)) if gagal else ""))
        time.sleep(5)

        try:
            iface.close()
        except Exception:
            pass
        iface = sambung(opsi["host"], opsi["port"])
        print("\nKeadaan setelah perubahan:")
        tampilkan(kumpulkan(iface)[1])

        if opsi["notif"] and berhasil:
            aksi = "dilepas" if opsi["lepas"] else "ditandai"
            kabarkan(
                "Favorite node RF %s" % aksi,
                ("%d node jalur radio %s Favorite:\n%s\n\nNode Favorite lebih "
                 "terlindungi saat NodeDB penuh."
                 % (len(berhasil), aksi,
                    "\n".join("  %s %s" % (r["id"], r["nama"]) for r in berhasil))),
                prioritas="default", tag="star")
        return 0
    finally:
        try:
            iface.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
