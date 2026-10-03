#!/usr/bin/env python3
# ============================================================
# emqx-monitor.py - pemantau broker EMQX lewat REST API (v6)
# ============================================================
# Membaca API manajemen EMQX Enterprise/Open Source edisi 6.x
# (OpenAPI 3.0, basis URL /api/v5) dan menampilkan keadaan broker:
#   * ringkasan cluster + per node (uptime, memori, beban, koneksi)
#   * penghitung pesan laju (terima/kirim/drop, langganan, topik)
#   * alarm aktif
#   * daftar klien MQTT terkoneksi (dengan saringan) + detail satu klien
#   * langganan, topik, langganan lambat
#   * keluaran metrik Prometheus (--metrik) untuk dipanen ke
#     Prometheus/Grafana yang sudah ada (satu baris per node/klien)
#
# Semua endpoint dan field diambil dari openapi.json EMQX Enterprise
# API v6.3.1 (komponen securitySchemes: basicAuth = API key, atau
# bearerAuth lewat POST /api/v5/login).
#
# Pakai
# ----
#   ./venv/Scripts/python emqx-monitor.py                  # ringkasan
#   ./venv/Scripts/python emqx-monitor.py --daftar-klien
#   ./venv/Scripts/python emqx-monitor.py --detail <clientid>
#   ./venv/Scripts/python emqx-monitor.py --metrik         # Prometheus
#   ./venv/Scripts/python emqx-monitor.py --watch 30       # ulang tiap 30 dtk
#
# Lingkungan
# ----------
#   EMQX_URL           alamat API manajemen (bawaan http://127.0.0.1:18083)
#   EMQX_API_KEY       API key EMQX (auth basicAuth: key sebagai nama pengguna)
#   EMQX_USERNAME      nama pengguna dasbor (bila tanpa API key)
#   EMQX_PASSWORD      sandi dasbor (bila tanpa API key) -> /login -> bearer
#   EMQX_TIMEOUT       batas waktu HTTP per permintaan, detik (bawaan 10)
#
# Salah satu dari EMQX_API_KEY atau pasangan EMQX_USERNAME/EMQX_PASSWORD
# wajib diisi. Keluar: 0 = baik, 1 = gagal sambung/uraian, 2 = ada
# alarm aktif (mode ringkasan/metrik) supaya bisa dipakai di cron.
#
# Tanpa dependensi baru - hanya pustaka standar (urllib, json, argparse).
# ============================================================

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://127.0.0.1:18083"
API_BAWAAN = "/api/v5"

# ---- Penguraian umur EMQX ("1d 2h 3m 4s", "2h 13m", "45s") --------------
_SATUAN_UMUR = {"d": 86400, "h": 3600, "m": 60, "s": 1}


def umur_ke_detik(teks):
    """Umur seperti '1d 2h 3m 4s' -> detik. None bila tidak terbaca."""
    if teks is None:
        return None
    if isinstance(teks, (int, float)):
        return float(teks)
    total = 0.0
    cocok = False
    for jumlah, satuan in re.findall(r"(\d+(?:\.\d+)?)\s*([dhms])", str(teks)):
        total += float(jumlah) * _SATUAN_UMUR[satuan]
        cocok = True
    return total if cocok else None


def angka(nilai):
    """Paksa ke float; EMQX kadang mengirim angka sebagai teks."""
    try:
        return float(nilai)
    except (TypeError, ValueError):
        return None


def esc_label(naskah):
    """Escape nilai label Prometheus (\\, ", newline)."""
    return str(naskah).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class EmqxApi:
    """Klien kecil untuk API manajemen EMQX /api/v5."""

    def __init__(self, url, api_key=None, username=None, password=None,
                 timeout=10.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._auth = None
        self._token = None
        if api_key:
            # API key EMQX dipakai sebagai nama pengguna basicAuth
            # (sandi boleh kosong).
            mentah = "%s:" % api_key
            self._auth = "Basic " + base64.b64encode(
                mentah.encode()).decode().strip()
        elif username and password:
            self._username = username
            self._password = password
        else:
            raise SystemExit(
                "Galat: atur EMQX_API_KEY atau EMQX_USERNAME+EMQX_PASSWORD")

    def _header(self):
        if self._auth:
            return {"Authorization": self._auth}
        return {"Authorization": "Bearer %s" % self._token} if self._token else {}

    def _buka(self, metode, jalur, param=None, badan=None, tanpa_redirect=False):
        if param:
            jalur += "?" + urllib.parse.urlencode(param, doseq=True)
        req = urllib.request.Request(self.url + jalur, method=metode,
                                     headers=self._header())
        if badan is not None:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(badan).encode()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as jaw:
                raw = jaw.read()
                return jaw.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as err:
            try:
                isi = json.loads(err.read().decode("utf-8", "replace"))
            except Exception:
                isi = {"message": "HTTP %s" % err.code}
            raise EmqxError(err.code, isi)
        except urllib.error.URLError as err:
            raise EmqxError(None, {"message": "tidak dapat menyambung: %s" % err.reason})

    def login(self):
        """Tukar nama pengguna/sandi dengan token bearer (/api/v5/login)."""
        status, isi = self._buka("POST", API_BAWAAN + "/login", badan={
            "username": self._username, "password": self._password})
        token = (isi or {}).get("token")
        if not token:
            raise EmqxError(status, {"message": "login tanpa token: %s" % isi})
        self._token = token
        return isi

    def get(self, jalur, param=None):
        return self._buka("GET", API_BAWAAN + jalur, param)[1]


class EmqxError(Exception):
    """Galat dari API EMQX (kode HTTP + isi JSON bila ada)."""

    def __init__(self, kode, isi):
        self.kode = kode
        self.isi = isi or {}
        super().__init__("EMQX API %s: %s" % (
            kode if kode is not None else "?",
            (self.isi.get("message") or self.isi.get("code") or self.isi)))


# ---------------------------------------------------------------------------
# Pengumpul data
# ---------------------------------------------------------------------------

def kumpulkan(api, semua_halaman=False):
    """Ambil semua potongan data pemantauan dalam satu pukulan."""
    data = {}
    data["cluster"] = api.get("/cluster")
    data["topologi"] = api.get("/cluster/topology")
    data["nodes"] = api.get("/nodes")
    data["monitor"] = api.get("/monitor_current")
    data["alarms"] = api.get("/alarms")

    klien_param = {"limit": 1000}
    klien = api.get("/clients", klien_param)
    if semua_halaman:
        halaman = 1
        while True:
            meta = (klien.get("meta") or {})
            if not meta.get("hasnext"):
                break
            halaman += 1
            berikut = api.get("/clients", dict(klien_param, page=halaman))
            klien["data"] = (klien.get("data") or []) + (berikut.get("data") or [])
            klien["meta"] = berikut.get("meta") or {}
    data["klien"] = klien
    return data


# ---------------------------------------------------------------------------
# Tampilan manusia
# ---------------------------------------------------------------------------

def cetak_ringkasan(api, data):
    cl = data["cluster"] or {}
    print("Cluster    : %s (%s)" % (cl.get("name") or "?",
                                     cl.get("description") or "?"))
    topo = data["topologi"] or []
    if topo:
        inti = [t.get("core_node") for t in topo if t.get("core_node")]
        repl = [r for t in topo for r in (t.get("replicant_nodes") or []) if r]
        print("Topologi   : %d inti, %d replicant" % (len(inti), len(repl)))

    print()
    print("NODE (%d):" % len(data["nodes"] or []))
    for n in data["nodes"] or []:
        up = umur_ke_detik(n.get("uptime"))
        up_s = ("%dd %02dj %02dm" % (up // 86400, (up % 86400) // 3600,
                                      (up % 3600) // 60)) if up is not None else str(n.get("uptime") or "?")
        mem = angka(n.get("memory_used"))
        mem_t = angka(n.get("memory_total"))
        mem_s = ("%.0f / %.0f MiB" % (mem / 1048576, mem_t / 1048576)
                 if mem is not None and mem_t else str(n.get("memory_used") or "?"))
        print("  %-24s %-8s %-10s up %-12s koneksi %-4s beban %s/%s/%s mem %s" % (
            n.get("node") or "?", n.get("node_status") or "?",
            n.get("role") or "?", up_s,
            n.get("connections"), n.get("load1"), n.get("load5"), n.get("load15"),
            mem_s))
        print("      versi %s %s, %s klien hidup, %s sesi cluster" % (
            n.get("version") or "?", n.get("edition") or "?",
            n.get("live_connections"), n.get("cluster_sessions")))

    mon = data["monitor"] or {}
    print()
    print("LAJU & JUMLAH:")
    for kunci, label in [
        ("live_connections", "koneksi hidup"),
        ("connections", "koneksi (termasuk putus tertunda)"),
        ("received_msg_rate", "pesan diterima /dtk"),
        ("sent_msg_rate", "pesan terkirim /dtk"),
        ("dropped_msg_rate", "pesan dibuang /dtk"),
        ("subscriptions", "langganan"),
        ("subscriptions_durable", "langganan durable"),
        ("topics", "topik"),
        ("retained_msg_count", "pesan retained"),
        ("cluster_sessions", "sesi cluster"),
    ]:
        nilai = mon.get(kunci)
        print("  %-32s %s" % (label, nilai if nilai is not None else "?"))

    alarms = data["alarms"] or {}
    items = alarms.get("data") or []
    print()
    print("ALARM (%d aktif):" % len(items))
    for a in items:
        print("  [%s] %s pada %s: %s" % (
            a.get("activate_at") or "?", a.get("name") or "?",
            a.get("node") or "?", a.get("message") or "?"))

    k = data["klien"] or {}
    meta = k.get("meta") or {}
    print()
    print("KLIEN: %d ditampilkan%s" % (
        len(k.get("data") or []),
        " dari %s (masih ada halaman berikutnya)" % meta.get("count")
        if meta.get("hasnext") else ""))


def cetak_klien(api, opsi):
    param = {"limit": opsi.batas or 100}
    if opsi.node:
        param["node"] = opsi.node
    if opsi.pengguna:
        param["username"] = opsi.pengguna
    if opsi.seperti:
        param["like_clientid"] = opsi.seperti
    if opsi.keadaan:
        param["conn_state"] = opsi.keadaan

    data = api.get("/clients", param)
    if opsi.semua:
        halaman = 1
        while (data.get("meta") or {}).get("hasnext"):
            halaman += 1
            berikut = api.get("/clients", dict(param, page=halaman))
            data["data"] = (data.get("data") or []) + (berikut.get("data") or [])
            data["meta"] = berikut.get("meta") or {}

    baris = data.get("data") or []
    meta = data.get("meta") or {}
    print("KLIEN: %d ditampilkan, %s total%s" % (
        len(baris), meta.get("count"),
        ", masih ada halaman berikutnya" if meta.get("hasnext") else ""))
    fmt = "  %-24s %-18s %-14s %-16s %-6s %-9s %-8s %s"
    print(fmt % ("clientid", "pengguna", "node", "ip", "proto", "langg.", "terima", "status"))
    for c in baris:
        print(fmt % (
            (c.get("clientid") or "?")[:24],
            (c.get("username") or "-")[:18],
            (c.get("node") or "?")[:14],
            c.get("ip_address") or "?",
            c.get("proto_ver") or "-",
            c.get("subscriptions_cnt"),
            c.get("recv_msg"),
            "hidup" if c.get("connected") else "putus"))


def cetak_detail(api, clientid):
    c = api.get("/clients/%s" % urllib.parse.quote(clientid, safe=""))
    if not c:
        print("Klien %s tidak ditemukan." % clientid)
        return
    kelompok = [
        ("Dasar", ["clientid", "username", "node", "ip_address", "port",
                   "connected", "connected_at", "disconnected_at", "created_at",
                   "clean_start", "durable", "is_bridge", "is_expired",
                   "mountpoint"]),
        ("Protokol", ["proto_name", "proto_ver", "keepalive", "expiry_interval",
                      "awaiting_rel_cnt", "awaiting_rel_max", "inflight_cnt",
                      "inflight_max", "mqueue_len", "mqueue_max", "mqueue_dropped",
                      "mailbox_len", "n_streams", "seqno_q1_next", "seqno_q2_next"]),
        ("Lalu lintas", ["recv_cnt", "recv_msg", "recv_oct", "recv_pkt",
                         "send_cnt", "send_msg", "send_oct", "send_pkt",
                         "total_payload_bytes", "subscriptions_cnt",
                         "subscriptions_max"]),
        ("Perincian terima", ["recv_msg.qos0", "recv_msg.qos1", "recv_msg.qos2",
                              "recv_msg.dropped", "recv_msg.dropped.await_pubrel_timeout"]),
        ("Perincian kirim", ["send_msg.qos0", "send_msg.qos1", "send_msg.qos2",
                             "send_msg.dropped", "send_msg.dropped.expired",
                             "send_msg.dropped.queue_full", "send_msg.dropped.too_large"]),
    ]
    for judul, kunci in kelompok:
        print("%s:" % judul)
        for k in kunci:
            if k in c:
                print("  %-34s %s" % (k, c.get(k)))


def cetak_langganan(api, node=None):
    param = {"limit": 1000}
    if node:
        param["node"] = node
    baris = api.get("/subscriptions", param) or []
    print("LANGGANAN (%d):" % len(baris))
    for s in baris:
        print("  %-28s %-40s qos=%s %s%s" % (
            (s.get("clientid") or "?")[:28], (s.get("topic") or "?")[:40],
            s.get("qos"), "durable " if s.get("durable") else "",
            "nl" if s.get("nl") else ""))


def cetak_topik(api, node=None):
    param = {"limit": 1000}
    if node:
        param["node"] = node
    data = api.get("/topics", param) or {}
    baris = data.get("data") or []
    meta = data.get("meta") or {}
    print("TOPIK (%d ditampilkan, %s total):" % (len(baris), meta.get("count")))
    for t in baris:
        print("  %-50s node=%s sesi=%s" % (
            (t.get("topic") or "?")[:50], t.get("node"), t.get("session")))


def cetak_langganan_lambat(api):
    data = api.get("/slow_subscriptions") or {}
    baris = data.get("data") or []
    print("LANGGANAN LAMBAT (%d):" % len(baris))
    for s in baris:
        print("  %-28s %-40s node=%s %s kali dalam %s dtk" % (
            (s.get("clientid") or "?")[:28], (s.get("topic") or "?")[:40],
            s.get("node"), s.get("timespan"), s.get("last_update_time")))


# ---------------------------------------------------------------------------
# Metrik Prometheus
# ---------------------------------------------------------------------------

def metrik(data):
    garis = []

    def ukur(nama, nilai, label=None, bantuan=""):
        if nilai is None:
            return
        lab = ""
        if label:
            lab = "{" + ",".join('%s="%s"' % (k, esc_label(v))
                                 for k, v in label.items()) + "}"
        garis.append("# HELP emqx_%s %s" % (nama, bantuan))
        garis.append("# TYPE emqx_%s gauge" % nama)
        garis.append("emqx_%s%s %s" % (nama, lab, nilai))

    cl = data["cluster"] or {}
    ukur("cluster_info", 1, {"name": cl.get("name") or "",
                              "description": cl.get("description") or ""},
         "Info cluster EMQX (selalu 1)")

    topo = data["topologi"] or []
    inti = [t.get("core_node") for t in topo if t.get("core_node")]
    repl = [r for t in topo for r in (t.get("replicant_nodes") or []) if r]
    ukur("cluster_core_nodes", len(inti), None, "Banyaknya node inti cluster")
    ukur("cluster_replicant_nodes", len(repl), None,
         "Banyaknya node replicant cluster")

    for n in data["nodes"] or []:
        label = {"node": n.get("node") or ""}
        ukur("node_info", 1, dict(label, role=n.get("role") or "",
                                   version=n.get("version") or "",
                                   edition=n.get("edition") or "",
                                   otp=n.get("otp_release") or "",
                                   status=n.get("node_status") or ""),
             "Metadata node EMQX (selalu 1)")
        ukur("node_uptime_seconds", umur_ke_detik(n.get("uptime")), label,
             "Uptime node (detik)")
        ukur("node_connections", angka(n.get("connections")), label,
             "Koneksi pada node")
        ukur("node_live_connections", angka(n.get("live_connections")), label,
             "Koneksi hidup pada node")
        ukur("node_cluster_sessions", angka(n.get("cluster_sessions")), label,
             "Sesi cluster pada node")
        ukur("node_memory_used_bytes", angka(n.get("memory_used")), label,
             "Memori terpakai node (byte)")
        ukur("node_memory_total_bytes", angka(n.get("memory_total")), label,
             "Memori total node (byte)")
        ukur("node_process_used", angka(n.get("process_used")), label,
             "Proses Erlang terpakai")
        ukur("node_process_available", angka(n.get("process_available")), label,
             "Proses Erlang tersedia")
        ukur("node_load1", angka(n.get("load1")), label, "Beban 1 menit")
        ukur("node_load5", angka(n.get("load5")), label, "Beban 5 menit")
        ukur("node_load15", angka(n.get("load15")), label, "Beban 15 menit")

    mon = data["monitor"] or {}
    for kunci, nama, bantuan in [
        ("live_connections", "live_connections", "Koneksi MQTT hidup (cluster)"),
        ("connections", "connections", "Koneksi (termasuk putus tertunda)"),
        ("disconnected_durable_sessions", "disconnected_durable_sessions",
         "Sesi durable yang terputus"),
        ("received_msg_rate", "received_msg_rate", "Laju pesan diterima (/dtk)"),
        ("sent_msg_rate", "sent_msg_rate", "Laju pesan terkirim (/dtk)"),
        ("dropped_msg_rate", "dropped_msg_rate", "Laju pesan dibuang (/dtk)"),
        ("subscriptions", "subscriptions", "Jumlah langganan"),
        ("subscriptions_durable", "subscriptions_durable",
         "Jumlah langganan durable"),
        ("topics", "topics", "Jumlah topik"),
        ("retained_msg_count", "retained_msg_count", "Jumlah pesan retained"),
        ("cluster_sessions", "cluster_sessions", "Sesi cluster"),
        ("actions_executed_rate", "actions_executed_rate",
         "Laju eksekusi action data integration (/dtk)"),
        ("rules_matched_rate", "rules_matched_rate",
         "Laju pesan cocok aturan (/dtk)"),
    ]:
        ukur(nama, angka(mon.get(kunci)), None, bantuan)

    items = (data["alarms"] or {}).get("data") or []
    ukur("alarms_active", len(items), None, "Banyaknya alarm aktif")
    for a in items:
        ukur("alarm_info", 1, {"name": a.get("name") or "",
                                "node": a.get("node") or "",
                                "message": a.get("message") or ""},
             "Satu alarm aktif (selalu 1)")

    for c in (data["klien"] or {}).get("data") or []:
        label = {"clientid": c.get("clientid") or "",
                 "node": c.get("node") or "",
                 "username": c.get("username") or ""}
        ukur("client_info", 1, dict(label, ip=c.get("ip_address") or "",
                                     proto=c.get("proto_name") or "",
                                     bridge=str(bool(c.get("is_bridge")))),
             "Klien MQTT terdaftar (selalu 1)")
        ukur("client_connected", 1 if c.get("connected") else 0, label,
             "1 bila klien sedang terkoneksi")
        ukur("client_subscriptions", angka(c.get("subscriptions_cnt")), label,
             "Jumlah langganan klien")
        ukur("client_recv_msg_total", angka(c.get("recv_msg")), label,
             "Pesan diterima klien (kumulatif)")
        ukur("client_send_msg_total", angka(c.get("send_msg")), label,
             "Pesan terkirim klien (kumulatif)")
        ukur("client_recv_msg_dropped", angka(c.get("recv_msg.dropped")), label,
             "Pesan diterima yang dibuang (kumulatif)")
        ukur("client_send_msg_dropped", angka(c.get("send_msg.dropped")), label,
             "Pesan terkirim yang dibuang (kumulatif)")
        ukur("client_keepalive_seconds", angka(c.get("keepalive")), label,
             "Keepalive klien (detik)")
        ukur("client_inflight", angka(c.get("inflight_cnt")), label,
             "Pesan inflight QoS>0")
        ukur("client_mqueue_len", angka(c.get("mqueue_len")), label,
             "Panjang antre pesan klien")

    # capai: jumlah klien yang tampil (bukan total) supaya diketahui
    meta = (data["klien"] or {}).get("meta") or {}
    ukur("clients_shown", angka(meta.get("count")), None,
         "Banyak klien menurut halaman pertama (meta.count)")
    return "\n".join(garis) + "\n"


# ---------------------------------------------------------------------------
# Utama
# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Pemantau broker EMQX lewat API manajemen /api/v5")
    ap.add_argument("--daftar-klien", action="store_true",
                    help="daftar klien MQTT terkoneksi")
    ap.add_argument("--detail", metavar="CLIENTID",
                    help="detail satu klien")
    ap.add_argument("--langganan", action="store_true", help="daftar langganan")
    ap.add_argument("--topik", action="store_true", help="daftar topik")
    ap.add_argument("--langganan-lambat", action="store_true",
                    help="daftar langganan lambat")
    ap.add_argument("--metrik", action="store_true",
                    help="keluaran metrik Prometheus")
    ap.add_argument("--semua", action="store_true",
                    help="ikuti semua halaman (klien)")
    ap.add_argument("--node", help="saring per nama node (emqx@host)")
    ap.add_argument("--pengguna", help="saring klien per nama pengguna")
    ap.add_argument("--seperti", help="saring clientid memuat teks ini")
    ap.add_argument("--keadaan", help="saring keadaan koneksi "
                    "(connected/idle/disconnected)")
    ap.add_argument("--batas", type=int, default=100,
                    help="banyak baris per halaman (bawaan 100)")
    ap.add_argument("--watch", type=float, metavar="DETIK",
                    help="ulang ringkasan tiap N detik")
    ap.add_argument("--putaran", type=int, default=0,
                    help="banyak putaran --watch (0 = tanpa batas)")
    opsi = ap.parse_args(argv)

    api = EmqxApi(
        os.environ.get("EMQX_URL", DEFAULT_URL),
        api_key=os.environ.get("EMQX_API_KEY"),
        username=os.environ.get("EMQX_USERNAME"),
        password=os.environ.get("EMQX_PASSWORD"),
        timeout=float(os.environ.get("EMQX_TIMEOUT", "10")),
    )
    if api._auth is None:
        api.login()

    def satu_putaran():
        data = kumpulkan(api, semua_halaman=opsi.semua)
        if opsi.metrik:
            sys.stdout.write(metrik(data))
        else:
            cetak_ringkasan(api, data)
        return data

    try:
        if opsi.detail:
            cetak_detail(api, opsi.detail)
        elif opsi.daftar_klien:
            cetak_klien(api, opsi)
        elif opsi.langganan:
            cetak_langganan(api, opsi.node)
        elif opsi.topik:
            cetak_topik(api, opsi.node)
        elif opsi.langganan_lambat:
            cetak_langganan_lambat(api)
        elif opsi.watch is not None:
            putaran = 0
            while True:
                data = satu_putaran()
                putaran += 1
                if opsi.putaran and putaran >= opsi.putaran:
                    break
                time.sleep(opsi.watch)
        else:
            data = satu_putaran()
    except EmqxError as err:
        print("GAGAL: %s" % err, file=sys.stderr)
        return 1

    # Kode keluar 2 bila ada alarm aktif (berguna untuk cron/monitoring)
    alarms = ((data.get("alarms") or {}).get("data") or []) if not (
        opsi.detail or opsi.daftar_klien or opsi.langganan or opsi.topik
        or opsi.langganan_lambat) else []
    if alarms:
        print()
        print("PERINGATAN: %d alarm aktif." % len(alarms), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
