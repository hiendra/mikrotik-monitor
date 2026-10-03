// ============================================================
// dasbor.js - menggambar kartu layanan di clusternet.my.id
// ============================================================
// Daftar layanan TIDAK lagi ditulis tangan di index.html. Berkas ini membaca
// ./layanan.json - berkas yang dihasilkan panel-kelola.html dan dikirim ke
// server oleh zima-deployer bersama Caddyfile. Menambah atau mengubah
// subdomain di panel cukup dilakukan sekali; dasbor mengikutinya sendiri.
//
// Dipisah ke berkas luar (bukan <script> sebaris) karena CSP situs ini
// memakai script-src 'self': skrip sebaris akan diblokir, berkas sendiri
// tidak. Jangan ubah menjadi sebaris.
"use strict";

const wadah = document.getElementById("daftar-layanan");

// Kartu dibangun dengan API DOM (bukan innerHTML) supaya judul/deskripsi
// yang berasal dari panel tidak pernah bisa menyisipkan HTML.
function buatKartu(baris) {
  const tautan = document.createElement("a");
  tautan.className = "kartu";
  tautan.href = String(baris.url || "#");
  tautan.target = "_blank";
  tautan.rel = "noopener noreferrer";

  const judul = document.createElement("h3");
  if (baris.ikon) {
    const ikon = document.createElement("span");
    ikon.className = "ikon";
    ikon.setAttribute("aria-hidden", "true");
    ikon.textContent = String(baris.ikon);
    judul.appendChild(ikon);
    judul.appendChild(document.createTextNode(" "));
  }
  judul.appendChild(document.createTextNode(String(baris.judul || "Layanan")));
  const status = document.createElement("span");
  status.className = "status";
  status.textContent = "Aktif";
  judul.appendChild(status);
  tautan.appendChild(judul);

  const url = document.createElement("span");
  url.className = "url";
  url.textContent = String(baris.url || "").replace(/^https?:\/\//, "") + " ";
  const luar = document.createElement("span");
  luar.className = "luar";
  luar.setAttribute("aria-hidden", "true");
  luar.textContent = "\u2197";
  url.appendChild(luar);
  tautan.appendChild(url);

  if (baris.deskripsi) {
    const ket = document.createElement("p");
    ket.textContent = String(baris.deskripsi);
    tautan.appendChild(ket);
  }

  return tautan;
}

function tampilkanCatatan(pesan) {
  wadah.innerHTML = "";
  const p = document.createElement("p");
  p.className = "catatan-muat";
  p.textContent = pesan;
  wadah.appendChild(p);
}

function gambar(layanan) {
  wadah.innerHTML = "";
  layanan.forEach((baris) => wadah.appendChild(buatKartu(baris)));
}

// Rahasia kecil agar perubahan langsung terlihat: berkas ini jarang berubah,
// tetapi layanan.json berubah setiap kali Anda menerapkan dari panel. Karena
// itu layanan.json sengaja diambil dengan no-store, bukan ikut di-cache.
fetch("layanan.json", { cache: "no-store" })
  .then((r) => {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  })
  .then((data) => {
    const layanan = Array.isArray(data) ? data : data.layanan || [];
    if (!layanan.length) throw new Error("daftar kosong");
    gambar(layanan);
  })
  .catch(() => {
    tampilkanCatatan(
      "Daftar layanan sedang tidak bisa dimuat. Coba muat ulang halaman ini.",
    );
  });
