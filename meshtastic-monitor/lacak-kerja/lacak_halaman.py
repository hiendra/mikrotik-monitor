#!/usr/bin/env python3
"""Halaman HTML tab 'Tracking Node': peta Leaflet + playback riwayat posisi.

Dua halaman diturunkan dari modul ini:

  halaman_daftar()  daftar node yang punya histori (tab Tracking Node)
  halaman_node()    satu node: peta, garis rute, playback, titik singgah

Kedua halaman memakai palet yang sama dengan halaman monitoring
(Meshnode-ID Monitor) supaya tab tidak terlihat seperti situs lain, dan
memakai Leaflet 1.9.4 yang disajikan sendiri (/leaflet/...) supaya halaman
tetap jalan di jaringan lokal tanpa akses ke CDN.

Semua data dihitung server-side (lihat lacak_node.susun_lacak) lalu dikirim
sebagai satu objek JSON yang ditanam di <script>. Peramban tidak
perlu menghitung apa pun: tugasnya hanya menggambar dan menganimasikan.
"""

import json
import time

from lacak_node import _wib_berlabel, _wib_pendek, posisi_bersih, WIB

# ------------------------------------------------------------------ CSS

# Warna disalin dari halaman monitoring (/). Tab harus terasa satu situs.
PALET = """
:root{
  color-scheme:dark;
  --bg:#0f1319; --surf:#1a212b; --surf2:#202836; --border:#2a3340;
  --teks:#e6edf3; --redup:#8b98a8; --samar:#5a6675;
  --aksen:#58a6ff; --hijau:#3fb950; --kuning:#e3b341; --merah:#f85149;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--teks);
     font:13.5px/1.5 system-ui,Segoe UI,Roboto,sans-serif;margin:0;padding:16px 20px 40px;
     max-width:1600px}
a{color:var(--aksen)}
.dim{color:var(--redup);font-size:12px}
.mono{font-family:ui-monospace,Consolas,monospace}

/* Tab: satu baris tab, tab aktif ditandai garis bawah accent. Dipakai
   oleh halaman monitoring dan kedua halaman lacak, supaya perpindahan tab
   terasa seperti satu aplikasi. */
.tabbar{display:flex;gap:4px;border-bottom:1px solid var(--border);margin:0 0 16px;
        overflow-x:auto;-webkit-overflow-scrolling:touch}
.tabbar a{display:block;padding:9px 14px;color:var(--redup);text-decoration:none;
          font-size:13.5px;white-space:nowrap;border-bottom:2px solid transparent}
.tabbar a:hover{color:var(--teks)}
.tabbar a.aktif{color:var(--teks);border-bottom-color:var(--aksen);font-weight:600}

.kepala{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;
        justify-content:space-between;padding-bottom:12px}
.merek{display:flex;align-items:center;gap:12px}
.logo{width:42px;height:42px;flex:0 0 auto;display:block}
h1{font-size:19px;margin:0 0 3px}
h2{font-size:14px;margin:22px 0 10px;border-bottom:1px solid #24303c;padding-bottom:7px;
   text-transform:uppercase;letter-spacing:.06em;color:#9fb0c3}

.kartu{display:grid;grid-template-columns:repeat(auto-fit,minmax(134px,1fr));gap:10px;margin:14px 0 4px}
.kotak{background:var(--surf);border:1px solid var(--border);border-radius:10px;padding:10px 14px}
.kotak b{display:block;font-size:22px;line-height:1.25;font-variant-numeric:tabular-nums}
.kotak span{color:var(--redup);font-size:11.5px}

.tata{display:grid;grid-template-columns:1fr minmax(270px,350px);gap:16px}
@media (max-width:900px){.tata{grid-template-columns:1fr}}
.panel{background:var(--surf);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.panel h2{margin:0;padding:12px 15px;font-size:13px;border-bottom:1px solid var(--border);
          text-transform:none;letter-spacing:0}
#peta{height:560px;width:100%;background:var(--surf2);position:relative}
#singgah{max-height:560px;overflow-y:auto}

/* Gaya popup Leaflet disamakan dengan palet di atas; bawaan putih terlihat
   seperti halaman lain di tengah tema gelap. */
.leaflet-container{background:var(--surf2);font:inherit}
.leaflet-popup-content-wrapper,.leaflet-popup-tip{background:var(--surf2);color:var(--teks)}
.leaflet-popup-content{margin:9px 12px;font-size:12px}
.leaflet-control-attribution{background:rgba(26,33,43,.85)!important;color:var(--samar)!important;
                             font-size:10px!important}
.leaflet-control-attribution a{color:var(--redup)!important}
.leaflet-bar a{background:var(--surf);color:var(--teks);border-color:var(--border)}
.leaflet-bar a:hover{background:var(--surf2);color:var(--aksen)}

/* Panel kendali playback di bawah peta. */
.kendali{display:flex;align-items:center;gap:12px;padding:11px 15px;border-top:1px solid var(--border)}
.kendali button{background:#1d3557;color:#79c0ff;border:1px solid #2c3641;border-radius:8px;
                width:34px;height:34px;font-size:15px;cursor:pointer;flex-shrink:0}
.kendali button:hover{background:#2a4670;color:#cfe6ff}
.kendali button.aktif{background:var(--aksen);color:#06101c;border-color:var(--aksen)}
.kendali input[type=range]{flex:1;accent-color:var(--aksen);min-width:80px}
.kendali select{background:var(--surf2);color:var(--teks);border:1px solid var(--border);
                border-radius:6px;padding:4px 6px;font:inherit}

/* Speedometer + kompas menempel di pojok kanan atas peta. */
#alat{position:absolute;top:12px;right:12px;z-index:500;display:flex;gap:10px;
      pointer-events:none}
.gauge{background:rgba(26,33,43,.88);border:1px solid var(--border);border-radius:10px;
       padding:8px 10px;text-align:center;box-shadow:0 4px 14px rgba(0,0,0,.35)}
.gauge .g-label{font-size:9px;letter-spacing:.5px;color:var(--samar);
                text-transform:uppercase;margin-bottom:2px}
#speedo{font-size:20px;font-weight:700;color:var(--hijau);font-variant-numeric:tabular-nums;line-height:1}
#speedo-satuan{font-size:10px;color:var(--redup)}
.mawar{width:46px;height:46px;border-radius:50%;border:1px solid var(--border);
       background:var(--surf2);position:relative;margin:0 auto}
.mawar .tik{position:absolute;font-size:8px;color:var(--samar);font-weight:600}
.mawar .tik.u{top:1px;left:50%;transform:translateX(-50%);color:var(--hijau)}
.mawar .tik.t{top:50%;right:2px;transform:translateY(-50%)}
.mawar .tik.s{bottom:1px;left:50%;transform:translateX(-50%)}
.mawar .tik.b{top:50%;left:2px;transform:translateY(-50%)}
#jarum{position:absolute;top:50%;left:50%;width:2px;height:17px;
       background:linear-gradient(#f0665a 50%,var(--samar) 50%);
       transform-origin:50% 100%;transform:translate(-50%,-100%) rotate(0deg);border-radius:1px}
#arah-teks{font-size:10px;color:var(--redup);margin-top:3px;font-variant-numeric:tabular-nums}

/* Balon yang menempel pada marker posisi saat ini. */
.balon{background:var(--surf);color:var(--teks);border:1px solid var(--border);border-radius:10px;
       padding:6px 10px;font-size:12px;line-height:1.5;box-shadow:0 4px 14px rgba(0,0,0,.35);
       white-space:nowrap;font-variant-numeric:tabular-nums}
.balon::before{border-top-color:var(--border)!important}
.balon .b-nama{font-weight:700;color:var(--aksen)}
.balon .b-kecepatan{font-weight:700;color:var(--hijau)}

/* Baris singgah: diklik untuk melompat ke waktu itu di playback. */
.baris{display:flex;align-items:flex-start;gap:10px;padding:9px 15px;
       border-bottom:1px solid var(--border);cursor:pointer}
.baris:last-child{border-bottom:none}
.baris:hover{background:var(--surf2)}
.baris.aktif{background:var(--surf2)}
.baris .titik{width:9px;height:9px;border-radius:50%;background:var(--samar);flex-shrink:0;margin-top:5px}
.baris.aktif .titik{background:var(--hijau)}
.baris .waktu{font-size:12.5px;font-variant-numeric:tabular-nums;flex:0 0 128px}
.baris .meta{font-size:11.5px;color:var(--redup)}

/* Tabel daftar node pada tab Tracking. */
.gulir{overflow:auto;max-height:74vh;background:var(--surf);border:1px solid #232c38;border-radius:10px}
table{width:100%;border-collapse:separate;border-spacing:0;font-size:12.5px}
th,td{padding:6px 9px;text-align:left;border-bottom:1px solid #232c38;white-space:nowrap}
thead th{position:sticky;top:0;z-index:2;background:var(--surf2);color:#9fb0c3;font-size:11px;
         text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid #2f3b4a}
tbody tr:nth-child(even){background:#1d252e}
tbody tr:hover{background:#26303c}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
td.nama{white-space:normal;min-width:150px;max-width:260px;overflow-wrap:anywhere}
.on{color:var(--hijau);font-weight:600}.off{color:var(--merah);font-weight:600}
.favorit{color:var(--kuning)}
.tag{display:inline-block;background:#21323f;color:#79c0ff;border-radius:4px;padding:1px 6px;
     font-size:11px;white-space:nowrap}
.via{display:inline-block;border-radius:4px;padding:1px 7px;font-size:10.5px;font-weight:600;
     letter-spacing:.04em}
.via-diri{background:#1d3557;color:#79c0ff}
.via-lora{background:#173a24;color:#56d364}
.via-mqtt{background:#2b3038;color:#9fb0c3}
input[type=search]{background:var(--surf);border:1px solid var(--border);color:var(--teks);
                   border-radius:8px;padding:8px 12px;width:280px;font:inherit}
input[type=search]:focus{outline:none;border-color:#3d5a80}
.peringatan{background:#3d1d1d;border:1px solid var(--merah);color:#ffb3ad;padding:10px 14px;
            border-radius:8px;margin:12px 0}
.info{background:#16232e;border:1px solid #2a3340;color:#9fb0c3;padding:10px 14px;
      border-radius:8px;margin:12px 0;font-size:12.5px}
.kaki{margin-top:22px;padding-top:12px;border-top:1px solid #24303c}

/* Tab Live Map: peta penuh di atas, daftar ringkas node yang bisa dicari di
   bawahnya. Marker memakai divIcon (titik CSS) supaya tidak perlu berkas
   gambar PNG per warna. */
#peta{height:clamp(360px,62vh,760px);width:100%;background:var(--surf2);position:relative}
.pin{display:block;width:13px;height:13px;border-radius:50%;
     border:2px solid rgba(0,0,0,.55);box-shadow:0 1px 4px rgba(0,0,0,.5)}
.pin-on{background:var(--hijau)}
.pin-off{background:var(--samar)}
.pin-gw{background:var(--aksen);width:16px;height:16px;border-color:#fff}
/* Isi popup: dua kolom label/nilai, nilai boleh membungkus supaya ID yang
   panjang tidak memaksa popup melebar melewati layar. */
.pop-judul{font-size:13px;font-weight:700;margin-bottom:5px;overflow-wrap:anywhere}
.pop-id{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--redup);
        margin-bottom:7px;overflow-wrap:anywhere}
.pop-tab{border-collapse:collapse;width:100%;font-size:11.5px}
.pop-tab th{text-align:left;color:var(--redup);font-weight:500;padding:2px 10px 2px 0;
            white-space:nowrap;vertical-align:top;border:0;background:none;text-transform:none;
            letter-spacing:0;font-size:11.5px}
.pop-tab td{padding:2px 0;vertical-align:top;overflow-wrap:anywhere;
            font-variant-numeric:tabular-nums}
.pop-aksi{margin-top:9px;display:inline-block;background:#1d3557;color:#79c0ff;
          border-radius:7px;padding:5px 11px;font-size:11.5px;text-decoration:none;
          white-space:nowrap;font-weight:600}
.pop-aksi:hover{background:#2a4670;color:#cfe6ff}
.legenda{display:flex;flex-wrap:wrap;gap:14px;margin:10px 0 2px;font-size:11.5px;
         color:var(--redup);align-items:center}
.legenda i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;
          vertical-align:-1px}
/* Label nama node: ditulis langsung di peta supaya tidak perlu diklik dulu.
   Latar gelap separuh tembus menjaga nama tetap terbaca di atas peta yang
   ramai warna, dan pointer-events dimatikan supaya label tidak menutupi
   marker yang ada di belakangnya. Lebar dibatasi + elipsis karena nama
   perangkat bisa sangat panjang; nama utuhnya tetap ada di popup. */
.leaflet-tooltip.label-node{background:rgba(13,17,23,.84);color:#e6edf3;
  border:1px solid #39424f;border-radius:6px;padding:1px 6px;font-size:11px;
  font-weight:500;line-height:1.4;max-width:150px;overflow:hidden;
  text-overflow:ellipsis;box-shadow:0 1px 4px rgba(0,0,0,.6);pointer-events:none}
.leaflet-tooltip.label-node::before{display:none}
/* Begitu kursor menyentuh satu marker, labelnya dinaikkan dan diberi warna
   aksen: di area padat (Bandung/Surabaya) label bertumpuk, dan tanpa ini
   nama yang sedang ditunjuk justru yang paling sulit dibaca. */
.leaflet-tooltip.label-node.label-naik{background:var(--aksen);color:#0d1117;
  border-color:#0d1117;font-weight:700}
.peta-tanpa-nama .leaflet-tooltip{display:none}
.saklar-nama{display:inline-flex;align-items:center;gap:5px;cursor:pointer;
             user-select:none;margin-left:auto}
.saklar-nama input{accent-color:var(--aksen);margin:0;cursor:pointer}
"""


def _esc(nilai):
    """Escape untuk teks HTML. Nama node berasal dari perangkat, jadi bisa
    memuat tanda kutip, kurung siku, atau bahkan </script>."""
    if nilai is None:
        return "-"
    s = str(nilai)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))


def _json_aman(data):
    """JSON untuk ditanam di dalam <script>.

    Dua hal dihitung di sini:
      1. '<' diganti \\u003c, supaya data tidak pernah bisa menutup tag <script>
         (nama node dari perangkat adalah input tak tepercaya);
      2. '>' diganti \\u003e agar urutan ']]>' atau '</' tidak pernah muncul
         di dalam literal JavaScript.
    """
    teks = json.dumps(data, ensure_ascii=False, allow_nan=False)
    return (teks.replace("<", "\\u003c").replace(">", "\\u003e")
               .replace("&", "\\u0026"))


# (nama kunci, jalur, label). Dulu ditulis sebagai format string dengan satu
# placeholder per tab; menambah tab berarti menambah placeholder lagi, jadi
# sekarang tabel dulu lalu dibentuk perulangan.
TAB_TAUTAN = (
    ("monitor", "/", "&#127968; Monitoring"),
    ("peta", "/peta", "&#128205; Live Map"),
    ("lacak", "/lacak", "&#128205; Tracking Node"),
)


def _tabbar(tab):
    return '<nav class="tabbar">%s</nav>' % "".join(
        '<a href="%s"%s>%s</a>' % (href, ' class="aktif"' if kunci == tab else "", label)
        for kunci, href, label in TAB_TAUTAN)


def _kepala(judul, sub, gambar=True, logo="/logo.png", judul_html=False):
    # judul_html=True berarti pemanggil melewatkan escaping dan hanya boleh dipakai
    # untuk markup statis milik halaman ini sendiri (mis. span kosong yang
    # diisi lewat JS). Data dari node SELALU lewat _esc.
    g = ('<img class="logo" src="%s" width="42" height="42" alt="Logo">' % logo) if gambar else ""
    return (
        '<div class="kepala"><div class="merek">%s<div><h1>%s</h1>'
        '<div class="dim">%s</div></div></div></div>'
        % (g, judul if judul_html else _esc(judul), sub)
    )


# ------------------------------------------------------------------ JS

# Logika playback di bawah mengikuti pola halaman pemantauan live yang pernah
# dibuat sebagai acuan tampilan ini, dengan dua penyesuaian untuk data node
# Meshtastic:
#   - legs (i0/i1) datang dari server, sehingga interpolasi memakai indeks
#     rute yang sama persis dengan yang dihitung server;
#   - tidak ada asumsi "bot", jadi tidak ada asumsi bahwa node adalah "bot" - nama dan koordinat ditampilkan apa adanya.
JS_LACAK = r"""
const DATA = __DATA__;
const map = L.map('peta', {zoomControl:true});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            {attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>', maxZoom:19})
  .addTo(map);

// fitBounds pada container yang belum berukuran menghasilkan zoom rusak
// (max-zoom di bbox nasional). Ukuran dicek ulang sampai benar.
function saatTerukur(f) {
  map.invalidateSize();
  const s = map.getSize();
  if (s.x > 0 && s.y > 0) { f(); return; }
  setTimeout(() => saatTerukur(f), 30);
}

// Garis rute penuh: hijau terang, tebal tipis supaya marker tetap terlihat di atasnya.
const garis = L.polyline(DATA.route, {color:'#3fb950', weight:3, opacity:0.5}).addTo(map);

// Nama node berasal dari perangkat (input tak tepercaya), jadi
// SELALU di-escape sebelum disisipkan ke HTML tooltip/popup. Di
// halaman monitoring nama diisi lewat textContent; di sini tooltip
// dan popup dibangun sebagai HTML, jadi escaping-nya eksplisit.
function escHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
const NAMA_NODE = escHtml(DATA.nama || DATA.node_id);

// Titik singgah: lingkaran kecil abu-abu, diklik membuka ringkasan.
// Popup diawali identitas node (nama + ID) supaya popup tetap jelas
// milik node mana ketika halaman dibuka dari tautan/bookmark.
DATA.stops.forEach((s, i) => {
  const warna = s.sintetis ? '#58a6ff' : '#93a3b4';
  L.circleMarker([s.lat, s.lon], {radius:5, color:warna, fillColor:warna, fillOpacity:0.85})
    .addTo(map)
    .bindPopup('<div class="pop-judul">' + NAMA_NODE + '</div>'
               + '<div class="pop-id">' + escHtml(DATA.node_id) + '</div>'
               + '<b>' + s.label + '</b><br>' + s.lat.toFixed(5) + ', ' + s.lon.toFixed(5)
               + (s.alt == null ? '' : '<br>&#9468; ' + Math.round(s.alt) + ' m')
               + (s.sintetis ? '<br><span style="color:#8b98a8">ujung rute</span>'
                             : '<br>&#9201; diam ' + s.durasi_jam + ' jam'));
});

// Marker posisi saat ini: merah, tepi putih - kontras dengan semua yang lain.
const marker = L.circleMarker(DATA.route[0],
  {radius:8, color:'#fff', weight:2, fillColor:'#f0665a', fillOpacity:1}).addTo(map);
marker.bindTooltip('', {permanent:true, direction:'top', offset:[0,-10], className:'balon'});

// Panjang kumulatif rute (meter) untuk interpolasi berbasis panjang busur:
// posisi dianimasi sejauh proportionate yang ditempuh, bukan sejauh fraksi
// indeks, supaya kecepatan animasi tidak meledak di bagian rute yang rapat.
const cum = [0];
for (let i = 1; i < DATA.route.length; i++) {
  cum.push(cum[i-1] + jarak(DATA.route[i-1], DATA.route[i]));
}
const totalPanjang = cum[cum.length-1] || 1;

function jarak(a, b) {
  const R = 6371000, rad = d => d * Math.PI / 180;
  const dLat = rad(b[0]-a[0]), dLon = rad(b[1]-a[1]);
  const h = Math.sin(dLat/2)**2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLon/2)**2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function arah(a, b) {
  const rad = d => d * Math.PI / 180, deg = r => r * 180 / Math.PI;
  const f1 = rad(a[0]), f2 = rad(b[0]), dLon = rad(b[1]-a[1]);
  const y = Math.sin(dLon) * Math.cos(f2);
  const x = Math.cos(f1) * Math.sin(f2) - Math.sin(f1) * Math.cos(f2) * Math.cos(dLon);
  return (deg(Math.atan2(y, x)) + 360) % 360;
}

// Titik pada jarak tertentu (meter) sepanjang rute, beserta arah gerak.
function titikPadaJarak(target) {
  if (target <= 0) return {titik: DATA.route[0], arah: null};
  if (target >= totalPanjang) return {titik: DATA.route[DATA.route.length-1], arah: null};
  for (let j = 1; j < cum.length; j++) {
    if (cum[j] >= target) {
      const seg = cum[j] - cum[j-1];
      const f = seg === 0 ? 0 : (target - cum[j-1]) / seg;
      return {
        titik: [DATA.route[j-1][0] + (DATA.route[j][0]-DATA.route[j-1][0])*f,
                DATA.route[j-1][1] + (DATA.route[j][1]-DATA.route[j-1][1])*f],
        arah: seg === 0 ? null : arah(DATA.route[j-1], DATA.route[j])
      };
    }
  }
  return {titik: DATA.route[DATA.route.length-1], arah: null};
}

// ---- Linimasa playback ------------------------------------------------
//
// Peta playback dibagi dua jenis segmen:
//   hold - node diam di satu singgah (menampilkan titik singgah)
//   move - node berpindah dari singgah ke singgah berikutnya
//
// Lamanya animasi TIDAK memakai waktu riil, karena riwayat bisa berdurasi
// berjam-jam: 40 jam Animasi memutar 40 jam akan membosankan. Yang dipakai:
//   - 12% dari total waktu animasi dibagi rata ke semua singgah (node diam);
//   - 88% dibagi menurut durasi kaki sebenarnya, dengan batas bawah 35%
//     agar kaki yang sangat singkat tetap terlihat (perbaikan yang sama
//     dipakai halaman pantau: tanpa batas bawah playback terlihat melompat).
const HOLD_PORSI = 0.12;
const BAWAAN_KAKI = 0.35;
const DETIK_PLAYBACK = 28;   // satu putaran penuh dikompres jadi ~28 detik

const kp = DATA.stops, legs = DATA.legs;
const linimasa = [];
let kursor = 0;
if (kp.length) {
  const holdTotal = HOLD_PORSI;
  const moveTotal = 1 - HOLD_PORSI;
  const perHold = holdTotal / kp.length;

  // Durasi kaki riil -> porsi animasi, dengan batas bawah per kaki.
  const durKaki = legs.map(l => Math.max(l.dur, 1));
  const totalDur = durKaki.reduce((a,b) => a+b, 0) || 1;
  const sama = 1 / Math.max(legs.length, 1);
  const kasar = durKaki.map(d => Math.max(d / totalDur, BAWAAN_KAKI * sama));
  const jumlahKasar = kasar.reduce((a,b) => a+b, 0) || 1;
  const porsi = kasar.map(k => k / jumlahKasar);

  for (let i = 0; i < kp.length; i++) {
    linimasa.push({t0:kursor, t1:kursor + perHold, jenis:'hold', idx:i});
    kursor += perHold;
    if (i < legs.length) {
      const d = moveTotal * porsi[i];
      linimasa.push({t0:kursor, t1:kursor + d, jenis:'move', idx:i});
      kursor += d;
    }
  }
}
const totalAnim = kursor || 1;

// Panjang setiap kaki (meter) dihitung dari indeks rute yang dikembalikan server.
const panjangKaki = legs.map(l => cum[Math.min(l.i1, cum.length-1)] - cum[Math.min(l.i0, cum.length-1)]);
const totalPanjangKaki = panjangKaki.reduce((a,b) => a+b, 0) || 1;

function keadaan(p) {
  const waktu = p * totalAnim;
  const s = linimasa.find(x => waktu <= x.t1) || linimasa[linimasa.length-1];
  if (!s) return {titik: DATA.route[0], kmh: 0, arah: null, aktif: 0, ts: kp[0].t0};
  if (s.jenis === 'hold') {
    const k = kp[s.idx];
    return {titik: [k.lat, k.lon], kmh: 0, arah: null, aktif: s.idx, ts: k.t0};
  }
  const leg = legs[s.idx];
  const f = s.t1 === s.t0 ? 1 : (waktu - s.t0) / (s.t1 - s.t0);
  const mulai = cum[Math.min(leg.i0, cum.length-1)];
  const panjang = panjangKaki[s.idx];
  const {titik, arah: a} = titikPadaJarak(mulai + panjang * f);
  const dur = Math.max(leg.dur, 1);
  return {
    titik: titik,
    // Kecepatan dibatasi 300 km/j: node yang "terlompat" jauh karena gap
    // posisi yang hilang (mis. node offline lama) akan menampilkan angka
    // ribuan km/j yang menyesatkan.
    kmh: Math.min(300, leg.kmh),
    arah: a,
    aktif: s.idx + 1,
    ts: leg.t0 + dur * f
  };
}

// ---- Kontrol ----------------------------------------------------------
let posisi = 0, berjalan = true, ikuti = false, terakhirTs = null;
const btnMain = document.getElementById('main');
const slider = document.getElementById('geser');
const pilih = document.getElementById('cepat');
const speedo = document.getElementById('speedo');
const jarum = document.getElementById('jarum');
const arahTeks = document.getElementById('arah-teks');
const ARAH = ['U','TL','T','TG','S','BD','B','BL'];
let arahTerakhir = 0;

// Zooman/panning oleh pengguna membatalkan mode ikuti dan jam animasi, supaya
// penanda tidak meloncat lagi setelah selesai zooming.
let sedangZoom = false;
map.on('zoomstart', () => { sedangZoom = true; });
map.on('zoomend', () => { sedangZoom = false; terakhirTs = null; gambar(posisi); });
map.on('dragstart', () => { ikuti = false; document.getElementById('fokus').classList.remove('aktif'); });

function gambar(p) {
  const k = keadaan(p);
  if (!sedangZoom) {
    marker.setLatLng(k.titik);
    if (ikuti) map.panTo(k.titik, {animate:false});
  }
  marker.setTooltipContent('<span class="b-nama">' + NAMA_NODE + '</span><br>'
                           + wib(k.ts)
                           + '<br><span class="b-kecepatan">' + k.kmh.toFixed(1) + ' km/j</span>');
  slider.value = Math.round(p * 1000);
  document.querySelectorAll('.baris').forEach(b => {
    b.classList.toggle('aktif', Number(b.dataset.idx) === k.aktif);
  });
  speedo.textContent = k.kmh.toFixed(1);
  if (k.arah !== null) arahTerakhir = k.arah;
  jarum.style.transform = 'translate(-50%,-100%) rotate(' + arahTerakhir + 'deg)';
  arahTeks.textContent = k.kmh > 0.5
    ? ARAH[Math.round(arahTerakhir / 45) % 8] + ' · ' + Math.round(arahTerakhir) + '°'
    : 'diam';
}

function bingkai(ts) {
  if (!berjalan) return;
  const dt = (ts - (terakhirTs === null ? ts : terakhirTs)) / 1000;
  terakhirTs = ts;
  posisi += (dt / DETIK_PLAYBACK) * parseFloat(pilih.value);
  if (posisi >= 1) posisi -= 1;
  gambar(posisi);
  requestAnimationFrame(bingkai);
}

btnMain.addEventListener('click', () => {
  berjalan = !berjalan;
  btnMain.textContent = berjalan ? '❚❚' : '▶';
  btnMain.classList.toggle('aktif', berjalan);
  if (berjalan) { terakhirTs = null; requestAnimationFrame(bingkai); }
});
document.getElementById('fokus').addEventListener('click', function () {
  ikuti = !ikuti;
  this.classList.toggle('aktif', ikuti);
  if (ikuti) map.flyTo(marker.getLatLng(), Math.max(map.getZoom(), 14));
});
slider.addEventListener('input', () => {
  berjalan = false;
  btnMain.textContent = '▶';
  btnMain.classList.remove('aktif');
  posisi = Number(slider.value) / 1000;
  gambar(posisi);
});
document.querySelectorAll('.baris').forEach(b => {
  b.addEventListener('click', () => {
    const s = linimasa.find(x => x.jenis === 'hold' && x.idx === Number(b.dataset.idx));
    if (!s) return;
    berjalan = false;
    btnMain.textContent = '▶';
    btnMain.classList.remove('aktif');
    posisi = s.t0 / totalAnim;
    gambar(posisi);
    map.panTo([kp[s.idx].lat, kp[s.idx].lon]);
  });
});

// Teks "Tracking Node — " sudah ada di markup server; isian span ini hanya
// nama node. Ditulis lewat textContent (bukan innerHTML) supaya nama dari
// gateway tidak pernah jadi markup.
document.getElementById('judul').textContent = DATA.nama;
document.getElementById('sub').textContent =
  DATA.nama + ' · ' + DATA.node_id + ' · ' + DATA.date_range;

const kartu = [
  ['JARAK TOTAL', DATA.stats.dist_km + ' km'],
  ['TITIK SINGGAH', DATA.stats.stops],
  ['DURASI', DATA.stats.duration_h + ' jam'],
  ['KECEPATAN RATA2', DATA.stats.avg_speed + ' km/j'],
  ['PERIODE LOG', DATA.date_range]
];
document.getElementById('kartu').innerHTML = kartu.map(([l, v], i) =>
  '<div class="kotak"><b' + (i === 4 ? ' style="font-size:13px;line-height:1.35"'
                                 : '') + '>' + v + '</b><span>' + l + '</span></div>').join('');

document.getElementById('singgah').innerHTML = kp.map((s, i) =>
  '<div class="baris" data-idx="' + i + '"><div class="titik"></div>'
  + '<div><div class="waktu">' + s.label + '</div>'
  + '<div class="meta">' + s.lat.toFixed(5) + ', ' + s.lon.toFixed(5)
  + (s.alt == null ? '' : ' · ⛰ ' + Math.round(s.alt) + ' m')
  + (s.sintetis ? ' · ujung rute' : ' · diam ' + s.durasi_jam + ' jam')
  + '</div></div></div>').join('');

saatTerukur(() => map.fitBounds(DATA.bounds, {padding:[24, 24]}));
gambar(0);
requestAnimationFrame(bingkai);

function wib(epoch) {
  return new Date(epoch * 1000).toLocaleString('id-ID', {
    timeZone: 'Asia/Jakarta', day: '2-digit', month: 'short',
    hour: '2-digit', minute: '2-digit'
  });
}
"""

# Peta tab Live Map. Isi popup dirakit di Python (lihat _pop_up_node) supaya
# nama node yang berasal dari perangkat SELALU ikut di-escape di satu tempat;
# di sini tidak ada interpolasi data node ke dalam HTML - yang masuk ke DOM
# cuma lat/lon (number dari server) dan string popup yang sudah di-escape.
#
# Penanda gateway berasal dari field "gw" hasil Python, bukan dari urutan
# array: urutan isi peta bergantung pada urutan bacaan NodeDB sehingga tidak
# boleh dijadikan penanda.
JS_PETA = r"""
(function(){
  var titik = __TITIK__;
  var peta = L.map('peta', {zoomControl:true}).setView([0,0], 2);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
              {maxZoom:19, attribution:'&copy; OpenStreetMap'}).addTo(peta);
  // Label marker butuh elemen DOM-nya; ambil lewat objek tooltip Leaflet dan
  // jangan menganggap elemennya selalu sudah ada (tooltip permanen dibuat
  // saat marker masuk peta, bukan saat bindTooltip dipanggil).
  function labelMarker(m){
    try{
      var tl = m.getTooltip();
      return tl ? tl.getElement() : null;
    }catch(e){ return null; }
  }
  function sorotLabel(m, nyala){
    var el = labelMarker(m);
    if(!el || !el.classList){ return; }
    if(nyala){ el.classList.add('label-naik'); } else { el.classList.remove('label-naik'); }
  }
  var semua = [];
  for(var i=0;i<titik.length;i++){
    var t = titik[i], m;
    if(t.gw){
      m = L.marker([t.lat,t.lon], {icon: L.divIcon({className:'', iconSize:[16,16],
            html:'<span class="pin pin-gw"></span>'})});
    } else {
      m = L.circleMarker([t.lat,t.lon], {radius:6, weight:2, color:'rgba(0,0,0,.55)',
            fillColor: t.on ? '#3fb950' : '#5a6675', fillOpacity:0.95});
    }
    m.bindPopup(t.popup, {maxWidth:320, autoPanPadding:[24,24]});
    // Nama node ditulis langsung di peta supaya tidak perlu diklik dulu untuk
    // tahu siapa yang di mana. permanen = tidak menunggu kursor, interactive
    // = false supaya label tidak menghalangi klik ke marker di belakangnya.
    if(t.nama){ m.bindTooltip(t.nama, {permanent:true, direction:'right',
          offset:[9,0], className:'label-node', interactive:false}); }
    m.on('mouseover', function(){ sorotLabel(this, true); });
    m.on('mouseout', function(){ sorotLabel(this, false); });
    m.addTo(peta);
    semua.push([t.lat,t.lon]);
  }
  // Saklar label: di area padat label bertumpuk, jadi harus bisa dimatikan.
  // Pilihannya diingat per tab supaya muat ulang tidak mengembalikannya ke
  // keadaan bawaan.
  (function(){
    var saklar = document.getElementById('saklar-nama');
    if(!saklar){ return; }
    var KUNCI_SAKLAR = 'meshid-peta-nama-1';
    try{
      if(sessionStorage.getItem(KUNCI_SAKLAR) === '0'){ saklar.checked = false; }
    }catch(e){}
    function terapkan(){
      var kotak = document.getElementById('peta');
      if(!kotak || !kotak.classList){ return; }
      if(saklar.checked){ kotak.classList.remove('peta-tanpa-nama'); }
      else { kotak.classList.add('peta-tanpa-nama'); }
    }
    saklar.addEventListener('change', function(){
      terapkan();
      try{ sessionStorage.setItem(KUNCI_SAKLAR, saklar.checked ? '1' : '0'); }catch(e){}
    });
    terapkan();
  })();
  // Tampilan peta (titik tengah + zoom) diingat per tab. Tanpa ini, membuka
  // Live Map lagi selalu melempar peta kembali ke kerangka "fit semua node",
  // sehingga orang kehilangan tempat yang sedang ia periksa. Simpanan berlaku
  // selama tab hidup (sessionStorage), jadi tidak mengunci tampilan selamanya;
  // kunjungan pertama tetap memakai fitBounds di bawah.
  //
  // Dua jebakan yang sudah terbukti dan sengaja dihindari di sini:
  //   1. Keputusan memakai fitBounds diambil dari ADA/TIDAKNYA simpanan - bukan
  //      dari "berhasil tidaknya setView". Kalau container #peta belum
  //      berukuran saat skrip ini jalan, setView bisa gagal; kalau kegagalan itu
  //      dianggap "tidak ada simpanan", fitBounds yang dijalankan pada container
  //      kosong menghasilkan zoom rusak (bbox raksasa -> zoom 3).
  //   2. Karena container bisa belum berukuran, simpanan DIPASANG ULANG setelah
  //      halaman selesai dimuat - tetapi hanya bila pengguna belum menggeser
  //      peta sendiri, supaya tidak menyentak tampilan yang sedang dipakai.
  var KUNCI_VIEW='meshid-peta-view-1';
  var tampilanTersimpan=null;
  try{ tampilanTersimpan=JSON.parse(sessionStorage.getItem(KUNCI_VIEW)||'null'); }catch(e){}
  var adaSimpanan=!!(tampilanTersimpan && isFinite(tampilanTersimpan[0])
                     && isFinite(tampilanTersimpan[1]) && isFinite(tampilanTersimpan[2]));
  var disentuhPengguna=false;
  function simpanTampilan(){
    try{
      var c=peta.getCenter();
      sessionStorage.setItem(KUNCI_VIEW, JSON.stringify([c.lat, c.lng, peta.getZoom()]));
    }catch(e){}
  }
  function pasangSimpanan(){
    if(!adaSimpanan || disentuhPengguna){ return; }
    try{
      peta.invalidateSize();
      peta.setView([tampilanTersimpan[0], tampilanTersimpan[1]], tampilanTersimpan[2]);
    }catch(e){}
  }
  peta.on('dragstart', function(){ disentuhPengguna=true; });
  peta.on('mousedown', function(){ disentuhPengguna=true; });
  if(adaSimpanan){ pasangSimpanan(); }
  else if(titik.length){ peta.fitBounds(semua, {padding:[28,28], maxZoom:15}); }
  window.__petaLive = peta;
  // Pencatatan baru dipasang SESUDAH tampilan awal ditentukan, supaya keadaan
  // sementara (container belum berukuran) tidak ikut tersimpan.
  peta.on('moveend', simpanTampilan);
  peta.on('zoomend', simpanTampilan);
  if(adaSimpanan){
    window.addEventListener('load', pasangSimpanan);
    setTimeout(pasangSimpanan, 300);
  }
})();
"""


# ------------------------------------------------------------------ Halaman node

def halaman_node(node_id, data, nama, gambar=True, db=None):
    """Satu node: peta + playback. `data` hasil lacak_node.susun_lacak()."""
    if data is None or not data.get("route"):
        return _halaman_kosong(node_id, nama,
                               "Belum ada histori posisi untuk node ini. "
                               "Riwayat terkumpul begitu node melaporkan "
                               "koordinat lewat GPS.", gambar=gambar)

    db = db or {}
    stops = data["stops"]
    legenda = (
        "Titik singgah dihitung dari riwayat: node dianggap berhenti bila "
        "berada dalam <b>%s m</b> dari posisi sebelumnya selama minimal "
        "<b>%s menit</b>. Titik biru adalah ujung rute (mulai / selesai), "
        "bukan singgah."
        % (_fmt_m(data["ambang"]["radius_m"]), _fmt_m(data["ambang"]["meninggah_s"] / 60.0, 0))
    )
    konteks = ""
    if db.get("aktif"):
        konteks = ('<span class="dim">Riwayat %s titik untuk %s node, disimpan %s hari.</span>'
                   % (_fmt_angka(db["jumlah"]), _fmt_angka(db["node"]),
                      _fmt_angka(db.get("simpan_hari", 30), 0)))

    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tracking Node — %s</title>
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="stylesheet" href="/leaflet/leaflet.css">
<style>%s</style></head><body>
%s%s
<div class="kartu" id="kartu"></div>
<div class="tata">
  <div class="panel">
    <h2>Peta Pergerakan</h2>
    <div id="peta">
      <div id="alat">
        <div class="gauge">
          <div class="g-label">Kecepatan</div>
          <div id="speedo">0.0</div><div id="speedo-satuan">km/j</div>
        </div>
        <div class="gauge">
          <div class="g-label">Arah</div>
          <div class="mawar"><span class="tik u">U</span><span class="tik t">T</span>
            <span class="tik s">S</span><span class="tik b">B</span>
            <div id="jarum"></div></div>
          <div id="arah-teks">--</div>
        </div>
      </div>
    </div>
    <div class="kendali">
      <button id="main" class="aktif" title="Putar / jeda">&#10074;&#10074;</button>
      <button id="fokus" title="Kunci kamera ke node">&#8982;</button>
      <input id="geser" type="range" min="0" max="1000" value="0" title="Geser waktu">
      <select id="cepat">
        <option value="0.5">0.5x</option>
        <option value="1" selected>1x</option>
        <option value="2">2x</option>
        <option value="4">4x</option>
      </select>
    </div>
  </div>
  <div class="panel">
    <h2>Titik Singgah (%d)</h2>
    <div id="singgah"></div>
  </div>
</div>
<div class="info">%s</div>
<div class="kaki dim">
  %s &middot; <a href="/lacak/%s.json">JSON</a> &middot;
  <a href="/">kembali ke Monitoring</a>
</div>
<script src="/leaflet/leaflet.js"></script>
<script>
%s
</script>
</body></html>""" % (
        _esc("%s (%s)" % (nama, node_id)),
        PALET,
        _tabbar("lacak"),
        _kepala('Tracking Node — <span id="judul"></span>',
                '<span id="sub" class="mono">%s</span> &middot; <span class="mono">%s</span>'
                % (_esc(node_id), konteks), judul_html=True),
        sum(1 for s in stops if not s["sintetis"]),
        legenda,
        konteks,
        _esc(node_id),
        JS_LACAK.replace("__DATA__", _json_aman(_siap_untuk_js(data, nama, node_id))),
    )


def _siap_untuk_js(data, nama, node_id):
    """Paket yang dikirim ke peramban.

    Field yang tidak dibutuhkan JavaScript (mis. t_awal/t_akhir, ambang)
    dibiarkan - ukurannya kecil dan berguna untuk pembacaan halaman.
    Yang WAJIB: `nama` dan `node_id`, karena header halaman mengisinya dari JS.
    """
    out = dict(data)
    out["nama"] = nama or node_id
    out["node_id"] = node_id
    return out


def _halaman_kosong(node_id, nama, pesan, gambar=True):
    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tracking Node — %s</title>
<link rel="icon" type="image/png" href="/favicon.png">
<style>%s</style></head><body>
%s%s
<div class="peringatan">%s</div>
<div class="kaki dim"><a href="/lacak">daftar node</a> &middot;
<a href="/">kembali ke Monitoring</a></div>
</body></html>""" % (
        _esc("%s (%s)" % (nama, node_id)), PALET, _tabbar("lacak"),
        _kepala("Tracking Node", '<span class="mono">%s</span>' % _esc(node_id)),
        _esc(pesan),
    )


# ------------------------------------------------------------------ Halaman daftar

def halaman_daftar(daftar, db, gambar=True):
    """Tab Tracking Node: node mana saja yang punya histori untuk dilacak."""
    if not db.get("aktif"):
        return """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tracking Node</title><link rel="icon" type="image/png" href="/favicon.png">
<style>%s</style></head><body>
%s%s
<div class="peringatan">Riwayat lokasi belum aktif: <span class="mono">%s</span></div>
<p class="dim">Perekaman dinonaktifkan lewat <span class="mono">MESH_LACAK_AKTIF=0</span>
atau database tidak bisa dibuka. Setel ulang ke <span class="mono">1</span> lalu restart
layanan.</p>
<div class="kaki dim"><a href="/">kembali ke Monitoring</a></div>
</body></html>""" % (PALET, _tabbar("lacak"),
                    _kepala("Tracking Node", "Riwayat lokasi node"),
                    _esc(db.get("pesan") or "alasan tidak diketahui"))

    baris = []
    for r in daftar:
        via = r.get("via") or ""
        kelas = {"diri": "via-diri", "lora": "via-lora"}.get(via, "via-mqtt")
        nama = r.get("long_name") or r.get("short_name") or "-"
        favorit = " <span class='favorit'>&#9733;</span>" if r.get("favorite") else ""
        jml = r["jumlah"]
        ada = "dipantau" if jml >= 2 else "baru 1 titik"
        baris.append(
            "<tr><td class='mono'>%s</td>"
            "<td class='nama'><b>%s</b>%s<br><span class='dim'>%s &middot; %s</span></td>"
            "<td><span class='via %s'>%s</span></td>"
            "<td>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td>"
            "<td class='mono'>%s<br><span class='dim'>&#9468; %s m</span></td>"
            "<td><a href='/lacak/%s'>lacak &#8594;</a></td></tr>"
            % (_esc(r["node_id"]), _esc(nama), favorit,
               _esc(r.get("short_name") or "-"), _esc(r.get("hw_model") or "-"),
               kelas, _esc(via.upper() if via else "-"),
               '<span class="on">ONLINE</span>' if r.get("online") else '<span class="off">OFFLINE</span>',
               _fmt_angka(jml), ada,
               # Satu argumen untuk "lat / lon": kalau dipisah jadi dua %s,
               # "%" di dalam teks sudah diformat lebih dulu dan hitungan
               # placeholder jadi tidak cocok saat koordinat kosong.
               _fmt_koordinat(r.get("lat"), r.get("lon")),
               ("%s m" % _fmt_angka(r["alt"], 0)) if r.get("alt") is not None else "-",
               _esc(r["node_id"]))
        )

    tabel = ("<div class='gulir'><table class='data'><thead><tr>"
             "<th>ID</th><th>Nama &amp; Perangkat</th><th>Via</th><th>Status</th>"
             "<th class='num'>Titik</th><th class='num'>Riwayat</th>"
             "<th>Lat / Lon / Alt</th><th>Aksi</th>"
             "</tr></thead><tbody>%s</tbody></table></div>") % ("".join(baris) or
                "<tr><td colspan='8' class='dim'>Belum ada node dengan histori posisi.</td></tr>")

    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tracking Node — daftar node</title>
<link rel="icon" type="image/png" href="/favicon.png">
<style>%s</style></head><body>
%s%s
<div class="kartu">
  <div class="kotak"><b>%s</b><span>node punya histori</span></div>
  <div class="kotak"><b>%s</b><span>total titik posisi</span></div>
  <div class="kotak"><b>%s</b><span>umur riwayat</span></div>
  <div class="kotak"><b>%s</b><span>ukuran database</span></div>
</div>
<div class="info">
  Riwayat posisi ditulis ke <span class="mono">%s</span> setiap kali node
  melaporkan koordinat baru (diam &gt; %s m atau sudah &gt; %s menit tanpa titik baru,
  supaya GPS yang tidak bergerak tidak membengkakkan database).
  Riwayat lebih tua dari <b>%s hari</b> dibuang otomatis.
</div>
<div class="dim" style="margin:14px 0 6px">
  <input type="search" id="saring" placeholder="saring: nama atau ID, mis. ROUTER, !da5a16f8">
  <span id="hasil" class="dim"></span>
</div>
%s
<div class="kaki dim">Rasio singgah: <b>%s m</b> radius &middot; minimal <b>%s menit</b> diam.
Klik <b>lacak</b> untuk membuka peta dan playbackRiwayatnya.</div>
<script>
(function(){
  var f=document.getElementById('saring'), h=document.getElementById('hasil');
  function saring(){
    var q=f.value.toLowerCase(), n=0, all=document.querySelectorAll('table.data tbody tr');
    for(var i=0;i<all.length;i++){
      var cocok=all[i].textContent.toLowerCase().indexOf(q)>=0;
      all[i].style.display=cocok?'':'none'; if(cocok) n++;
    }
    h.textContent = q ? n + ' dari ' + all.length + ' node cocok' : '';
    try{history.replaceState(null,'','#'+encodeURIComponent(f.value));}catch(e){}
  }
  var awal=decodeURIComponent((location.hash||'').slice(1));
  if(awal){f.value=awal;saring();}
  f.addEventListener('input',saring);
})();
</script>
</body></html>""" % (
        PALET, _tabbar("lacak"),
        _kepala("Tracking Node", "Pilih node untuk melihat peta dan riwayat pergerakannya"),
        _fmt_angka(db["node"]), _fmt_angka(db["jumlah"]),
        "%s hari" % _fmt_angka(db.get("simpan_hari", 30), 0),
        _ukuran_bytes(db["bytes"]),
        _esc(db["lokasi"]),
        _fmt_angka(_lacak_min_jarak()), _fmt_angka(_lacak_min_sela() / 60.0, 0),
        _fmt_angka(db.get("simpan_hari", 30), 0),
        tabel,
        _fmt_angka(_radius_singgah()), _fmt_angka(_meninggah() / 60.0, 0),
    )


# Nilai ambang ikut dicetak di halaman daftar supaya angka yang tampil bisa
# diperiksa pembaca terhadap setelan yang benar-benar dipakai perhitungannya.
def _ambang(nama, bawaan):
    import os
    v = os.environ.get(nama, "")
    try:
        return float(v) if v not in ("", None) else float(bawaan)
    except (TypeError, ValueError):
        return float(bawaan)


def _lacak_min_jarak():
    return _ambang("MESH_LACAK_MIN_JARAK", 5.0)


def _lacak_min_sela():
    return _ambang("MESH_LACAK_MIN_SELA", 600)


def _radius_singgah():
    return _ambang("MESH_LACAK_RADIUS_SINGGAH", 75.0)


def _meninggah():
    return _ambang("MESH_LACAK_MENINGGAH", 300)


def _fmt_angka(nilai, digit=0):
    try:
        n = float(nilai)
    except (TypeError, ValueError):
        return "-"
    return ("{:,.%df}" % digit).format(n).replace(",", " ")


def _fmt_m(nilai, digit=0):
    return _fmt_angka(nilai, digit) + " m"


def _fmt_koordinat(lat, lon, digit=5):
    if lat is None or lon is None:
        return "- / -"
    return ("%.*f / %.*f" % (digit, float(lat), digit, float(lon)))


def _ukuran_bytes(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    for satuan in ("B", "KB", "MB", "GB"):
        if n < 1024 or satuan == "GB":
            # _fmt_angka memakai koma sebagai pemisah ribuan dan titik sebagai
            # desimal (gaya penulisan angka). Untuk ukuran file, satu digit di bawah
            # koma tidak pernah jadi ribuan, jadi titik ditukar ke koma agar
            # konsisten dengan penulisan "2,0 KB" di teks berbahasa Indonesia.
            teks = _fmt_angka(n, 0 if satuan == "B" else 1)
            if satuan != "B":
                teks = teks.replace(".", ",")
            return "%s %s" % (teks, satuan)
        n /= 1024.0
    return "-"


# ------------------------------------------------------------------ Tab Live Map

def _durasi(detik):
    """Lama (detik) -> teks ringkas: "42s", "3m", "2j 5m", "1h 4j".

    Dipakai dua tempat sekaligus: selisih "terakhir terdengar" dan umur nyala
    (uptime) perangkat - keduanya lama, bukan titik waktu.
    """
    try:
        detik = max(0, int(detik))
    except (TypeError, ValueError):
        return "-"
    if detik < 60:
        return "%ds" % detik
    if detik < 3600:
        return "%dm" % (detik // 60)
    if detik < 86400:
        return "%dj %dm" % (detik // 3600, (detik % 3600) // 60)
    return "%dh %dj" % (detik // 86400, (detik % 86400) // 3600)


def _lama(epoch, sekarang):
    """Selisih waktu -> teks ringkas ("3m", "2j"); None bila tidak ada."""
    if epoch is None:
        return "-"
    try:
        return _durasi(int(sekarang) - int(float(epoch)))
    except (TypeError, ValueError):
        return "-"


def _nama_node(r):
    """Nama tampilan satu node.

    Dipakai bersama oleh label di peta dan judul popup supaya keduanya tidak
    pernah menampilkan nama yang berbeda untuk node yang sama; perangkat yang
    baru muncul bisa belum mengirim nama sama sekali.
    """
    return r.get("long_name") or r.get("short_name") or "(tanpa nama)"


def _pop_up_node(node_id, r, sekarang):
    """Isi popup satu node: identitas, posisi, daya, sinyal, dan tautan lacak.

    Nama node berasal dari perangkat, jadi SELALU lewat _esc. Nilai yang sudah
    diformat (mis. "12,3 dB") disisipkan sebagai teks, bukan sebagai format
    string, supaya karakter '%' di dalamnya tidak mengacaukan substitution.
    """
    nama = _nama_node(r)
    favorit = " &#9733;" if r.get("favorite") else ""
    via = (r.get("via") or "").lower()
    kelas = {"diri": "via-diri", "lora": "via-lora"}.get(via, "via-mqtt")
    lencana = ('<span class="on">ONLINE</span>' if r.get("online")
               else '<span class="off">OFFLINE</span>')

    teg = r.get("voltage")
    try:
        teg = None if (teg is None or abs(float(teg)) < 0.05) else teg
    except (TypeError, ValueError):
        teg = None

    rows = [
        ("Status", lencana),
        ("Via", '<span class="via %s">%s</span>' % (kelas, _esc(via.upper() or "-"))),
        ("Terakhir", _esc(_lama(r.get("last"), sekarang))),
        ("Baterai", _esc(_fmt_angka(r.get("battery"), 0) + "%")
         if r.get("battery") is not None else "-"),
    ]
    if teg is not None:
        rows.append(("Tegangan", _esc("%.2f V" % float(teg))))
    # SNR cuma bermakna untuk node yang benar-benar terdengar lewat radio
    # gateway; angka dari node jalur MQTT bukan ukuran kualitas tautan radio.
    if via != "mqtt" and r.get("snr") is not None:
        rows.append(("SNR", _esc("%.1f dB" % float(r["snr"]))))
    if r.get("hops") is not None:
        rows.append(("Hop", _esc(_fmt_angka(r["hops"], 0))))
    if r.get("hw_model") or r.get("role"):
        rows.append(("Perangkat", _esc(r.get("hw_model") or "-")))
    if r.get("role"):
        rows.append(("Peran", _esc(r["role"])))
    if r.get("uptime") is not None:
        rows.append(("Uptime", _esc(_durasi(r["uptime"]))))
    # Telemetri perangkat. Satu baris per besaran, dan barisnya HANYA muncul
    # bila perangkat benar-benar mengirim angka itu - deretan "-" bertumpuk
    # tidak memberi keterangan apa pun. Satuannya ditulis sebagai karakter
    # sungguhan ("°C"), bukan entitas HTML: nilai di sini di-escape sekali
    # setelah dirangkai, jadi "&deg;" justru akan tampil sebagai tulisan
    # "&deg;" itu sendiri.
    for label, pola, nilai, satuan in (
            ("Suhu", "%.1f", r.get("temp"), " \u00b0C"),
            ("Kelembapan", "%.0f", r.get("hum"), "% RH"),
            ("Tekanan", "%.0f", r.get("press"), " hPa"),
            ("Kanal", "%.1f", r.get("chan_util"), "%"),
            ("Udara TX", "%.1f", r.get("air_tx"), "%")):
        if nilai is None:
            continue
        try:
            rows.append((label, _esc(pola % float(nilai) + satuan)))
        except (TypeError, ValueError):
            continue
    rows.append(("Posisi", _esc(_fmt_koordinat(r.get("lat"), r.get("lon")))))
    if r.get("alt") is not None:
        rows.append(("Ketinggian", _esc("%s m" % _fmt_angka(r["alt"], 0))))

    isi = "".join("<tr><th>%s</th><td>%s</td></tr>" % (k, v) for k, v in rows)
    return (
        '<div class="pop-judul">%s%s</div>'
        '<div class="pop-id">%s</div>'
        '<table class="pop-tab">%s</table>'
        '<a class="pop-aksi" href="/lacak/%s">lacak node &#8594;</a>'
        % (_esc(nama), favorit, _esc(node_id), isi, _esc(node_id))
    )


def halaman_peta(daftar, sekarang, gambar=True):
    """Tab Live Map: semua node yang punya koordinat pada satu peta.

    `daftar` berisi node hasil exporter (node_dengan_status) - sudah memuat node_id,
    online, via, dan deviceMetrics. Node tanpa koordinat tidak bisa jadi marker
    tapi tetap dihitung di supaya, supaya angka tidak membuat orang mengira
    node-nya hilang.
    """
    titik, tanpa_pos, n_online = [], 0, 0
    for r in daftar:
        node_id = r.get("node_id") or ""
        via = (r.get("via") or "").lower()
        # posisi_bersih menyaring nilai kosong, nilai di luar rentang bumi, dan
        # sisa bit di sekitar (0,0) - titik terakhir itu yang paling merusak
        # karena Leaflet menaikkan bingkai peta sampai seluruh dunia dan zoom
        # jatuh ke 3, sehingga peta terlihat "kembali ke posisi awal".
        lat, lon = posisi_bersih(r.get("lat"), r.get("lon"))
        if not node_id or lat is None or lon is None:
            tanpa_pos += 1
            continue
        if r.get("online"):
            n_online += 1
        titik.append({"lat": lat, "lon": lon,
                      "on": bool(r.get("online")),
                      "gw": via == "diri",
                      # Nama untuk label yang menempel di peta. Di-escape di
                      # sini karena Leaflet menulis isi tooltip sebagai HTML.
                      "nama": _esc(_nama_node(r)),
                      "popup": _pop_up_node(node_id, r, sekarang)})

    # online/offline dihitung dari marker yang benar-benar dipetakan, bukan
    # dari seluruh node: menghitung dari daftar membuat kotak "offline" bisa
    # negatif kalau ada node online yang tidak punya koordinat.
    summary = (
        '<div class="kartu">'
        '<div class="kotak"><b>%s</b><span>node dipetakan</span></div>'
        '<div class="kotak"><b>%s</b><span>online</span></div>'
        '<div class="kotak"><b>%s</b><span>offline</span></div>'
        '<div class="kotak"><b>%s</b><span>tanpa koordinat</span></div>'
        '</div>' % (_fmt_angka(len(titik)), _fmt_angka(n_online),
                     _fmt_angka(len(titik) - n_online), _fmt_angka(tanpa_pos)))

    kosong = (
        '<div class="peringatan">Belum ada node yang melaporkan koordinat '
        '(latitude/longitude). Peta akan terisi begitu node mengirim '
        'posisi lewat GPS.</div>'
        if not titik else "")

    return """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Live Map Node</title>
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="stylesheet" href="/leaflet/leaflet.css">
<style>%s</style></head><body>
%s%s
%s%s
<div id="peta"></div>
<div class="legenda">
  <span><i style="background:var(--hijau)"></i>online</span>
  <span><i style="background:var(--samar)"></i>offline</span>
  <span><i style="background:var(--aksen)"></i>gateway sendiri</span>
  <label class="saklar-nama"><input type="checkbox" id="saklar-nama" checked>
    nama node</label>
</div>
<div class="info">Posisi diambil dari laporan terakhir tiap node
(<span class="mono">latitude</span>/<span class="mono">longitude</span>), jadi
titik bisa tertinggal bila node sedang tidak terdengar. Klik node untuk
melihat rincian dan membuka riwayat pergerakannya.</div>
<div class="kaki dim">Peta diperbarui tiap muat halaman &middot;
<a href="/lacak">daftar Tracking Node</a> &middot;
<a href="/">kembali ke Monitoring</a></div>
<script src="/leaflet/leaflet.js"></script>
<script>
%s
</script>
</body></html>""" % (
        PALET, _tabbar("peta"),
        _kepala("Live Map Node", "Posisi terkini semua node yang terdengar gateway"),
        summary, kosong,
        JS_PETA.replace("__TITIK__", _json_aman(titik)),
    )


def waktu_indonesia(epoch):
    """Waktu epoch -> teks WIB; dipakai halaman daftar untuk kolom terakhir."""
    return _wib_berlabel(epoch)


def waktu_ringkas(epoch):
    return _wib_pendek(epoch)


def sekarang():
    return time.time()


# Dipakai ulang oleh halaman monitoring supaya format waktu di kedua tab sama.
ZONA = WIB