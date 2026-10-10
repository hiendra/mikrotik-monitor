# ============================================================
# tm-auth - API akun & sesi warga tamanmarina.my.id
# ============================================================
# Sengaja TANPA dependensi npm (hanya modul bawaan node:), jadi
# build tidak butuh jaringan npm dan image tetap kecil.
# Data pengguna/audit disimpan di volume /data (lihat
# docker-compose.yml), bukan di dalam image.
#
# Container ini TIDAK menerbitkan port ke host - hanya Caddy
# (web-router) yang menghubunginya lewat network `web`:
#   reverse_proxy tm-auth:3000
#
# PENTING: proses berjalan sebagai root HANYA untuk `chown /data`
# di mula.sh (volume Docker = root:root, user node tidak bisa
# menulis -> EACCES crash), lalu langsung turun privilige ke user
# `node` via su-exec sebelum server.start().
# ============================================================

FROM node:22-alpine

ENV NODE_ENV=production
WORKDIR /app

# su-exec: pemindah privilige kecil & andal (dipakai entrypoint).
RUN apk add --no-cache su-exec

COPY izin.mjs penyimpanan.mjs server.mjs mula.sh ./

EXPOSE 3000

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD wget -qO /dev/null http://127.0.0.1:3000/api/health || exit 1

# sh -c tanpa argumen tambahan: seluruh perintah ada di dalam berkas.
ENTRYPOINT ["sh", "/app/mula.sh"]
