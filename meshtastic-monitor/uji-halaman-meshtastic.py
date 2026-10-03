#!/usr/bin/env python3
# ============================================================
# uji-halaman-meshtastic.py - uji render halaman & metrik exporter
# ============================================================
# Menguji exporter-meshtastic.py TANPA menyambung ke node Meshtastic, jadi
# aman dijalankan kapan saja - termasuk saat layanan produksi sedang hidup.
#
# Yang diperiksa:
#   1. Halaman HTML tetap bisa dirender dan memuat semua bagian penting.
#   2. Pewarnaan ambang operasional muncul di nilai yang tepat:
#        kanal  : <25 sehat, 25-40 sedang, 40-50 tinggi, >50 padat
#        air TX : <5 bagus, 5-8 wajar, >8 kelebihan
#        hop    : 0 langsung, 1-2 dekat, 3-4 jauh, >=5 sangat jauh
#   3. Metrik baru meshtastic_node_last_heard_timestamp_seconds terisi sama
#      dengan waktu paket terakhir (epoch), berdampingan dengan metrik umur.
#
# Data node di bawah adalah karangan yang sengaja ditempatkan tepat di tiap
# batas, supaya perubahan ambang yang tidak disengaja langsung ketahuan.
#
# Pakai (dari folder meshtastic-monitor):
#   ./venv/Scripts/python uji-halaman-meshtastic.py
#
# Keluaran HTML ditulis ke .tmp-uji-halaman/tampilan.html di akar repo supaya
# bisa dibuka di peramban. Tidak ada berkas lain yang diubah.
# ============================================================

import http.client
import importlib.util
import os
import sys
import time
import types

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AKAR = os.path.dirname(os.path.abspath(__file__))
BERKAS_EXPORTER = os.path.join(AKAR, "exporter-meshtastic.py")
KELUARAN = os.path.join(AKAR, "..", ".tmp-uji-halaman", "tampilan.html")

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


def muat_exporter():
    """Muat exporter-meshtastic.py sebagai modul (namanya mengandung tanda -)."""
    spec = importlib.util.spec_from_file_location("exporter_meshtastic", BERKAS_EXPORTER)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def node(via, snr=None, hops=None, chan=None, air=None, detik_lalu=60, nama="N"):
    """Satu entri node tiruan; detik_lalu = umur sejak paket terakhir."""
    return {
        "via": via,
        "favorite": via == "lora",
        "long_name": nama,
        "short_name": nama[:3],
        "hw_model": "SEEED_XIAO_S3",
        "role": "CLIENT",
        "battery": 80,
        "voltage": 4.1,
        "chan_util": chan,
        "air_tx": air,
        "uptime": 3600,
        "snr": snr,
        "hops": hops,
        "last": time.time() - detik_lalu,
        "lat": -6.2,
        "lon": 106.8,
        "alt": 20,
        "temp": 30.0,
        "hum": 70.0,
        "press": 1008.0,
    }


class IfaceLoraPalsu:
    """Iface palsu minimal untuk menguji pembacaan setelan radio gateway.

    Hanya bagian yang dipakai kumpulkan() untuk menentukan lantai demodulasi
    SNR yang disediakan; sisanya dibiarkan kosong supaya jalur "tidak terbaca"
    juga ikut teruji.
    """

    def __init__(self, use_preset=True, preset=0, sf=0, bw=0):
        lora = types.SimpleNamespace(use_preset=use_preset, modem_preset=preset,
                                     spread_factor=sf, bandwidth=bw)
        self.localNode = types.SimpleNamespace(
            localConfig=types.SimpleNamespace(lora=lora))
        self.nodes = {}
        self.myInfo = None
        self.metadata = None
        self.ditutup = False

    def getMyNodeInfo(self):
        return None

    def close(self):
        self.ditutup = True


class IfacePalsu:
    """Pengganti TCPInterface untuk uji penjaga koneksi.

    ``nodes`` berisi data untuk beberapa akses pertama saja, lalu kosong -
    meniru socket yang mati sesudah handshake sementara penanda internal
    pustaka meshtastic tetap mengaku tersambung.
    """

    def __init__(self, jumlah_penuh, jumlah_node=3):
        self.sisa_penuh = jumlah_penuh
        self.data = {}
        for i in range(jumlah_node):
            self.data["!%08x" % (i + 1)] = {
                "user": {"longName": "N%d" % i, "shortName": "N%d" % i,
                         "hwModel": "SEEED_XIAO_S3", "role": "CLIENT"},
                "deviceMetrics": {"batteryLevel": 50},
                "position": {},
                "environmentMetrics": {},
                "lastHeard": time.time(),
            }
        self.myInfo = None
        self.metadata = None
        self.ditutup = False

    @property
    def nodes(self):
        if self.sisa_penuh > 0:
            self.sisa_penuh -= 1
            return self.data
        return {}

    def getMyNodeInfo(self):
        return None

    def close(self):
        self.ditutup = True


def main():
    print("=" * 60)
    print(" UJI HALAMAN & METRIK EXPORTER MESHTASTIC (tanpa node asli)")
    print("=" * 60)

    expl = muat_exporter()

    # --- data tiruan: tiap batas ambang diwakili satu node -----------------
    nodes = {
        # Gateway meniru keadaan nyata: firmware melaporkan 101 (bertenaga
        # listrik) dan tegangan di lantai derau ADC (-0.001 V).
        "!00000001": dict(node("diri", snr=None, hops=None, chan=24.9, air=4.9,
                               detik_lalu=1, nama="GATEWAY"),
                          battery=101, voltage=-0.001,
                          long_name="[B-75]MTL|CBT|HOME"),
        "!00000002": node("lora", snr=8.5, hops=0, chan=25.0, air=5.0,
                          detik_lalu=120, nama="MOB-01"),
        "!00000003": node("lora", snr=3.0, hops=2, chan=40.0, air=8.0,
                          detik_lalu=600, nama="MOB-02"),
        "!00000004": node("lora", snr=-2.0, hops=4, chan=50.0, air=9.0,
                          detik_lalu=900, nama="ROUTER"),
        "!00000005": node("lora", snr=None, hops=7, chan=75.0, air=25.0,
                          detik_lalu=1200, nama="JAUH"),
        "!00000006": node("mqtt", snr=None, hops=None, chan=None, air=None,
                          detik_lalu=5000, nama="MQTT-NODE"),
    }
    gateway = {
        "node_id": "!00000001", "uptime": 90000, "reboot_count": 46,
        "nodedb_count": 83, "firmware": "2.7.15.567b8ea", "role": "CLIENT",
        "hw_model": "SEEED_XIAO_S3", "jumlah_node": len(nodes),
        "jumlah_lora": 4, "jumlah_mqtt": 1,
    }

    cuplikan = expl.Cuplikan()
    cuplikan.ganti(nodes, gateway)

    # --- 1. render halaman -------------------------------------------------
    print("\n1. Render halaman HTML")
    html = expl.halaman_html(cuplikan, 10800, "192.168.20.31", 4403, True)
    periksa("halaman dirender", len(html) > 4000, "panjang=%d" % len(html))
    for bagian in ("Meshnode-ID Monitor", "/data.json", "database node",
                   "NODE LEWAT MQTT"):
        periksa("memuat '%s'" % bagian, bagian in html)
    periksa("panah details masih ada", "details[open]>summary::before" in html)

    # --- 2. pewarnaan ambang ----------------------------------------------
    print("\n2. Pewarnaan ambang operasional")
    periksa("legenda ambang tampil", "Ambang yang dipakai halaman ini" in html)
    for kelas in ("a-aman", "a-sedang", "a-tinggi", "a-padat",
                  "hop-0", "hop-1", "hop-2", "hop-3"):
        periksa("kelas .%s terpakai" % kelas, ("class='%s'" % kelas) in html)

    # 24.9 -> sehat, 25.0 -> sedang, 40.0 -> tinggi, 50.0 -> padat (batas atas
    # masuk tingkat berikutnya, sesuai pedoman "mulai 25%").
    baris = expl._baris_node("!00000002", nodes["!00000002"], 10800, time.time())
    periksa("kanal 25.0 pada batas -> sedang", "a-sedang" in baris)
    baris = expl._baris_node("!00000001", nodes["!00000001"], 10800, time.time())
    periksa("kanal 24.9 di bawah batas -> sehat", "a-aman" in baris)
    baris = expl._baris_node("!00000005", nodes["!00000005"], 10800, time.time())
    periksa("kanal 75 -> padat & air 25 -> kelebihan",
            "a-padat" in baris and "kelebihan" in baris)
    periksa("hop 0 -> langsung", "langsung" in expl._baris_node(
        "!00000002", nodes["!00000002"], 10800, time.time()))
    periksa("hop 7 -> sangat jauh", "sangat jauh" in expl._baris_node(
        "!00000005", nodes["!00000005"], 10800, time.time()))
    periksa("nilai kosong tidak diwarnai", expl._sel_ambang(None, "%", 1,
            expl.TANGGA_CHUTIL) == "-")
    periksa("hop kosong tetap '-'", expl._sel_hop(None) == "-")

    # --- 2b. tampilan baterai & tegangan ----------------------------------
    print("\n2b. Baterai 101 dan tegangan derau")
    # "101" tetap muncul di keterangan (menyebut kode firmware), yang penting
    # TIDAK ada "101%" yang terbaca sebagai persentase baterai.
    periksa("baterai 101 -> 'charge', bukan 101%",
            "charge" in expl._sel_baterai(101) and "101%" not in expl._sel_baterai(101))
    periksa("baterai 100 tetap angka persen", expl._sel_baterai(100) == "100%")
    periksa("baterai 45 tetap angka persen", expl._sel_baterai(45) == "45%")
    periksa("baterai kosong -> '-'", expl._sel_baterai(None) == "-")
    periksa("tegangan -0.001 -> '-' (tidak '-0.00 V')",
            "0.00" not in expl._sel_tegangan(-0.001))
    periksa("tegangan 0 -> '-'", "0.00" not in expl._sel_tegangan(0))
    periksa("tegangan 4.139 tetap angkanya", expl._sel_tegangan(4.139) == "4.14 V")
    periksa("halaman memuat lencana charge", "class='charge'" in html)
    periksa("halaman menjelaskan arti charge di legenda",
            "tersambung listrik/USB" in html)
    periksa("halaman TIDAK memuat '101%'", "101%" not in html)

    # --- 3. metrik baru ----------------------------------------------------
    print("\n3. Metrik meshtastic_node_last_heard_timestamp_seconds")
    pengumpul = expl.PengumpulMesh(cuplikan, 10800)
    # Nilai label disimpan sebagai kamus, jadi diambil lewat nama labelnya.
    teks = {}
    for famili in pengumpul.collect():
        for metrik in famili.samples:
            # Sebagian keluarga (mis. kesehatan gateway) tidak punya label
            # node_id, jadi kuncinya dibuat dari semua label yang ada.
            kunci = metrik.labels.get("node_id") or "(gateway)"
            teks.setdefault(famili.name, {})[kunci] = metrik.value

    periksa("keluarga metrik ada", "meshtastic_node_last_heard_timestamp_seconds" in teks)
    umur = teks.get("meshtastic_node_last_heard_seconds", {})
    ts = teks.get("meshtastic_node_last_heard_timestamp_seconds", {})
    periksa("jumlah label sama dengan metrik umur", len(ts) == len(umur),
            "ts=%d umur=%d" % (len(ts), len(umur)))
    # timestamp + umur harus kembali ke waktu sekarang: timestamp adalah
    # kapan paket terakhir datang, umur adalah jarak dari sekarang ke situ.
    jumlah = ts["!00000002"] + umur["!00000002"]
    periksa("timestamp + umur == waktu sekarang (selisih <2s)",
            abs(jumlah - time.time()) < 2, "selisih=%.1f" % (jumlah - time.time()))
    periksa("semua node berwaktu terdengar punya timestamp",
            len(ts) == 6, "jumlah=%d" % len(ts))
    periksa("timestamp lebih besar dari umur",
            ts["!00000002"] > umur["!00000002"])

    # --- 4. penjaga "hidup tetapi buta" ------------------------------------
    # Inilah penyebab halaman produksi kosong pada 28 Sep 2026 sore: socket
    # mati setelah handshake, pustaka meshtastic tidak membersihkan penandanya,
    # dan penjaga lama tidak menyala karena pembacaan PERTAMA sudah kosong.
    print("\n4. Penjaga 'hidup tetapi buta'")
    asli_tcp = expl.TCPInterface
    asli_env = dict(os.environ)
    try:
        os.environ["MESH_TUNGGU_AWAL"] = "1"
        os.environ["MESH_KOSONG_MAKS"] = "3"
        os.environ.pop("MESH_BUTA_TUNGGU", None)
        expl.EXPORTER_UP.set(1)

        # (a) handshake sempat melihat isi database, lalu semua pembacaan kosong.
        palsu = IfacePalsu(3)
        expl.TCPInterface = lambda **kw: palsu
        pesan = ""
        try:
            expl.sambung("127.0.0.1", 4403, 0.01, expl.Cuplikan())
        except RuntimeError as e:
            pesan = str(e)
        periksa("kosong setelah handshake -> berhenti & sambung ulang",
                bool(pesan), pesan or "tidak berhenti")
        periksa("up turun ke 0 saat buta", expl.EXPORTER_UP._value.get() == 0,
                "up=%.0f" % expl.EXPORTER_UP._value.get())
        periksa("interface ditutup sebelum menyambung ulang", palsu.ditutup)

        # (b) sejak awal tidak ada isi: penjaga tetap menyala setelah tenggat
        # MESH_BUTA_TUNGGU, jadi gelandangan tidak diam menunggu selamanya.
        # Handshake sengaja dimatikan supaya yang diuji memang penjaga kedua.
        os.environ["MESH_TUNGGU_AWAL"] = "0"
        os.environ["MESH_BUTA_TUNGGU"] = "1"
        palsu2 = IfacePalsu(0)
        expl.TCPInterface = lambda **kw: palsu2
        pesan2 = ""
        try:
            expl.sambung("127.0.0.1", 4403, 0.05, expl.Cuplikan())
        except RuntimeError as e:
            pesan2 = str(e)
        periksa("tanpa isi sejak awal -> tetap menyambung ulang",
                bool(pesan2), pesan2 or "tidak berhenti")
        periksa("tercatat sebagai 'tidak ada data dari gateway'",
                pesan2 == "gateway berhenti mengirim data", pesan2)
    finally:
        expl.TCPInterface = asli_tcp
        os.environ.clear()
        os.environ.update(asli_env)

    # --- 5. umur data & penanda up saat loop tersangkut --------------------
    # Halaman dilayani thread HTTP terpisah, jadi umur data dihitung saat
    # di-scrape - bukan oleh loop pengumpul.
    print("\n5. Umur data & penanda up")
    segar = expl.PengumpulMesh(cuplikan, 10800, 90)
    teks_segar = {f.name: [m.value for m in f.samples] for f in segar.collect()}
    periksa("up=1 saat data baru", expl.EXPORTER_UP._value.get() == 1)
    umur_metrik = teks_segar.get("meshtastic_cuplikan_umur_seconds", [])
    periksa("metrik umur cuplikan ada", len(umur_metrik) == 1)
    periksa("umur data baru < 5 detik", umur_metrik and umur_metrik[0] < 5,
            "umur=%.1f" % (umur_metrik[0] if umur_metrik else -1))
    periksa("data.json memuat umur_data_seconds",
            "umur_data_seconds" in expl.data_json(cuplikan, 10800, "h", 4403))

    basi = expl.Cuplikan()
    basi.ganti(nodes, gateway)
    basi._sekarang = time.time() - 500          # loop tersangkut 8 menit
    # collect() berupa generator: badan barunya jalan saat ditelusuri, jadi
    # harus dihabiskan (persis seperti prometheus_client saat scrape).
    list(expl.PengumpulMesh(basi, 10800, 90).collect())
    periksa("up=0 saat cuplikan basi (loop tersangkut)",
            expl.EXPORTER_UP._value.get() == 0,
            "up=%.0f" % expl.EXPORTER_UP._value.get())
    periksa("umur basi ikut dilaporkan",
            expl.data_json(basi, 10800, "h", 4403)["umur_data_seconds"] > 400)

    # --- 6. kerapian tabel & lencana ---------------------------------------
    # Kerapian ini bukan selera: tabel 14 kolom lebih lebar dari layar sehingga
    # seluruh halaman ikut bergeser ke kanan, dan "6.5 dB" pecah dua baris.
    # Uji di bawah menjaga hasil rapinya.
    print("\n6. Kerapian tabel & lencana")
    periksa("tiap tabel punya kotak gulir sendiri",
            html.count('<div class="gulir">') == 4,
            "jumlah=%d" % html.count('<div class="gulir">'))
    # Dihitung dari kepala selnya ("<th>" dan "<th "), BUKAN dari "<th" —
    # pola longgar itu ikut menghitung tag <thead> yang membungkusnya.
    jumlah_kolom = html.count("<th>") + html.count("<th ")
    periksa("kepala tabel dibagi bersama (3x12 + 6 kolom paket)",
            jumlah_kolom == 42, "jumlah=%d" % jumlah_kolom)
    periksa("kolom dibagi 12 setelah perangkat & tegangan digabung",
            "Role / Perangkat" not in html and "Tegangan</th>" not in html)
    periksa("header tabel lengket", "position:sticky" in html)
    periksa("angka rata kanan (kelas num)", html.count("class='num'") >= 20)
    periksa("lencana jalur lora & mqtt ada",
            "class='via via-lora'" in html and "class='via via-mqtt'" in html)
    baris_gw = expl._baris_node("!00000001", nodes["!00000001"], 10800, time.time())
    periksa("baris node 12 sel", baris_gw.count("<td") == 12,
            "jumlah=%d" % baris_gw.count("<td"))
    periksa("tegangan derau tidak ditulis (tak ada 0.00 V)", "0.00" not in baris_gw)
    periksa("lencana charge tetap ada tanpa tegangan", "class='charge'" in baris_gw)
    baris_mob = expl._baris_node("!00000002", nodes["!00000002"], 10800, time.time())
    periksa("tegangan sungguhan tetap ditulis", "4.10 V" in baris_mob,
            baris_mob[:80])
    periksa("perangkat ikut ke sel nama", "SEEED_XIAO_S3" in baris_mob)

    # --- 7. urutan online/offline & telemetri ------------------------------
    # Permintaan pemilik halaman: node offline ditaruh paling bawah, dan data
    # telemetri (suhu/kelembapan/tekanan/ketinggian/uptime) ditampilkan bila
    # perangkat memang mengirimkannya.
    print("\n7. Urutan online/offline & telemetri")
    n7 = {
        "!00000011": dict(node("lora", snr=7.0, hops=0, detik_lalu=10,
                               nama="ONLINE-A"),
                          temp=28.5, hum=65.0, press=1010.0, alt=35.0,
                          uptime=7200),
        # Sengaja SAMA-SAMA hops 0 supaya keduanya masuk tabel "tersambung
        # langsung". Kalau berbeda tabel, uji urutan di bawah tidak berarti.
        "!00000012": dict(node("lora", snr=2.0, hops=0, detik_lalu=99999,
                               nama="OFFLINE-B"),
                          temp=None, hum=None, press=None, alt=None,
                          uptime=None),
    }
    c7 = expl.Cuplikan()
    c7.ganti(n7, gateway)
    h7 = expl.halaman_html(c7, 10800, "h", 4403, True)
    periksa("node offline diurutkan ke bawah",
            h7.index("ONLINE-A") < h7.index("OFFLINE-B"),
            "online=%d offline=%d" % (h7.index("ONLINE-A"), h7.index("OFFLINE-B")))
    periksa("ringkasan memakai kata 'node', bukan 'baris'",
            "&mdash; 2 node</summary>" in h7)
    periksa("suhu, kelembapan, tekanan tampil bila ada",
            "28.5 \u00b0C" in h7 and "65.0 % RH" in h7 and "1010 hPa" in h7)
    periksa("ketinggian tampil bila ada", "35 m" in h7)
    periksa("uptime perangkat tampil bila ada", "up 2j 0m" in h7)
    baris_b = expl._baris_node("!00000012", n7["!00000012"], 10800, time.time())
    periksa("node tanpa telemetri tidak diisi tanda '-' bertumpuk",
            "RH" not in baris_b and "hPa" not in baris_b and "up " not in baris_b,
            baris_b[:120])

    # --- 8. logo & ikon tab ------------------------------------------------
    # Logo dilayani sebagai berkas terpisah (bukan disisipkan ke HTML), supaya
    # halaman yang menyegar tiap 5 detik tidak mengunduh ulang gambarnya.
    print("\n8. Logo & ikon tab")
    gambar = expl.baca_gambar()
    periksa("berkas logo & favicon terbaca",
            set(gambar) == {"/logo.png", "/favicon.png"}, str(sorted(gambar)))
    periksa("favicon lebih ringan daripada logo",
            len(gambar["/favicon.png"][0]) < len(gambar["/logo.png"][0]),
            "favicon=%d logo=%d" % (len(gambar["/favicon.png"][0]),
                                    len(gambar["/logo.png"][0])))
    periksa("logo tampil di samping judul", 'class="logo" src="/logo.png"' in html)
    periksa("ikon tab dipasang", 'rel="icon"' in html and "/favicon.png" in html)
    html_polos = expl.halaman_html(cuplikan, 10800, "h", 4403, True, False)
    periksa("tanpa berkas logo halaman tetap wajar",
            "/logo.png" not in html_polos and "Meshnode-ID Monitor" in html_polos)

    # Jalur gambar diuji sungguhan: server sementara di loopback, lalu ditutup.
    srv = expl.jalankan_web("127.0.0.1", 0, cuplikan, 10800, "h", 4403, gambar)
    try:
        port = srv.server_address[1]
        konek = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        konek.request("GET", "/logo.png")
        jawab = konek.getresponse()
        isi = jawab.read()
        periksa("rute /logo.png melayani PNG + header cache",
                jawab.status == 200
                and jawab.getheader("Content-Type") == "image/png"
                and "max-age" in (jawab.getheader("Cache-Control") or ""),
                "status=%s tipe=%s" % (jawab.status, jawab.getheader("Content-Type")))
        periksa("isi /logo.png sama dengan berkas di disk",
                isi == gambar["/logo.png"][0])
        # Halaman tetap dilayani di jalur yang sama seperti sebelumnya.
        konek.request("GET", "/")
        jawab = konek.getresponse()
        periksa("halaman utama tetap dilayani",
                jawab.status == 200 and b"Meshnode-ID Monitor" in jawab.read())
        konek.close()
    finally:
        srv.shutdown()

    # --- 9. status buka/tutup bagian diingat ------------------------------
    # Halaman menyegar sendiri tiap 5 detik; tanpa diingat, bagian yang baru
    # dibuka menutup sendiri di penyegaran berikutnya.
    print("\n9. Status buka/tutup bagian diingat")
    periksa("tiap bagian punya kelas .bagian", html.count('class="bagian"') == 3,
            "jumlah=%d" % html.count('class="bagian"'))
    for id_bagian in ("bagian-gateway", "bagian-ragu", "bagian-mqtt"):
        periksa("id %s ada" % id_bagian, ('id="%s"' % id_bagian) in html)
    periksa("status disimpan di peramban",
            "localStorage" in html and "'toggle'" in html)

    # --- 10. kotak saring di atas tabel MQTT & kata saring tersimpan ------
    # Permintaan pemilik halaman: saringan harus bisa dipakai tepat di atas
    # tabel MQTT yang panjang (105 node), dan katanya tetap tersimpan saat
    # halaman menyegar sendiri tiap 5 detik.
    print("\n10. Kotak saring di atas tabel MQTT")
    periksa("kotak saring utama tetap ada", 'id="saring" data-saring' in html)
    periksa("ada kotak saring kedua di atas tabel MQTT",
            'id="saring-mqtt" data-saring' in html)
    periksa("keduanya berbagi satu saringan (2 kotak, 2 hasil)",
            html.count("data-saring placeholder") == 2
            and html.count('class="hasil"') == 2,
            "kotak=%d hasil=%d" % (html.count("data-saring placeholder"),
                                   html.count('class="hasil"')))
    # Kotak harus benar-benar SEBELUM baris tabel MQTT-nya, bukan sesudahnya.
    periksa("kotak MQTT mendahului baris tabel MQTT",
            html.index('id="saring-mqtt"') < html.index("MQTT-NODE"))
    periksa("placeholder menyebut jumlah node MQTT",
            "saring 1 node MQTT" in html)
    # Saringan tersimpan di localStorage, bukan hanya di #hash: #hash mudah
    # hilang (mis. alamat diketik ulang), sedangkan penyegaran halaman ini
    # tidak boleh membuang kata saringan yang sudah diketik.
    periksa("kata saringan disimpan di localStorage",
            "meshid-saring-1" in html and "setItem(KUNCI_SARING" in html)
    periksa("simpanan dipakai saat halaman dimuat",
            "|| bacaSaring()" in html)
    periksa("kotak yang sedang dipakai diingat untuk fokus",
            "meshid-saring-fokus" in html and "sessionStorage" in html)
    periksa("fokus dikembalikan setelah menyegar",
            "aktif.focus()" in html and "setSelectionRange" in html)

    # --- 11. meter sinyal tiap node ---------------------------------------
    # Diukur dari apa yang dipakai aplikasi resmi Meshtastic: SNR relatif
    # terhadap LANTAI DEMODULASI preset, bukan kuat-lemahnya pancaran. Angka
    # tabel di bawah disalin dari tabel lintas-platform aplikasi Android & Apple
    # (Meshtastic-Android ChannelOption.kt, Meshtastic-Apple
    # ModemPresetSnrLimitTests.swift) - uji ini yang menahan agar tidak berubah
    # diam-diam, karena angka yang salah membuat tautan sehat dinilai buruk.
    print("\n11. Meter sinyal (mengikuti meter resmi Meshtastic)")
    for nama, lantai in (("LONG_SLOW", -20.0), ("LONG_FAST", -17.5),
                         ("LONG_MODERATE", -17.5), ("MEDIUM_SLOW", -15.0),
                         ("MEDIUM_FAST", -12.5), ("LONG_TURBO", -12.5),
                         ("SHORT_SLOW", -10.0), ("SHORT_FAST", -7.5),
                         ("SHORT_TURBO", -7.5)):
        periksa("lantai preset %s = %.1f dB" % (nama, lantai),
                expl.lantai_snr(preset=nama) == lantai,
                "dapat=%s" % expl.lantai_snr(preset=nama))
    periksa("enum mentah 0 -> LONG_FAST (-17.5 dB)",
            expl.nama_preset(0) == "LONG_FAST" and expl.lantai_snr(preset=0) == -17.5)
    periksa("enum mentah 1 -> LONG_SLOW (-20 dB)",
            expl.nama_preset(1) == "LONG_SLOW" and expl.lantai_snr(preset=1) == -20.0)
    periksa("preset tak dikenal jatuh ke lantai bawaan",
            expl.lantai_snr(preset="ENTAH") == expl.BAWAAN_LANTAI_SNR)
    periksa("setelan kustom dihitung dari SF (SF12 -> -20 dB)",
            expl.lantai_snr(sf=12, bw=125) == -20.0)
    periksa("SF7 -> -7.5 dB", expl.lantai_snr(sf=7, bw=250) == -7.5)
    periksa("bandwidth 500 kHz menaikkan lantai 5 dB",
            expl.lantai_snr(sf=11, bw=500) == -12.5)

    print("\n11b. Ambang mutu (margin terhadap lantai)")
    L = -17.5
    periksa("margin +1 dB -> Baik (3 batang)", expl.mutu_sinyal(L + 1, L) == 3)
    periksa("tepat di lantai -> Cukup (2 batang)", expl.mutu_sinyal(L, L) == 2)
    periksa("margin -5.4 dB -> masih Cukup", expl.mutu_sinyal(L - 5.4, L) == 2)
    periksa("margin -5.5 dB -> Buruk (1 batang)", expl.mutu_sinyal(L - 5.5, L) == 1)
    periksa("margin -7.5 dB -> masih Buruk", expl.mutu_sinyal(L - 7.5, L) == 1)
    periksa("margin -7.6 dB -> Nihil (0 batang)", expl.mutu_sinyal(L - 7.6, L) == 0)
    periksa("SNR kosong -> None, bukan dianggap Nihil",
            expl.mutu_sinyal(None, L) is None)
    # Inilah alasan lantai preset harus dibaca dari gateway: SNR yang SAMA bisa
    # berarti "Baik" di satu preset dan "Buruk" di preset lain.
    periksa("SNR -15 Baik di LongSlow (-20 dB)", expl.mutu_sinyal(-15, -20.0) == 3)
    periksa("SNR -15 Buruk di ShortFast (-7.5 dB)", expl.mutu_sinyal(-15, -7.5) == 1)

    print("\n11c. Meter di halaman & /data.json")
    n11 = {
        "!00000021": node("lora", snr=-10.0, hops=0, detik_lalu=10, nama="DEKAT"),
        "!00000022": node("lora", snr=-26.0, hops=1, detik_lalu=10, nama="JAUH"),
        "!00000023": node("lora", snr=None, hops=2, detik_lalu=10, nama="TANPA-SNR"),
        "!00000024": node("mqtt", snr=None, hops=None, detik_lalu=10, nama="LEWAT-INTERNET"),
        "!00000025": node("lora", snr=-19.5, hops=1, detik_lalu=10, nama="TENGAH"),
    }
    c11 = expl.Cuplikan()
    c11.ganti(n11, dict(gateway, preset="LONG_FAST", lantai_snr=-17.5, kustom=False))
    h11 = expl.halaman_html(c11, 10800, "h", 4403, True)
    baris11 = {}
    for nid in n11:
        baris11[nid] = expl._baris_node(nid, n11[nid], 10800, time.time(), "", -17.5)
    periksa("SNR di atas lantai -> 3 batang menyala + 'Baik'",
            baris11["!00000021"].count("class='nyala'") == 3
            and "Baik" in baris11["!00000021"], baris11["!00000021"][:200])
    periksa("SNR 2 dB di bawah lantai -> 2 batang + 'Cukup'",
            baris11["!00000025"].count("class='nyala'") == 2
            and "Cukup" in baris11["!00000025"])
    periksa("SNR 8.5 dB di bawah lantai -> 0 batang + 'Nihil'",
            baris11["!00000022"].count("class='nyala'") == 0
            and "Nihil" in baris11["!00000022"])
    periksa("angka SNR mentah tetap dicetak", "-10.0 dB" in baris11["!00000021"])
    periksa("node tanpa SNR tetap '-', bukan meter Nihil",
            "nyala" not in baris11["!00000023"] and "Nihil" not in baris11["!00000023"])
    periksa("node jalur MQTT tidak diberi meter",
            "nyala" not in baris11["!00000024"]
            and "lewat internet" in baris11["!00000024"])
    periksa("meter tetap 12 sel", baris11["!00000021"].count("<td") == 12)
    periksa("legenda menjelaskan meter", "Meter sinyal" in h11
            and "Cara membacanya" in h11)
    periksa("legenda menuliskan preset & lantai yang dipakai",
            "LONG_FAST" in h11 and "-17.5 dB" in h11)
    periksa("kepala halaman menyebut preset gateway",
            "preset <span class=\"mono\">LONG_FAST</span>" in h11)
    periksa("kepala tabel memuat kolom Sinyal (SNR)",
            "<th class='sinyal'>Sinyal (SNR)</th>" in h11)
    # Kolom sinyal TIDAK memakai kelas .num: isinya meter, bukan angka, dan
    # rata kanan membuatnya menempel ke kolom Hop di sebelahnya.
    periksa("kolom sinyal rata kiri, bukan kolom angka",
            "<td class='sinyal'>" in baris11["!00000021"])
    periksa("jarak kolom sinyal dilebihkan di CSS",
            "td.sinyal{white-space:nowrap;padding-right:20px}" in h11)
    # Angka SNR harus berada DI DALAM pembungkus .meter, supaya jaraknya diatur
    # gap yang sama dengan batang dan kata mutunya - bukan menempel seperti
    # "Baik6.2 dB".
    akhir_sinyal = baris11["!00000021"].split("<td class='sinyal'>")[1].split("</td>")[0]
    periksa("angka SNR ada di dalam pembungkus meter",
            "<span class='db'>-10.0 dB</span>" in akhir_sinyal
            and akhir_sinyal.rstrip().endswith("</span></span>"),
            akhir_sinyal)
    periksa("mutu dan angka dipisah titik tengah lewat CSS",
            ".meter .db::before{content:\"\\00b7\"" in h11)
    d11 = expl.data_json(c11, 10800, "h", 4403)
    mutu11 = {x["node_id"]: x["mutu_sinyal"] for x in d11["node"]}
    periksa("data.json memuat mutu_sinyal per node",
            mutu11["!00000021"] == 3 and mutu11["!00000025"] == 2
            and mutu11["!00000022"] == 0, str(mutu11))
    periksa("data.json menandai node MQTT tanpa mutu", mutu11["!00000024"] is None)
    periksa("data.json memuat lantai gateway",
            d11["kesehatan_gateway"]["lantai_snr"] == -17.5)

    print("\n11d. Preset & lantai dibaca dari gateway")
    cupl = expl.Cuplikan()
    expl.kumpulkan(IfaceLoraPalsu(), cupl)
    gw11 = cupl.baca()[1]
    periksa("preset dibaca dari setelan LoRa", gw11["preset"] == "LONG_FAST",
            str(gw11.get("preset")))
    periksa("lantai mengikuti tabel preset", gw11["lantai_snr"] == -17.5)
    periksa("preset bukan setelan kustom", gw11["kustom"] is False)
    cupl2 = expl.Cuplikan()
    expl.kumpulkan(IfaceLoraPalsu(use_preset=False, preset=0, sf=12, bw=125), cupl2)
    gw12 = cupl2.baca()[1]
    periksa("setelan kustom ditaksir dari SF/BW",
            gw12["kustom"] is True and gw12["lantai_snr"] == -20.0,
            str(gw12.get("lantai_snr")))
    cupl3 = expl.Cuplikan()
    expl.kumpulkan(IfacePalsu(3), cupl3)
    gw13 = cupl3.baca()[1]
    periksa("setelan tak terbaca -> lantai bawaan, tidak error",
            gw13["lantai_snr"] == expl.BAWAAN_LANTAI_SNR
            and gw13["preset"] is None, str(gw13.get("preset")))
    h13 = expl.halaman_html(cupl3, 10800, "h", 4403, True)
    periksa("halaman tanpa preset tetap wajar",
            "tidak terbaca" in h13 and "Meter sinyal" in h13)
    periksa("lantai yang diasumsikan ditandai apa adanya",
            "diasumsikan" in h13)

    # --- 12. tab menu: tabel & peta --------------------------------------
    # Permintaan pemilik: tab menu yang menampilkan peta node live seperti
    # meshmap.net, diklik per node untuk data popup + tautan lacak otomatis.
    print("\n12. Tab Tabel / Peta dan panel peta")
    periksa("bilah tab ada", 'class="tab"' in html and 'role="tablist"' in html)
    periksa("dua tab: tabel & peta",
            'data-tab="tabel"' in html and 'data-tab="peta"' in html)
    periksa("panel tabel & panel peta ada",
            'id="panel-tabel"' in html and 'id="panel-peta"' in html)
    periksa("panel peta disembunyikan secara bawaan",
            '<div id="panel-peta" class="panel" hidden>' in html)
    periksa("tab yang dipakai diingat di peramban",
            "meshid-tab-1" in html and "setItem(KUNCI" in html)
    periksa("tab peta mematikan penyegaran halaman yang merusak peta",
            'meta[http-equiv="refresh"]' in html and "removeChild(m)" in html)
    periksa("peta menyegar lewat /data.json tanpa memuat ulang halaman",
            "setInterval(muatPeta,5000)" in html)
    # Tab CSS hidup di gaya_peta; tiap panel disembunyikan lewat atribut hidden.
    periksa("CSS tab & panel terpasang",
            ".tab-tombol.aktif" in html and ".panel[hidden]{display:none}" in html)
    for elemen in ("peta-kanvas", "peta-pas", "peta-segar", "peta-ringkas",
                   "peta-galat"):
        periksa("panel peta punya #%s" % elemen, ('id="%s"' % elemen) in html)
    for kunci_warna in ("w-hijau", "w-biru", "w-abu", "w-merah"):
        periksa("kunci warna .%s ada" % kunci_warna,
                ('.%s{' % kunci_warna) in html)
    # Panel peta TIDAK boleh menambah kotak gulir / bagian details, kalau tidak
    # hitungan langkah 6 dan 9 di atas ikut berubah.
    periksa("panel peta tidak mengubah jumlah kotak gulir",
            html.count('<div class="gulir">') == 4)
    periksa("panel peta tidak menambah bagian details",
            html.count('class="bagian"') == 3)
    periksa("tidak ada placeholder template yang tersisa", "%(" not in html)

    print("\n12b. Peta memuat Leaflet secara malas (lazy)")
    # Pustaka peta hanya diunduh saat tab Peta benar-benar dibuka: halaman tabel
    # yang menyegar tiap 5 detik tidak boleh ikut mengunduh 140 KB tiap kali.
    periksa("Leaflet tidak dipasang sebagai <script src> di HTML",
            '<script src=' not in html)
    periksa("URL Leaflet ada di skrip (dimuat saat dibutuhkan)",
            "unpkg.com/leaflet" in html)
    periksa("skrip menyuntikkan tag script sendiri",
            "document.createElement('script')" in html
            and "js.onload" in html and "js.onerror" in html)
    periksa("basemap OpenStreetMap dipakai",
            "tile.openstreetmap.org" in html)

    print("\n12c. Popup node + tautan lacak otomatis")
    # Inti permintaan: klik node -> popup data node, dan di dalamnya tautan
    # OTOMATIS ke /lacak/<node_id> - dibangun dari id node, bukan diketik manual.
    periksa("tautan lacak dibentuk dari id node",
            "'/lacak/'+encodeURIComponent(n.node_id)" in html)
    periksa("popup memuat tombol 'Lacak node ini'",
            "Lacak node ini" in html)
    periksa("popup menampilkan id, sinyal, hop, baterai, posisi, perangkat",
            all(x in html for x in
                ("popup-id", "popup-tabel", "Sinyal", "Hop", "Baterai",
                 "Posisi", "Ketinggian", "Perangkat")))
    periksa("popup punya tombol 'Tengahin ke peta'",
            "tombol-tengah" in html and "Tengahin ke peta" in html)
    periksa("penanda dibedakan menurut status & jalur",
            "fillColor:warna(n)" in html and "circleMarker" in html)
    periksa("node tanpa koordinat dilaporkan, tidak dipetakan",
            "node tanpa koordinat tidak dipetakan" in html)
    # Bug yang terbukti di produksi: peta menyegar tiap 5 detik dan membersihkan
    # lapisannya, sehingga popup yang sedang terbuka (beserta tautan "Lacak node
    # ini") menutup sendiri beberapa detik sesudah node diklik - terbaca sebagai
    # "menu lacak hilang". Penyegaran sekarang MEMPERBARUI penanda di tempat.
    print("\n12d. Popup tidak boleh tertutup oleh penyegaran 5 detik")
    periksa("lapisan peta tidak dibersihkan saat menyegar",
            "clearLayers" not in expl.SKRIP_PETA and "clearLayers" not in html,
            "masih ada clearLayers()")
    periksa("penanda yang ada diperbarui di tempat",
            "mar.setLatLng(" in html and "mar.setPopupContent(popup(n))" in html)
    periksa("penanda disimpan per id node", "PENANDA[n.node_id]=mar" in html)
    periksa("penanda node yang hilang baru dibuang",
            "LAPISAN.removeLayer(PENANDA[id])" in html)
    # Isi popup diganti tiap 5 detik, jadi tombol tidak boleh memakai onclick
    # per tombol (ikutt lenyap bersama isi lamanya). Pendengar ditaruh di
    # pembungkus popup yang tidak ikut diganti.
    periksa("tombol 'Tengahin' membawa data-node, bukan onclick",
            "class=\"tombol-tengah\" data-node=" in html
            and "onclick=function(){ PETA.setView" not in html)
    periksa("pendengar tombol dipasang di pembungkus popup",
            "ev.popup.getElement()" in html
            and "wadah.addEventListener('click'" in html
            and "__tengahAda" in html)

    # --- 13. halaman lacak per node (/lacak/<id>) -------------------------
    print("\n13. Halaman lacak /lacak/<node_id>")
    hlm = expl.halaman_lacak(cuplikan, 10800, "h", 4403, "!00000002", True)
    periksa("node yang ada -> halaman dibuat", hlm is not None)
    periksa("judul memuat nama node", "MOB-01" in hlm)
    periksa("halaman menyorot node (PETA_SOROT)",
            '"!00000002"' in hlm and "PETA_AUTO=true" in hlm)
    periksa("halaman memuat peta & panel rincian",
            'id="peta-kanvas"' in hlm and 'id="lacak-rincian"' in hlm)
    periksa("halaman punya jalan kembali ke monitor node",
            'href="/"' in hlm and "Kembali ke monitor node" in hlm)
    periksa("halaman lacak tanpa placeholder tersisa", "%(" not in hlm)
    periksa("node tak dikenal -> None (pemanggil jawab 404)",
            expl.halaman_lacak(cuplikan, 10800, "h", 4403, "!mati", True) is None)
    # Id node datang dari URL, jadi WAJIB di-escape sebelum ditempel ke HTML.
    periksa("_esc menutup tag berbahaya",
            "<" not in expl._esc("<script>alert(1)</script>")
            and "&lt;script&gt;" in expl._esc("<script>"))
    h404 = expl.halaman_tidak_ada("<script>alert(1)</script>")
    periksa("404 meng-escape id node dari URL",
            "<script>alert" not in h404 and "&lt;script&gt;" in h404)

    # --- 14. rute /lacak lewat server sungguhan ---------------------------
    print("\n14. Rute /lacak lewat server")
    srv2 = expl.jalankan_web("127.0.0.1", 0, cuplikan, 10800, "h", 4403, gambar)
    try:
        port2 = srv2.server_address[1]
        konek2 = http.client.HTTPConnection("127.0.0.1", port2, timeout=5)
        konek2.request("GET", "/lacak/!00000002")
        jawab2 = konek2.getresponse()
        isi2 = jawab2.read().decode("utf-8", "replace")
        periksa("/lacak/<id> node ada -> 200", jawab2.status == 200,
                "status=%s" % jawab2.status)
        periksa("isinya halaman lacak node itu",
                "MOB-01" in isi2 and 'id="peta-kanvas"' in isi2)
        konek2.request("GET", "/lacak/!tidakada")
        jawab3 = konek2.getresponse()
        isi3 = jawab3.read().decode("utf-8", "replace")
        periksa("/lacak/<id> node tak ada -> 404", jawab3.status == 404,
                "status=%s" % jawab3.status)
        periksa("404 menjelaskan sebabnya", "tidak ditemukan" in isi3)
        # Percobaan injeksi lewat alamat: id node harus tampil ter-escape.
        konek2.request("GET", "/lacak/%3Cscript%3Ealert(1)%3C/script%3E")
        jawab4 = konek2.getresponse()
        isi4 = jawab4.read().decode("utf-8", "replace")
        periksa("id jahat di URL tidak jadi <script> mentah",
                "<script>alert" not in isi4, isi4[:120])
        # Halaman utama & data.json tetap seperti semula.
        konek2.request("GET", "/")
        jawab5 = konek2.getresponse()
        isi5 = jawab5.read().decode("utf-8", "replace")
        periksa("halaman utama tetap memuat tab peta",
                jawab5.status == 200 and 'data-tab="peta"' in isi5)
        konek2.close()
    finally:
        srv2.shutdown()

    # --- 15. failover gateway cadangan (MESH_HOST_CADANGAN) ---------------
    print("\n15. Failover gateway cadangan")
    periksa("daftar_tujuan: utama dulu, cadangan dipisah koma",
            expl.daftar_tujuan("utama", "cad1,cad2") == ["utama", "cad1", "cad2"])
    periksa("daftar_tujuan: spasi juga diterima",
            expl.daftar_tujuan("a", "b c") == ["a", "b", "c"])
    periksa("daftar_tujuan: alamat kembar dibuang",
            expl.daftar_tujuan("a", "a,b,a") == ["a", "b"])
    periksa("daftar_tujuan: tanpa cadangan = satu tujuan",
            expl.daftar_tujuan("a", "") == ["a"])
    periksa("_alamat menerima teks (pemakaian lama)",
            expl._alamat("192.168.20.31") == "192.168.20.31")
    sumber = expl.SumberGateway("utama", ["cad"])
    periksa("_alamat menerima callable (host_aktif)",
            expl._alamat(sumber.host_aktif) == "utama")
    sumber.pindah("cad")
    periksa("host_aktif berpindah ke cadangan",
            expl._alamat(sumber.host_aktif) == "cad")
    periksa("metrik cadangan menyala saat pakai cadangan",
            expl.EXPORTER_CADANGAN._value.get() == 1)
    sumber.pindah("utama")
    periksa("metrik cadangan padam saat kembali ke utama",
            expl.EXPORTER_CADANGAN._value.get() == 0)
    # Halaman & data.json harus menampilkan gateway yang SEDANG dibaca, bukan
    # yang dikonfigurasi - itulah gunanya host_aktif yang bisa berubah.
    d_aktif = expl.data_json(cuplikan, 10800, sumber.host_aktif, 4403)
    periksa("data.json menampilkan gateway aktif",
            d_aktif["gateway"]["host"] == "utama")
    h_aktif = expl.halaman_html(cuplikan, 10800, sumber.host_aktif, 4403, True)
    periksa("halaman menampilkan gateway aktif", "utama:4403" in h_aktif)
    sumber.pindah("cad")
    h_cad = expl.halaman_html(cuplikan, 10800, sumber.host_aktif, 4403, True)
    periksa("halaman ikut berpindah setelah failover", "cad:4403" in h_cad)
    sumber.pindah("utama")

    # main() harus benar-benar bergilir utama -> cadangan -> utama. Sambung,
    # server web, dan jeda dipalsukan supaya uji ini tidak menyentuh jaringan
    # dan tidak menunggu 5 detik per perpindahan.
    urutan = []

    def sambung_palsu(host, port, interval, cuplikan):
        urutan.append(host)
        if len(urutan) >= 4:
            raise KeyboardInterrupt
        raise RuntimeError("palsu: gateway mati")

    asli_sambung = expl.sambung
    asli_web = expl.jalankan_web
    asli_sleep = expl.time.sleep
    expl.sambung = sambung_palsu
    expl.jalankan_web = lambda *a, **k: None
    expl.time.sleep = lambda *a, **k: None
    os.environ["MESH_HOST"] = "utama"
    os.environ["MESH_HOST_CADANGAN"] = "cad1, cad2"
    try:
        kode = expl.main()
    finally:
        expl.sambung = asli_sambung
        expl.jalankan_web = asli_web
        expl.time.sleep = asli_sleep
        os.environ.pop("MESH_HOST", None)
        os.environ.pop("MESH_HOST_CADANGAN", None)
    periksa("main bergilir utama -> cad1 -> cad2 -> utama",
            urutan == ["utama", "cad1", "cad2", "utama"], urutan)
    periksa("main berhenti bersih saat dihentikan (keluar 0)", kode == 0,
            "kode=%s" % kode)

    # Tampilan halaman lacak ikut disimpan supaya bisa dibuka di peramban.
    with open(os.path.join(os.path.dirname(KELUARAN), "lacak.html"), "w",
              encoding="utf-8") as f:
        f.write(hlm)

    # --- simpan tampilan untuk dilihat -------------------------------------
    os.makedirs(os.path.dirname(KELUARAN), exist_ok=True)
    with open(KELUARAN, "w", encoding="utf-8") as f:
        f.write(html)
    print("\nTampilan disimpan ke: %s" % os.path.abspath(KELUARAN))

    print("\n" + "=" * 60)
    print("  Lolos: %d | GAGAL: %d" % (lolos, gagal))
    print("  %s" % ("SEMUA UJI LULUS." if not gagal else "ADA YANG GAGAL."))
    return 1 if gagal else 0


if __name__ == "__main__":
    sys.exit(main())
