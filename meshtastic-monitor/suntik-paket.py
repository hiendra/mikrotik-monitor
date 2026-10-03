#!/usr/bin/env python3
# ============================================================
# suntik-paket.py - paket "seolah diterima dari udara" untuk node virtual
# ============================================================
# Alat ini memalsukan node yang tidak ada: ia menyusun sebuah MeshPacket,
# membungkusnya dalam portnum SIMULATOR_APP, lalu mengirimkannya lewat API
# (TCP) ke sebuah node. Node penerima MEMBONGKAR bungkusan itu dan
# memperlakukannya persis seperti paket yang baru diterima dari chip LoRa -
# termasuk from/to/id/kanal DAN metadata tautan rx_snr/rx_rssi.
#
# Kenapa berguna
# --------------
# Bot tidak perlu menunggu ada orang memancar untuk bisa diuji. Dengan node
# virtual, /dasbor uji jaringan (jangkauan terjauh, sparkline SNR, kontak per
# node) bisa diisi dari data yang Anda tentukan sendiri, TANPA satu byte pun
# ke udara dan tanpa risiko mengganggu mesh.
#
# Dua jalur di firmware (keduanya sudah ada di pohon firmware/)
# ------------------------------------------------------------
#   1. Node simulasi (ARCH_PORTDUINO, flag `--sim`):
#      MeshService::handleToRadio -> SimRadio::unpackAndReceive.
#      Bawaan aman: node ini tidak punya radio, jadi tidak ada airtime nyata.
#   2. Perangkat NYATA: MeshService::injectAsReceived(), di balik build-flag
#      MESHTASTIC_ENABLE_FRAME_INJECTION yang BAIKAANNYA 0. Komentar di
#      firmware/ menulis tegas: "it lets anything with a wired connection
#      forge over-the-air traffic, so it must never ship enabled."
#      Selama flag itu 0, perangkat nyata akan menolak paket seperti ini.
#
# Aturan yang ditiru dari firmware (jangan diubah tanpa mengubah firmware)
# -----------------------------------------------------------------------
#   * from == 0 ditolak (meniru RadioLibInterface yang membuang sender 0).
#   * rx_snr == 0 -> firmware mengisinya 8 ("plausible synthetic link
#     metadata"), jadi SNR 0 berarti "terserah firmware", bukan 0 dB.
#   * rx_rssi hanya diisi -40 bila pemanggil TIDAK mengirim nilainya.
#     Di binding Python field ini tidak punya presence, dan nilai 0 TIDAK
#     ikut terserialisasi - jadi kirim nilai bukan-nol bila ingin dihormati.
#   * Muatan asli dibungkus meshtastic_Compressed{portnum, data} dan
#     ditempatkan di decoded.payload, yang hanya muat 233 byte
#     (DATA_PAYLOAD_LEN). Karena itu muatan mentah maksimum ~228 byte.
#
# Pakai
# -----
#   ./venv/Scripts/python suntik-paket.py --uji-diri
#                          buktikan paketnya bisa dibongkar ulang TANPA radio,
#                          tanpa jaringan, tanpa node (keluar 0 bila semua lulus)
#
#   ./venv/Scripts/python suntik-paket.py --kering --node '!11112222:7.5:-92:0:MOB-UJI'
#                          rangkai + tampilkan saja, jangan menyentuh jaringan
#
#   ./venv/Scripts/python suntik-paket.py --node '!11112222:7.5:-92:0:MOB-UJI'
#                          kirim ke node simulasi (bawaan 127.0.0.1:4404)
#
#   ./venv/Scripts/python suntik-paket.py --sapuan --langkah 2
#                          skenario drive test: satu node menjauh lalu mendekat
#
# Opsi
# ----
#   --host H --port P     node tujuan (bawaan 127.0.0.1:4404 = node simulasi)
#   --node SPEC           id[:snr[:rssi[:hop[:nama]]]], bisa diulang
#   --posisi SPEC         id:LAT:LON[:ALT] - jarak di dasbor butuh ini
#   --teks TEKS           isi pesan yang "diterima" (bawaan "test")
#   --sapuan              jalankan skenario drive test bawaan
#   --nama NAMA           nama node drive test untuk --sapuan (bawaan "MOB-UJI")
#   --gw LAT:LON          posisi gateway untuk --sapuan (bawaan -6.2:106.8)
#   --langkah DET         jeda antar paket (bawaan 2 detik)
#   --kanal N             kanal paket (bawaan 0)
#   --kering              rangkai saja, jangan kirim
#   --ya                  izin menyuntik ke host BUKAN loopback (berbahaya)
#   --uji-diri            uji mandiri tanpa node, lalu keluar
#   -h, --help            tampilkan bantuan ini
# ============================================================

import os
import random
import sys
import time

AKAR = os.path.dirname(os.path.abspath(__file__))

# DATA_PAYLOAD_LEN di protobufs/meshtastic/mesh.proto - ukuran medan
# decoded.payload.bytes tempat bungkusan Compressed harus muat.
BATAS_MUATAN = 233

# Paket kita berangkat dengan sisa hop yang sehat, supaya node penerima tidak
# membuangnya karena hop habis. Jarak hopnya sendiri = hop_start - hop_limit.
SISA_HOP = 3

BAWAAN_HOST = "127.0.0.1"
BAWAAN_PORT = 4404          # sengaja bukan 4403: itu gateway sungguhan
BAWAAN_TEKS = "test"
BAWAAN_NAMA = "MOB-UJI"
BAWAAN_GW = (-6.2, 106.8)

LOLOS = 0
GAGAL = 0

_DIPAKAI = set()
_ACAK = random.Random()


# ------------------------------------------------------------
# Protobuf Meshtastic (dipisah supaya --uji-diri jelas soal ketergantungan)
# ------------------------------------------------------------

def pustaka():
    """Impor protobuf Meshtastic; beri pesan jelas bila tidak ada."""
    try:
        from meshtastic.protobuf import mesh_pb2, portnums_pb2
    except ImportError as e:
        print("protobuf Meshtastic tidak tersedia (%s)." % e, file=sys.stderr)
        print("Pasang dulu: ./venv/Scripts/python -m pip install meshtastic",
              file=sys.stderr)
        raise SystemExit(2)
    return mesh_pb2, portnums_pb2


# ------------------------------------------------------------
# Alat kecil
# ------------------------------------------------------------

def catat(pesan):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), pesan), flush=True)


def bagian(judul):
    print("\n%s" % judul)


def lolos(pesan):
    global LOLOS
    LOLOS += 1
    print("  [LULUS] %s" % pesan)


def gagal(pesan):
    global GAGAL
    GAGAL += 1
    print("  [GAGAL] %s" % pesan)


def id_paket():
    """ID paket unik dan bukan nol.

    Penting: bot mendeduplikasi paket berdasarkan id, jadi id yang terpakai
    ulang akan membuat paket kedua tampak "sudah pernah dilihat" dan diam-diam
    dibuang - gejalanya bot seperti tidak bereaksi.
    """
    while True:
        nilai = _ACAK.randint(1, 0x7FFFFFFF)
        if nilai not in _DIPAKAI:
            _DIPAKAI.add(nilai)
            return nilai


def id_node(teks, siapa="node"):
    """Terima '!11112222' (heksadesimal) atau '286331153' (desimal)."""
    t = (teks or "").strip()
    if not t:
        raise ValueError("%s kosong" % siapa)
    try:
        nilai = int(t[1:], 16) if t.startswith("!") else int(t)
    except ValueError:
        raise ValueError("%s bukan id node: %r" % (siapa, teks))
    if nilai <= 0 or nilai > 0xFFFFFFFF:
        raise ValueError("%s di luar rentang 32 bit: %r" % (siapa, teks))
    return nilai


def teks_id(nilai):
    return "!%08x" % nilai


# ------------------------------------------------------------
# Merangkai paket
# ------------------------------------------------------------

def kapasitas(portnum):
    """Muatan mentah terbesar yang masih muat setelah dibungkus Compressed."""
    mesh_pb2, _ = pustaka()
    muat = 0
    for n in range(1, BATAS_MUATAN + 1):
        c = mesh_pb2.Compressed(portnum=portnum, data=b"x" * n)
        if len(c.SerializeToString()) > BATAS_MUATAN:
            break
        muat = n
    return muat


def rangkai(portnum, muatan, dari, snr=6.5, rssi=-95, hop=0, kanal=0,
            ke=0xFFFFFFFF, pid=None):
    """Bungkus muatan asli jadi paket yang diterima jalur RX seperti dari udara.

    Cermin dari SimRadio::startSend() / MeshService::injectAsReceived():
    muatan asli masuk ke meshtastic_Compressed{portnum, data}, bungkusan itu
    ditaruh di decoded.payload, lalu decoded.portnum diubah menjadi
    SIMULATOR_APP sebagai penanda.
    """
    mesh_pb2, portnums_pb2 = pustaka()
    batin = mesh_pb2.Compressed()
    batin.portnum = portnum
    batin.data = muatan

    p = mesh_pb2.MeshPacket()
    setattr(p, "from", int(dari))     # 'from' kata kunci Python: wajib setattr
    p.to = int(ke)
    p.id = int(pid) if pid else id_paket()
    p.channel = int(kanal)
    p.rx_snr = float(snr)
    p.rx_rssi = int(rssi)
    p.hop_start = int(hop) + SISA_HOP
    p.hop_limit = SISA_HOP
    p.decoded.portnum = portnums_pb2.PortNum.SIMULATOR_APP
    p.decoded.payload = batin.SerializeToString()

    luar = mesh_pb2.ToRadio()
    luar.packet.CopyFrom(p)
    return luar


def rangkai_teks(teks, dari, **sisa):
    _, portnums_pb2 = pustaka()
    return rangkai(portnums_pb2.PortNum.TEXT_MESSAGE_APP, teks.encode("utf-8"),
                   dari, **sisa)


def rangkai_posisi(lat, lon, dari, alt=0, **sisa):
    mesh_pb2, portnums_pb2 = pustaka()
    pos = mesh_pb2.Position()
    pos.latitude_i = int(round(float(lat) * 1e7))
    pos.longitude_i = int(round(float(lon) * 1e7))
    pos.altitude = int(alt)
    return rangkai(portnums_pb2.PortNum.POSITION_APP, pos.SerializeToString(),
                   dari, **sisa)


def rangkai_nodeinfo(dari, nama, singkat=None, **sisa):
    mesh_pb2, portnums_pb2 = pustaka()
    u = mesh_pb2.User()
    u.id = teks_id(dari)
    u.long_name = (nama or teks_id(dari))[:39]
    u.short_name = (singkat or (nama or "SIM")[:4])[:4]
    return rangkai(portnums_pb2.PortNum.NODEINFO_APP, u.SerializeToString(),
                   dari, **sisa)


def periksa(paket):
    """Kembalikan daftar PERINGATAN atas paket yang akan dikirim (bukan error).

    Isinya meniru aturan firmware supaya paket yang "diam" tidak membingungkan.
    """
    _, portnums_pb2 = pustaka()
    p = paket.packet
    catatan = []
    if getattr(p, "from") == 0:
        catatan.append("pengirim 0 akan DITOLAK node (meniru jalur RX nyata)")
    if p.rx_snr == 0:
        catatan.append("SNR 0 ditafsirkan 'terserah firmware' -> diisi 8 di "
                       "perangkat nyata, tetap 0 di node simulasi")
    if p.rx_rssi == 0:
        catatan.append("RSSI 0 tidak punya presence -> tidak ikut terkirim; "
                       "perangkat nyata akan mengisinya -40")
    if p.decoded.portnum == portnums_pb2.PortNum.SIMULATOR_APP:
        batin = pustaka()[0].Compressed()
        batin.ParseFromString(p.decoded.payload)
        if len(p.decoded.payload) > BATAS_MUATAN:
            catatan.append("bungkusan %d byte melebihi batas %d byte"
                           % (len(p.decoded.payload), BATAS_MUATAN))
        if batin.portnum == portnums_pb2.PortNum.UNKNOWN_APP:
            catatan.append("portnum dalam UNKNOWN_APP -> diperlakukan sebagai "
                           "CIPHERTEXT, bukan teks biasa")
    return catatan


# ------------------------------------------------------------
# Membongkar kembali (cermin firmware, dipakai --uji-diri)
# ------------------------------------------------------------

def bongkar(paket):
    """Cermin SimRadio::unpackAndReceive(): buka bungkusan SIMULATOR_APP.

    Mengembalikan dict berisi apa yang akan "terdengar" oleh node:
    portnum asli, muatan asli, dan metadata tautannya.
    """
    mesh_pb2, portnums_pb2 = pustaka()
    p = paket.packet
    hasil = {
        "dari": getattr(p, "from"), "ke": p.to, "id": p.id, "kanal": p.channel,
        "snr": p.rx_snr, "rssi": p.rx_rssi,
        "hop": p.hop_start - p.hop_limit,
        "batin": None, "muatan": None, "teks": None, "posisi": None,
        "nama": None, "tersandi": False,
    }
    if p.WhichOneof("payload_variant") != "decoded":
        hasil["tersandi"] = True
        return hasil
    if p.decoded.portnum != portnums_pb2.PortNum.SIMULATOR_APP:
        hasil["batin"] = p.decoded.portnum
        hasil["muatan"] = p.decoded.payload
        return hasil

    batin = mesh_pb2.Compressed()
    batin.ParseFromString(p.decoded.payload)
    hasil["batin"] = batin.portnum
    hasil["muatan"] = batin.data
    if batin.portnum == portnums_pb2.PortNum.UNKNOWN_APP:
        hasil["tersandi"] = True
    elif batin.portnum == portnums_pb2.PortNum.TEXT_MESSAGE_APP:
        hasil["teks"] = batin.data.decode("utf-8", "replace")
    elif batin.portnum == portnums_pb2.PortNum.POSITION_APP:
        pos = mesh_pb2.Position()
        pos.ParseFromString(batin.data)
        hasil["posisi"] = {"lat": pos.latitude_i / 1e7,
                           "lon": pos.longitude_i / 1e7, "alt": pos.altitude}
    elif batin.portnum == portnums_pb2.PortNum.NODEINFO_APP:
        u = mesh_pb2.User()
        u.ParseFromString(batin.data)
        hasil["nama"] = (u.long_name, u.short_name)
    return hasil


# ------------------------------------------------------------
# Skenario: node virtual berjalan menjauh lalu mendekat
# ------------------------------------------------------------

def _lintang_geser(meter):
    """Perkiraan geseran lintang untuk jarak tertentu (1 derajat ~ 111.320 m)."""
    return meter / 111320.0


def rencana_sapuan(gw, jumlah=12, dekat=200, jauh=9000):
    """(jarak_m, snr_db) tiap langkah: dari dekat ke jauh, lalu kembali.

    SNR diturunkan terhadap jarak supaya grafik drive test punya bentuk yang
    masuk akal: kuat di dekat, tenggelam di ujung, pulih saat kembali.
    """
    setengah = max(1, jumlah // 2)
    jarak = []
    for i in range(setengah):
        jarak.append(dekat + (jauh - dekat) * (i / float(setengah - 1 or 1)))
    for i in range(setengah - 2, -1, -1):
        jarak.append(dekat + (jauh - dekat) * (i / float(setengah - 1 or 1)))
    langkah = []
    for d in jarak:
        bagian_atas = (d - dekat) / float(jauh - dekat or 1)
        langkah.append((int(d), round(8.0 - 24.0 * bagian_atas, 1)))
    return langkah


# ------------------------------------------------------------
# Pengiriman
# ------------------------------------------------------------

def loopback(host):
    return (host or "").strip().lower() in ("127.0.0.1", "localhost", "::1")


def sambung(host, port, tunggu=20):
    """Sambung ke node lewat TCP."""
    from meshtastic.tcp_interface import TCPInterface
    iface = TCPInterface(hostname=host, portNumber=port)
    batas = time.time() + tunggu
    while time.time() < batas:
        ln = getattr(iface, "localNode", None)
        if ln is not None and getattr(ln, "channels", None):
            return iface
        time.sleep(1)
    return iface


def kirim(iface, paket):
    """Kirim satu ToRadio. _sendToRadio adalah API privat pustaka meshtastic."""
    iface._sendToRadio(paket)


# ------------------------------------------------------------
# Uji mandiri - membuktikan paket bisa dibongkar ulang TANPA radio
# ------------------------------------------------------------

def uji_diri():
    global LOLOS, GAGAL
    LOLOS = GAGAL = 0
    mesh_pb2, portnums_pb2 = pustaka()

    print("=" * 62)
    print(" UJI MANDIRI suntik-paket.py - tanpa radio, tanpa jaringan")
    print("=" * 62)

    bagian("1. Bungkusan & pembongkaran")
    p = rangkai_teks("halo dunia", dari=0x11112222, snr=7.5, rssi=-92, hop=0, pid=101)
    if p.packet.decoded.portnum == portnums_pb2.PortNum.SIMULATOR_APP:
        lolos("pembungkus memakai SIMULATOR_APP (portnum %d)"
              % portnums_pb2.PortNum.SIMULATOR_APP)
    else:
        gagal("portnum pembungkus salah: %d" % p.packet.decoded.portnum)

    hasil = bongkar(p)
    if hasil["batin"] == portnums_pb2.PortNum.TEXT_MESSAGE_APP and hasil["teks"] == "halo dunia":
        lolos("pesan utuh setelah dibongkar kembali: %r" % hasil["teks"])
    else:
        gagal("pesan tidak utuh: %r" % hasil)
    if hasil["dari"] == 0x11112222:
        lolos("pengirim dipertahankan (%s)" % teks_id(hasil["dari"]))
    else:
        gagal("pengirim berubah: %r" % hasil["dari"])
    if hasil["snr"] == 7.5 and hasil["rssi"] == -92:
        lolos("SNR/RSSI pilihan sampai apa adanya (%.1f dB / %d dBm)"
              % (hasil["snr"], hasil["rssi"]))
    else:
        gagal("SNR/RSSI tidak sesuai: %r" % hasil)

    p = rangkai_teks("test", dari=0x22223333, hop=3, pid=202)
    if bongkar(p)["hop"] == 3:
        lolos("hop dihitung dari hop_start - hop_limit (3 hop)")
    else:
        gagal("hop salah: %r" % bongkar(p)["hop"])

    bagian("2. Aturan yang meniru firmware")
    catatan = periksa(rangkai_teks("x", dari=0x33334444, snr=0, rssi=0, pid=303))
    if any("pengirim 0" in c for c in catatan) is False and \
            any("SNR 0" in c for c in catatan) and any("RSSI 0" in c for c in catatan):
        lolos("SNR 0 dan RSSI 0 sama-sama diperingatkan (%d catatan)" % len(catatan))
    else:
        gagal("peringatan SNR/RSSI nol tidak muncul: %r" % catatan)
    catatan = periksa(rangkai_teks("x", dari=0, snr=5, rssi=-90, pid=304))
    if any("pengirim 0" in c for c in catatan):
        lolos("pengirim 0 diperingatkan akan ditolak node")
    else:
        gagal("pengirim 0 tidak diperingatkan: %r" % catatan)
    catatan = periksa(rangkai_teks("x", dari=0x44445555, snr=5, rssi=-90, pid=305))
    if not catatan:
        lolos("paket sehat tidak memunculkan peringatan apa pun")
    else:
        gagal("paket sehat malah diperingatkan: %r" % catatan)

    # Bungkusan berisi ciphertext harus dikenali sebagai ciphertext, bukan teks.
    cipher = rangkai(portnums_pb2.PortNum.UNKNOWN_APP, b"\x01\x02\x03",
                     dari=0x55556666, pid=306)
    if bongkar(cipher)["tersandi"]:
        lolos("UNKNOWN_APP di dalam dikenali sebagai ciphertext (bukan teks)")
    else:
        gagal("ciphertext tidak dikenali: %r" % bongkar(cipher))

    bagian("3. Batas muatan (233 byte DATA_PAYLOAD_LEN)")
    muat = kapasitas(portnums_pb2.PortNum.TEXT_MESSAGE_APP)
    bungkus = len(mesh_pb2.Compressed(
        portnum=portnums_pb2.PortNum.TEXT_MESSAGE_APP, data=b"x" * muat).SerializeToString())
    lewat = len(mesh_pb2.Compressed(
        portnum=portnums_pb2.PortNum.TEXT_MESSAGE_APP, data=b"x" * (muat + 1)).SerializeToString())
    if bungkus <= BATAS_MUATAN < lewat:
        lolos("tepat di batas: %d byte muatan -> %d byte terbungkus (maks %d)"
              % (muat, bungkus, BATAS_MUATAN))
    else:
        gagal("batas muatan salah hitung: %d -> %d, %d -> %d"
              % (muat, bungkus, muat + 1, lewat))
    catatan = periksa(rangkai_teks("y" * (muat + 1), dari=0x66667777, pid=307))
    if any("melebihi batas" in c for c in catatan):
        lolos("muatan kelebihan satu byte sudah diperingatkan sebelum dikirim")
    else:
        gagal("muatan kelebihan tidak diperingatkan: %r" % catatan)

    bagian("4. Posisi & nama node virtual")
    hasil = bongkar(rangkai_posisi(-6.2, 106.8, dari=0x77778888, alt=12, pid=308))
    if hasil["posisi"] and abs(hasil["posisi"]["lat"] + 6.2) < 1e-6 \
            and abs(hasil["posisi"]["lon"] - 106.8) < 1e-6 and hasil["posisi"]["alt"] == 12:
        lolos("posisi bulat-balik utuh (%.5f, %.5f, %d m)"
              % (hasil["posisi"]["lat"], hasil["posisi"]["lon"], hasil["posisi"]["alt"]))
    else:
        gagal("posisi tidak utuh: %r" % hasil["posisi"])
    hasil = bongkar(rangkai_nodeinfo(0x88889999, "MOB-UJI", "MOB", pid=309))
    if hasil["nama"] == ("MOB-UJI", "MOB"):
        lolos("nodeinfo bulat-balik (%s / %s)" % hasil["nama"])
    else:
        gagal("nodeinfo tidak utuh: %r" % hasil["nama"])

    bagian("5. ID paket unik (bot mendeduplikasi per id)")
    kumpul = [id_paket() for _ in range(500)]
    if len(set(kumpul)) == 500 and 0 not in kumpul:
        lolos("500 id berbeda dan tidak ada yang nol")
    else:
        gagal("ada id kembar atau nol: %d unik" % len(set(kumpul)))

    bagian("6. Skenario sapuan (drive test)")
    langkah = rencana_sapuan((-6.2, 106.8))
    jarak = [d for d, _ in langkah]
    snr = [s for _, s in langkah]
    tengah = len(jarak) // 2
    # Bentuk yang diharapkan: menanjak sampai titik terjauh, lalu menurun
    # kembali ke titik awal - titik terjauh sengaja TIDAK diulang.
    menanjak = all(jarak[i] < jarak[i + 1] for i in range(tengah))
    menurun = all(jarak[i] > jarak[i + 1] for i in range(tengah, len(jarak) - 1))
    if (jarak[0] == jarak[-1] == min(jarak) and jarak[tengah] == max(jarak)
            and menanjak and menurun
            and snr[0] == snr[-1] == max(snr) and snr[tengah] == min(snr)
            and min(snr) >= -16):
        lolos("%d langkah: terdekat %d m (SNR %.1f) -> terjauh %d m (SNR %.1f) "
              "-> kembali" % (len(langkah), jarak[0], snr[0], max(jarak), min(snr)))
    else:
        gagal("skenario sapuan tidak berbentuk menjauh-lalu-mendekat: %r" % langkah)

    # Drive test harus MENGUMUMKAN dirinya dulu: tanpa NodeInfo, penerima cuma
    # tahu nomor node, jadi balasan bot dan kartu dasbor berisi "!6d0b0001"
    # alih-alih nama mobil ujinya.
    o = baca_opsi(["--sapuan"])
    kiriman = bahan(o)
    paket_nama = [(ket, bongkar(p)) for ket, p in kiriman
                  if bongkar(p)["batin"] == portnums_pb2.PortNum.NODEINFO_APP]
    jumlah_teks = len([1 for _, p in kiriman
                       if bongkar(p)["batin"] == portnums_pb2.PortNum.TEXT_MESSAGE_APP])
    if (len(kiriman) == 1 + 2 * len(langkah) and len(paket_nama) == 1
            and jumlah_teks == len(langkah)
            and paket_nama[0][1]["nama"] and paket_nama[0][1]["nama"][0] == BAWAAN_NAMA):
        lolos("sapuan mengirim %d paket: 1 NodeInfo '%s' + %d posisi + %d teks"
              % (len(kiriman), paket_nama[0][1]["nama"][0], len(langkah), jumlah_teks))
        if paket_nama[0][1]["snr"] == snr[0]:
            lolos("NodeInfo drive test ikut membawa SNR langkah pertama (%.1f dB)"
                  % paket_nama[0][1]["snr"])
        else:
            gagal("SNR NodeInfo %r bukan SNR langkah pertama %r"
                  % (paket_nama[0][1]["snr"], snr[0]))
    else:
        gagal("sapuan tanpa NodeInfo bernama: %d paket, %d nodeinfo, %d teks"
              % (len(kiriman), len(paket_nama), jumlah_teks))

    print("\n" + "=" * 62)
    print(" HASIL: %d lulus, %d gagal" % (LOLOS, GAGAL))
    print("=" * 62)
    if GAGAL:
        print(" Paket TIDAK terbukti bisa dibongkar ulang - jangan dipakai mengirim.")
        return 1
    print(" Paket terbukti bisa dirangkai dan dibongkar ulang tanpa radio.")
    return 0


# ------------------------------------------------------------
# Opsi & program utama
# ------------------------------------------------------------

USAGE = """suntik-paket.py - paket "seolah diterima dari udara" untuk node virtual

  suntik-paket.py --uji-diri            uji mandiri tanpa radio/jaringan (bawaan aman)
  suntik-paket.py --kering --node ...   rangkai & tampilkan, jangan kirim
  suntik-paket.py --node '!11112222:7.5:-92:0:MOB-UJI'
  suntik-paket.py --sapuan --langkah 2  skenario drive test menjauh lalu mendekat

  --host H --port P    node tujuan (bawaan %s:%s)
  --node SPEC          id[:snr[:rssi[:hop[:nama]]]] (bisa diulang)
  --posisi SPEC        id:LAT:LON[:ALT] - perlu agar jarak di dasbor terisi
  --teks TEKS          isi pesan yang "diterima" (bawaan "%s")
  --sapuan             jalankan skenario drive test bawaan
  --nama NAMA          nama node drive test untuk --sapuan (bawaan "%s")
  --gw LAT:LON         posisi gateway untuk --sapuan (bawaan %.1f:%.1f)
  --langkah DET        jeda antar paket (bawaan 2 detik)
  --kanal N            kanal paket (bawaan 0)
  --kering             jangan kirim apa pun
  --ya                 izin menyuntik ke host BUKAN loopback
  --uji-diri           uji mandiri, tidak menyentuh jaringan
  -h, --help           tampilkan bantuan ini
"""


def baca_opsi(argv):
    o = {"host": BAWAAN_HOST, "port": BAWAAN_PORT, "node": [], "posisi": [],
         "teks": BAWAAN_TEKS, "sapuan": False, "gw": BAWAAN_GW, "langkah": 2.0,
         "nama": BAWAAN_NAMA,
         "kanal": 0, "kering": False, "ya": False, "uji_diri": False, "tolong": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        nilai = None
        if a.startswith("--") and "=" in a:
            a, nilai = a.split("=", 1)
        if a in ("-h", "--help"):
            o["tolong"] = True
            i += 1
            continue
        if a in ("--uji-diri", "--sapuan", "--kering", "--ya"):
            o[a[2:].replace("-", "_")] = True
            i += 1
            continue
        if nilai is None:
            if i + 1 >= len(argv):
                raise SystemExit("Opsi %s butuh nilai." % a)
            nilai = argv[i + 1]
            i += 2
        else:
            i += 1
        if a == "--host":
            o["host"] = nilai
        elif a == "--port":
            o["port"] = int(nilai)
        elif a == "--node":
            o["node"].append(nilai)
        elif a == "--posisi":
            o["posisi"].append(nilai)
        elif a == "--teks":
            o["teks"] = nilai
        elif a == "--nama":
            o["nama"] = nilai
        elif a == "--gw":
            lat, lon = nilai.split(":")
            o["gw"] = (float(lat), float(lon))
        elif a == "--langkah":
            o["langkah"] = float(nilai)
        elif a == "--kanal":
            o["kanal"] = int(nilai)
        else:
            raise SystemExit("Opsi tidak dikenal: %s" % a)
    return o


def baca_node(spec, teks, kanal):
    """'id[:snr[:rssi[:hop[:nama]]]]' -> (paket teks, paket nodeinfo/nama)."""
    keping = spec.split(":")
    if not keping or not keping[0].strip():
        raise SystemExit("Spesifikasi node kosong: %r" % spec)
    dari = id_node(keping[0], "node")
    snr = float(keping[1]) if len(keping) > 1 and keping[1] != "" else 6.5
    rssi = int(keping[2]) if len(keping) > 2 and keping[2] != "" else -95
    hop = int(keping[3]) if len(keping) > 3 and keping[3] != "" else 0
    nama = keping[4] if len(keping) > 4 and keping[4] else None
    return dari, {"snr": snr, "rssi": rssi, "hop": hop, "kanal": kanal}, nama


def bahan(o):
    """Daftar (keterangan, paket) yang akan dikirim, semuanya sudah dirangkai."""
    daftar = []
    posisi = {}
    for spec in o["posisi"]:
        keping = spec.split(":")
        if len(keping) < 3:
            raise SystemExit("Spesifikasi posisi kurang: %r" % spec)
        dari = id_node(keping[0], "posisi")
        posisi[dari] = (float(keping[1]), float(keping[2]),
                        int(keping[3]) if len(keping) > 3 else 0)

    if o["sapuan"]:
        # Satu node virtual berjalan menjauh lalu kembali. Posisi disuntik dulu
        # supaya bot bisa menghitung jarak ke gateway (dasbor butuh itu).
        dari = 0x6D0B0001
        langkah = rencana_sapuan(o["gw"])
        # NodeInfo diumumkan LEBIH DULU, seperti node yang baru masuk mesh.
        # Tanpa ini penerima hanya tahu NOMOR node, sehingga balasan bot dan
        # kartu dasbor menampilkan "!6d0b0001" alih-alih nama mobil ujinya -
        # kekurangan yang ketahuan saat uji ujung-ke-ujung dijalankan.
        jarak0, snr0 = langkah[0]
        daftar.append(("nama   %s" % o["nama"],
                       rangkai_nodeinfo(dari, o["nama"], _singkat(o["nama"]),
                                        snr=snr0, rssi=-40 - int(jarak0 / 200.0),
                                        hop=0, kanal=o["kanal"])))
        for nomor, (jarak, snr) in enumerate(langkah, start=1):
            lat = o["gw"][0] + _lintang_geser(jarak)
            # Paket posisi memakai SNR yang SAMA dengan langkahnya: node yang
            # jauh memang lemah pada semua paketnya, bukan hanya pada teksnya.
            # Kalau tidak, grafik drive test akan penuh titik kuat di jarak
            # jauh dan itu menyesatkan.
            taut = {"snr": snr, "rssi": -40 - int(jarak / 200.0),
                    "hop": 0 if jarak < 3000 else 1, "kanal": o["kanal"]}
            daftar.append(("posisi %d/%d %s m" % (nomor, len(langkah), jarak),
                           rangkai_posisi(lat, o["gw"][1], dari, **taut)))
            daftar.append(("teks   %d/%d (%s dB)" % (nomor, len(langkah), snr),
                           rangkai_teks(o["teks"], dari, **taut)))
        return daftar

    for spec in o["node"]:
        dari, meta, nama = baca_node(spec, o["teks"], o["kanal"])
        if nama:
            daftar.append(("nama   %s" % nama,
                           rangkai_nodeinfo(dari, nama, _singkat(nama), **meta)))
        if dari in posisi:
            lat, lon, alt = posisi[dari]
            daftar.append(("posisi %s" % teks_id(dari),
                           rangkai_posisi(lat, lon, dari, alt=alt, **meta)))
        daftar.append(("teks   %s (%s dB)" % (teks_id(dari), meta["snr"]),
                       rangkai_teks(o["teks"], dari, **meta)))
    return daftar


def _singkat(nama):
    huruf = "".join(c for c in nama if c.isalnum())
    return (huruf[:4] or "SIM").upper()


def main(argv):
    for aliran in (sys.stdout, sys.stderr):
        try:
            aliran.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    o = baca_opsi(argv)
    if o["tolong"]:
        print(USAGE % (BAWAAN_HOST, BAWAAN_PORT, BAWAAN_TEKS, BAWAAN_NAMA,
                       BAWAAN_GW[0], BAWAAN_GW[1]))
        return 0
    if o["uji_diri"]:
        return uji_diri()

    if not o["node"] and not o["sapuan"]:
        print("Tidak ada yang dikirim: beri --node atau --sapuan "
              "(atau --uji-diri untuk menguji skripnya sendiri).")
        print(USAGE % (BAWAAN_HOST, BAWAAN_PORT, BAWAAN_TEKS, BAWAAN_NAMA,
                       BAWAAN_GW[0], BAWAAN_GW[1]))
        return 2

    kiriman = bahan(o)
    print("=" * 62)
    print(" SUNTIK PAKET - node virtual%s" % (" (KERING: tidak dikirim)" if o["kering"] else ""))
    print("=" * 62)
    print(" Tujuan   : %s:%s" % (o["host"], o["port"]))
    print(" Kanal    : %s | jeda %s detik | %d paket"
          % (o["kanal"], o["langkah"], len(kiriman)))
    print("-" * 62)

    catatan_semua = []
    for ket, paket in kiriman:
        catatan_semua.extend(periksa(paket))
    for c in sorted(set(catatan_semua)):
        print(" [!] %s" % c)
    if catatan_semua:
        print("-" * 62)

    # Mode kering tidak menyentuh jaringan sama sekali, jadi aman ke host mana pun.
    if not o["kering"] and not loopback(o["host"]) and not o["ya"]:
        print(" BERHENTI: %s bukan alamat loopback." % o["host"])
        print(" Menyuntik ke perangkat NYATA hanya bekerja bila firmware dibangun")
        print(" dengan MESHTASTIC_ENABLE_FRAME_INJECTION=1, dan firmware sendiri")
        print(" memperingatkan: flag itu 'must never ship enabled' karena siapa pun")
        print(" yang tersambung kabel dapat memalsukan lalu lintas udara.")
        print(" Bila benar-benar paham risikonya, tambahkan --ya.")
        return 3

    iface = None
    if not o["kering"]:
        catat("menyambung ke %s:%s" % (o["host"], o["port"]))
        iface = sambung(o["host"], o["port"])
        if getattr(iface, "localNode", None) is None:
            print("Gagal menyambung ke %s:%s." % (o["host"], o["port"]), file=sys.stderr)
            return 1
        try:
            diri = "!%08x" % iface.myInfo.my_node_num
        except Exception:
            diri = "?"
        catat("tersambung, node tujuan %s" % diri)

    total = 0
    try:
        for nomor, (ket, paket) in enumerate(kiriman, start=1):
            hasil = bongkar(paket)
            catat("%-28s %s %s" % (ket, teks_id(hasil["dari"]),
                                   "kirim" if not o["kering"] else "kering"))
            if not o["kering"]:
                kirim(iface, paket)
            total += 1
            if nomor < len(kiriman) and o["langkah"] > 0:
                time.sleep(o["langkah"])
    finally:
        if iface is not None:
            try:
                iface.close()
            except Exception:
                pass

    print("-" * 62)
    catat("%d paket %s" % (total, "dirangkai saja" if o["kering"] else "dikirim"))
    if not o["kering"]:
        print(" Periksa dampaknya di dasbor bot: http://<host-bot>:9209/dasbor")
        print(" Bila bot tidak bereaksi, lihat catatan [!] di atas - terutama id")
        print(" paket yang terpakai ulang akan dibuang bot sebagai duplikat.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
