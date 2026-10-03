#!/usr/bin/env python3
# ============================================================
# notif-meshtastic.py - kirim notifikasi ntfy saat node Meshtastic offline/pulih
# ============================================================
# Membaca data yang sudah disajikan exporter (bawaan
# http://127.0.0.1:9208/data.json), lalu mengirim notifikasi ke ntfy HANYA
# saat ada PERUBAHAN status (pola yang sama dengan paket mikrotik-ntfy/):
#
#   * node online  -> offline   : peringatan (tag red_circle)
#   * node offline -> online    : pemulihan (tag green_circle)
#   * baterai turun melewati ambang : peringatan (tag warning)
#   * baterai naik melewati ambang  : pemulihan (tag battery)
#   * SNR link turun melewati ambang : peringatan (tag signal_strength)
#   * SNR link membaik             : pemulihan (tag signal_strength)
#   * hop bertambah dari titik terbaiknya : peringatan (tag arrows_counterclockwise)
#   * hop kembali ke titik terbaik : pemulihan (tag arrows_counterclockwise)
#   * node HILANG dari database gateway  : peringatan (tag warning)
#   * node muncul kembali di database    : pemulihan (tag green_circle)
#   * gateway baru saja reboot           : peringatan (tag recycle)
#   * database gateway hampir penuh      : peringatan (tag warning)
#   * node RF belum ditandai Favorite    : saran sekali per node (tag star)
#
# TIGA KABAR YANG DIMINTA KHUSUS OLEH PEMILIK HALAMAN:
#
#   * NODE LoRa BARU TERDETEKSI LANGSUNG oleh radio gateway, yaitu node yang
#     SNR-nya BENAR-BENAR diukur gateway sendiri. Notifikasinya memuat id node,
#     nama, hop, baterai, dan KUALITAS SINYALnya (Baik/Cukup/Buruk/Nihil +
#     angka SNR) memakai penilaian yang sama dengan halaman web - termasuk
#     kalau kontak radio node itu TERUKUR KEMBALI setelah lama hanya lewat
#     MQTT. Peluang ini tidak dimiliki halaman web: halaman hanya bisa
#     ditengok, sedangkan notifikasi mencari Anda.
#
#   * GATEWAY MATI / tidak terbaca lagi: exporter tidak menjawab, datanya
#     sudah basi (loop pengumpul tersangkut), atau gateway tidak melaporkan
#     apa pun (0 node + firmware tidak terbaca - "hidup tetapi buta", kendala
#     yang terbukti pada 28 Sep 2026). Diperiksa dari SISI NOTIFIER, karena
#     halaman web tidak bisa memberi tahu siapa pun saat dirinya sendiri mati.
#     Ada kabar pemulihannya juga, lengkap dengan lama matinya.
#
#   * NODE YANG TERSAMBUNG KE GATEWAY menjadi OFFLINE (sudah ada sebelumnya,
#     lingkup bawaan = node jalur radio). Kini isinya ikut menyebut kualitas
#     sinyal terakhirnya, supaya bisa dibedakan "node putus" dari "node pindah
#     jauh dan sinyalnya sekarat".
#
# Jendela tenang pasca-reset: bila reset-node.py baru saja mengosongkan NodeDB
# gateway (penanda reset-terakhir.json masih segar), alarm "node hilang"
# DITAHAN selama NOTIF_JENDELA_RESET detik (bawaan 1800) supaya reset itu
# sendiri tidak memicu banjir alarm palsu. Lihat reset-node.py.
#
# DUA TOPIK, SATU SERVER. Ketiga kabar di atas dikirim ke topik TERPISAH
# (bawaan mesh-penting-2kevnee56c4) supaya di ponsel bisa diberi nada dering dan
# aturan "jangan ganggu" sendiri - frekuensinya jauh lebih jarang daripada kabar
# rutin lainnya. Yang ikut ke topik penting hanya: gateway mati & pulih, node
# LoRa terdeteksi & kontak kembali, dan node offline & pulih. Kabar rutin
# (baterai, SNR lemah, hop, saran Favorite, node hilang dari database) tetap di
# topik umum (bawaan mesh-6h4v8p2rxq). Atur lewat NTFY_TOPIK_PENTING /
# --topik-penting; isi kosong berarti kembali ke satu topik seperti semula.
#
# Kanal dikirim berurutan sampai berhasil (sama seperti ntfy-kirim.rsc):
#   1) server utama (bawaan ntfy.adminforge.de)
#   2) server utama sekali lagi setelah jeda 3 detik
#   3) ntfy lokal ZimaOS lewat LAN (tidak menyentuh internet)
#
# Kanál Meshtastic SENGAJA terpisah dari kanal router (rt-...) dan kanal
# Uptime Kuma (kuma-...), supaya gangguan antar-sistem tidak tercampur.
#
# Pakai
# -----
#   python notif-meshtastic.py                 # jalan terus (layanan)
#   python notif-meshtastic.py --sekali        # satu putaran (untuk scheduler)
#   MESH_DATA=http://192.168.20.31:9208/data.json python notif-meshtastic.py
#
# Opsi
# ----
#   --data URL       alamat /data.json exporter   (bawaan http://127.0.0.1:9208/data.json)
#   --state BERKAS   berkas penyimpan status       (bawaan notif-meshtastic-state.json)
#   --interval DET   jeda antar putaran            (bawaan 60)
#   --sekali         jalankan satu putaran lalu keluar
#   --lapor-awal     kirim juga untuk node yang sudah offline saat pertama jalan
#   --ambang-baterai N   ambang baterai rendah     (bawaan 20; 0 = matikan)
#   --ambang-snr N   ambang SNR lemah (dB)         (bawaan -7; off = matikan)
#   --margin-snr N   histeresis pemulihan SNR (dB) (bawaan 3)
#   --semua-node     pantau SEMUA node di database, termasuk yang lewat MQTT
#                    (bawaan: HANYA node yang terdengar langsung lewat LoRa)
#   --node ID1,ID2   batasi ke daftar node tertentu (opsional, paling ketat)
#   --tanpa-kontak   jangan kabari node LoRa yang baru terdeteksi langsung
#   --jeda-kontak DET  jeda minimum kabar "kontak radio kembali" per node
#                    (bawaan 21600 = 6 jam; 0 = tanpa jeda)
#   --basi-gw DETIK  umur data yang masih dianggap sehat (bawaan 180; "off" mematikan)
#   --absen-gw N     putaran gagal berturut-turut sebelum Gateway MATI dilaporkan
#                    (bawaan 2)
#
# Lingkungan
# ----------
#   MESH_DATA         sama dengan --data
#   NTFY_SERVER       server utama   (bawaan https://ntfy.adminforge.de)
#   NTFY_TOPIK        nama topik umum     (bawaan mesh-6h4v8p2rxq)
#   NTFY_TOPIK_PENTING  topik kabar penting (bawaan mesh-penting-2kevnee56c4;
#                     kosong = semua kembali ke satu topik)
#   NTFY_TOKEN        token opsional (dikirim sebagai Bearer)
#   NTFY_LOKAL        ntfy lokal     (bawaan http://192.168.200.253:7200; kosong = matikan)
#   NOTIF_SNR_AMBANG  ambang SNR (dB)         (bawaan -7; "off" = matikan)
#   NOTIF_SNR_MARGIN  histeresis pemulihan    (bawaan 3)
#   NOTIF_HOP_NAIK    kenaikan hop pemicu     (bawaan 1; "off" = matikan)
#   NOTIF_LINGKUP     "lora" (bawaan) = hanya node radio langsung,
#                     "semua" = ikut node yang masuk lewat MQTT
#   NOTIF_NODE        daftar ID dipisah koma, mis. "!da5a16f8,!02ee76d0"
#   NOTIF_KECUALI     daftar ID yang JANGAN dipantau
#   NOTIF_ABSEN       berapa putaran absen sebelum dilaporkan hilang (bawaan 2)
#   NOTIF_DB_AMBANG   ambang peringatan database gateway (bawaan 190)
#   NOTIF_SARAN_FAVORIT  "0" mematikan saran menandai Favorite
#   NOTIF_KONTAK_BARU "0" mematikan kabar node LoRa baru terdeteksi langsung
#   NOTIF_JEDA_KONTAK jeda kabar "kontak radio kembali" per node (detik, bawaan 21600)
#   NOTIF_BASI_GW     ambang umur data gateway (detik, bawaan 180; "off" mematikan)
#   NOTIF_ABSEN_GW    putaran gagal berturut-turut sebelum dilaporkan (bawaan 2)
#
# Mengapa lingkup dibatasi: database satu node bisa berisi ratusan node dari
# broker MQTT publik (mesh se-Indonesia). Tanpa pembatasan ini, notifikasi akan
# berbunyi untuk node orang lain yang tidak ada hubungannya dengan jaringan RF
# Anda. Lingkup "lora" hanya menyorot node yang benar-benar terdengar radio.
#
# Aman: hanya membaca /data.json dan mengirim HTTP POST ke ntfy.
# ============================================================

import json
import os
import sys
import time
import urllib.error
import urllib.request

AKAR = os.path.dirname(os.path.abspath(__file__))
BAWAAN_DATA = "http://127.0.0.1:9208/data.json"
BAWAAN_SERVER = "https://ntfy.adminforge.de"
BAWAAN_TOPIK = "mesh-6h4v8p2rxq"
# Topik KEDUA, khusus kabar yang harus benar-benar terlihat: gateway mati,
# node LoRa terdeteksi langsung, dan node yang tersambung gateway menjadi
# offline. Dipisah karena frekuensinya jauh lebih jarang daripada kabar rutin
# (baterai, SNR lemah, hop bertambah, saran Favorite) - dan di ponsel, langganan
# terpisah berarti nada dering dan aturan "jangan ganggu" bisa disetel sendiri
# untuknya. Kabar PEMULIHAN dari ketiga hal itu ikut ke sini juga, supaya topik
# ini tidak pernah berbunyi tanpa kabar sembuhnya. Nama topik adalah satu-satunya
# "sandi" - biarkan acak. Kosongkan (NTFY_TOPIK_PENTING=) untuk menggabungkan
# kembali semuanya ke BAWAAN_TOPIK.
BAWAAN_TOPIK_PENTING = "mesh-penting-2kevnee56c4"
BAWAAN_LOKAL = "http://192.168.200.253:7200"
BAWAAN_STATE = os.path.join(AKAR, "notif-meshtastic-state.json")
BAWAAN_AMBANG_BATERAI = 20
BAWAAN_OFFLINE_SECS = 10800
# Link: sinyal dianggap lemah bila SNR turun di bawah ambang; dianggap pulih
# bila naik kembali melewati ambang + margin (histeresis, mencegah notifikasi
# bolak-balik saat SNR berayun di sekitar ambang). "off" mematikan.
BAWAAN_SNR_AMBANG = -7.0
BAWAAN_SNR_MARGIN = 3.0
# Hop: peringatan bila hop node bertambah >= nilai ini dari titik TERBAIKNYA
# (baseline = hop terkecil yang pernah terlihat), lalu pulih saat kembali ke
# baseline. 0 / "off" mematikan.
BAWAAN_HOP_NAIK = 1
# Berapa putaran berturut-turut sebuah node boleh absen dari database sebelum
# dilaporkan hilang (mencegah laporan palsu karena satu pembacaan gagal).
BAWAAN_ABSEN_TOLERANSI = 2
# Ambang peringatan isi database gateway (lihat penjelasan di exporter).
BAWAAN_DB_AMBANG = 190
# Setelah reset-node.py mengosongkan daftar node, SEMUA node memang hilang dari
# daftar. Selama jendela ini, alarm "hilang dari database" ditahan agar reset
# tidak dilaporkan sebagai kerusakan.
BAWAAN_JENDELA_RESET = 1800
BAWAAN_MARKER = os.path.join(AKAR, "reset-terakhir.json")

# --- kabar "node LoRa terdeteksi langsung" ---------------------------------
# SNR hanya terisi bila radio gateway SENDIRI yang menerima paket node itu.
# Jadi SNR yang ada + jalur radio = bukti kontak radio, bukan paket yang
# menumpang internet (MQTT). Kabar ini menyebut id node dan KUALITAS sinyalnya.
BAWAAN_KONTAK_BARU = True
# Jeda minimum sebelum kabar "kontak radio kembali" boleh diulang untuk node
# yang sama. Jalur (`via`) mengikuti paket TERAKHIR, jadi node yang berada di
# antara dua jalur bisa bergantian radio <-> MQTT; tanpa jeda ini tiap
# pergantian menjadi notifikasi.
BAWAAN_JEDA_KONTAK = 6 * 3600
MUTU_KATA = {3: "Baik", 2: "Cukup", 1: "Buruk", 0: "Nihil"}
# Lantai demodulasi bawaan (LONG_FAST) dipakai HANYA bila exporter belum
# mengirimkan lantai presetnya sendiri di /data.json.
BAWAAN_LANTAI_SNR = -17.5

# --- kabar "gateway mati" --------------------------------------------------
# Ambang umur data: exporter yang hidup tetapi loop pengumpulnya tersangkut
# tetap melayani /data.json dengan isi lama. Umur itulah tanda paling andal
# bahwa "hidup" bukan berarti "membaca gateway".
BAWAAN_BASI_GW = 180
# Berapa putaran berturut-turut gagal sebelum dilaporkan (mencegah satu
# kegagalan sesaat - mis. exporter sedang restart - menjadi alarm palsu).
BAWAAN_ABSEN_GW = 2

USAGE = """notif-meshtastic.py - notifikasi ntfy untuk node Meshtastic

Pakai:
  python notif-meshtastic.py [opsi]

Opsi:
  --data URL        alamat /data.json exporter (bawaan %s)
  --data-cadangan URL1,URL2  sumber /data.json cadangan bila utama tak terbaca
  --state BERKAS    berkas penyimpan status
  --interval DET    jeda antar putaran (bawaan 60)
  --sekali          jalankan satu putaran lalu keluar
  --lapor-awal      kirim juga untuk node yang sudah offline saat pertama jalan
  --semua-node      ikut pantau node yang masuk lewat MQTT (bawaan: hanya LoRa)
  --node ID1,ID2    batasi ke node tertentu saja (paling ketat)
  --kecuali ID1,ID2 jangan pantau node tertentu (mis. node yang sudah dibongkar)
  --absen N         berapa putaran absen sebelum dilaporkan hilang (bawaan 2)
  --db-ambang N     ambang peringatan database gateway (bawaan 190)
  --jendela-reset DETIK  tenang sesudah reset-node.py (bawaan 1800)
  --tanpa-saran-favorit  matikan saran menandai node sebagai Favorite
  --ambang-baterai N   ambang baterai rendah (bawaan %d; 0 = matikan)
  --ambang-snr N    ambang SNR lemah (bawaan %s; off = matikan)
  --margin-snr N    histeresis pemulihan SNR (bawaan %s)
  --hop-naik N      peringatan bila hop bertambah >= N (bawaan %s; off = matikan)
  --tanpa-kontak    jangan kabari node LoRa yang baru terdeteksi langsung
  --jeda-kontak DET jeda minimum kabar "kontak radio kembali" per node (bawaan %d)
  --basi-gw DETIK   umur data yang masih dianggap sehat (bawaan %d; off = matikan)
  --absen-gw N      putaran gagal berturut-turut sebelum Gateway MATI dilaporkan
                    (bawaan %d)
  --topik-penting NAMA  topik kedua untuk kabar penting: gateway mati/pulih,
                    node LoRa terdeteksi langsung, node offline/pulih
                    (bawaan %s; kosongkan untuk memakai satu topik saja)
  --server URL / --topik NAMA / --token TOKEN / --lokal URL
  -h, --help        tampilkan bantuan ini

Lingkungan: MESH_DATA, MESH_DATA_CADANGAN, NTFY_SERVER, NTFY_TOPIK,
            NTFY_TOPIK_PENTING, NTFY_TOKEN, NTFY_LOKAL,
            NOTIF_SNR_AMBANG, NOTIF_SNR_MARGIN, NOTIF_HOP_NAIK,
            NOTIF_KONTAK_BARU, NOTIF_JEDA_KONTAK, NOTIF_BASI_GW, NOTIF_ABSEN_GW
""" % (BAWAAN_DATA, BAWAAN_AMBANG_BATERAI, BAWAAN_SNR_AMBANG,
         BAWAAN_SNR_MARGIN, BAWAAN_HOP_NAIK, BAWAAN_JEDA_KONTAK,
         BAWAAN_BASI_GW, BAWAAN_ABSEN_GW, BAWAAN_TOPIK_PENTING)


def durasi(detik):
    if detik is None:
        return "tidak diketahui"
    detik = int(max(0, detik))
    hari, sisa = divmod(detik, 86400)
    jam, sisa = divmod(sisa, 3600)
    menit, _ = divmod(sisa, 60)
    if hari:
        return "%d hari %d jam" % (hari, jam)
    if jam:
        return "%d jam %d menit" % (jam, menit)
    if menit:
        return "%d menit" % menit
    return "%d detik" % detik


def ambil_data(url, timeout=15):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "notif-meshtastic/1.0")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def ambil_data_aman(url, timeout=15):
    """Ambil data exporter DAN alasannya bila gagal.

    Kembalikan (data, galat): galat None berarti pembacaan berhasil. Dibedakan
    dari data kosong, karena "exporter mati" dan "gateway melaporkan nol node"
    adalah dua kejadian berbeda dan pesan ke pengguna tidak boleh tertukar.
    """
    try:
        return ambil_data(url, timeout), None
    except Exception as e:
        return {}, "%s: %s" % (type(e).__name__, e)


def daftar_tujuan(utama, cadangan):
    """Urutan sumber data: utama dulu, lalu cadangan (dipisah koma/spasi).

    Dipakai bergilir: bila /data.json utama tak terbaca (mis. host exporter
    mati), notifier pindah ke cadangan; bila cadangan pun gagal, ia kembali
    mencoba yang utama. Jadi begitu sumber utama pulih, ia terpakai lagi tanpa
    perlu restart. Bila `cadangan` kosong, perilakunya sama seperti sebelumnya
    (satu sumber saja).
    """
    hasil = [utama]
    for bagian in (cadangan or "").replace(",", " ").split():
        if bagian and bagian not in hasil:
            hasil.append(bagian)
    return hasil


def ambil_data_bergilir(opsi):
    """Ambil /data.json dari sumber aktif; bila gagal, bergilir ke cadangan.

    Mengembalikan (data, galat, url) seperti ambil_data_aman. Sumber aktif
    disimpan di opsi["_sumber_idx"] supaya putaran berikutnya memakai yang
    sama, dan bergilir lagi hanya bila sumber itu benar-benar gagal.
    """
    tujuan = opsi.get("_tujuan")
    if not tujuan:
        tujuan = daftar_tujuan(opsi["data"], opsi.get("data_cadangan") or "")
        opsi["_tujuan"] = tujuan
    idx = opsi.get("_sumber_idx", 0) % len(tujuan)
    percobaan = 0
    galat = "tidak ada sumber data"
    while percobaan < len(tujuan):
        url = tujuan[idx]
        data, galat = ambil_data_aman(url)
        if not galat:
            opsi["_sumber_idx"] = idx
            return data, None, url
        percobaan += 1
        if len(tujuan) > 1:
            idx = (idx + 1) % len(tujuan)
            print("[sumber data %s gagal: %s] mencoba %s" % (url, galat, tujuan[idx]),
                  file=sys.stderr)
    opsi["_sumber_idx"] = idx
    return {}, galat, tujuan[idx]


def mutu_dari(item, lantai=BAWAAN_LANTAI_SNR):
    """Kata mutu sinyal sebuah node, atau None bila belum pernah diukur.

    Sumber utamanya kolom `mutu_sinyal` dari /data.json: exporter sudah
    menghitungnya dengan tabel lantai demodulasi preset resmi Meshtastic (lihat
    exporter-meshtastic.py dan README), jadi notifier TIDAK menyalin tabel itu.
    Bila exporter-nya lebih tua dan belum punya kolom tersebut, angkanya
    dihitung di sini dengan ambang yang sama: 0 / -5.5 / -7.5 dB di bawah lantai.
    """
    tingkat = item.get("mutu_sinyal")
    if tingkat is None:
        snr = item.get("snr")
        if item.get("via") == "mqtt" or not isinstance(snr, (int, float)):
            return None
        try:
            margin = float(snr) - float(lantai)
        except (TypeError, ValueError):
            return None
        tingkat = 3 if margin > 0 else 2 if margin > -5.5 else 1 if margin >= -7.5 else 0
    return MUTU_KATA.get(int(tingkat))


def kontak_radio(item):
    """True bila node ini benar-benar terdengar LANGSUNG oleh radio gateway."""
    return (item.get("via") in ("lora", "diri")
            and isinstance(item.get("snr"), (int, float)))


# ------------------------------------------------------------
# Penyusun isi notifikasi
# ------------------------------------------------------------

def _baris_sinyal(mutu, snr, lantai=None, label="Kualitas sinyal terakhir"):
    """Satu baris "kualitas sinyal" untuk dipakai beberapa pesan.

    Mutu ditulis lebih dulu karena itulah yang bisa dibaca cepat; angka SNR dan
    lantainya menyusul sebagai bukti - supaya pembaca tidak menebak dari mana
    kata "Baik" itu datang.
    """
    if mutu and isinstance(snr, (int, float)):
        return "%s: %s (SNR %.1f dB%s)" % (
            label, mutu, snr,
            "; lantai preset %+.1f dB" % float(lantai) if lantai is not None else "")
    if isinstance(snr, (int, float)):
        return "%s: SNR %.1f dB" % (label, snr)
    return None


def pesan_offline(nama, node_id, role, usia, mutu=None, snr=None, lantai=None, hop=None):
    baris = ["Node %s (%s) tidak terdengar lagi." % (nama, node_id),
             "Role   : %s" % role,
             "Terakhir terdengar: %s lalu" % durasi(usia)]
    sinyal = _baris_sinyal(mutu, snr, lantai)
    if sinyal:
        baris.append(sinyal)
    if isinstance(hop, (int, float)):
        baris.append("Jarak terakhir: %d hop dari gateway" % int(hop))
    baris.append("Periksa daya/antena node tersebut.")
    return _penting({
        "judul": "Node Meshtastic OFFLINE: %s" % nama,
        "pesan": "\n".join(baris),
        "prioritas": "high",
        "tag": "red_circle",
    })


def pesan_kontak_radio(item, lama=False, lantai=None):
    """Kabar node LoRa yang terdengar LANGSUNG oleh radio gateway.

    `lama=True` dipakai untuk kontak yang TERUKUR KEMBALI - node yang tadinya
    hanya terdengar lewat MQTT, atau yang sempat tidak punya SNR sama sekali.

    `lantai` adalah lantai demodulasi preset gateway (dari kesehatan_gateway di
    /data.json). Tanpa itu angka SNR tidak bisa ditafsirkan - node dengan SNR
    -18 dB itu BAIK pada preset LONG_SLOW (lantai -20) tetapi BURUK pada
    SHORT_TURBO (lantai -7.5).
    """
    node_id = item.get("node_id") or "?"
    nama = item.get("long_name") or item.get("short_name") or node_id
    if lantai is None:
        lantai = item.get("lantai_snr") if item.get("lantai_snr") is not None \
            else BAWAAN_LANTAI_SNR
    mutu = mutu_dari(item, lantai)
    baris = [("Node %s (%s) kembali terukur lewat RADIO gateway." % (nama, node_id))
             if lama else
             ("Node %s (%s) terdeteksi LANGSUNG oleh radio gateway." % (nama, node_id)),
             "ID node  : %s" % node_id]
    sinyal = _baris_sinyal(mutu, item.get("snr"), lantai, "Kualitas sinyal")
    if sinyal:
        baris.append(sinyal)
    if item.get("role"):
        baris.append("Role     : %s" % item["role"])
    if isinstance(item.get("hops"), (int, float)):
        baris.append("Hop      : %d" % int(item["hops"]))
    baterai = item.get("battery")
    if isinstance(baterai, (int, float)) and 0 <= baterai <= 100:
        baris.append("Baterai  : %d%%" % int(baterai))
    baris.append("")
    baris.append("SNR itu diukur radio gateway sendiri, jadi node ini benar-benar "
                 "terdengar lewat udara - bukan node yang paketnya menumpang "
                 "internet (MQTT).")
    return _penting({
        "judul": ("Kontak radio kembali: %s" if lama else "Node LoRa terdeteksi: %s") % nama,
        "pesan": "\n".join(baris),
        "prioritas": "default",
        "tag": "signal_strength",
    })


def pesan_gw_mati(alasan, sudah=0):
    return _penting({
        "judul": "GATEWAY Meshtastic MATI / tidak terbaca",
        "pesan": ("Exporter di host tidak bisa membaca gateway.\n"
                  "Alasan  : %s\n"
                  "Sudah   : %s\n\n"
                  "Selama ini pemantauan buta: halaman web maupun notifikasi node "
                  "tidak bisa dipercaya, karena datanya memang tidak diperbarui.\n"
                  "Periksa berurutan: daya gateway, kabel/jaringan ke gateway, lalu "
                  "layanan exporter di host."
                  % (alasan or "tidak diketahui", durasi(sudah))),
        "prioritas": "max",
        "tag": "red_circle",
    })


def pesan_gw_pulih(lama):
    return _penting({
        "judul": "Gateway Meshtastic terbaca kembali",
        "pesan": ("Exporter sudah bisa membaca gateway lagi.\n"
                  "Lama tidak terbaca: %s\n\n"
                  "Pemantauan node (offline/pulih, baterai, sinyal) berjalan normal "
                  "lagi mulai sekarang." % durasi(lama)),
        "prioritas": "default",
        "tag": "green_circle",
    })


def pesan_pulih(nama, node_id, sejak, sekarang):
    return _penting({
        "judul": "Node Meshtastic ONLINE: %s" % nama,
        "pesan": ("Node %s (%s) kembali terdengar.\n"
                  "Lama offline: %s" % (nama, node_id, durasi(sekarang - sejak))),
        "prioritas": "default",
        "tag": "green_circle",
    })


def pesan_baterai(nama, node_id, persen):
    return {
        "judul": "Baterai node %s lemah: %d%%" % (nama, int(persen)),
        "pesan": ("Level baterai node %s (%s) tinggal %d%%.\n"
                  "Siapkan penggantian/pengisian daya." % (nama, node_id, int(persen))),
        "prioritas": "high",
        "tag": "warning",
    }


def pesan_baterai_pulih(nama, node_id, persen):
    return {
        "judul": "Baterai node %s normal kembali: %d%%" % (nama, int(persen)),
        "pesan": "Level baterai node %s (%s) kembali ke %d%%." % (nama, node_id, int(persen)),
        "prioritas": "default",
        "tag": "battery",
    }


def pesan_snr_lemah(nama, node_id, snr, ambang):
    return {
        "judul": "Sinyal node %s melemah: %.1f dB" % (nama, snr),
        "pesan": ("SNR link ke node %s (%s) turun ke %.1f dB (ambang %.1f dB).\n"
                  "Cek antena/ketinggian atau halangan antara node dan gateway."
                  % (nama, node_id, snr, ambang)),
        "prioritas": "high",
        "tag": "signal_strength",
    }


def pesan_snr_pulih(nama, node_id, snr):
    return {
        "judul": "Sinyal node %s membaik: %.1f dB" % (nama, snr),
        "pesan": "SNR link ke node %s (%s) kembali normal di %.1f dB." % (nama, node_id, snr),
        "prioritas": "default",
        "tag": "signal_strength",
    }


def pesan_hop_naik(nama, node_id, hop, baseline):
    return {
        "judul": "Rute node %s bertambah: %d hop" % (nama, int(hop)),
        "pesan": ("Node %s (%s) sekarang %d hop dari gateway (sebelumnya %d hop).\n"
                  "Biasanya berarti node perantara ikut putus - periksa node di antaranya."
                  % (nama, node_id, int(hop), int(baseline))),
        "prioritas": "high",
        "tag": "arrows_counterclockwise",
    }


def pesan_hop_pulih(nama, node_id, hop):
    return {
        "judul": "Rute node %s normal kembali: %d hop" % (nama, int(hop)),
        "pesan": "Node %s (%s) kembali ke %d hop dari gateway." % (nama, node_id, int(hop)),
        "prioritas": "default",
        "tag": "arrows_counterclockwise",
    }


def pesan_hilang(nama, node_id, sejak):
    lama = (" Node terakhir terlihat %s lalu." % durasi(time.time() - sejak)) if sejak else ""
    return {
        "judul": "Node %s HILANG dari database gateway" % nama,
        "pesan": ("Node %s (%s) tidak lagi ada di daftar database gateway.%s\n"
                  "Kemungkinan: tergeser karena database gateway penuh, atau node "
                  "keluar dari jangkauan radio." % (nama, node_id, lama)),
        "prioritas": "high",
        "tag": "warning",
    }


def pesan_muncul(nama, node_id, sejak):
    lama = (" Setelah absen %s." % durasi(time.time() - sejak)) if sejak else ""
    return {
        "judul": "Node %s muncul kembali di database" % nama,
        "pesan": "Node %s (%s) kembali terdaftar di gateway.%s" % (nama, node_id, lama),
        "prioritas": "default",
        "tag": "green_circle",
    }


def pesan_gateway_reboot(gw, tambahan):
    return {
        "judul": "Gateway Meshtastic baru saja reboot",
        "pesan": ("Node gateway %s reboot lagi (bertambah %d; total %s kali).\n"
                  "Uptime sekarang: %s.\n"
                  "Reboot berulang biasanya berarti masalah catu daya, panas, atau watchdog."
                  % (gw.get("node_id") or "?", tambahan, gw.get("reboot_count"),
                     durasi(gw.get("uptime")))),
        "prioritas": "high",
        "tag": "recycle",
    }


def pesan_db_penuh(gw, nodedb, ambang):
    return {
        "judul": "Database node gateway hampir penuh (%s entri)" % int(nodedb),
        "pesan": ("Database node gateway %s berisi %s entri (ambang %d).\n"
                  "Saat database penuh, Meshtastic membuang node terlama/paling tidak "
                  "menarik - node RF yang jarang memancar bisa ikut tergeser.\n"
                  "Tindakan: tandai node RF Anda sebagai Favorite, dan kurangi downlink MQTT "
                  "pada gateway (atau pindah ke broker sendiri)."
                  % (gw.get("node_id") or "?", int(nodedb), ambang)),
        "prioritas": "high",
        "tag": "warning",
    }


def pesan_saran_favorit(item):
    nama = item.get("long_name") or item.get("node_id")
    return {
        "judul": "Node %s belum ditandai Favorite" % nama,
        "pesan": ("Node RF %s (%s) belum ditandai Favorite di gateway.\n"
                  "Node tanpa Favorite lebih mudah tergeser dari database saat penuh.\n"
                  "Cara: buka aplikasi Meshtastic pada gateway -> daftar node -> pilih node "
                  "ini -> tandai Favorite." % (nama, item.get("node_id"))),
        "prioritas": "default",
        "tag": "star",
    }


# ------------------------------------------------------------
# Deteksi perubahan status
# ------------------------------------------------------------

def _tandai(pesan, node_id):
    pesan = dict(pesan)
    pesan["node_id"] = node_id
    return pesan


def topik_untuk(pesan, topik_umum, topik_penting):
    """Topik yang dipakai sebuah notifikasi: topik penting atau topik umum.

    Dipisah jadi fungsi sendiri supaya pengujian bisa memakai aturan yang SAMA
    dengan layanan - kalau aturannya disalin ke dalam uji, ujinya bisa lulus
    sementara layanannya mengirim ke topik yang salah.
    """
    if pesan.get("penting") and topik_penting:
        return topik_penting
    return topik_umum


def _penting(pesan):
    """Tandai notifikasi sebagai "kabar penting" (dikirim ke topik terpisah).

    Dipakai untuk lima pesan: gateway mati & pulih, node LoRa terdeteksi &
    kontak radio kembali, serta node offline & pulih. Penandanya dibawa di
    dalam pesannya sendiri, bukan disimpulkan dari judul, supaya
    penambahan/penyuntingan kalimat tidak diam-diam memindahkan kabar penting
    keluar dari topiknya.
    """
    pesan = dict(pesan)
    pesan["penting"] = True
    return pesan


def dalam_jendela_reset(berkas, jendela):
    """True bila reset-node.py baru saja berjalan (masih dalam jendela tenang)."""
    if jendela <= 0 or not os.path.exists(berkas):
        return False, 0
    try:
        with open(berkas, encoding="utf-8") as f:
            data = json.load(f)
        selisih = time.time() - float(data.get("waktu", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return False, 0
    if 0 <= selisih < jendela:
        return True, int(jendela - selisih)
    return False, 0


def _tandai_gw(pesan):
    """Tandai notifikasi yang berasal dari kesehatan gateway (bukan per node)."""
    pesan = dict(pesan)
    pesan["gw"] = True
    return pesan


def deteksi(data, state, offline_secs=BAWAAN_OFFLINE_SECS, baterai_ambang=BAWAAN_AMBANG_BATERAI,
            lapor_awal=False, snr_ambang=BAWAAN_SNR_AMBANG, snr_margin=BAWAAN_SNR_MARGIN,
            hop_naik=BAWAAN_HOP_NAIK, lingkup="lora", node_diminta=None, kecuali=None,
            absen_toleransi=BAWAAN_ABSEN_TOLERANSI, jendela_reset=False, sekarang=None,
            konfirmasi_kontak=BAWAAN_KONTAK_BARU, jeda_kontak=BAWAAN_JEDA_KONTAK,
            data_terbaca=True, lantai_bawaan=None):
    """Bandingkan data eksporter dengan status sebelumnya.

    Kembalikan (daftar_notifikasi, state_baru). Notifikasi hanya dibuat saat
    ada PERUBAHAN, jadi tidak ada pesan berulang tiap putaran.

    `data_terbaca=False` berarti /data.json gagal dibaca (exporter mati). Dalam
    keadaan itu tidak ada penilaian apa pun yang boleh dibuat - dan catatan lama
    harus UTUH, karena kalau dikosongkan setiap gangguan sebentar akan membuat
    notifier "lupa" semua node lalu melaporkannya sebagai pulih/hilang saat
    gateway kembali. Kejadian itu dilaporkan terpisah oleh deteksi_gateway_koneksi().
    """
    sekarang = sekarang if sekarang is not None else time.time()
    lama = (state or {}).get("node", {})
    baru = {}
    notif = []

    # Lantai demodulasi preset gateway dipakai untuk menafsirkan SNR. /data.json
    # mengirimkannya SEKALI untuk seluruh halaman (di kesehatan_gateway), bukan
    # per node; kunci per node hanya menang bila ada di exporter yang lebih baru.
    if lantai_bawaan is None:
        lantai_bawaan = ((data or {}).get("kesehatan_gateway") or {}).get("lantai_snr")
    if not isinstance(lantai_bawaan, (int, float)):
        lantai_bawaan = BAWAAN_LANTAI_SNR

    if not data_terbaca:
        return [], dict(state or {})

    daftar = data.get("node", [])
    hadir = set()
    # Node yang ADA di data tetapi tidak masuk lingkup pantauan (mis. jalur
    # MQTT saat lingkup "lora"). Dicatat supaya tidak dikira HILANG dari
    # database: node yang paket terakhirnya kebetulan datang dari internet
    # masih terdaftar di gateway, hanya tidak kita pantau.
    di_luar_lingkup = set()
    for item in daftar:
        node_id = item.get("node_id") or "?"

        # --- penyaring lingkup ---
        if kecuali and node_id in kecuali:
            continue
        if node_diminta and node_id not in node_diminta:
            continue
        if lingkup == "lora" and item.get("via") != "lora":
            di_luar_lingkup.add(node_id)
            continue
        # Node yang belum pernah terdengar sama sekali tidak punya status yang
        # bisa dipastikan - melewatinya mencegah alarm palsu.
        if item.get("last_heard_seconds") is None:
            continue
        hadir.add(node_id)

        nama = item.get("long_name") or item.get("short_name") or node_id
        role = item.get("role") or "-"
        usia = item.get("last_heard_seconds")
        snr = item.get("snr")
        # Lantai demodulasi preset gateway. /data.json mengirimkannya di
        # kesehatan_gateway (BUKAN per node), jadi `lantai_bawaan` dari pemanggil
        # itulah yang dipakai; kunci per node hanya menang bila ada (versi
        # exporter yang lebih baru). Tanpa ini, teks notifikasi akan memakai
        # lantai bawaan - dan salah begitu preset gateway diubah.
        lantai = item.get("lantai_snr")
        if lantai is None:
            lantai = lantai_bawaan
        mutu = mutu_dari(item, lantai)
        online_eksp = item.get("online")
        if online_eksp is None:
            online = usia is not None and usia <= offline_secs
        else:
            online = bool(online_eksp)

        sblm = lama.get(node_id)

        # Node yang tadinya HILANG dari database dan kini muncul lagi: beri kabar
        # sendiri, dan paksa status lama "online" agar tidak ada pesan pemulihan
        # ganda di putaran yang sama.
        if (sblm is not None and not jendela_reset
                and int(sblm.get("absen") or 0) >= absen_toleransi):
            notif.append(_tandai(pesan_muncul(nama, node_id, sblm.get("hilang_sejak")), node_id))
            sblm = dict(sblm, online=True)

        offline_sejak = (sblm or {}).get("offline_sejak")
        if online:
            offline_sejak = None
        elif offline_sejak is None:
            offline_sejak = sekarang

        # Satu node hanya boleh melahirkan SATU pesan status per putaran;
        # tanpa penanda ini, node yang baru pulih akan langsung menyusul dengan
        # pesan "kontak radio kembali" - dua pesan untuk satu kejadian.
        status_dilaporkan = False
        if sblm is None:
            if lapor_awal and not online:
                notif.append(_tandai(pesan_offline(nama, node_id, role, usia, mutu, snr,
                                                   lantai, item.get("hops")), node_id))
                status_dilaporkan = True
        elif sblm.get("online") and not online:
            notif.append(_tandai(pesan_offline(nama, node_id, role, usia, mutu, snr,
                                               lantai, item.get("hops")), node_id))
            status_dilaporkan = True
        elif not sblm.get("online") and online:
            notif.append(_tandai(pesan_pulih(nama, node_id, offline_sejak or sekarang, sekarang), node_id))
            status_dilaporkan = True

        # --- kontak radio: SNR yang diukur radio GATEWAY sendiri ---
        # Inilah kabar yang diminta: node LoRa yang benar-benar terdengar lewat
        # udara, lengkap dengan id dan kualitas sinyalnya. Karena `via` mengikuti
        # paket TERAKHIR, node di dekat dua jalur bisa bergantian radio/MQTT -
        # karena itu kabar "kontak kembali" diberi jeda minimum per node supaya
        # tidak menjadi banjir pesan.
        kontak = kontak_radio(item)
        snr_sebelum = (sblm or {}).get("snr_diketahui")
        kontak_terakhir = (sblm or {}).get("kontak_dilaporkan") or 0
        if konfirmasi_kontak and online and kontak and not status_dilaporkan:
            if sblm is None:
                # Pemantau baru mulai: kabari hanya bila diminta (--lapor-awal),
                # supaya start pertama tidak membanjiri ntfy dengan seluruh node
                # yang memang sudah lama terdengar.
                if lapor_awal:
                    notif.append(_tandai(pesan_kontak_radio(item, lantai=lantai), node_id))
                    kontak_terakhir = sekarang
            elif (snr_sebelum is False
                  and sekarang - kontak_terakhir >= jeda_kontak):
                notif.append(_tandai(pesan_kontak_radio(item, lama=True, lantai=lantai),
                                     node_id))
                kontak_terakhir = sekarang
        # Catatan migrasi: node yang sudah ada di state SEBELUM fitur ini ada
        # tidak punya kunci snr_diketahui. Itu dibaca sebagai "sudah diketahui"
        # supaya pembaruan ini tidak memicu satu gelombang kabar sekaligus.
        if snr_sebelum is None:
            snr_diketahui = True if sblm is not None else kontak
        else:
            snr_diketahui = kontak

        baterai = item.get("battery")
        rendah = (isinstance(baterai, (int, float)) and baterai <= baterai_ambang
                  and baterai <= 100)
        if baterai_ambang > 0 and sblm is not None and isinstance(baterai, (int, float)):
            if rendah and not sblm.get("baterai_rendah"):
                notif.append(_tandai(pesan_baterai(nama, node_id, baterai), node_id))
            elif not rendah and sblm.get("baterai_rendah"):
                notif.append(_tandai(pesan_baterai_pulih(nama, node_id, baterai), node_id))

        # --- kualitas link: SNR ---
        snr_lemah = (sblm or {}).get("snr_lemah", False)
        if online and snr_ambang is not None and isinstance(snr, (int, float)):
            if not snr_lemah and snr < snr_ambang:
                notif.append(_tandai(pesan_snr_lemah(nama, node_id, snr, snr_ambang), node_id))
                snr_lemah = True
            elif snr_lemah and snr >= snr_ambang + snr_margin:
                notif.append(_tandai(pesan_snr_pulih(nama, node_id, snr), node_id))
                snr_lemah = False

        # --- kualitas link: hop ---
        hop = item.get("hops")
        hop_baseline = (sblm or {}).get("hop_baseline")
        hop_naik_aktif = (sblm or {}).get("hop_naik", False)
        if online and hop_naik > 0 and isinstance(hop, (int, float)):
            if hop_baseline is None or hop < hop_baseline:
                hop_baseline = hop
            if not hop_naik_aktif and hop >= hop_baseline + hop_naik:
                notif.append(_tandai(pesan_hop_naik(nama, node_id, hop, hop_baseline), node_id))
                hop_naik_aktif = True
            elif hop_naik_aktif and hop <= hop_baseline:
                notif.append(_tandai(pesan_hop_pulih(nama, node_id, hop), node_id))
                hop_naik_aktif = False

        baru[node_id] = {
            "online": online,
            "nama": nama,
            "offline_sejak": offline_sejak,
            "baterai_rendah": rendah,
            "snr_lemah": snr_lemah,
            "hop_baseline": hop_baseline,
            "hop_naik": hop_naik_aktif,
            "snr_diketahui": snr_diketahui,
            "kontak_dilaporkan": kontak_terakhir,
            "absen": 0,
        }

    # Node yang tadinya dipantau tetapi sudah tidak ada lagi di daftar data.
    # Hanya diperiksa bila daftar datanya wajar (tidak kosong), supaya kegagalan
    # membaca exporter tidak dilaporkan sebagai "node hilang".
    if daftar:
        for node_id, sblm in lama.items():
            if node_id in hadir:
                # Catatannya sudah dihitung ulang di loop di atas. JANGAN ditimpa
                # dengan catatan lama - kalau ditimpa, status node tidak pernah
                # maju dan setiap putaran kembali melaporkan kejadian yang sama
                # (mis. node yang sudah offline dilaporkan offline terus).
                continue
            if node_id in di_luar_lingkup:
                # Node masih ada di data, hanya tidak masuk lingkup pantauan
                # (mis. paket terakhirnya lewat MQTT). Bukan node hilang, dan
                # catatannya harus tetap utuh supaya saat kembali ke jalur radio
                # ia tidak dianggap sebagai kejadian baru.
                baru[node_id] = dict(sblm)
                baru[node_id]["absen"] = 0
                baru[node_id]["hilang_sejak"] = None
                continue
            if jendela_reset:
                # Baru saja ada reset NodeDB: ketiadaan node memang wajar, jadi
                # catatannya ditahan tanpa alarm dan penghitung absen di-nol-kan.
                entri = dict(sblm)
                entri["absen"] = 0
                entri["hilang_sejak"] = None
                baru[node_id] = entri
                continue
            absen = int(sblm.get("absen") or 0) + 1
            entri = dict(sblm)
            entri["absen"] = absen
            if absen == 1:
                entri["hilang_sejak"] = sekarang
            baru[node_id] = entri
            if absen == absen_toleransi:
                notif.append(_tandai(
                    pesan_hilang(sblm.get("nama") or node_id, node_id, entri.get("hilang_sejak")),
                    node_id))

    return notif, {"node": baru, "diperbarui": sekarang}


def deteksi_gateway_koneksi(data, galat, state, basi=BAWAAN_BASI_GW, absen=BAWAAN_ABSEN_GW,
                            sekarang=None):
    """Pantau apakah gateway masih bisa dibaca SAMA SEKALI.

    Diperiksa dari sisi notifier, bukan dari halaman web: saat gateway mati,
    halaman web tidak bisa memberi tahu siapa pun - ia sendiri yang diam. Tiga
    sebab yang dianggap "gateway tidak terbaca", semuanya kegagalan yang benar-
    benar terjadi di perangkat ini:

      1. exporter tidak menjawab (layanan mati / host mati);
      2. data exporter BASI - exporter hidup dan tetap melayani /data.json, tetapi
         loop pengumpulnya tersangkut sehingga isinya lama (kendala 28 Sep 2026);
      3. gateway tidak melaporkan apa pun: 0 node DAN firmware tidak terbaca
         ("hidup tetapi buta" - up=1, halaman kosong, tanpa satu pun alert).

    Kembalikan (notifikasi, state_gateway).
    """
    sekarang = sekarang if sekarang is not None else time.time()
    sg = dict((state or {}).get("gateway_koneksi") or {})
    notif = []
    if basi is None:
        return notif, sg

    alasan = None
    if galat:
        alasan = "exporter tidak menjawab (%s)" % galat
    else:
        umur = data.get("umur_data_seconds")
        gw = data.get("kesehatan_gateway") or {}
        if isinstance(umur, (int, float)) and umur > basi:
            alasan = ("data exporter sudah basi %s (ambang %s) - loop pengumpul "
                      "tersangkut, gateway tidak lagi dibaca" % (durasi(umur), durasi(basi)))
        elif data.get("jumlah_node") == 0 and not gw.get("firmware"):
            # Syaratnya "jumlah_node ADA dan bernilai 0", bukan "kosong". Payload
            # yang tidak lengkap (kunci `jumlah_node` tidak dikirim sama sekali)
            # tidak boleh disimpulkan sebagai gateway buta: itu justru bisa
            # terjadi saat exporter baru saja dimulai. Kegagalan membaca gateway
            # sudah tertangkap jalur lain (exporter tidak menjawab / data basi).
            alasan = ("gateway tidak melaporkan apa pun: 0 node dan firmware tidak "
                      "terbaca (exporter hidup tetapi buta)")

    gagal = int(sg.get("gagal") or 0)
    if alasan:
        if gagal == 0:
            sg["sejak"] = sekarang
        gagal += 1
        sg["gagal"] = gagal
        sg["alasan"] = alasan
        if gagal >= absen and not sg.get("mati"):
            sg["mati"] = True
            sg["mulai_mati"] = sg.get("sejak") or sekarang
            notif.append(_tandai_gw(pesan_gw_mati(alasan, sekarang - sg["mulai_mati"])))
    else:
        if sg.get("mati"):
            notif.append(_tandai_gw(pesan_gw_pulih(
                sekarang - (sg.get("mulai_mati") or sekarang))))
        sg["gagal"] = 0
        sg["alasan"] = None
        sg["mati"] = False
        sg["sejak"] = None
    sg["diperiksa"] = sekarang
    return notif, sg


def deteksi_gateway(gw, daftar, state, db_ambang=BAWAAN_DB_AMBANG, saran_favorit=True):
    """Periksa kesehatan gateway: reboot, isi database, dan saran Favorite."""
    sg = dict((state or {}).get("gateway") or {})
    notif = []

    if gw:
        reboot = gw.get("reboot_count")
        if isinstance(reboot, (int, float)) and isinstance(sg.get("reboot_count"), (int, float)):
            if reboot > sg["reboot_count"]:
                notif.append(_tandai_gw(pesan_gateway_reboot(gw, int(reboot - sg["reboot_count"]))))
        nodedb = gw.get("nodedb_count")
        penuh = isinstance(nodedb, (int, float)) and nodedb >= db_ambang
        if penuh and not sg.get("db_penuh"):
            notif.append(_tandai_gw(pesan_db_penuh(gw, nodedb, db_ambang)))
        sg["db_penuh"] = penuh
        sg["nodedb_count"] = nodedb
        if isinstance(reboot, (int, float)):
            sg["reboot_count"] = reboot
        sg["node_id"] = gw.get("node_id")

    if saran_favorit:
        dilaporkan = set(sg.get("favorit_dilaporkan") or [])
        for item in daftar:
            if item.get("via") != "lora" or item.get("last_heard_seconds") is None:
                continue
            node_id = item.get("node_id")
            if node_id in dilaporkan or item.get("favorite"):
                continue
            notif.append(_tandai_gw(pesan_saran_favorit(item)))
            dilaporkan.add(node_id)
        sg["favorit_dilaporkan"] = sorted(dilaporkan)

    return notif, sg


# ------------------------------------------------------------
# Pengiriman multi-kanal (server utama -> ulangi -> ntfy lokal)
# ------------------------------------------------------------

def _aman_header(nilai):
    """Ubah nilai header agar aman dikirim.

    http.client menulis header sebagai latin-1. Nama node Meshtastic sering
    memuat emoji (mis. "MQTT-GateWay_GTP\u26f0"), dan emoji di luar latin-1
    membuat add_header melempar UnicodeEncodeError. Karena error itu turunan
    ValueError - yang ditangkap kirim() - akibatnya SELURUH kanal dilaporkan
    gagal dan notifikasi hilang diam-diam. Nilai non-ASCII dikirim sebagai byte
    UTF-8 supaya lolos tanpa kehilangan karakter.
    """
    try:
        nilai.encode("ascii")
        return nilai
    except UnicodeEncodeError:
        return nilai.encode("utf-8")


def _post(url, isi, header, timeout):
    req = urllib.request.Request(url, data=isi.encode("utf-8"), method="POST")
    for k, v in header.items():
        req.add_header(k, _aman_header(v))
    req.add_header("User-Agent", "notif-meshtastic/1.0")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


def kirim(judul, isi, prioritas, tag, server, topik, token=None, lokal=None, timeout=15):
    """Kirim satu notifikasi. Kembalikan (nama_kanal, galat). Salah satu None."""
    header = {"Title": judul, "Priority": prioritas, "Tags": tag}
    if token:
        header["Authorization"] = "Bearer " + token

    tujuan = []
    if server:
        tujuan.append(("server utama (%s)" % server, server.rstrip("/") + "/" + topik))
    if server:
        tujuan.append(("server utama (percobaan ke-2)", server.rstrip("/") + "/" + topik))
    if lokal:
        tujuan.append(("ntfy lokal (%s)" % lokal, lokal.rstrip("/") + "/" + topik))

    galat = []
    for i, (nama, url) in enumerate(tujuan):
        if nama.endswith("ke-2"):
            time.sleep(3)
        try:
            _post(url, isi, header, timeout)
            return nama, None
        except (urllib.error.URLError, OSError, ValueError) as e:
            galat.append("%s gagal (%s)" % (nama, e))
    return None, " | ".join(galat) or "tidak ada kanal yang dikonfigurasi"


# ------------------------------------------------------------
# Penyimpan status
# ------------------------------------------------------------

def muat_state(berkas):
    try:
        with open(berkas, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def simpan_state(berkas, state):
    tmp = berkas + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, berkas)


# ------------------------------------------------------------
# Program utama
# ------------------------------------------------------------

def angka_atau_off(nilai, bawaan):
    """Ubah teks menjadi float; "off"/kosong berarti fitur dimatikan (None)."""
    if nilai is None:
        return bawaan
    teks = str(nilai).strip().lower()
    if teks in ("off", "none", "tidak", ""):
        return None
    try:
        return float(teks)
    except ValueError:
        return bawaan


def baca_opsi(argv):
    opsi = {
        "data": os.environ.get("MESH_DATA", BAWAAN_DATA),
        "data_cadangan": os.environ.get("MESH_DATA_CADANGAN", ""),
        "state": BAWAAN_STATE,
        "interval": 60,
        "sekali": False,
        "lapor_awal": False,
        "ambang_baterai": BAWAAN_AMBANG_BATERAI,
        "snr_ambang": angka_atau_off(os.environ.get("NOTIF_SNR_AMBANG"), BAWAAN_SNR_AMBANG),
        "snr_margin": angka_atau_off(os.environ.get("NOTIF_SNR_MARGIN"), BAWAAN_SNR_MARGIN),
        "hop_naik": angka_atau_off(os.environ.get("NOTIF_HOP_NAIK"), BAWAAN_HOP_NAIK),
        "kontak_baru": (os.environ.get("NOTIF_KONTAK_BARU", "1") != "0"),
        "jeda_kontak": max(0, int(os.environ.get("NOTIF_JEDA_KONTAK", BAWAAN_JEDA_KONTAK))),
        "basi_gw": angka_atau_off(os.environ.get("NOTIF_BASI_GW"), BAWAAN_BASI_GW),
        "absen_gw": max(1, int(os.environ.get("NOTIF_ABSEN_GW", BAWAAN_ABSEN_GW))),
        "lingkup": (os.environ.get("NOTIF_LINGKUP") or "lora").strip().lower(),
        "kecuali": {x.strip() for x in (os.environ.get("NOTIF_KECUALI") or "").split(",")
                    if x.strip()} or None,
        "absen_toleransi": max(1, int(os.environ.get("NOTIF_ABSEN", BAWAAN_ABSEN_TOLERANSI))),
        "db_ambang": int(os.environ.get("NOTIF_DB_AMBANG", BAWAAN_DB_AMBANG)),
        "saran_favorit": (os.environ.get("NOTIF_SARAN_FAVORIT", "1") != "0"),
        "jendela_reset": int(os.environ.get("NOTIF_JENDELA_RESET", BAWAAN_JENDELA_RESET)),
        "marker": os.environ.get("NOTIF_MARKER", BAWAAN_MARKER),
        "node_diminta": {x.strip() for x in (os.environ.get("NOTIF_NODE") or "").split(",")
                         if x.strip()} or None,
        "server": os.environ.get("NTFY_SERVER", BAWAAN_SERVER),
        "topik": os.environ.get("NTFY_TOPIK", BAWAAN_TOPIK),
        # Topik kedua untuk kabar penting. Sengaja TIDAK memakai `or BAWAAN_*`:
        # nilai kosong berarti pemiliknya memang ingin MEMATIKAN pemisahan itu
        # (semua kembali ke satu topik), bukan ingin nilai bawaan.
        "topik_penting": (os.environ.get("NTFY_TOPIK_PENTING")
                          if os.environ.get("NTFY_TOPIK_PENTING") is not None
                          else BAWAAN_TOPIK_PENTING) or None,
        "token": os.environ.get("NTFY_TOKEN") or None,
        "lokal": os.environ.get("NTFY_LOKAL", BAWAAN_LOKAL),
    }
    kunci = {"--data": "data", "--data-cadangan": "data_cadangan",
             "--state": "state", "--server": "server",
             "--topik": "topik", "--topik-penting": "topik_penting",
             "--token": "token", "--lokal": "lokal"}
    kunci_int = {"--interval": "interval", "--ambang-baterai": "ambang_baterai",
                 "--absen": "absen_toleransi", "--db-ambang": "db_ambang",
                 "--jendela-reset": "jendela_reset", "--absen-gw": "absen_gw",
                 "--jeda-kontak": "jeda_kontak"}
    kunci_off = {"--ambang-snr": "snr_ambang", "--margin-snr": "snr_margin",
                 "--hop-naik": "hop_naik", "--basi-gw": "basi_gw"}

    def pasang_node(nilai):
        opsi["node_diminta"] = {x.strip() for x in nilai.split(",") if x.strip()} or None

    def pasang_kecuali(nilai):
        opsi["kecuali"] = {x.strip() for x in nilai.split(",") if x.strip()} or None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(USAGE)
            raise SystemExit(0)
        if a == "--sekali":
            opsi["sekali"] = True; i += 1; continue
        if a == "--lapor-awal":
            opsi["lapor_awal"] = True; i += 1; continue
        if a == "--semua-node":
            opsi["lingkup"] = "semua"; i += 1; continue
        if a == "--tanpa-saran-favorit":
            opsi["saran_favorit"] = False; i += 1; continue
        if a == "--tanpa-kontak":
            opsi["kontak_baru"] = False; i += 1; continue
        if a == "--node":
            if i + 1 >= len(argv):
                print("Opsi --node butuh nilai.", file=sys.stderr)
                raise SystemExit(2)
            pasang_node(argv[i + 1])
            i += 2; continue
        if a == "--kecuali":
            if i + 1 >= len(argv):
                print("Opsi --kecuali butuh nilai.", file=sys.stderr)
                raise SystemExit(2)
            pasang_kecuali(argv[i + 1])
            i += 2; continue
        if a in kunci or a in kunci_int or a in kunci_off:
            if i + 1 >= len(argv):
                print("Opsi %s butuh nilai." % a, file=sys.stderr)
                raise SystemExit(2)
            nilai = argv[i + 1]
            if a in kunci:
                # Nilai kosong pada topik penting berarti "matikan pemisahan" -
                # jadi disimpan sebagai None, bukan diganti nilai bawaan.
                opsi[kunci[a]] = (nilai or None) if kunci[a] == "topik_penting" else nilai
            elif a in kunci_int:
                opsi[kunci_int[a]] = int(nilai)
            else:
                opsi[kunci_off[a]] = angka_atau_off(nilai, opsi[kunci_off[a]])
            i += 2; continue
        print("Opsi tidak dikenal: %s" % a, file=sys.stderr)
        raise SystemExit(2)
    return opsi


def jalankan_putaran(opsi, state):
    """Satu putaran: baca data, deteksi, kirim, simpan state. Kembalikan jumlah kirim."""
    # Dibaca dengan cara yang MEMBEDAKAN "exporter mati" dari "gateway melapor
    # nol node". Keduanya sama-sama data kosong, tetapi yang pertama berarti kita
    # buta dan tidak boleh menilai apa pun, sedangkan yang kedua adalah kabar
    # gateway itu sendiri - dan justru itulah yang perlu dilaporkan.
    data, galat, sumber = ambil_data_bergilir(opsi)
    if galat:
        print("[exporter tidak terbaca] %s (%s)" % (galat, sumber), file=sys.stderr)

    kesehatan = data.get("kesehatan_gateway") or {}

    notif, state_baru = deteksi(
        data, state,
        offline_secs=BAWAAN_OFFLINE_SECS,
        baterai_ambang=opsi["ambang_baterai"],
        lapor_awal=opsi["lapor_awal"],
        snr_ambang=opsi["snr_ambang"],
        snr_margin=opsi["snr_margin"],
        hop_naik=opsi["hop_naik"],
        lingkup=opsi["lingkup"],
        node_diminta=opsi["node_diminta"],
        kecuali=opsi["kecuali"],
        absen_toleransi=opsi["absen_toleransi"],
        jendela_reset=dalam_jendela_reset(opsi["marker"], opsi["jendela_reset"])[0],
        konfirmasi_kontak=opsi["kontak_baru"],
        jeda_kontak=opsi["jeda_kontak"],
        data_terbaca=not galat)

    # Gateway mati diperiksa TERPISAH dari node: saat gateway tidak terbaca,
    # daftar node di data.json bisa kosong atau sudah basi, jadi tidak ada satu
    # pun kesimpulan per node yang sah. Deteksi node di atas sudah menahan diri
    # (data_terbaca=False) atau memakai data basi apa adanya; di sini yang
    # dilaporkan adalah SEBAB-nya.
    notif_mati, state_mati = deteksi_gateway_koneksi(
        data, galat, state, basi=opsi["basi_gw"], absen=opsi["absen_gw"])
    state_baru["gateway_koneksi"] = state_mati
    notif = list(notif) + notif_mati

    notif_gw, state_gw = deteksi_gateway(
        kesehatan, data.get("node", []), state,
        db_ambang=opsi["db_ambang"], saran_favorit=opsi["saran_favorit"])
    state_baru["gateway"] = state_gw
    notif = list(notif) + notif_gw

    terkirim = 0
    gagal_node = set()
    gagal_gw = False
    for n in notif:
        # Dua topik, satu server: kabar penting dipisah supaya bisa diberi
        # perlakuan berbeda di ponsel. Bila topik pentingnya dikosongkan,
        # semuanya kembali ke topik umum tanpa perlu mengubah apa pun lagi.
        topik = topik_untuk(n, opsi["topik"], opsi["topik_penting"])
        kanal, galat_kirim = kirim(n["judul"], n["pesan"], n["prioritas"], n["tag"],
                                   opsi["server"], topik, opsi["token"], opsi["lokal"])
        if kanal:
            terkirim += 1
            print("[terkirim via %s -> %s] %s" % (kanal, topik, n["judul"]))
        else:
            if n.get("gw"):
                gagal_gw = True
            else:
                gagal_node.add(n["node_id"])
            print("[GAGAL] %s -> %s" % (n["judul"], galat_kirim), file=sys.stderr)

    # Notifikasi yang GAGAL tidak boleh "menelan" perubahan status: kembalikan
    # catatan node itu ke keadaan sebelumnya supaya dicoba lagi putaran depan.
    if gagal_node:
        lama = (state or {}).get("node", {})
        for node_id in gagal_node:
            if node_id in lama:
                state_baru["node"][node_id] = lama[node_id]
    if gagal_gw:
        # Kabar gateway (termasuk "gateway mati") yang gagal terkirim harus
        # diulang, jadi penanda bahwa ia sudah dilaporkan dibatalkan. Ini penting
        # untuk kabar mati: sekali ditandai "mati" dan notifikasinya hilang,
        # pemulihannya nanti akan terkirim tanpa pernah ada kabar matinya.
        state_baru["gateway"] = (state or {}).get("gateway") or {}
        state_baru["gateway_koneksi"] = (state or {}).get("gateway_koneksi") or {}

    simpan_state(opsi["state"], state_baru)

    if not notif:
        print("tidak ada perubahan status (%d node dipantau)" % len(state_baru["node"]))
    return terkirim, state_baru


def main(argv):
    # Konsol Windows (cp1252) tidak bisa mencetak emoji yang dipakai sebagian
    # nama node. Saat keluaran dialihkan ke berkas (mulai-layanan.bat), Python
    # memakai encoding lokal, sehingga print() melempar UnicodeEncodeError.
    # Pencetakan terjadi SESUDAH percobaan kirim tetapi SEBELUM keadaan
    # disimpan, jadi tiap putaran mati di titik yang sama: notifier hidup,
    # tidak pernah melapor, dan mengulang alarm yang sama. Paksa UTF-8 dengan
    # pengganti agar satu nama beremoji tidak mematikan seluruh notifier.
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    opsi = baca_opsi(argv)
    print("Meshtastic -> ntfy")
    print("  data   : %s" % opsi["data"])
    if opsi.get("data_cadangan"):
        print("  cadangan data: %s" % opsi["data_cadangan"])
    print("  server : %s" % opsi["server"])
    print("  topik  : %s (kabar rutin)" % opsi["topik"])
    print("           %s (kabar penting: gateway, kontak radio, node offline)"
          % (opsi["topik_penting"] if opsi["topik_penting"]
             else "— MATI, digabung ke topik di atas"))
    print("  cadangan: %s" % (opsi["lokal"] or "(nonaktif)"))
    print("  lingkup: %s%s" % (
        "HANYA node LoRa langsung" if opsi["lingkup"] == "lora" else "SEMUA node (termasuk MQTT)",
        " | daftar: %s" % ", ".join(sorted(opsi["node_diminta"])) if opsi["node_diminta"] else ""))
    if opsi["kecuali"]:
        print("  dikecualikan: %s" % ", ".join(sorted(opsi["kecuali"])))
    print("  ambang : baterai<=%s%% | SNR<%s dB (pulih di +%s) | hop naik>=%s | DB>=%s" % (
        opsi["ambang_baterai"],
        opsi["snr_ambang"] if opsi["snr_ambang"] is not None else "off",
        opsi["snr_margin"],
        opsi["hop_naik"] if opsi["hop_naik"] else "off", opsi["db_ambang"]))
    print("  kontak radio: %s%s" % (
        "aktif" if opsi["kontak_baru"] else "nonaktif",
        " (jeda kabar ulang %s)" % durasi(opsi["jeda_kontak"]) if opsi["kontak_baru"] else ""))
    print("  gateway mati: %s%s" % (
        "dipantau" if opsi["basi_gw"] is not None else "nonaktif",
        " (data basi > %s, %d putaran gagal berturut-turut)" % (
            durasi(opsi["basi_gw"]), opsi["absen_gw"]) if opsi["basi_gw"] is not None else ""))

    state = muat_state(opsi["state"])
    while True:
        try:
            jalankan_putaran(opsi, state)
            state = muat_state(opsi["state"])
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print("putaran gagal: %s" % e, file=sys.stderr)
            if opsi["sekali"]:
                return 1
        if opsi["sekali"]:
            return 0
        time.sleep(opsi["interval"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
