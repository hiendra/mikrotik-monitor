#!/bin/sh
# ============================================================
# mula.sh - entrypoint container tm-auth
# ============================================================
# Volume /data dibuat Docker sebagai root:root, sementara server
# harus berjalan sebagai pengguna non-root "node". Tanpa chown ini
# server crash EACCES saat menulis pengguna.json (pernah terjadi:
# container restart-loop dan /api/health menjawab 502).
#
# Urutan: chown sekali di awal -> turun privilige via su-exec ->
# jalankan server. Bila chown gagal, container berhenti keras
# (set -e) supaya kegagalan tidak disembunyikan.
# ============================================================
set -e

mkdir -p /data
chown -R node:node /data

exec su-exec node node server.mjs
