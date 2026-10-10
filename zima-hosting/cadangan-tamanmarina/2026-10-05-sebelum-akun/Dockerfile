# ============================================================
# tm-auth - API akun & sesi warga tamanmarina.my.id
# ============================================================
# Sengaja TANPA dependensi npm (hanya modul bawaan node:), jadi
# build tidak membutuhkan jaringan dan image tetap kecil.
# Data pengguna/sesi/audit disimpan di volume /data (dipasang
# docker-compose.yml), bukan di dalam image.
#
# Container ini TIDAK menerbitkan port ke host - hanya Caddy
# (web-router) yang menghubunginya lewat network `web`:
#   reverse_proxy tm-auth:3000
# ============================================================

FROM node:22-alpine

ENV NODE_ENV=production
WORKDIR /app

COPY izin.mjs penyimpanan.mjs server.mjs ./

# Akun non-root "node" sudah tersedia di image resmi.
USER node

EXPOSE 3000

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD wget -qO /dev/null http://127.0.0.1:3000/api/health || exit 1

CMD ["node", "server.mjs"]
