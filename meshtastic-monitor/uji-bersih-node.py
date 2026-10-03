#!/usr/bin/env python3
# ============================================================
# uji-bersih-node.py - uji aturan pemilihan node lama (tanpa gateway)
# ============================================================
# Menguji bersih-node.py TANPA menyambung ke node Meshtastic dan tanpa
# menghapus apa pun: seluruh "gateway" di sini palsu, dan penanda hasil
# ditulis ke folder sementara. Jadi aman dijalankan kapan saja, termasuk saat
# layanan produksi sedang hidup.
#
# Yang diperiksa:
#   1. Aturan pemilihan kandidat:
#        ambang   : tepat 5 hari masih AKTIF, lewat 1 detik sudah kandidat
#        pelindung: gateway sendiri, node Favorite, node jalur RADIO,
#                   node tanpa `lastHeard`, dan id yang dikecualikan
#        luas     : --termasuk-favorit / --termasuk-radio membuka pelindung
#        batas    : --batas memotong jumlah, sisanya dilaporkan
#   2. Pembacaan opsi baris perintah (angka salah, opsi asing, --help).
#   3. Jalan lengkap dengan iface palsu: mode periksa tidak menghapus,
#      mode --ya menghapus HANYA kandidat, lalu membuktikannya dengan
#      membaca ulang, menulis penanda, dan menghormati --jeda-min-jam.
#
# Pakai (dari folder meshtastic-monitor):
#   ./venv/Scripts/python uji-bersih-node.py
# ============================================================

import importlib.util
import io
import json
import os
import sys
import tempfile
import time
import types
from contextlib import redirect_stdout, redirect_stderr

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AKAR = os.path.dirname(os.path.abspath(__file__))
BERKAS = os.path.join(AKAR, "bersih-node.py")
SEHARI = 86400.0

lolos = 0
gagal = 0


def periksa(nama, syarat, bukti=""):
    global lolos, gagal
    if syarat:
        lolos += 1
        print("  [OK  ] %s" % nama)
    else:
        gagal += 1
        print("  [GAGAL] %s %s" % (nama, bukti))


def muat_modul():
    """Muat bersih-node.py sebagai modul (namanya mengandung tanda -)."""
    spec = importlib.util.spec_from_file_location("bersih_node", BERKAS)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def entri(nama, umur_hari, via_mqtt=True, favorit=False, tanpa_waktu=False,
          dasar=None):
    """Satu entri NodeDB tiruan dengan umur tertentu.

    `dasar` adalah patokan "sekarang". Untuk uji fungsi murni patokannya tetap
    (SEKARANG), tetapi untuk uji yang menjalankan main() patokan itu harus
    diambil SAAT ITU JUGA - main() memakai jam sungguhan, dan entri berumur
    tepat 5 hari akan berubah jadi kandidat hanya karena uji berjalan 10 detik.
    """
    d = {"user": {"longName": nama}, "viaMqtt": via_mqtt,
         "isFavorite": favorit}
    if not tanpa_waktu:
        d["lastHeard"] = (SEKARANG if dasar is None else dasar) - umur_hari * SEHARI
    return d


def kumpulan_node(dasar=None):
    """Satu set NodeDB tiruan lengkap: semua aturan pelindung terwakili."""
    return {
        "!00000001": entri("GATEWAY", 999, dasar=dasar),                 # gateway sendiri
        "!00000002": entri("MQTT-LAMA", 30, dasar=dasar),               # kandidat utama
        "!00000003": entri("MQTT-BARU", 0.5, dasar=dasar),              # masih aktif
        "!00000004": entri("RADIO-LAMA", 40, via_mqtt=False, dasar=dasar),
        "!00000005": entri("FAVORIT-LAMA", 20, favorit=True, dasar=dasar),
        "!00000006": entri("TANPA-WAKTU", 0, tanpa_waktu=True, dasar=dasar),
        "!00000007": entri("MQTT-DEKAT-5H", 4.9, dasar=dasar),         # masih aktif
        "!00000008": entri("MQTT-LEWAT-5H", 5.5, dasar=dasar),          # kandidat
        "!00000009": entri("DIKECUALIKAN", 60, dasar=dasar),
    }


# --------------------------------------------------------------------------
# "Gateway" palsu: cukup menyerupai bagian yang dipakai bersih-node.py.
#
# Catatan penting: satu objek yang SAMA dipakai ulang untuk setiap
# "sambungan", karena main() menutup sambungan lalu menyambung ulang untuk
# memeriksa hasilnya. Kalau setiap sambungan mengembalikan objek baru, uji ini
# akan memeriksa objek yang salah - dan lulus/gagalnya jadi tidak berarti.
# --------------------------------------------------------------------------
class LocalNodePalsu:
    def __init__(self, iface):
        self.iface = iface
        self.dihapus = []

    def getMetadata(self):
        return {"firmwareVersion": "2.7.15.palsu"}

    def removeNode(self, nid):
        self.dihapus.append(nid)
        self.iface.nodes.pop(nid, None)


class IfacePalsu:
    def __init__(self, nodes, diri="!00000001"):
        self.nodes = nodes
        self.localNode = LocalNodePalsu(self)
        self.myInfo = types.SimpleNamespace(
            myNodeNum=int(diri[1:], 16), nodedbCount=len(nodes), rebootCount=7)
        self.ditutup = False

    def close(self):
        self.ditutup = True


class TimePalsu:
    """Modul time tiruan: sleep dicatat, sisanya diteruskan ke aslinya."""

    def __init__(self):
        self.asli = time
        self.ditidurkan = []

    def __getattr__(self, nama):
        return getattr(self.asli, nama)

    def sleep(self, detik):
        self.ditidurkan.append(detik)


def jalan_main(modul, argv, nodes, diri="!00000001", marker=None):
    """Jalankan main() dengan gateway & penanda palsu.

    Kembalikan (kode keluar, seluruh keluaran, iface palsu, pencatat sleep).
    """
    iface = IfacePalsu(nodes, diri)

    def sambung_palsu(host, port, tunggu=25):
        return iface

    waktu = TimePalsu()
    lama = (modul.sambung, modul.MARKER, modul.time)
    modul.sambung = sambung_palsu
    modul.MARKER = marker or os.path.join(TEMP, "penanda-tidak-ada.json")
    modul.time = waktu
    keluaran = io.StringIO()
    try:
        with redirect_stdout(keluaran), redirect_stderr(keluaran):
            kode = modul.main(argv)
    finally:
        modul.sambung, modul.MARKER, modul.time = lama
    return kode, keluaran.getvalue(), iface, waktu


SEKARANG = time.time()
TEMP = tempfile.mkdtemp(prefix="uji-bersih-node-")


def main():
    print("=" * 62)
    print(" UJI ATURAN BERSIH-NODE (tanpa gateway, tanpa menghapus)")
    print("=" * 62)

    modul = muat_modul()

    # --- 1. aturan pemilihan kandidat -------------------------------------
    print("\n1. Aturan pemilihan kandidat (ambang bawaan 5 hari)")
    nodes = {
        "!00000001": entri("GATEWAY", 999),                 # gateway sendiri
        "!00000002": entri("MQTT-LAMA", 30),                # kandidat utama
        "!00000003": entri("MQTT-BARU", 1),                 # masih aktif
        "!00000004": entri("RADIO-LAMA", 40, via_mqtt=False),
        "!00000005": entri("FAVORIT-LAMA", 20, favorit=True),
        "!00000006": entri("TANPA-WAKTU", 0, tanpa_waktu=True),
        "!00000007": entri("MQTT-TEPAT-5H", 5.0),           # tepat di ambang
        "!00000008": entri("MQTT-LEWAT-5H", 5.0 + 1.0 / SEHARI),
        "!00000009": entri("DIKECUALIKAN", 60),
    }
    kandidat, dilewati = modul.pilih_kandidat(
        nodes, "!00000001", SEKARANG, 5.0, kecuali=["!00000009"])

    ids = [k["id"] for k in kandidat]
    periksa("gateway sendiri tidak pernah diusulkan",
            "!00000001" not in ids and "!00000001" in dilewati["diri"])
    periksa("node MQTT 30 hari jadi kandidat", "!00000002" in ids)
    periksa("node yang masih aktif dilewati", "!00000003" in dilewati["masih_aktif"])
    periksa("node jalur radio dilewati secara bawaan",
            "!00000004" not in ids and "!00000004" in dilewati["radio"])
    periksa("node Favorite dilewati secara bawaan",
            "!00000005" not in ids and "!00000005" in dilewati["favorit"])
    periksa("node tanpa lastHeard dilewati (umur tak diketahui)",
            "!00000006" not in ids and "!00000006" in dilewati["tanpa_waktu"])
    periksa("tepat 5 hari masih dihitung AKTIF",
            "!00000007" in dilewati["masih_aktif"] and "!00000007" not in ids)
    periksa("lewat 5 hari sedikit sudah jadi kandidat", "!00000008" in ids)
    periksa("id yang dikecualikan tidak diusulkan",
            "!00000009" not in ids and "!00000009" in dilewati["kecuali"])
    periksa("kandidat tidak memuat node lain", len(kandidat) == 2,
            "jumlah=%d (%s)" % (len(kandidat), ids))
    periksa("urutan paling lama dulu",
            ids == sorted(ids, key=lambda x: -dict(
                (k["id"], k["umur"]) for k in kandidat)[x]),
            str([(k["id"], round(k["umur"] / SEHARI, 1)) for k in kandidat]))
    periksa("jalur kandidat ditandai", all(k["via"] == "mqtt" for k in kandidat))

    # --- 1b. membuka pelindung -------------------------------------------
    print("\n1b. Membuka pelindung secara sadar")
    k2, _ = modul.pilih_kandidat(nodes, "!00000001", SEKARANG, 5.0,
                                 termasuk_favorit=True, termasuk_radio=True,
                                 kecuali=["!00000009"])
    ids2 = [k["id"] for k in k2]
    periksa("--termasuk-radio ikut menghapus node radio", "!00000004" in ids2)
    periksa("--termasuk-favorit ikut menghapus node Favorite", "!00000005" in ids2)
    periksa("node tanpa waktu tetap aman", "!00000006" not in ids2)
    periksa("node masih aktif tetap aman", "!00000003" not in ids2)

    # --- 1c. batas jumlah & ambang lain ----------------------------------
    print("\n1c. Batas jumlah dan ambang lain")
    k3, d3 = modul.pilih_kandidat(nodes, "!00000001", SEKARANG, 5.0, batas=1,
                                  kecuali=["!00000009"])
    periksa("--batas memotong jumlah kandidat", len(k3) == 1, "jumlah=%d" % len(k3))
    periksa("sisanya dilaporkan sebagai dilewati", len(d3["batas"]) == 1,
            str(d3["batas"]))
    periksa("yang tersisa adalah yang paling lama",
            k3[0]["id"] == "!00000002")
    # Node tertua di set ini berumur 60 hari, jadi ambang 100 hari harus
    # menyisakan NOL kandidat - ambang yang lebih longgar berarti lebih sedikit
    # yang dihapus, bukan lebih banyak.
    k4, d4 = modul.pilih_kandidat(nodes, "!00000001", SEKARANG, 100.0)
    periksa("ambang 100 hari tidak menyisakan kandidat", k4 == [],
            str([k["id"] for k in k4]))
    k4b, _ = modul.pilih_kandidat(nodes, "!00000001", SEKARANG, 20.0,
                                 kecuali=["!00000009"])
    periksa("ambang 20 hari menyisakan MQTT 30 hari & yang dikecualikan tetap aman",
            [k["id"] for k in k4b] == ["!00000002"],
            str([k["id"] for k in k4b]))
    k5, _ = modul.pilih_kandidat({}, "!00000001", SEKARANG, 5.0)
    periksa("NodeDB kosong tidak error", k5 == [])
    k6, d6 = modul.pilih_kandidat(None, "!00000001", SEKARANG, 5.0)
    periksa("NodeDB None tidak error", k6 == [] and d6["masih_aktif"] == [])

    # --- 1d. umur yang tidak masuk akal ----------------------------------
    print("\n1d. Nilai lastHeard yang aneh")
    aneh = {"!0000000a": entri("NOL", 0), "!0000000b": entri("MINUS", 0)}
    aneh["!0000000a"]["lastHeard"] = 0
    aneh["!0000000b"]["lastHeard"] = -5
    ka, da = modul.pilih_kandidat(aneh, "!00000001", SEKARANG, 5.0)
    periksa("lastHeard 0 / negatif dianggap tanpa waktu",
            ka == [] and len(da["tanpa_waktu"]) == 2, str(da["tanpa_waktu"]))

    # --- 2. pembacaan opsi ------------------------------------------------
    print("\n2. Pembacaan opsi baris perintah")
    o = modul.baca_opsi([])
    periksa("bawaan: 5 hari, belum --ya, batas 200",
            o["hari"] == 5.0 and o["ya"] is False and o["batas"] == 200)
    o = modul.baca_opsi(["--hari", "7", "--ya", "--kecuali", "!a,!b"])
    periksa("--hari 7 & --kecuali terdaftar",
            o["hari"] == 7.0 and o["ya"] is True and o["kecuali"] == ["!a", "!b"])
    periksa("--termasuk-radio terbaca", modul.baca_opsi(["--termasuk-radio"])["termasuk_radio"])
    periksa("--termasuk-favorit terbaca",
            modul.baca_opsi(["--termasuk-favorit"])["termasuk_favorit"])
    periksa("--help mengembalikan None", modul.baca_opsi(["--help"]) is None)
    simpan = sys.stderr
    sys.stderr = io.StringIO()
    try:
        kode_asing = modul.baca_opsi(["--entah"])
        kode_angka = modul.baca_opsi(["--hari", "lima"])
    finally:
        pesan = sys.stderr.getvalue()
        sys.stderr = simpan
    periksa("opsi asing ditolak dengan kode 2", kode_asing == 2)
    periksa("angka yang salah ditolak dengan kode 2", kode_angka == 2)
    periksa("pesan kesalahannya jelas", "tidak dikenal" in pesan and "butuh angka" in pesan)

    # --- 2b. teks umur ----------------------------------------------------
    print("\n2b. Teks umur")
    periksa("5 hari 3 jam -> '5h 3j'", modul.hari_teks(5 * SEHARI + 3 * 3600) == "5h 3j")
    periksa("45 menit -> '45m'", modul.hari_teks(2700) == "45m")
    periksa("umur tak diketahui -> '-'", modul.hari_teks(None) == "-")

    # --- 3. jalan lengkap: mode periksa -----------------------------------
    # Memakai iface palsu: tidak ada jaringan, tidak ada radio yang tersentuh.
    print("\n3. Mode periksa (--tanpa --ya) tidak menghapus")
    nodes3 = kumpulan_node(time.time())
    kode, teks, iface3, _ = jalan_main(
        modul, ["--tanpa-notif", "--kecuali", "!00000009"], nodes3)
    periksa("keluar dengan kode 0", kode == 0, "kode=%s" % kode)
    periksa("TIDAK ada perintah hapus yang dikirim", iface3.localNode.dihapus == [],
            str(iface3.localNode.dihapus))
    periksa("jumlah kandidat dicetak", "Calon dihapus" in teks)
    periksa("diberi tahu cara menghapus", "--ya" in teks and "TIDAK ada perubahan" in teks)
    periksa("jalur admin diuji tanpa mengubah", "jalur admin OK" in teks)
    periksa("sambungan ditutup lagi", iface3.ditutup is True)
    periksa("penanda TIDAK ditulis saat periksa",
            "Penanda ditulis" not in teks)

    # --- 4. jalan lengkap: mode --ya --------------------------------------
    print("\n4. Mode --ya menghapus HANYA kandidat")
    marker = os.path.join(TEMP, "bersih-penanda.json")
    if os.path.exists(marker):
        os.remove(marker)
    nodes4 = kumpulan_node(time.time())
    kode, teks, iface4, waktu4 = jalan_main(
        modul, ["--ya", "--tanpa-notif", "--jeda", "0", "--kecuali", "!00000009"],
        nodes4, marker=marker)
    dihapus = iface4.localNode.dihapus
    periksa("keluar dengan kode 0", kode == 0, "kode=%s" % kode)
    periksa("hanya 2 kandidat yang dihapus", sorted(dihapus) == ["!00000002", "!00000008"],
            str(dihapus))
    periksa("gateway sendiri tidak pernah dihapus", "!00000001" not in dihapus)
    periksa("node radio tidak dihapus", "!00000004" not in dihapus)
    periksa("node Favorite tidak dihapus", "!00000005" not in dihapus)
    periksa("node yang masih aktif tidak dihapus",
            all(x in dihapus for x in ("!00000002", "!00000008")))
    periksa("hasil dibuktikan dengan membaca ulang",
            "Benar-benar hilang : 2" in teks and "9 entri -> 7 entri" in teks,
            teks[-600:])
    periksa("tidak ada yang dilaporkan tertinggal", "Masih tercatat" not in teks)
    periksa("penanda ditulis", os.path.exists(marker))
    if os.path.exists(marker):
        with open(marker, encoding="utf-8") as f:
            isi = json.load(f)
        periksa("penanda memuat jumlah yang dihapus", isi.get("dihapus") == 2, str(isi)[:200])
        periksa("penanda memuat ambang hari", isi.get("hari") == 5.0)
        periksa("penanda memuat daftar kandidat", len(isi.get("kandidat", [])) == 2)
    periksa("jumlah node benar-benar berkurang", len(nodes4) == 7, "sisa=%d" % len(nodes4))

    # --- 5. pengaman jeda minimum ----------------------------------------
    # Timer harian memakai --jeda-min-jam supaya pemasangan ulang layanan atau
    # reboot (Persistent=true) tidak menjalankannya dua kali sehari.
    print("\n5. Pengaman --jeda-min-jam")
    nodes5 = kumpulan_node(time.time())
    kode, teks, iface5, _ = jalan_main(
        modul, ["--ya", "--tanpa-notif", "--jeda-min-jam", "20"],
        nodes5, marker=marker)
    periksa("keluar dengan kode 0 (dilewati, bukan gagal)", kode == 0)
    periksa("tidak ada yang dihapus", iface5.localNode.dihapus == [],
            str(iface5.localNode.dihapus))
    periksa("alasannya disebutkan", "jeda minimum" in teks, teks[:300])

    # --- 6. gagal menyambung ---------------------------------------------
    print("\n6. Gateway tidak bisa disambung")
    lama = modul.sambung
    def tolak(host, port, tunggu=25):
        raise OSError("connection refused")
    modul.sambung = tolak
    keluaran = io.StringIO()
    try:
        with redirect_stdout(keluaran), redirect_stderr(keluaran):
            kode = modul.main(["--tanpa-notif"])
    finally:
        modul.sambung = lama
    periksa("keluar dengan kode 1", kode == 1, "kode=%s" % kode)
    periksa("galatnya dilaporkan", "Gagal menyambung" in keluaran.getvalue())

    # --- 7. jeda antar perintah admin ------------------------------------
    print("\n7. Jeda antar perintah admin")
    # Dua kandidat (MQTT 30 hari & 5,5 hari) = dua perintah admin = dua jeda.
    nodes7 = kumpulan_node(time.time())
    marker7 = os.path.join(TEMP, "penanda-jeda.json")
    kode, teks, iface7, waktu7 = jalan_main(
        modul, ["--ya", "--tanpa-notif", "--jeda", "1.5", "--kecuali", "!00000009"],
        nodes7, marker=marker7)
    periksa("tiap kandidat diberi jeda", waktu7.ditidurkan.count(1.5) == 2,
            str(waktu7.ditidurkan))

    print("\n" + "=" * 62)
    print("  Lolos: %d | GAGAL: %d" % (lolos, gagal))
    print("  %s" % ("SEMUA UJI LULUS." if not gagal else "ADA YANG GAGAL."))
    return 1 if gagal else 0


if __name__ == "__main__":
    sys.exit(main())
