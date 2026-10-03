#!/usr/bin/env python3
# ============================================================
# uji-notif-meshtastic.py - uji ujung-ke-ujung notifikasi Meshtastic -> ntfy
# ============================================================
# Membuktikan tiga hal, bukan sekadar "skrip ada":
#
#   1. exporter terjangkau dan /data.json bisa dibaca (sumber datanya hidup),
#   2. logika deteksi BENAR: node offline memicu peringatan, node pulih
#      memicu pemulihan, baterai rendah memicu peringatan - dan TIDAK
#      mengulang saat status tidak berubah,
#   2c. dua topik ntfy: kabar penting (gateway mati/pulih, node LoRa terdeteksi,
#      node offline/pulih) benar-benar dipisah dari kabar rutin, dan pemisahan
#      itu bisa dicabut dengan mengosongkan nama topiknya,
#   2b. tiga kabar yang diminta pemilik halaman ikut diuji: node LoRa yang
#      terdeteksi LANGSUNG oleh radio gateway (memuat id node + kualitas sinyal,
#      berikut kabar "kontak kembali" yang dibatasi jeda), gateway MATI karena
#      tiga sebab yang berbeda (exporter tidak menjawab, data basi, gateway
#      "hidup tetapi buta") beserta pemulihannya, dan ketahanan state saat
#      exporter mati (gateway yang tidak terbaca tidak boleh membuat notifier
#      lupa semua node lalu melaporkannya sebagai pulih),
#   3. jalur kirim benar-benar sampai: bukan satu pesan saja, melainkan KETIGA
#      jenis kabar yang diminta (kontak radio langsung, node offline, gateway
#      mati) - disusun dari node yang NYATA ada di /data.json saat uji dijalankan,
#      diarahkan ke topiknya oleh fungsi yang sama dengan layanan (topik_untuk),
#      lalu masing-masing DIBACA KEMBALI dari server ntfy. Hanya kabar gateway
#      mati yang disimulasikan (gateway sehat tidak mungkin dimatikan dari sini),
#      dan pesannya diberi label jelas bahwa itu uji.
#
# Jadi kanal yang mati langsung ketahuan tanpa menunggu node betulan jatuh.
#
# Pakai
# -----
#   python uji-notif-meshtastic.py
#   MESH_DATA=http://192.168.20.31:9208/data.json python uji-notif-meshtastic.py
#   python uji-notif-meshtastic.py --kering    # lewati pengiriman nyata
#
# Opsi
# ----
#   --data URL       alamat /data.json exporter
#   --server URL     server ntfy   (bawaan dari lingkungan / notif-meshtastic.py)
#   --topik NAMA     nama topik rutin  (bawaan dari lingkungan / notif-meshtastic.py)
#   --topik-penting NAMA  topik kabar penting (sama bawaannya)
#   --lokal URL      ntfy lokal    (bawaan dari lingkungan / notif-meshtastic.py)
#   --timeout DET    batas tunggu pesan muncul, bawaan 30
#   --kering         jangan kirim apa pun; hanya uji baca data + logika deteksi
#
# Lingkungan
# ----------
#   UJI_TLS_INSECURE "1" mematikan verifikasi TLS (hanya untuk diagnosis)
#
# Hasil: LULUS bila semua langkah terbukti; selain itu GAGAL (kode keluar 1).
# ============================================================

import importlib.util
import json
import os
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

AKAR = os.path.dirname(os.path.abspath(__file__))
BERKAS_NOTIF = os.path.join(AKAR, "notif-meshtastic.py")

LOLOS = 0
GAGAL = 0


def lolos(pesan):
    global LOLOS
    LOLOS += 1
    print("  [LULUS]      %s" % pesan)


def gagal(pesan):
    global GAGAL
    GAGAL += 1
    print("  [GAGAL]      %s" % pesan)


def info(pesan):
    print("               -> %s" % pesan)


def muat_notifier():
    """Impor notif-meshtastic.py (nama berkas bertanda hubung)."""
    if not os.path.exists(BERKAS_NOTIF):
        print("ERROR: notif-meshtastic.py tidak ditemukan di %s" % AKAR, file=sys.stderr)
        raise SystemExit(2)
    spec = importlib.util.spec_from_file_location("notif_meshtastic", BERKAS_NOTIF)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def pembuka_tls():
    if os.environ.get("UJI_TLS_INSECURE") == "1":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return ssl.create_default_context()


def ambil(url, ctx, timeout=20):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "uji-notif-meshtastic/1.0")
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read().decode("utf-8", "replace")


def poll_topik(server, topik, sejak, penanda, ctx):
    """Cari pesan berisi penanda di topik ntfy. Kembalikan (objek|False, galat)."""
    url = "%s/%s/json?poll=1&since=%d" % (server.rstrip("/"), urllib.parse.quote(topik), sejak)
    try:
        bahan = ambil(url, ctx)
    except urllib.error.URLError as e:
        return None, "tidak bisa menghubungi %s (%s)" % (server, e)
    for baris in bahan.splitlines():
        baris = baris.strip()
        if not baris:
            continue
        try:
            obj = json.loads(baris)
        except json.JSONDecodeError:
            continue
        if penanda in (obj.get("message") or "") or penanda in (obj.get("title") or ""):
            return obj, None
    return False, None


def data_uji(online_tower, baterai_client, snr_client=5.0, hop_client=0, online_mqtt=True,
             online_client=True):
    return {"node": [
        {"node_id": "!aaaa0001", "long_name": "Tower-RTR", "short_name": "TWR",
         "role": "ROUTER", "online": online_tower,
         "last_heard_seconds": 60 if online_tower else 9999, "battery": 87,
         "snr": 6.0, "hops": 0, "via": "lora"},
        {"node_id": "!aaaa0002", "long_name": "Client-1", "short_name": "CL1",
         "role": "CLIENT", "online": online_client,
         "last_heard_seconds": 30 if online_client else 9999,
         "battery": baterai_client, "snr": snr_client, "hops": hop_client, "via": "lora"},
        # node lewat MQTT (mesh publik) - harus DIABAIKAN pada lingkup "lora"
        {"node_id": "!bbbb0001", "long_name": "Node-MQTT-Jauh", "short_name": "JAU",
         "role": "CLIENT", "online": online_mqtt,
         "last_heard_seconds": 30 if online_mqtt else 9999, "battery": 77, "via": "mqtt"},
        # node gateway sendiri - harus diabaikan
        {"node_id": "!8f4c1354", "long_name": "Gateway-Diri", "short_name": "GW",
         "role": "CLIENT", "online": False, "last_heard_seconds": None, "via": "diri"},
        # tercatat di database tetapi belum pernah terdengar - harus dilewati
        {"node_id": "!cccc0001", "long_name": "Belum-Terdengar", "short_name": "BEL",
         "role": "CLIENT", "online": False, "last_heard_seconds": None, "via": "lora"},
    ]}


def uji_deteksi(modul):
    """Uji logika deteksi tanpa jaringan."""
    notif, s1 = modul.deteksi(data_uji(True, 50), {})
    if not notif:
        lolos("putaran pertama hanya mencatat status (tidak ada notif)")
    else:
        gagal("putaran pertama memicu %d notif (seharusnya tenang)" % len(notif))

    notif, s2 = modul.deteksi(data_uji(False, 50), s1)
    if len(notif) == 1 and "OFFLINE" in notif[0]["judul"] and notif[0]["tag"] == "red_circle":
        lolos("node offline memicu peringatan (tag red_circle)")
    else:
        gagal("node offline TIDAK memicu peringatan yang benar: %s" % notif)

    notif, s3 = modul.deteksi(data_uji(False, 50), s2)
    if not notif:
        lolos("status offline berulang tidak mengulang notifikasi")
    else:
        gagal("status offline berulang memicu %d notif (harusnya diam)" % len(notif))

    notif, s4 = modul.deteksi(data_uji(True, 50), s3)
    if len(notif) == 1 and "ONLINE" in notif[0]["judul"] and notif[0]["tag"] == "green_circle":
        lolos("node pulih memicu pemulihan (tag green_circle)")
    else:
        gagal("pemulihan node TIDAK memicu notifikasi yang benar: %s" % notif)

    notif, s5 = modul.deteksi(data_uji(True, 10), s4)
    if len(notif) == 1 and "Baterai" in notif[0]["judul"] and notif[0]["prioritas"] == "high":
        lolos("baterai rendah memicu peringatan (prioritas high)")
    else:
        gagal("baterai rendah TIDAK memicu peringatan yang benar: %s" % notif)

    notif, s6 = modul.deteksi(data_uji(True, 50), s5)
    if len(notif) == 1 and "normal kembali" in notif[0]["judul"]:
        lolos("baterai normal kembali memicu pemulihan")
    else:
        gagal("kepulihan baterai TIDAK memicu notifikasi yang benar: %s" % notif)

    # --- kualitas link: SNR ---
    notif, s7 = modul.deteksi(data_uji(True, 50, snr_client=-12.0), s6)
    if len(notif) == 1 and "Sinyal" in notif[0]["judul"] and notif[0]["tag"] == "signal_strength":
        lolos("SNR turun melewati ambang memicu peringatan")
    else:
        gagal("SNR lemah TIDAK memicu peringatan yang benar: %s" % notif)

    notif, s8 = modul.deteksi(data_uji(True, 50, snr_client=-6.0), s7)
    if not notif:
        lolos("SNR sedikit di atas ambang (belum lewat histeresis) tidak mengulang")
    else:
        gagal("histeresis SNR gagal (dipicu %d notif): %s" % (len(notif), notif))

    notif, s9 = modul.deteksi(data_uji(True, 50, snr_client=2.0), s8)
    if len(notif) == 1 and "membaik" in notif[0]["judul"]:
        lolos("SNR membaik melewati histeresis memicu pemulihan")
    else:
        gagal("pemulihan SNR TIDAK memicu notifikasi yang benar: %s" % notif)

    # --- kualitas link: hop ---
    notif, s10 = modul.deteksi(data_uji(True, 50, hop_client=1), s9)
    if len(notif) == 1 and "bertambah" in notif[0]["judul"] and notif[0]["tag"] == "arrows_counterclockwise":
        lolos("hop bertambah dari titik terbaik memicu peringatan")
    else:
        gagal("hop bertambah TIDAK memicu peringatan yang benar: %s" % notif)

    notif, s11 = modul.deteksi(data_uji(True, 50, hop_client=1), s10)
    if not notif:
        lolos("hop tetap tinggi tidak mengulang notifikasi")
    else:
        gagal("hop berulang memicu %d notif (harusnya diam)" % len(notif))

    notif, s12 = modul.deteksi(data_uji(True, 50, hop_client=0), s11)
    if len(notif) == 1 and "normal kembali" in notif[0]["judul"]:
        lolos("hop kembali ke titik terbaik memicu pemulihan")
    else:
        gagal("pemulihan hop TIDAK memicu notifikasi yang benar: %s" % notif)

    # --- penyaring lingkup: hanya node LoRa langsung ---
    notif, _ = modul.deteksi(data_uji(True, 50, online_mqtt=False), s12)
    if not notif:
        lolos("node lewat MQTT offline TIDAK memicu notifikasi (lingkup lora)")
    else:
        gagal("node MQTT masih memicu notifikasi: %s" % notif)

    # lingkup "semua": catat dulu baseline node MQTT, baru buat ia offline.
    _, s_mqtt = modul.deteksi(data_uji(True, 50, online_mqtt=True), s12, lingkup="semua")
    notif, _ = modul.deteksi(data_uji(True, 50, online_mqtt=False), s_mqtt, lingkup="semua")
    if len(notif) == 1 and "Node-MQTT-Jauh" in notif[0]["judul"]:
        lolos("lingkup \"semua\" memang ikut memantau node MQTT")
    else:
        gagal("lingkup semua tidak memantau node MQTT: %s" % notif)

    notif, _ = modul.deteksi(data_uji(False, 50), s12, node_diminta={"!aaaa0001"})
    if len(notif) == 1 and "Tower-RTR" in notif[0]["judul"]:
        lolos("daftar node tertentu membatasi ke node yang diminta")
    else:
        gagal("daftar node tertentu tidak bekerja: %s" % notif)

    notif, _ = modul.deteksi(data_uji(True, 50, online_client=False), s12,
                             node_diminta={"!aaaa0001"})
    if not notif:
        lolos("daftar node tertentu mengabaikan node di luar daftar")
    else:
        gagal("node di luar daftar masih memicu notifikasi: %s" % notif)

    _, s13 = modul.deteksi(data_uji(True, 50), s12)
    if "!cccc0001" not in s13["node"] and "!8f4c1354" not in s13["node"]:
        lolos("node belum-pernah-terdengar dan node gateway tidak ikut dicatat")
    else:
        gagal("penyaring lingkup bocor: %s" % sorted(s13["node"]))

    # kirim kandidat untuk langkah uji kirim
    notif, _ = modul.deteksi(data_uji(False, 50), s1)
    return notif[0] if notif else None


def uji_topik_penting(modul):
    """Uji pemisahan dua topik: kabar penting vs kabar rutin.

    Yang diperiksa bukan hanya penandanya, tetapi juga bahwa penanda itu benar-
    benar dipakai saat MEMILIH topik - termasuk jalan kembalinya (topik penting
    dikosongkan) supaya pemisahan ini bisa dicabut tanpa menyunting kode.
    """
    item = {"node_id": "!aaaa0001", "long_name": "Tower-RTR", "via": "lora",
            "snr": 6.0, "hops": 0, "role": "ROUTER"}

    penting = [
        ("node offline", modul.pesan_offline("Tower-RTR", "!aaaa0001", "ROUTER", 9999)),
        ("node pulih", modul.pesan_pulih("Tower-RTR", "!aaaa0001", 1, 2)),
        ("kontak radio langsung", modul.pesan_kontak_radio(item)),
        ("kontak radio kembali", modul.pesan_kontak_radio(item, lama=True)),
        ("gateway mati", modul.pesan_gw_mati("exporter tidak menjawab", 60)),
        ("gateway pulih", modul.pesan_gw_pulih(60)),
    ]
    if all(p.get("penting") for _, p in penting):
        lolos("topik penting: %d kabar utama (gateway & node) ditandai penting" % len(penting))
    else:
        gagal("topik penting: ada yang tidak ditandai: %s"
              % [n for n, p in penting if not p.get("penting")])

    rutin = [
        ("baterai lemah", modul.pesan_baterai("Tower-RTR", "!aaaa0001", 10)),
        ("baterai pulih", modul.pesan_baterai_pulih("Tower-RTR", "!aaaa0001", 80)),
        ("SNR lemah", modul.pesan_snr_lemah("Tower-RTR", "!aaaa0001", -12.0, -7.0)),
        ("SNR pulih", modul.pesan_snr_pulih("Tower-RTR", "!aaaa0001", 2.0)),
        ("hop naik", modul.pesan_hop_naik("Tower-RTR", "!aaaa0001", 2, 1)),
        ("hop pulih", modul.pesan_hop_pulih("Tower-RTR", "!aaaa0001", 1)),
        ("node hilang dari database", modul.pesan_hilang("Tower-RTR", "!aaaa0001", 1)),
        ("node muncul di database", modul.pesan_muncul("Tower-RTR", "!aaaa0001", 1)),
        ("saran Favorite", modul.pesan_saran_favorit(item)),
        ("gateway reboot", modul.pesan_gateway_reboot({"node_id": "!8f4c1354",
                                                       "reboot_count": 47, "uptime": 60}, 1)),
        ("database penuh", modul.pesan_db_penuh({"node_id": "!8f4c1354"}, 195, 190)),
    ]
    bocor = [n for n, p in rutin if p.get("penting")]
    if not bocor:
        lolos("topik penting: %d kabar rutin TIDAK ikut pindah topik" % len(rutin))
    else:
        gagal("topik penting: kabar rutin bocor ke topik penting: %s" % bocor)

    # --- pemilihan topik yang sebenarnya, lewat jalankan_putaran() ---
    opsi = modul.baca_opsi([])
    opsi["state"] = os.path.join(tempfile.gettempdir(), "uji-notif-topik-%d.json" % os.getpid())
    opsi["saran_favorit"] = False
    # Pengiriman jaringan diganti penadah: uji ini memeriksa PEMILIHAN TOPIK,
    # bukan apakah internetnya hidup - jadi tidak perlu menyentuh ntfy.
    terpakai = []

    def kirim_palsu(judul, isi, prio, tag, server, topik, token=None, lokal=None,
                    timeout=15):
        terpakai.append((topik, judul))
        return "kanal-palsu", None

    def ambil_palsu(data):
        return lambda url, timeout=15: (data, None)

    asli_ambil, asli_kirim = modul.ambil_data_aman, modul.kirim
    try:
        modul.kirim = kirim_palsu

        modul.ambil_data_aman = ambil_palsu(data_uji(True, 50))
        _, s = modul.jalankan_putaran(opsi, {})
        if not terpakai:
            lolos("topik: putaran pertama (baseline) tidak mengirim apa pun")
        else:
            gagal("topik: putaran pertama mengirim %s" % [t[1] for t in terpakai])

        terpakai.clear()
        modul.ambil_data_aman = ambil_palsu(data_uji(True, 10))
        _, s = modul.jalankan_putaran(opsi, s)
        salah = [t for t in terpakai if t[0] != opsi["topik"]]
        if len(terpakai) == 1 and not salah:
            lolos("topik: kabar baterai pergi ke topik RUTIN")
        else:
            gagal("topik: kabar rutin salah topik: %s" % terpakai)

        terpakai.clear()
        modul.ambil_data_aman = ambil_palsu(data_uji(False, 10))
        _, s = modul.jalankan_putaran(opsi, s)
        salah = [t for t in terpakai if t[0] != opsi["topik_penting"]]
        if len(terpakai) == 1 and "OFFLINE" in terpakai[0][1] and not salah:
            lolos("topik: kabar node OFFLINE pergi ke topik PENTING")
        else:
            gagal("topik: kabar penting salah topik: %s" % terpakai)

        # Dikosongkan -> semuanya kembali ke satu topik (jalan kembali tanpa
        # menyunting kode, cukup mengubah satu setelan).
        opsi["topik_penting"] = None
        modul.ambil_data_aman = ambil_palsu(data_uji(True, 50))
        _, s = modul.jalankan_putaran(opsi, {})
        terpakai.clear()
        modul.ambil_data_aman = ambil_palsu(data_uji(False, 10))
        modul.jalankan_putaran(opsi, s)
        salah = [t for t in terpakai if t[0] != opsi["topik"]]
        judul = [t[1] for t in terpakai]
        if (terpakai and not salah
                and any("OFFLINE" in j for j in judul) and any("Baterai" in j for j in judul)):
            lolos("topik: topik penting dikosongkan -> semua kembali ke topik umum")
        else:
            gagal("topik: jalan kembali satu topik gagal: %s" % terpakai)
    finally:
        modul.ambil_data_aman, modul.kirim = asli_ambil, asli_kirim
        try:
            os.remove(opsi["state"])
        except OSError:
            pass


def uji_sumber_cadangan(modul):
    tujuan = modul.daftar_tujuan(
        "http://utama/data.json",
        "http://cad1/data.json, http://cad2/data.json http://cad1/data.json")
    if tujuan == ["http://utama/data.json", "http://cad1/data.json",
                  "http://cad2/data.json"]:
        lolos("daftar_tujuan: utama dulu, cadangan menyusul, kembar dibuang")
    else:
        gagal("daftar_tujuan salah: %r" % tujuan)

    opsi = modul.baca_opsi(["--data", "http://utama/data.json",
                            "--data-cadangan", "http://cad1/data.json"])
    if opsi["data_cadangan"] == "http://cad1/data.json":
        lolos("--data-cadangan terbaca dari baris perintah")
    else:
        gagal("--data-cadangan tidak terbaca: %r" % opsi["data_cadangan"])

    asli = modul.ambil_data_aman
    dipanggil = []

    def ambil_palsu(url, timeout=15):
        dipanggil.append(url)
        if "utama" in url:
            return {}, "ConnectionRefusedError: sumber utama mati"
        return {"node": [], "kesehatan_gateway": {}}, None
    opsi2 = {"data": "http://utama/data.json",
             "data_cadangan": "http://cad1/data.json"}
    try:
        modul.ambil_data_aman = ambil_palsu
        data, galat, url = modul.ambil_data_bergilir(opsi2)
    finally:
        modul.ambil_data_aman = asli
    if galat is None and url == "http://cad1/data.json" and opsi2["_sumber_idx"] == 1:
        lolos("sumber utama tak terbaca -> notifier pindah ke cadangan")
    else:
        gagal("failover sumber gagal: galat=%r url=%r idx=%r"
              % (galat, url, opsi2.get("_sumber_idx")))

    # Putaran berikutnya tetap memakai cadangan yang sedang sehat.
    try:
        modul.ambil_data_aman = ambil_palsu
        _, _, url = modul.ambil_data_bergilir(opsi2)
    finally:
        modul.ambil_data_aman = asli
    if url == "http://cad1/data.json":
        lolos("putaran berikutnya tetap memakai sumber cadangan yang sehat")
    else:
        gagal("sumber cadangan tidak dipertahankan: %r" % url)

    # Semua sumber gagal -> galat terisi, agar alarm "gateway mati" tetap jalan.
    def ambil_mati(url, timeout=15):
        return {}, "ConnectionRefusedError: semua sumber mati"
    try:
        modul.ambil_data_aman = ambil_mati
        opsi3 = {"data": "http://utama/data.json",
                 "data_cadangan": "http://cad1/data.json"}
        data, galat, url = modul.ambil_data_bergilir(opsi3)
    finally:
        modul.ambil_data_aman = asli
    if galat and not data:
        lolos("semua sumber gagal -> galat dilaporkan (bukan data kosong yang menyesatkan)")
    else:
        gagal("semua sumber gagal tidak dilaporkan galat: %r" % galat)


def kirim_dan_tunggu(modul, server, topik_tujuan, token, lokal, ctx,
                     pesan, batas_detik, catatan=""):
    """Kirim satu notifikasi lalu buktikan pesannya benar-benar TIBA di topiknya.

    Ketiga jenis kabar diuji dengan cara yang persis sama supaya tidak ada yang
    lolos hanya karena pemeriksaannya berbeda. Penanda unik ditempelkan pada
    judul DAN isi, lalu dicari kembali di server - bukan sekadar percaya bahwa
    "POST berhasil".
    """
    penanda = "UJI-%d" % (int(time.time() * 1000) % 1000000000)
    judul = "%s [%s]" % (pesan["judul"], penanda)
    isi = pesan["pesan"] + ("\n\n%s" % catatan if catatan else "")
    isi += "\nPenanda uji: %s" % penanda
    sejak = int(time.time()) - 5

    kanal, galat_kirim = modul.kirim(judul, isi, pesan["prioritas"], pesan["tag"],
                                     server, topik_tujuan, token, lokal)
    if not kanal:
        gagal("gagal mengirim \"%s\" -> %s" % (pesan["judul"], galat_kirim))
        return False
    info("terkirim ke topik %s (%s)" % (topik_tujuan, kanal))

    batas = time.time() + batas_detik
    galat_terakhir = None
    while time.time() < batas:
        hasil, galat_poll = poll_topik(server, topik_tujuan, sejak, penanda, ctx)
        if galat_poll:
            galat_terakhir = galat_poll
        elif hasil:
            lolos("\"%s\" TIBA di %s" % (pesan["judul"], topik_tujuan))
            return True
        time.sleep(3)
    if galat_terakhir:
        gagal("tidak bisa membaca topik %s (%s)" % (topik_tujuan, galat_terakhir))
    else:
        gagal("\"%s\" TIDAK muncul di %s dalam %ds"
              % (pesan["judul"], topik_tujuan, batas_detik))
        info("kanal mati ATAU topiknya berbeda")
    return False


def data_satu(node_id="!aaaa0001", via="lora", snr=6.0, online=True, hop=0,
              baterai=90, nama="Tower-RTR"):
    """Satu node saja - supaya hasil tiap uji bisa dipastikan tanpa teralih
    node lain. Node ini radio gateway sendiri (lantai LONG_FAST -17.5 dB)."""
    return {"node": [{
        "node_id": node_id, "long_name": nama, "short_name": "TWR",
        "role": "ROUTER", "online": online, "via": via,
        "last_heard_seconds": 30 if online else 9999,
        "battery": baterai, "snr": snr, "hops": hop,
    }]}


def uji_fitur_baru(modul):
    """Uji tiga kabar yang diminta pemilik halaman.

      1. node LoRa terdeteksi LANGSUNG oleh radio gateway (id + kualitas sinyal);
      2. gateway mati / tidak terbaca (tiga sebab) beserta pemulihannya;
      3. exporter mati tidak boleh membuat notifier "lupa" semua node.
    """
    t = 1700000000.0   # waktu tetap supaya jeda/usia bisa diuji tanpa menunggu

    # --- 1. kontak radio langsung ---
    n0, s0 = modul.deteksi(data_satu(), {}, konfirmasi_kontak=True, sekarang=t)
    if not n0:
        lolos("kontak radio: putaran pertama hanya mencatat (tidak membanjiri ntfy)")
    else:
        gagal("kontak radio: putaran pertama memicu %d notif: %s" % (len(n0), n0))

    n1, s1 = modul.deteksi(data_satu(), s0, konfirmasi_kontak=True, sekarang=t + 60)
    if not n1:
        lolos("kontak radio: node yang tetap terdengar tidak mengulang kabar")
    else:
        gagal("kontak radio: kabar terulang tiap putaran: %s" % n1)

    # --lapor-awal: pemantau baru mengabari node radio yang memang sudah ada.
    n2, _ = modul.deteksi(data_satu(), {}, konfirmasi_kontak=True, lapor_awal=True,
                          sekarang=t)
    if len(n2) == 1 and "terdeteksi" in n2[0]["judul"] and n2[0]["tag"] == "signal_strength":
        lolos("kontak radio: --lapor-awal mengabari node radio yang sudah ada")
    else:
        gagal("kontak radio: --lapor-awal tidak mengabari: %s" % n2)

    isi = n2[0]["pesan"] if n2 else ""
    if "!aaaa0001" in isi and "Baik" in isi and "SNR" in isi:
        lolos("kontak radio: isi memuat id node + kualitas sinyal (mutu & SNR)")
    else:
        gagal("kontak radio: isi tidak lengkap: %r" % isi)

    # Lantai preset tidak ikut per node di /data.json (hanya di
    # kesehatan_gateway), jadi notifier harus memakai lantai GATEWAY - kalau
    # tidak, teksnya memakai lantai bawaan dan salah saat preset diubah.
    d_lantai = data_satu(via="lora", snr=-18.0)
    d_lantai["kesehatan_gateway"] = {"lantai_snr": -20.0, "preset": "LONG_SLOW"}
    nl3, _ = modul.deteksi(d_lantai, {}, konfirmasi_kontak=True, lapor_awal=True,
                           sekarang=t)
    if nl3 and "-20.0 dB" in nl3[0]["pesan"]:
        lolos("kontak radio: lantai sinyal diambil dari preset gateway")
    else:
        gagal("kontak radio: lantai gateway tidak dipakai: %s" % (nl3[0]["pesan"] if nl3 else nl3))

    # kontak KEMBALI: node yang tadinya hanya lewat MQTT lalu terukur radio.
    # Lingkup "semua" dipakai karena pada lingkup "lora" node MQTT memang di
    # luar pantauan dan catatannya sengaja dibekukan.
    _, sm = modul.deteksi(data_satu(via="mqtt", snr=None), {}, lingkup="semua",
                          konfirmasi_kontak=True, sekarang=t)
    if sm["node"].get("!aaaa0001", {}).get("snr_diketahui") is False:
        lolos("kontak radio: node MQTT dicatat belum terukur radio (snr_diketahui=False)")
    else:
        gagal("kontak radio: snr_diketahui bukan False untuk node MQTT: %s" % sm["node"])

    nk, sk = modul.deteksi(data_satu(via="lora", snr=5.0), sm, lingkup="semua",
                           konfirmasi_kontak=True, sekarang=t + 60)
    if len(nk) == 1 and "kembali" in nk[0]["judul"]:
        lolos("kontak radio: node yang terukur radio kembali memicu kabar")
    else:
        gagal("kontak radio: kontak kembali tidak dikabari: %s" % nk)

    # Jeda: bolak-balik radio <-> MQTT tidak boleh menghasilkan satu pesan tiap
    # pergantian.
    _, sb = modul.deteksi(data_satu(via="mqtt", snr=None), sk, lingkup="semua",
                          konfirmasi_kontak=True, sekarang=t + 120)
    nj, _ = modul.deteksi(data_satu(via="lora", snr=5.0), sb, lingkup="semua",
                          konfirmasi_kontak=True, sekarang=t + 180)
    if not nj:
        lolos("kontak radio: kabar ulang ditahan oleh jeda (tidak banjir pesan)")
    else:
        gagal("kontak radio: jeda tidak menahan kabar ulang: %s" % nj)

    nj2, _ = modul.deteksi(data_satu(via="lora", snr=5.0), sb, lingkup="semua",
                           konfirmasi_kontak=True,
                           sekarang=t + modul.BAWAAN_JEDA_KONTAK + 200)
    if len(nj2) == 1:
        lolos("kontak radio: setelah jeda lewat, kabar boleh diulang")
    else:
        gagal("kontak radio: setelah jeda lewat tetap diam: %s" % nj2)

    ntk, _ = modul.deteksi(data_satu(), {}, konfirmasi_kontak=False, lapor_awal=True,
                           sekarang=t)
    if not ntk:
        lolos("kontak radio: --tanpa-kontak benar-benar mematikan kabar")
    else:
        gagal("kontak radio: --tanpa-kontak masih mengabari: %s" % ntk)

    # --- 2. gateway mati / pulih ---
    galat = "URLError: connection refused"

    def sehat(umur=5):
        return {"umur_data_seconds": umur, "jumlah_node": 100,
                "kesehatan_gateway": {"firmware": "2.7.15", "node_id": "!8f4c1354"}}

    nm, gm1 = modul.deteksi_gateway_koneksi({}, galat, {}, basi=180, absen=2, sekarang=t)
    if not nm and gm1.get("gagal") == 1:
        lolos("gateway: satu kegagalan sesaat belum dilaporkan (toleransi)")
    else:
        gagal("gateway: kegagalan pertama langsung dilaporkan: %s" % nm)

    nm, gm2 = modul.deteksi_gateway_koneksi({}, galat, {"gateway_koneksi": gm1},
                                            basi=180, absen=2, sekarang=t + 60)
    if len(nm) == 1 and nm[0].get("gw") and nm[0]["prioritas"] == "max" \
            and "MATI" in nm[0]["judul"]:
        lolos("gateway: exporter tidak menjawab -> Gateway MATI (prioritas max)")
    else:
        gagal("gateway: sebab exporter mati tidak terdeteksi: %s" % nm)

    nm, gm3 = modul.deteksi_gateway_koneksi({}, galat, {"gateway_koneksi": gm2},
                                            basi=180, absen=2, sekarang=t + 120)
    if not nm:
        lolos("gateway: gateway yang tetap mati tidak mengulang notifikasi")
    else:
        gagal("gateway: notifikasi mati berulang tiap putaran: %s" % nm)

    nm, gm4 = modul.deteksi_gateway_koneksi(sehat(), None, {"gateway_koneksi": gm3},
                                            basi=180, absen=2, sekarang=t + 180)
    if len(nm) == 1 and "kembali" in nm[0]["judul"].lower() and not gm4.get("mati"):
        lolos("gateway: kembali terbaca -> notifikasi pemulihan")
    else:
        gagal("gateway: pemulihan tidak dilaporkan: %s" % nm)

    # sebab 2: exporter hidup, tetapi datanya sudah basi (loop tersangkut).
    nb, gb = modul.deteksi_gateway_koneksi(
        {"umur_data_seconds": 600, "jumlah_node": 100,
         "kesehatan_gateway": {"firmware": "2.7.15"}}, None, {},
        basi=180, absen=1, sekarang=t)
    if len(nb) == 1 and "basi" in nb[0]["pesan"]:
        lolos("gateway: data exporter basi terdeteksi sebagai sebab mati")
    else:
        gagal("gateway: data basi tidak terdeteksi: %s" % nb)

    # sebab 3: gateway tidak melaporkan apa pun (hidup tetapi buta).
    nbl, _ = modul.deteksi_gateway_koneksi(
        {"umur_data_seconds": 5, "jumlah_node": 0, "kesehatan_gateway": {}}, None, {},
        basi=180, absen=1, sekarang=t)
    if len(nbl) == 1 and "buta" in nbl[0]["pesan"]:
        lolos("gateway: 0 node + firmware tak terbaca terdeteksi (hidup tetapi buta)")
    else:
        gagal("gateway: keadaan buta tidak terdeteksi: %s" % nbl)

    ns, _ = modul.deteksi_gateway_koneksi(sehat(), None, {"gateway_koneksi": {}},
                                          basi=180, absen=1, sekarang=t)
    if not ns:
        lolos("gateway: data sehat tidak memicu notifikasi")
    else:
        gagal("gateway: data sehat memicu notifikasi: %s" % ns)

    # Payload yang BELUM LENGKAP (mis. exporter baru dimulai) tidak boleh
    # disimpulkan sebagai gateway buta - itu alarm palsu yang menakutkan.
    nk_, _ = modul.deteksi_gateway_koneksi({"node": []}, None, {},
                                           basi=180, absen=1, sekarang=t)
    if not nk_:
        lolos("gateway: payload tanpa jumlah_node tidak dikira gateway mati")
    else:
        gagal("gateway: payload tidak lengkap memicu alarm palsu: %s" % nk_)

    noff, _ = modul.deteksi_gateway_koneksi({}, galat, {}, basi=None, absen=2, sekarang=t)
    if not noff:
        lolos("gateway: --basi-gw off mematikan pemantauan gateway")
    else:
        gagal("gateway: pemantauan gateway tidak bisa dimatikan: %s" % noff)

    # --- 3. exporter mati: state harus UTUH ---
    _, sblm_ex = modul.deteksi(data_uji(True, 50), {}, konfirmasi_kontak=True)
    sblm_ex = dict(sblm_ex, penanda="jangan-hilang")
    nk3, sd = modul.deteksi({}, sblm_ex, data_terbaca=False, sekarang=t)
    if (not nk3 and sd.get("penanda") == "jangan-hilang"
            and sd.get("node") == sblm_ex.get("node")):
        lolos("exporter mati: tidak ada penilaian apa pun dan state tetap utuh")
    else:
        gagal("exporter mati: state berubah atau tergantikan: %s" % sorted(sd))

    # --- 4. pindah jalur ke MQTT BUKAN "hilang" ---
    _, sl = modul.deteksi(data_satu(via="lora", snr=6.0), {})
    nl, sl2 = modul.deteksi(data_satu(via="mqtt", snr=None), sl)
    if (not nl and "!aaaa0001" in sl2.get("node", {})
            and sl2["node"]["!aaaa0001"].get("absen") == 0):
        lolos("node pindah ke MQTT tidak dilaporkan hilang (di luar lingkup)")
    else:
        gagal("node pindah jalur MQTT salah dilaporkan: %s" % nl)


def main(argv):
    # Konsol Windows (cp1252) tidak bisa mencetak emoji yang dipakai sebagian
    # nama node Meshtastic; paksa UTF-8 dengan pengganti agar tidak berhenti
    # di tengah. Tanpa ini, uji gagal hanya karena mencoba MENAMPILKAN nama.
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    opsi = {
        "data": os.environ.get("MESH_DATA", "http://127.0.0.1:9208/data.json"),
        "server": os.environ.get("NTFY_SERVER"),
        "topik": os.environ.get("NTFY_TOPIK"),
        "topik_penting": os.environ.get("NTFY_TOPIK_PENTING"),
        "lokal": os.environ.get("NTFY_LOKAL"),
        "timeout": 30,
        "kering": False,
    }
    i = 0
    kunci = {"--data": "data", "--server": "server", "--topik": "topik",
             "--topik-penting": "topik_penting",
             "--lokal": "lokal", "--timeout": "timeout"}
    while i < len(argv):
        a = argv[i]
        if a == "--kering":
            opsi["kering"] = True; i += 1; continue
        if a in kunci:
            if i + 1 >= len(argv):
                print("Opsi %s butuh nilai." % a, file=sys.stderr)
                return 2
            nilai = argv[i + 1]
            opsi[kunci[a]] = int(nilai) if kunci[a] == "timeout" else nilai
            i += 2; continue
        print("Opsi tidak dikenal: %s" % a, file=sys.stderr)
        return 2

    modul = muat_notifier()
    server = opsi["server"] or modul.BAWAAN_SERVER
    topik = opsi["topik"] or modul.BAWAAN_TOPIK
    # Topik penting ikut diuji kirim: kalau topiknya salah ketik atau tidak bisa
    # ditulis, justru kabar paling penting itulah yang hilang diam-diam.
    topik_penting = (opsi["topik_penting"] if opsi["topik_penting"] is not None
                     else getattr(modul, "BAWAAN_TOPIK_PENTING", None))
    lokal = opsi["lokal"] if opsi["lokal"] is not None else modul.BAWAAN_LOKAL
    token = os.environ.get("NTFY_TOKEN") or None
    ctx = pembuka_tls()

    print("=" * 60)
    print(" UJI UJUNG-KE-UJUNG: node Meshtastic -> ntfy")
    print("=" * 60)
    print("Data   : %s" % opsi["data"])
    print("Server : %s" % server)
    print("Topik  : %s (rutin)" % topik)
    print("         %s (penting)" % (topik_penting or "(tidak dipakai)"))
    print("Mode   : %s" % ("kering (tanpa kirim)" if opsi["kering"] else "kirim nyata"))
    print()

    # --- 1. Sumber data hidup? ---
    print("1. Membaca data dari exporter")
    # Penangkapan galat sengaja DIPERSEMPIT ke pengambilan+penguraian saja.
    # Dulu blok try membungkus loop pencetakan juga, sehingga kegagalan
    # MENAMPILKAN nama (mis. emoji di konsol cp1252) dilaporkan keliru sebagai
    # "tidak bisa membaca <url>" - pesan yang menyesatkan saat mencari masalah.
    data = None
    try:
        teks = ambil(opsi["data"], ctx)
        data = json.loads(teks)
    except Exception as e:
        gagal("tidak bisa membaca %s (%s)" % (opsi["data"], e))
        info("pastikan exporter jalan: python exporter-meshtastic.py")
    if data is not None:
        jumlah = data.get("jumlah_node", len(data.get("node", [])))
        if jumlah:
            lolos("exporter menjawab: %d node dipantau" % jumlah)
        else:
            gagal("exporter menjawab tetapi belum ada node sama sekali")
        for item in data.get("node", [])[:10]:
            info("%s  %s  %s  baterai=%s" % (
                item.get("node_id"), item.get("long_name") or "(tanpa nama)",
                "ONLINE" if item.get("online") else "OFFLINE",
                item.get("battery")))
    print()

    # --- 2. Logika deteksi ---
    print("2. Logika deteksi: offline, baterai, kualitas link (SNR/hop), dan lingkup")
    kandidat = uji_deteksi(modul)
    print()

    # --- 2b. fitur yang diminta pemilik halaman ---
    print("2b. Kontak radio langsung, gateway mati/pulih, dan ketahanan state")
    uji_fitur_baru(modul)
    print()

    # --- 2c. dua topik: kabar penting vs kabar rutin ---
    print("2c. Pemisahan topik: kabar penting (gateway/node) vs kabar rutin")
    uji_topik_penting(modul)
    print()

    # --- 2d. failover sumber data /data.json ---
    print("2d. Failover sumber data /data.json (MESH_DATA_CADANGAN)")
    uji_sumber_cadangan(modul)
    print()

    # --- 3. Ketiga jenis kabar, dari data NYATA, lewat topik yang SEBENARNYA ---
    # Bukan pesan buatan: isi pesannya disusun dari node yang benar-benar ada di
    # /data.json saat ini, dan topiknya dipilih oleh fungsi yang sama dengan yang
    # dipakai layanan (topik_untuk). Jadi yang diuji adalah jalurnya, bukan
    # sekadar kemampuan mengirim HTTP POST.
    print("3. Uji kirim ketiga jenis kabar ke topik yang sebenarnya")
    if opsi["kering"]:
        info("dilewati (--kering)")
        print()
    else:
        nyata = (data or {}).get("node", [])
        radio = [n for n in nyata
                 if n.get("via") == "lora" and isinstance(n.get("snr"), (int, float))
                 and n.get("last_heard_seconds") is not None]
        radio_offline = [n for n in radio if not n.get("online")]
        info("%d node radio terbaca (SNR terisi), %d di antaranya sedang offline"
             % (len(radio), len(radio_offline)))

        # 3a. kontak radio langsung - data nyata
        print("   3a. kontak radio langsung")
        if radio:
            kirim_dan_tunggu(modul, server,
                             modul.topik_untuk(modul.pesan_kontak_radio(radio[0]),
                                               topik, topik_penting),
                             token, lokal, ctx, modul.pesan_kontak_radio(radio[0]),
                             opsi["timeout"], "Pesan UJI dari uji-notif-meshtastic.py.")
        else:
            info("dilewati: belum ada satu pun node radio dengan SNR terbaca")
            info("ini bukan kegagalan kanal - memang belum ada kontak radio saat ini")

        # 3b. node yang tersambung gateway menjadi offline - data nyata
        print("   3b. node gateway/via radio menjadi offline")
        if radio_offline:
            n = radio_offline[0]
            pesan_off = modul.pesan_offline(
                n.get("long_name") or n.get("short_name") or n.get("node_id"),
                n.get("node_id"), n.get("role") or "-", n.get("last_heard_seconds"),
                modul.mutu_dari(n, n.get("lantai_snr") or modul.BAWAAN_LANTAI_SNR),
                n.get("snr"), n.get("lantai_snr") or modul.BAWAAN_LANTAI_SNR,
                n.get("hops"))
            kirim_dan_tunggu(modul, server,
                             modul.topik_untuk(pesan_off, topik, topik_penting),
                             token, lokal, ctx, pesan_off, opsi["timeout"],
                             "Pesan UJI (node ini memang sedang offline saat uji dijalankan).")
        elif kandidat is not None:
            info("tidak ada node radio yang offline sekarang -> memakai contoh buatan")
            kirim_dan_tunggu(modul, server,
                             modul.topik_untuk(kandidat, topik, topik_penting),
                             token, lokal, ctx, kandidat, opsi["timeout"],
                             "Pesan UJI dengan data buatan (bukan node sungguhan).")
        else:
            gagal("tidak ada node untuk menguji kabar offline")

        # 3c. gateway mati - SATU-SATUNYA yang disimulasikan, dan diberi label
        print("   3c. gateway mati (disimulasikan)")
        pesan_mati = modul.pesan_gw_mati(
            "SIMULASI UJI - gateway sebenarnya sehat; dipicu sengaja oleh "
            "uji-notif-meshtastic.py untuk membuktikan kanalnya hidup", 0)
        tujuan_mati = modul.topik_untuk(pesan_mati, topik, topik_penting)
        if tujuan_mati != topik_penting:
            gagal("kabar gateway mati TIDAK diarahkan ke topik penting (ke %s)"
                  % tujuan_mati)
        else:
            lolos("kabar gateway mati memang diarahkan ke topik PENTING")
        kirim_dan_tunggu(modul, server, tujuan_mati, token, lokal, ctx, pesan_mati,
                         opsi["timeout"],
                         "*** INI HANYA UJI - gateway Anda TIDAK mati. ***")

        # 3d. semua yang rutin harus tetap pergi ke topik rutin
        print("   3d. kabar rutin tetap ke topik rutin")
        pesan_rutin = modul.pesan_baterai("UJI-baterai", "!00000000", 5)
        tujuan_rutin = modul.topik_untuk(pesan_rutin, topik, topik_penting)
        if tujuan_rutin != topik:
            gagal("kabar rutin salah diarahkan ke %s" % tujuan_rutin)
        else:
            lolos("kabar rutin memang diarahkan ke topik rutin")
            kirim_dan_tunggu(modul, server, tujuan_rutin, token, lokal, ctx,
                             pesan_rutin, opsi["timeout"],
                             "Pesan UJI kanal rutin.")
        print()

    print("=" * 60)
    print(" Lolos: %d | GAGAL: %d" % (LOLOS, GAGAL))
    if GAGAL:
        print(" HASIL: kanal notifikasi Meshtastic TIDAK terbukti hidup.")
    else:
        print(" HASIL: jalur exporter -> deteksi -> ntfy terbukti ujung-ke-ujung.")
        print(" Pastikan ponsel berlangganan server/topik di atas.")
    print("=" * 60)
    return 0 if GAGAL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
