#!/usr/bin/env python3
# ============================================================
# lacak_node.py - penyimpanan & analitik HISTORI LOKASI node Meshtastic
# ============================================================
# Modul ini menjawab satu masalah: /data.json hanya memuat posisi TERAKINI
# setiap node, sedangkan halaman pelacakan butuh JEJAK PERGERAKAN (kapan node
# ada di mana). Modul ini karena itu menyimpan setiap fixes posisi baru yang
# muncul di snapshot ke SQLite, lalu mengubahnya menjadi:
#   - garis rute (polyline) untuk diputar di peta,
#   - titik singgah (knode node berhenti di satu tempat),
#   - statistik: jarak total, durasi, kecepatan rata-rata.
#
# Sisi penyimpanan sengaja dipisah dari exporter-meshtastic.py supaya:
#   - modul bisa diuji sendiri tanpa perangkat radio,
#   - kegagalan database tidak pernah menjatuhkan exporter: semua fungsi
#     publik menangkap exception lalu mengembalikan nilai kosong.
#
# Penghematan ruang: node yang diam tidak ditulis tiap 30 detik. Sebuah titik
# baru disimpan hanya bila node bergerak lebih jauh dari MESH_LACAK_MIN_JARAK,
# ATAU sudah lebih lama dari MESH_LACAK_MIN_SELA tanpa titik baru. Jerit GPS
# sementara (< 5 m) karena itu tidak membengkakkan database.
#
# Database
# --------
#   /DATA/AppData/meshtastic-monitor/lacak.sqlite3   (bawaan, ubah lewat
#   MESH_LACAK_DB). Satu tabel `posisi` dengan kunci (node_id, t), jadi
#   penulisan ulang titik dengan waktu yang sama tidak pernah menggandakan
#   baris.
#
# Lingkungan
# ------
#   MESH_LACAK_DB            path file SQLite
#   MESH_LACAK_SIMPAN_HARI   hapus riwayat lebih tua dari ini (bawaan 30)
#   MESH_LACAK_MIN_JARAK     meter; bergerak sefarat ini = titik baru (bawaan 5)
#   MESH_LACAK_MIN_SELA      detik; titlek tanpa gerak pun tetap disimpan
#                            setelah selang ini (bawaan 600)
#   MESH_LACAK_RADIUS_SINGGAH  meter; radius searchesgahan node (bawaan 75)
#   MESH_LACAK_MENINGGAH      detik; minimal diam agar dihitung singgah
#                            (bawaan 300)
#   MESH_LACAK_MAKS_TITIK     batas titik rute per node (bawaan 4000)
#   MESH_LACAK_AKTIF          0 mematikan perekaman sepenuhnya
# ============================================================

import logging
import math
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

LOG = logging.getLogger("meshtastic-exporter.lacak")

# Laju maksimum yang masih dianggap "diam" (meter per detik). 1,0 m/s =
# 3,6 km/j, yaitu langkah kaki orang. Di atas itu node dianggap bergerak,
# berapa pun kecil jaraknya per sampel - inilah yang mencegah node yang
# berjalan pelan salah dihitung sebagai singgah.
LAJU_DIAM_MPS = 1.0

# Indonesia tidak memakai DST sejak 2024, jadi WIB = UTC+7 sepanjang tahun.
# Offset tetap dipakai (bukan zoneinfo) supaya modul ini tidak bergantung pada
# berkas tzdata yang belum tentu ada di host mini-NAS.
WIB = timezone(timedelta(hours=7), "WIB")


def _env(nama, bawaan):
    v = os.environ.get(nama, "")
    return v if v not in ("", None) else str(bawaan)


def _env_int(nama, bawaan, minimum=None):
    try:
        v = int(_env(nama, bawaan))
    except (TypeError, ValueError):
        return bawaan
    if minimum is not None and v < minimum:
        return minimum
    return v


def _env_float(nama, bawaan, minimum=None):
    try:
        v = float(_env(nama, bawaan))
    except (TypeError, ValueError):
        return bawaan
    if minimum is not None and v < minimum:
        return minimum
    return v


KONFIG = {
    "db": _env("MESH_LACAK_DB", os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "lacak.sqlite3")),
    "simpan_hari": _env_int("MESH_LACAK_SIMPAN_HARI", 30, 1),
    "min_jarak": _env_float("MESH_LACAK_MIN_JARAK", 5.0, 0.0),
    "min_sela": _env_int("MESH_LACAK_MIN_SELA", 600, 30),
    "radius_singgah": _env_float("MESH_LACAK_RADIUS_SINGGAH", 75.0, 1.0),
    "meninggah": _env_int("MESH_LACAK_MENINGGAH", 300, 10),
    "maks_titik": _env_int("MESH_LACAK_MAKS_TITIK", 4000, 50),
    "aktif": _env("MESH_LACAK_AKTIF", "1") not in ("0", "false", "no", "off"),
}


# ------------------------------------------------------------
# Kelayakan koordinat
# ------------------------------------------------------------

# Perangkat yang belum mengunci GPS tetap melaporkan posisi - dan yang
# dilaporkan bukan tempat di bumi, melainkan sisa bit: 0,0 atau angka kecil
# seperti 0,0016384 dan 0,0262144. Titik di sekitar (0,0) itu dikenal sebagai
# "Null Island" (laut lepas di Teluk Guinea).
#
# Satu node saja yang membawa nilai seperti ini cukup untuk merusak peta:
# bingkai "fit semua node" ikut melebar ke seluruh dunia, zoom jatuh ke
# tingkat 3, dan node yang sungguh ada mengecil sampai tak terlihat. Karena
# itu semuanya diperlakukan sama dengan node tanpa GPS.
#
# 0,1 derajat (kira-kira 11 km) dipilih karena node kami berada di Indonesia
# dan tidak ada satu pun yang mungkin muncul di radius itu; ambang yang lebih
# ketat (mis. 1e-6) meloloskan justru nilai sisa bit yang paling sering.
AMBANG_TITIK_NOL = 0.1


def posisi_bersih(lat, lon):
    """(lat, lon) yang layak dipetakan, atau (None, None) bila tidak layak.

    Menyaring sekaligus tiga hal: nilai kosong, nilai yang bukan angka, dan
    koordinat di luar rentang bumi. Dipakai bersama oleh penyimpan riwayat
    (catat_snapshot), halaman Live Map, dan exporter supaya ketiganya
    sepakat soal node mana yang "punya koordinat" - kalau tidak, peta bisa
    memakai titik yang justru ditolak daftar.
    """
    if lat is None or lon is None:
        return (None, None)
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return (None, None)
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return (None, None)
    if abs(lat) < AMBANG_TITIK_NOL and abs(lon) < AMBANG_TITIK_NOL:
        return (None, None)
    return (lat, lon)


# ------------------------------------------------------------
# Matematika geografi
# ------------------------------------------------------------

def jarak_m(a_lat, a_lon, b_lat, b_lon):
    """Jarak dua titik di bumi dalam meter (haversine, R = 6371 km).

    Rumus simetris dipakai (bukan aproksimasi dlon * cos(lebar)) karena jarak
    singgah dipakai membandingkan dua arah: asimetri 1,5 meter yang terlihat
    pada jarak 15 km akan membuat ambang 75 m terasa acak di tepi ambang.
    """
    r = 6371000.0
    rad = math.radians
    dlat = rad(b_lat - a_lat)
    dlon = rad(b_lon - a_lon)
    h = (math.sin(dlat / 2.0) ** 2
         + math.cos(rad(a_lat)) * math.cos(rad(b_lat)) * math.sin(dlon / 2.0) ** 2)
    return 2.0 * r * math.asin(min(1.0, math.sqrt(max(0.0, h))))


def arah_arah(a_lat, a_lon, b_lat, b_lon):
    """Bearing awal dua titik, derajat 0..360, 0 = utara sejati."""
    f1, f2 = math.radians(a_lat), math.radians(b_lat)
    dl = math.radians(b_lon - a_lon)
    y = math.sin(dl) * math.cos(f2)
    x = math.cos(f1) * math.sin(f2) - math.sin(f1) * math.cos(f2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def _wib(epoch):
    return datetime.fromtimestamp(epoch, WIB)


def _wib_pendek(epoch):
    return _wib(epoch).strftime("%d %b %H:%M")


def _wib_panjang(epoch):
    return _wib(epoch).strftime("%d %b %Y %H:%M")


def _wib_berlabel(epoch):
    return _wib(epoch).strftime("%d %b %H:%M") + " WIB"


# ------------------------------------------------------------
# Penyimpanan
# ------------------------------------------------------------

class Penyimpan:
    """SQLite untuk histori posisi.

    Setiap thread memakai koneksi sendiri (sqlite3 melarang berbagi koneksi
    antar thread) yang diambil dari threading.local. contention hanya terjadi
    pada INSERT dari collector, jadi WAL + busy_timeout cukup.
    """

    SKEMA = """
    CREATE TABLE IF NOT EXISTS posisi (
        node_id TEXT    NOT NULL,
        t       REAL    NOT NULL,
        lat     REAL,
        lon     REAL,
        alt     REAL,
        PRIMARY KEY (node_id, t)
    ) WITHOUT ROWID;
    CREATE TABLE IF NOT EXISTS meta (
        k TEXT PRIMARY KEY,
        v TEXT
    );
    """

    def __init__(self, konfig=None):
        self.konfig = dict(konfig or KONFIG)
        self._lokal = threading.local()
        self.kunci = threading.Lock()
        self._pangkas_terakhir = 0.0
        self.siap = False
        self.pesan_error = None
        if not self.konfig["aktif"]:
            self.pesan_error = "perekaman dimatikan lewat MESH_LACAK_AKTIF=0"
            LOG.warning("lacak: %s", self.pesan_error)
            return
        try:
            con = self._konek()
            con.executescript(self.SKEMA)
            con.commit()
            self.siap = True
            LOG.info("lacak: database %s siap", self.konfig["db"])
        except Exception as exc:  # noqa: BLE001
            self.pesan_error = "%s: %s" % (type(exc).__name__, exc)
            LOG.error("lacak: database tidak bisa dibuka (%s); lacakan dimatikan",
                      self.pesan_error)

    def _konek(self):
        con = getattr(self._lokal, "con", None)
        if con is None:
            con = sqlite3.connect(self.konfig["db"], timeout=15.0)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute("PRAGMA busy_timeout=15000")
            self._lokal.con = con
        return con

    def tutup(self):
        con = getattr(self._lokal, "con", None)
        if con is not None:
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
            self._lokal.con = None

    # -- penulisan ------------------------------------------------

    def catat_snapshot(self, nodes, sekarang=None):
        """Simpan posisi baru dari snapshot node.

        `nodes` adalah dict {node_id: {...}} seperti yang Cuplikan.baca()
        kembalikan. Hanya node dengan lat/lon yang masuk database - node tanpa
        GPS tidak punya jejak untuk dilacak.

        Mengembalikan jumlah baris yang benar-benar ditulis.
        """
        if not self.siap:
            return 0
        t0 = time.time() if sekarang is None else float(sekarang)
        baris = []
        for node_id, r in (nodes or {}).items():
            lat, lon, alt = r.get("lat"), r.get("lon"), r.get("alt")
            # Termasuk node yang membawa sisa bit di sekitar (0,0): kalau
            # diloloskan, satu titik sampah itu masuk riwayat dan membuat
            # peta halaman /lacak/<id> melompat ke Teluk Guinea.
            lat, lon = posisi_bersih(lat, lon)
            if lat is None or lon is None:
                continue
            try:
                alt = float(alt) if alt is not None else None
            except (TypeError, ValueError):
                alt = None
            baris.append((node_id, t0, lat, lon, alt))

        if not baris:
            return 0

        # Nama node ikut disimpan: halaman /lacak/<id> perlu menampilkan nama
        # yang masuk akal walaupun node itu sudah tergeser keluar dari
        # database gateway (nodedb penuh) atau lama tidak terdengar.
        for node_id, _, _, _, _ in baris:
            r = (nodes or {}).get(node_id) or {}
            nama = r.get("long_name") or r.get("short_name")
            if nama:
                self._ingat_nama(node_id, nama)

        ditulis = 0
        try:
            con = self._konek()
            min_jarak = self.konfig["min_jarak"]
            min_sela = self.konfig["min_sela"]
            with self.kunci:
                for node_id, t, lat, lon, alt in baris:
                    if not self._layak_simpan(con, node_id, t, lat, lon,
                                             min_jarak, min_sela):
                        continue
                    con.execute(
                        "INSERT OR IGNORE INTO posisi (node_id,t,lat,lon,alt) "
                        "VALUES (?,?,?,?,?)", (node_id, t, lat, lon, alt))
                    ditulis += 1
                con.commit()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("lacak: gagal menyimpan posisi: %s", exc)
            return 0

        self._mungkin_pangkas()
        return ditulis

    def _layak_simpan(self, con, node_id, t, lat, lon, min_jarak, min_sela):
        """Gerakan cukup jauh ATAU sudah terlalu lama tanpa titik baru."""
        baris = con.execute(
            "SELECT t,lat,lon FROM posisi WHERE node_id=? ORDER BY t DESC LIMIT 1",
            (node_id,)).fetchone()
        if baris is None:
            return True
        if (t - baris["t"]) >= min_sela:
            return True
        return jarak_m(baris["lat"], baris["lon"], lat, lon) >= min_jarak

    def _ingat_nama(self, node_id, nama):
        """Simpan nama terakhir node di tabel meta (idempoten, sekali per poll)."""
        try:
            with self.kunci:
                self._konek().execute(
                    "INSERT OR REPLACE INTO meta (k,v) VALUES (?,?)",
                    ("nama:" + node_id, str(nama)[:200]))
        except Exception as exc:  # noqa: BLE001
            LOG.debug("lacak: gagal menyimpan nama %s: %s", node_id, exc)

    def _mungkin_pangkas(self):
        """Buang baris lama. Dijalankan max sekali per jam, bukan tiap poll."""
        now = time.time()
        if now - self._pangkas_terakhir < 3600.0:
            return
        self._pangkas_terakhir = now
        try:
            batas = now - self.konfig["simpan_hari"] * 86400.0
            with self.kunci:
                con = self._konek()
                con.execute("DELETE FROM posisi WHERE t < ?", (batas,))
                con.commit()
            LOG.info("lacak: riwayat dipangkas ke %s hari", self.konfig["simpan_hari"])
        except Exception as exc:  # noqa: BLE001
            LOG.warning("lacak: gagal memangkas riwayat: %s", exc)

    # -- pembacaan ------------------------------------------------

    def titik(self, node_id, sejak=None, sampai=None, maks=None):
        """Titik posisi satu node, urut waktu: [{t,lat,lon,alt}]."""
        if not self.siap:
            return []
        syarat, arg = ["node_id=?"], [node_id]
        if sejak is not None:
            syarat.append("t>=?")
            arg.append(float(sejak))
        if sampai is not None:
            syarat.append("t<=?")
            arg.append(float(sampai))
        sql = ("SELECT t,lat,lon,alt FROM posisi WHERE %s ORDER BY t ASC"
               % " AND ".join(syarat))
        try:
            with self.kunci:
                baris = self._konek().execute(sql, arg).fetchall()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("lacak: gagal membaca titik %s: %s", node_id, exc)
            return []
        # Baris lama (ditulis sebelum pembersihan penulisan, 28 Sep
        # 2026) mungkin masih menyimpan sisa bit di sekitar (0,0).
        # Saring lagi di sini: satu baris saja cukup untuk merobek
        # garis rute dan bingkai halaman /lacak/<id>. posisi_bersih
        # idempotent, jadi baris yang sudah bersih tidak berubah.
        hasil = []
        for b in baris:
            lat, lon = posisi_bersih(b["lat"], b["lon"])
            if lat is None:
                continue
            hasil.append({"t": b["t"], "lat": lat, "lon": lon,
                          "alt": b["alt"]})
        maks = maks or self.konfig["maks_titik"]
        return _tipkan(hasil, maks)

    def node_berriwayat(self, nodes=None, sejak=None):
        """Ringkasan node yang punya histori, paling baru dulu."""
        if not self.siap:
            return []
        since = float(sejak if sejak is not None
                      else time.time() - self.konfig["simpan_hari"] * 86400.0)
        try:
            with self.kunci:
                baris = self._konek().execute(
                    "SELECT node_id, COUNT(*) n, MIN(t) t0, MAX(t) t1 "
                    "FROM posisi WHERE t>=? GROUP BY node_id ORDER BY t1 DESC",
                    (since,)).fetchall()
                hasil = []
                for b in baris:
                    akhir = self._konek().execute(
                        "SELECT lat,lon,alt FROM posisi WHERE node_id=? "
                        "ORDER BY t DESC LIMIT 1", (b["node_id"],)).fetchone()
                    hasil.append({
                        "node_id": b["node_id"],
                        "jumlah": b["n"],
                        "t0": b["t0"],
                        "t1": b["t1"],
                        "lat": akhir["lat"] if akhir else None,
                        "lon": akhir["lon"] if akhir else None,
                        "alt": akhir["alt"] if akhir else None,
                    })
        except Exception as exc:  # noqa: BLE001
            LOG.warning("lacak: gagal membaca daftar node: %s", exc)
            return []

        # Gabungkan dengan cuplikan sekarang supaya nama/via/status tetap segar.
        for r in hasil:
            n = (nodes or {}).get(r["node_id"]) or {}
            r["long_name"] = n.get("long_name") or ""
            r["short_name"] = n.get("short_name") or ""
            r["hw_model"] = n.get("hw_model") or ""
            r["via"] = n.get("via") or ""
            r["favorite"] = bool(n.get("favorite"))
            r["online"] = bool(n.get("online"))
            r["last"] = n.get("last")
            r["snr"] = n.get("snr")
            r["hops"] = n.get("hops")
            r["battery"] = n.get("battery")
        return hasil

    def statistik_db(self):
        """Angka ringkas database, untuk kartu di halaman."""
        if not self.siap:
            return {"jumlah": 0, "node": 0, "bytes": 0, "aktif": False,
                    "pesan": self.pesan_error, "lokasi": self.konfig["db"]}
        try:
            with self.kunci:
                con = self._konek()
                n = con.execute("SELECT COUNT(*) c FROM posisi").fetchone()["c"]
                u = con.execute("SELECT COUNT(DISTINCT node_id) c FROM posisi").fetchone()["c"]
        except Exception as exc:  # noqa: BLE001
            return {"jumlah": 0, "node": 0, "bytes": 0, "aktif": False,
                    "pesan": str(exc), "lokasi": self.konfig["db"]}
        ukuran = 0
        try:
            ukuran = os.path.getsize(self.konfig["db"])
        except OSError:
            pass
        return {"jumlah": n, "node": u, "bytes": ukuran, "aktif": True,
                "pesan": None, "lokasi": self.konfig["db"],
                "simpan_hari": self.konfig["simpan_hari"]}


def _tipkan(titik, maks):
    """Kurangi jumlah titik dengan=stride, tapi titik pertama & terakhir selalu
    dipertahankan. Batas jumlah titik menjaga payload JSON halaman tetap
    kecil untuk node yang direkam berhari-hari."""
    n = len(titik)
    if n <= maks or maks < 2:
        return titik
    langkah = max(1, int(math.ceil(n / float(maks))))
    hasil = titik[::langkah]
    if hasil[-1] is not titik[-1]:
        hasil.append(titik[-1])
    return hasil


# ------------------------------------------------------------
# Titik singgah & statistik
# ------------------------------------------------------------

def _cari_singgah(titik, radius_m, meninggah_s, laju_diam=None):
    """Temukan rentang titik tempat node diam.

    Dua syarat dipakai BERSAMAAN, dan keduanya perlu:

      1. laju antar dua titik <= LAJU_DIAM_MPS (bawaan 1,0 m/s = 3,6 km/j).
         Ini yang membedakan "berhenti" dari "jalan pelan". Syarat jarak saja
         tidak cukup: node yang berjalan 4 km/j dengan sampel tiap 30 detik
         hanya bergerak 33 meter per sampel, jadi selalu terlihat "di dalam
         radius" padahal terus berjalan.
      2. simpangan dari titik awal kandidat <= radius_m. Tanpa ini, node yang
         berjalan sangat pelan (mis. 1 km/j selama satu jam = 1 km) akan
         buildup menjadi satu "singgah" raksasa yang diam 1 jam.

    Sebuah rentang baru dianggap singgah bila durasinya >= meninggah_s.

    Mengembalikan daftar dict {i0, i1, t0, t1, lat, lon, alt} dengan i0/i1
    sebagai indeks ke dalam `titik`.
    """
    laju_diam = LAJU_DIAM_MPS if laju_diam is None else laju_diam
    hasil = []
    n = len(titik)
    i = 0
    while i < n - 1:
        j = i
        while j + 1 < n:
            a, b = titik[j], titik[j + 1]
            dt = b["t"] - a["t"]
            if dt <= 0:
                # Dua titik dengan cap waktu sama: tak ada informasi laju, jadi
                # gabung saja (dataset bisa memuatnya setelah impor).
                j += 1
                continue
            if jarak_m(a["lat"], a["lon"], b["lat"], b["lon"]) / dt > laju_diam:
                break
            if jarak_m(titik[i]["lat"], titik[i]["lon"], b["lat"], b["lon"]) > radius_m:
                break
            j += 1
        if j > i and (titik[j]["t"] - titik[i]["t"]) >= meninggah_s:
            potongan = titik[i:j + 1]
            hasil.append({
                "i0": i, "i1": j,
                "t0": potongan[0]["t"], "t1": potongan[-1]["t"],
                "lat": sum(p["lat"] for p in potongan) / len(potongan),
                "lon": sum(p["lon"] for p in potongan) / len(potongan),
                "alt": _alt_tengah(potongan),
            })
            i = j + 1
        else:
            i += 1
    return hasil


def _alt_tengah(potongan):
    yang_ada = [p["alt"] for p in potongan if p.get("alt") is not None]
    return sum(yang_ada) / len(yang_ada) if yang_ada else None


def susun_lacak(titik, konfig=None, sejak=None, sampai=None):
    """Ubah daftar titik mentah menjadi paket data untuk halaman lacak.

    Keluaran:
      route   [[lat,lon], ...] garis polyline
      stops   [{lat,lon,alt,t0,t1,label,i}] titik singgah; entri pertama &
              terakhir bersifat sintetis (label "Mulai"/"Selesai") supaya
              ada kaki dari posisi awal sampai singgah pertama dan dari
              singgah terakhir sampai posisi akhir.
      legs    [{i0,i1,t0,t1,dist_m,dur,kmh}]_segments antar singgah
      bounds  [[lat_min,lon_min],[lat_max,lon_max]] untuk fitBounds
      stats   jarak total, jumlah singgah, durasi, kecepatan rata-rata
    """
    k = dict(konfig or KONFIG)
    # Penyaringan kedua: penyimpanan menyaring saat menulis, tetapi
    # pemanggil bisa menyerahkan titik mentah (mis. dari database
    # yang ditulis sebelum pembersihan penulisan). Sisa bit di
    # sekitar (0,0) cukup satu titik untuk membuat garis rute
    # menyebrang seluruh peta.
    bersih = []
    for p in titik:
        la, lo = posisi_bersih(p.get("lat"), p.get("lon"))
        if la is not None:
            bersih.append({"t": p["t"], "lat": la, "lon": lo,
                           "alt": p.get("alt")})
    titik = bersih
    if sejak is not None:
        titik = [p for p in titik if p["t"] >= sejak]
    if sampai is not None:
        titik = [p for p in titik if p["t"] <= sampai]
    if not titik:
        return None

    # Titik singgah dicari pada SELURUH titik sebelum pentipkan: kalau tipikan
    # dilakukan lebih dulu, radius singgah jadi tidak bermakna karena jarak
    # antar titik yang tersisa bisa jauh lebih besar.
    semua_titik = titik
    singgah = _cari_singgah(semua_titik, k["radius_singgah"], k["meninggah"])
    tips = _tipkan(semua_titik, k["maks_titik"])

    # Peta indeks singgah -> indeks pada `tips` (yang dikirim ke peramban).
    def ke_tipkan(indeks):
        if indeks <= 0:
            return 0
        if indeks >= len(semua_titik) - 1:
            return len(tips) - 1
        rasio = indeks / float(len(semua_titik) - 1)
        return min(len(tips) - 1, max(0, int(round(rasio * (len(tips) - 1)))))

    stops = []
    for s in singgah:
        awal = datetime.fromtimestamp(s["t0"], WIB)
        akhir = datetime.fromtimestamp(s["t1"], WIB)
        label = awal.strftime("%d %b %H:%M")
        if s["t1"] - s["t0"] >= 60:
            label += " – " + akhir.strftime("%d %b %H:%M")
        stops.append({
            "lat": s["lat"], "lon": s["lon"], "alt": s["alt"],
            "t0": s["t0"], "t1": s["t1"], "label": label,
            "sintetis": False, "i": ke_tipkan(s["i0"]),
            "durasi_jam": round((s["t1"] - s["t0"]) / 3600.0, 2),
        })

    # Titik ujung sintetis: tanpa ini, Client tidak punya kaki dari posisi
    # pertama ke singgah pertama, dan playback akan melompat.
    pertama, terakhir = tips[0], tips[-1]
    if not stops or stops[0]["i"] > 0:
        stops.insert(0, {
            "lat": pertama["lat"], "lon": pertama["lon"], "alt": pertama["alt"],
            "t0": pertama["t"], "t1": pertama["t"],
            "label": "Mulai " + _wib_pendek(pertama["t"]),
            "sintetis": True, "i": 0, "durasi_jam": 0.0,
        })
    if not stops or stops[-1]["i"] < len(tips) - 1:
        stops.append({
            "lat": terakhir["lat"], "lon": terakhir["lon"], "alt": terakhir["alt"],
            "t0": terakhir["t"], "t1": terakhir["t"],
            "label": "Selesai " + _wib_pendek(terakhir["t"]),
            "sintetis": True, "i": len(tips) - 1, "durasi_jam": 0.0,
        })

    # Kaki: dari satu singgah ke singgah berikutnya, diukur sepanjang rute.
    legs = []
    for a, b in zip(stops, stops[1:]):
        i0, i1 = a["i"], b["i"]
        if i1 <= i0:
            i1 = i0 + 1
        dist = _panjang_potong(tips, i0, i1)
        t0, t1 = a["t1"], b["t0"]
        dur = max(t1 - t0, 1.0)
        legs.append({
            "i0": i0, "i1": min(i1, len(tips) - 1),
            "t0": t0, "t1": t1, "dist_m": dist, "dur": dur,
            "kmh": (dist / 1000.0) / (dur / 3600.0),
        })

    # Statistik dihitung dari rute lengkap, bukan dari tips, supaya jaraknya
    # tidak bergantung pada ketebalan pentipkan.
    total_m = _panjang_potong(semua_titik, 0, len(semua_titik) - 1)
    durasi_jam = max(semua_titik[-1]["t"] - semua_titik[0]["t"], 0.0) / 3600.0
    lats = [p["lat"] for p in tips]
    lons = [p["lon"] for p in tips]
    stats = {
        "dist_km": round(total_m / 1000.0, 1),
        "stops": sum(1 for s in stops if not s["sintetis"]),
        "duration_h": round(durasi_jam, 1),
        "avg_speed": round((total_m / 1000.0) / durasi_jam, 1) if durasi_jam > 0 else 0.0,
        "points": len(semua_titik),
    }

    return {
        "route": [[round(p["lat"], 6), round(p["lon"], 6)] for p in tips],
        "stops": stops,
        "legs": legs,
        "bounds": [[min(lats), min(lons)], [max(lats), max(lons)]],
        "stats": stats,
        "date_range": "%s – %s" % (_wib_pendek(semua_titik[0]["t"]),
                                   _wib_berlabel(semua_titik[-1]["t"])),
        "t_awal": semua_titik[0]["t"],
        "t_akhir": semua_titik[-1]["t"],
        "ambang": {
            "radius_m": k["radius_singgah"],
            "meninggah_s": k["meninggah"],
            "min_jarak": k["min_jarak"],
        },
    }


def _panjang_potong(titik, i0, i1):
    """Panjang busur sepanjang titik[i0..i1] dalam meter."""
    i0 = max(0, i0)
    i1 = min(len(titik) - 1, i1)
    total = 0.0
    for k in range(i0, i1):
        a, b = titik[k], titik[k + 1]
        total += jarak_m(a["lat"], a["lon"], b["lat"], b["lon"])
    return total


def titik_singgah_baru(titik, radius_m, meninggah_s):
    """Deteksi singgah tanpa membangun paket UI - dipakai pengujian."""
    return _cari_singgah(titik, radius_m, meninggah_s)


# ------------------------------------------------------------
# Pembungkus untuk exporter
# ------------------------------------------------------------

# Satu objek Penyimpan dipakai seluruh proses. Disini, bukan di main(),
# supaya handler HTTP dan collector pasti memakai database yang sama.
PENYIMPAN = None


def init(konfig=None):
    """Siapkan penyimpanan. Kembalikan objek Penyimpan (siap atau tidak)."""
    global PENYIMPAN
    PENYIMPAN = Penyimpan(konfig)
    return PENYIMPAN


def _penyimpan():
    global PENYIMPAN
    if PENYIMPAN is None:
        PENYIMPAN = Penyimpan()
    return PENYIMPAN


def catat_snapshot(nodes, sekarang=None):
    """Panggil dari loop collector setelah kumpulkan()."""
    return _penyimpan().catat_snapshot(nodes, sekarang)


def node_berriwayat(nodes=None):
    return _penyimpan().node_berriwayat(nodes)


def statistik_db():
    return _penyimpan().statistik_db()


def paket_node(node_id, sejak=None, sampai=None):
    """Paket siap-halaman untuk satu node; None bila belum ada histori."""
    return susun_lacak(_penyimpan().titik(node_id, sejak, sampai),
                       KONFIG, sejak, sampai)


def node_nama(node_id):
    """Nama terbaik yang tersimpan untuk node_id, atau None.

    Dipakai supaya /lacak/<id> tetap menampilkan nama yang masuk akal
    meskipun node sudah tidak ada di snapshot gateway anymore.
    """
    p = _penyimpan()
    if not p.siap:
        return None
    try:
        with p.kunci:
            baris = p._konek().execute(
                "SELECT v FROM meta WHERE k=?", ("nama:" + node_id,)).fetchone()
    except Exception:  # noqa: BLE001
        return None
    return baris["v"] if baris else None


def ingat_nama(node_id, nama):
    """Simpan nama node agar halaman lacak tetap informatif setelah node
    hilang dari database gateway."""
    p = _penyimpan()
    if not p.siap or not nama:
        return
    try:
        with p.kunci:
            con = p._konek()
            con.execute("INSERT OR REPLACE INTO meta (k,v) VALUES (?,?)",
                        ("nama:" + node_id, str(nama)[:200]))
            con.commit()
    except Exception:  # noqa: BLE001
        pass