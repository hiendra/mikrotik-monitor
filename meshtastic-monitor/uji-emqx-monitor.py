#!/usr/bin/env python3
# ============================================================
# uji-emqx-monitor.py - uji emqx-monitor.py tanpa broker EMQX
# ============================================================
# Menyalakan server HTTP palsu yang menjawab persis seperti
# EMQX v6 (menurut openapi.json EMQX Enterprise API 6.3.1),
# lalu menjalankan emqx-monitor.py terhadapnya dalam beberapa
# mode dan memeriksa keluarannya.
#
#   ./venv/Scripts/python uji-emqx-monitor.py
# ============================================================

import contextlib
import importlib.util
import io
import json
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

# Berkas sasaran memakai strip dalam namanya, jadi dimuat lewat importlib.
_spec = importlib.util.spec_from_file_location(
    "emqx_monitor",
    __file__.replace("uji-emqx-monitor.py", "emqx-monitor.py"))
emqx_monitor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(emqx_monitor)


NODE = {
    "node": "emqx1@127.0.0.1", "node_status": "Running",
    "role": "core", "version": "6.3.1", "edition": "enterprise",
    "feature_preset": "production", "otp_release": "26.2.1",
    "uptime": "2d 3h 14m 5s", "connections": 128, "live_connections": 120,
    "cluster_sessions": 130, "load1": 0.42, "load5": 0.31, "load15": 0.22,
    "memory_used": 536870912, "memory_total": 8589934592,
    "process_used": 9000, "process_available": 1048576,
    "max_fds": 1048576, "sys_path": "/usr/lib/emqx",
    "log_path": "/var/log/emqx", "security_profile": "production",
}

KLIEN = [
    {"clientid": "gw-meshtastic-01", "username": "gateway",
     "node": "emqx1@127.0.0.1", "ip_address": "192.168.20.31",
     "port": 51234, "connected": True, "connected_at": 1790000000,
     "created_at": 1789990000, "clean_start": True, "durable": False,
     "is_bridge": False, "is_expired": False, "mountpoint": "",
     "proto_name": "MQTT", "proto_ver": 5, "keepalive": 60,
     "expiry_interval": 0, "awaiting_rel_cnt": 0, "awaiting_rel_max": 100,
     "inflight_cnt": 0, "inflight_max": 20, "mqueue_len": 0, "mqueue_max": 1000,
     "mqueue_dropped": 0, "mailbox_len": 0, "n_streams": 1,
     "seqno_q1_next": 1, "seqno_q2_next": 1,
     "recv_cnt": 1000, "recv_msg": 900, "recv_oct": 45000, "recv_pkt": 1000,
     "send_cnt": 800, "send_msg": 790, "send_oct": 40000, "send_pkt": 800,
     "total_payload_bytes": 30000, "subscriptions_cnt": 2, "subscriptions_max": 1000,
     "heap_size": 233, "reductions": 12345,
     "recv_msg.qos0": 700, "recv_msg.qos1": 150, "recv_msg.qos2": 50,
     "recv_msg.dropped": 0, "recv_msg.dropped.await_pubrel_timeout": 0,
     "send_msg.qos0": 600, "send_msg.qos1": 150, "send_msg.qos2": 40,
     "send_msg.dropped": 0, "send_msg.dropped.expired": 0,
     "send_msg.dropped.queue_full": 0, "send_msg.dropped.too_large": 0,
     "seqno_q1_comm": 0, "seqno_q1_dup": 0, "seqno_q2_comm": 0,
     "seqno_q2_dup": 0, "seqno_q2_rec": 0},
    {"clientid": "bot-notifikasi", "username": "bot",
     "node": "emqx1@127.0.0.1", "ip_address": "192.168.20.36",
     "port": 51999, "connected": True, "connected_at": 1790000100,
     "created_at": 1789990000, "clean_start": True, "durable": False,
     "is_bridge": False, "is_expired": False, "mountpoint": "",
     "proto_name": "MQTT", "proto_ver": 4, "keepalive": 30,
     "expiry_interval": 0, "awaiting_rel_cnt": 0, "awaiting_rel_max": 100,
     "inflight_cnt": 1, "inflight_max": 20, "mqueue_len": 0, "mqueue_max": 1000,
     "mqueue_dropped": 0, "mailbox_len": 0, "n_streams": 1,
     "seqno_q1_next": 5, "seqno_q2_next": 2,
     "recv_cnt": 500, "recv_msg": 450, "recv_oct": 20000, "recv_pkt": 500,
     "send_cnt": 400, "send_msg": 399, "send_oct": 18000, "send_pkt": 400,
     "total_payload_bytes": 12000, "subscriptions_cnt": 1, "subscriptions_max": 1000,
     "heap_size": 233, "reductions": 9999,
     "recv_msg.qos0": 400, "recv_msg.qos1": 50, "recv_msg.qos2": 0,
     "recv_msg.dropped": 0, "recv_msg.dropped.await_pubrel_timeout": 0,
     "send_msg.qos0": 350, "send_msg.qos1": 49, "send_msg.qos2": 0,
     "send_msg.dropped": 0, "send_msg.dropped.expired": 0,
     "send_msg.dropped.queue_full": 0, "send_msg.dropped.too_large": 0,
     "seqno_q1_comm": 0, "seqno_q1_dup": 0, "seqno_q2_comm": 0,
     "seqno_q2_dup": 0, "seqno_q2_rec": 0},
]

JAWAB = {
    "/api/v5/cluster": {
        "description": "EMQX Cluster", "name": "emqx@127.0.0.1",
        "nodes": ["emqx1@127.0.0.1"], "self": "emqx1@127.0.0.1"},
    "/api/v5/cluster/topology": [
        {"core_node": "emqx1@127.0.0.1", "replicant_nodes": [],
         "streams": {}}],
    "/api/v5/nodes": [NODE],
    "/api/v5/monitor_current": {
        "actions_executed_rate": 0.0, "actions_messages_rate": 0.0,
        "cluster_sessions": 130, "connections": 128,
        "disconnected_durable_sessions": 0, "dropped_msg_rate": 0.0,
        "license_quota": 100000, "live_connections": 120,
        "persisted_rate": 0.0, "received_msg_rate": 12.5,
        "retained_msg_count": 3, "rules_matched_rate": 1.2,
        "sent_msg_rate": 10.1, "subscriptions": 45,
        "subscriptions_durable": 2, "topics": 30,
        "transformation_failed_rate": 0.0, "transformation_succeeded_rate": 1.2,
        "validation_failed_rate": 0.0, "validation_succeeded_rate": 0.0,
        "sessions_hist_hwmark": {"current_value": 10, "peak_time": 1,
                                  "peak_value": 10}},
    "/api/v5/alarms": {"data": [], "meta": {"count": 0, "hasnext": False,
                                             "limit": 100, "page": 1}},
    "/api/v5/clients": {
        "data": KLIEN,
        "meta": {"count": len(KLIEN), "hasnext": False, "limit": 1000,
                  "page": 1}},
    "/api/v5/clients/gw-meshtastic-01": KLIEN[0],
    "/api/v5/subscriptions": [
        {"clientid": "gw-meshtastic-01", "node": "emqx1@127.0.0.1",
         "topic": "msh/ID/2/e/4/#", "qos": 0, "nl": 0, "rap": 0, "rh": 0,
         "durable": False},
        {"clientid": "bot-notifikasi", "node": "emqx1@127.0.0.1",
         "topic": "msh/ID/2/e/json/$", "qos": 1, "nl": 0, "rap": 0, "rh": 0,
         "durable": False}],
    "/api/v5/topics": {
        "data": [{"node": "emqx1@127.0.0.1", "session": 1,
                   "topic": "msh/ID/2/e/4/#"}],
        "meta": {"count": 1, "hasnext": False, "limit": 1000, "page": 1}},
    "/api/v5/slow_subscriptions": {"data": []},
    "/api/v5/login": {"token": "token-uuji", "role": "administrator",
                       "license": {"edition": "enterprise"},
                       "password_expire_in_seconds": 3600},
}

ALARM_AKTIF = {"data": [{
    "name": "emqx_vm_memory_high_watermark",
    "node": "emqx1@127.0.0.1",
    "message": "memory usage is high",
    "activate_at": 1790000000, "deactivate_at": None, "duration": 12,
    "details": {}}], "meta": {"count": 1, "hasnext": False,
                                "limit": 100, "page": 1}}

HASIL = []


class Palsu(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        jalur = urllib.parse.urlparse(self.path).path
        if jalur == "/api/v5/login":
            jaw = JAWAB["/api/v5/login"]
        else:
            jaw = {"code": "NOT_FOUND", "message": "tidak ada"}
        badan = json.dumps(jaw).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(badan)))
        self.end_headers()
        self.wfile.write(badan)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        jalur = parsed.path
        if jalur == "/api/v5/clients" and parsed.query:
            kueri = dict(urllib.parse.parse_qsl(parsed.query))
            if int(kueri.get("page", "1")) >= 2:
                # halaman berikutnya: kosong, tidak ada lagi
                badan = json.dumps({"data": [], "meta": {
                    "count": len(KLIEN), "hasnext": False,
                    "limit": 1000, "page": 2}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(badan)))
                self.end_headers()
                self.wfile.write(badan)
                return
        jaw = JAWAB.get(jalur, {"code": "NOT_FOUND", "message": "tidak ada"})
        if jalur == "/api/v5/alarms" and getattr(self.server, "alarm", False):
            jaw = ALARM_AKTIF
        badan = json.dumps(jaw).encode()
        self.send_response(200 if jalur in JAWAB else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(badan)))
        self.end_headers()
        self.wfile.write(badan)


def jalankan(argv, alarm=False):
    """Jalankan emqx-monitor.main(argv) dengan URL palsu; kembalikan
    (kode keluar, keluaran stdout, keluaran stderr)."""
    import os
    os.environ["EMQX_URL"] = "http://127.0.0.1:%d" % SERVER.server_address[1]
    os.environ["EMQX_API_KEY"] = "kunci-uuji"
    out, err = io.StringIO(), io.StringIO()
    server = SERVER
    server.alarm = alarm
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        kode = emqx_monitor.main(argv)
    return kode, out.getvalue(), err.getvalue()


def periksa(nama, kondisi, keterangan=""):
    status = "LULUS" if kondisi else "GAGAL"
    HASIL.append(kondisi)
    print("  [%s] %s%s" % (status, nama,
                            (" -- " + keterangan) if (keterangan and not kondisi) else ""))


def main():
    global SERVER
    SERVER = HTTPServer(("127.0.0.1", 0), Palsu)
    threading.Thread(target=SERVER.serve_forever, daemon=True).start()

    print("1) ringkasan (bawaan)")
    kode, out, err = jalankan([])
    periksa("keluar 0 tanpa alarm", kode == 0, "kode=%r" % kode)
    periksa("nama cluster tampil", "emqx@127.0.0.1" in out)
    periksa("node tampil", "emqx1@127.0.0.1" in out)
    periksa("uptime diurai", "up 2d 03j 14m" in out, out[:200])
    periksa("laju pesan tampil", "12.5" in out and "10.1" in out)
    periksa("alarm 0 aktif", "ALARM (0 aktif)" in out)

    print("2) ringkasan dengan alarm aktif -> keluar 2")
    kode, out, err = jalankan([], alarm=True)
    periksa("keluar 2 saat ada alarm", kode == 2, "kode=%r" % kode)
    periksa("alarm tercetak", "emqx_vm_memory_high_watermark" in out)

    print("3) --daftar-klien")
    kode, out, err = jalankan(["--daftar-klien"])
    periksa("dua klien tampil", "gw-meshtastic-01" in out and "bot-notifikasi" in out)
    periksa("ip klien tampil", "192.168.20.31" in out)
    periksa("meta count tampil", "2 total" in out)

    print("4) --daftar-klien --semua (meta.hasnext dipakai)")
    JAWAB["/api/v5/clients"]["meta"]["hasnext"] = True
    kode, out, err = jalankan(["--daftar-klien", "--semua"])
    periksa("tetap dua klien (halaman berikutnya kosong)",
            out.count("gw-meshtastic-01") == 1, out[:120])
    JAWAB["/api/v5/clients"]["meta"]["hasnext"] = False

    print("5) --detail <clientid>")
    kode, out, err = jalankan(["--detail", "gw-meshtastic-01"])
    periksa("clientid tampil", "gw-meshtastic-01" in out)
    periksa("kelompok dasar", "Dasar:" in out)
    periksa("lalu lintas", "recv_msg" in out and "send_msg" in out)

    print("6) --langganan / --topik / --langganan-lambat")
    kode, out, err = jalankan(["--langganan"])
    periksa("topik langganan tampil", "msh/ID/2/e/4/#" in out)
    kode, out, err = jalankan(["--topik"])
    periksa("daftar topik tampil", "msh/ID/2/e/4/#" in out)
    kode, out, err = jalankan(["--langganan-lambat"])
    periksa("langganan lambat kosong tampil", "LANGGANAN LAMBAT (0)" in out)

    print("7) --metrik (format Prometheus)")
    kode, out, err = jalankan(["--metrik"])
    periksa("HELP/TYPE ada", "# HELP emqx_node_info" in out
            and "# TYPE emqx_node_info gauge" in out)
    periksa("metrik node uptime", "emqx_node_uptime_seconds{node=\"emqx1@127.0.0.1\"}" in out)
    periksa("uptime 2d 3h 14m 5s = 184445 dtk",
            any(l.startswith("emqx_node_uptime_seconds{") and l.endswith(" 184445.0")
                for l in out.splitlines()), out[:300])
    periksa("laju pesan", "emqx_received_msg_rate 12.5" in out)
    periksa("alarms_active 0", "emqx_alarms_active 0" in out)
    periksa("info klien", "emqx_client_info{" in out and 'clientid="gw-meshtastic-01"' in out)
    periksa("client_connected 1", "emqx_client_connected{clientid=\"gw-meshtastic-01\"" in out)

    print("8) --metrik dengan alarm aktif")
    kode, out, err = jalankan(["--metrik"], alarm=True)
    periksa("emqx_alarms_active 1", "emqx_alarms_active 1" in out)
    periksa("emqx_alarm_info ada", "emqx_alarm_info{" in out)

    print("9) --watch --putaran 2")
    kode, out, err = jalankan(["--watch", "0", "--putaran", "2"])
    periksa("dua putaran", out.count("Cluster    :") == 2, out[:200])

    print("10) galat: klien tak dikenal")
    kode, out, err = jalankan(["--detail", "tidak-ada"])
    periksa("detail kosong tidak meruntuhkan", kode in (0, 1))

    SERVER.shutdown()
    lulus = sum(1 for h in HASIL if h)
    print("\n%d/%d uji lulus" % (lulus, len(HASIL)))
    return 0 if lulus == len(HASIL) else 1


if __name__ == "__main__":
    sys.exit(main())
