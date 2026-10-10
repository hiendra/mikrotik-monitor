(function () {
  'use strict';
  var daftar = document.getElementById('metodeBayarDaftar');
  if (!daftar) return;
  var labelJenis = {
    transfer: 'Transfer Bank',
    qris: 'QRIS',
    ewallet: 'E-Wallet',
    tunai: 'Tunai',
    lainnya: 'Metode lain'
  };
  function el(tag, kelas, teks) {
    var node = document.createElement(tag);
    if (kelas) node.className = kelas;
    if (teks !== undefined) node.textContent = teks;
    return node;
  }
  fetch('/api/metode-publik', { credentials: 'same-origin', cache: 'no-store' })
    .then(function (response) {
      if (!response.ok) throw new Error('HTTP ' + response.status);
      return response.json();
    })
    .then(function (data) {
      var metode = Array.isArray(data.metode) ? data.metode : [];
      daftar.replaceChildren();
      if (!metode.length) {
        daftar.appendChild(el('p', 'catatan-kecil', 'Belum ada metode pembayaran yang aktif. Silakan hubungi pengurus.'));
        return;
      }
      metode.forEach(function (item) {
        var kartu = el('div', 'metode-item');
        var jenis = labelJenis[item.jenis] || labelJenis.lainnya;
        kartu.appendChild(el('b', '', jenis + (item.bank ? ' — ' + item.bank : '')));
        var rincian = [];
        if (item.nomor_rekening) rincian.push(item.nomor_rekening);
        if (item.atas_nama) rincian.push('a.n. ' + item.atas_nama);
        if (item.keterangan) rincian.push(item.keterangan);
        if (rincian.length) kartu.appendChild(el('span', '', rincian.join(' · ')));
        daftar.appendChild(kartu);
      });
    })
    .catch(function () {
      daftar.replaceChildren(el('p', 'catatan-kecil', 'Metode pembayaran belum dapat dimuat. Silakan hubungi pengurus.'));
    });
})();
