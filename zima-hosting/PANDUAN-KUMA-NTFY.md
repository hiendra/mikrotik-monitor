# Notifikasi Uptime Kuma ke iPhone (topik **terpisah** dari MikroTik)

Panduan ini mencatat notifikasi **Uptime Kuma** → **ntfy**, sengaja memakai
**topik lain** daripada notifikasi router, supaya dua sumber gangguan tidak
tercampur di layar kunci: router bermasalah = topik A, layanan bermasalah =
topik B.

| | Nilai |
|---|---|
| Halaman kelola | `https://kuma.clusternet.my.id/manage-status-page` |
| Panel notifikasi | `https://kuma.clusternet.my.id/settings/notifications` |
| Versi Kuma saat dipasang | **2.4.0** |
| Jenis notifikasi | **Ntfy** (bawaan Kuma — bukan skrip) |
| Nama ramah | `ntfy Kuma (adminforge)` |
| Server URL | `https://ntfy.adminforge.de` |
| Topik | `kuma-7m3xq9dt2v` |
| Prioritas UP | `3` (default) |
| Prioritas DOWN | `5` (max/urgent) |
| Cakupan | semua monitor yang ada **dan** monitor baru |

> **Nama topik = sandi.** Siapa pun yang tahu namanya bisa membaca isinya di
> server publik `ntfy.adminforge.de`. Perlakukan sama seperti sandi router.

Topik router tetap `rt-7k2m9dx4q8wf` (lihat `mikrotik-ntfy/README.md`).
Dua topik ini **tidak** saling mengganggu.

---

## 1. Mengapa pakai notifikasi bawaan Kuma, bukan skrip

Kuma sudah tahu persis kapan sebuah monitor berubah down/up, jadi ia yang
mengirim sendiri — tanpa polling, tanpa state tambahan di repo:

- **seketika**, tidak menunggu jadwal (skrip polling punya jeda sampai ~1 menit);
- **ada percobaan ulang** bawaan bila server ntfy sedang tidak bisa dihubungi;
- **tidak ada komponen baru** yang bisa layu (timer systemd, berkas penanda);
- tetap dapat dipakai dari HP: tombol **Test** di panel Kuma.

Skrip polling halaman status tetap mungkin (`sinkron-status-kuma.sh` sudah
membuktikan pola akses DB-nya), tetapi di sini tidak perlu.

---

## 2. Yang dikirim Kuma (format bawaan, sengaja tidak diubah)

Dari sumber `server/notification-providers/ntfy.js` (Kuma 2.x), untuk peristiwa
down/up biasa:

| Bagian | Isi |
|---|---|
| Judul | `Nama Monitor Down [Uptime-Kuma]` / `Nama Monitor Up [Uptime-Kuma]` |
| Isi | pesan heartbeat Kuma (mis. `200 - OK`, `Timeout`) — boleh kosong untuk monitor ping |
| Tag ikon | `red_circle` saat DOWN, `green_circle` saat UP |
| Prioritas | UP = 3 (default), DOWN = 5 (max/urgent) |
| Tombol | **Open Nama Monitor** → membuka URL monitor |

Ikon lingkaran datang dari **tag**, persis seperti keputusan di paket
MikroTik — jadi judul tidak perlu emoji tambahan dan tidak ada lingkaran dobel.
Kolom **Icon URL** sengaja **dikosongkan**; mengisinya akan menambah ikon kedua
di samping lingkaran tag.

**Template kustom sengaja TIDAK dinyalakan.** Kalau nanti ingin judul lebih
ringkas (mis. tanpa akhiran `[Uptime-Kuma]`), centang
**Customize notification templates** lalu uji dulu dengan tombol **Test** —
kesalahan template membuat notifikasi gagal terkirim sama sekali, dan cabang
UP/DOWN-nya tidak bisa diuji tanpa gangguan sungguhan.

---

## 3. Memasang (sudah dikerjakan — untuk mengulang bila Kuma dipasang ulang)

1. Buka `https://kuma.clusternet.my.id/settings/notifications`.
2. **Set Up Notification**.
3. **Notification Type** → **Ntfy**.
4. Isi:
   - **Friendly Name**: `ntfy Kuma (adminforge)`
   - **ntfy Topic**: `kuma-7m3xq9dt2v`
   - **Server URL**: `https://ntfy.adminforge.de`
     (**tanpa** nama topik di belakangnya — Kuma menolak bila digabung)
   - **Priority**: `3` · **Priority for DOWN-events**: `5`
   - **Authentication Method**: `None` (ntfy publik, tanpa akun)
5. Centang **Default enabled** dan **Apply on all existing monitors**.
6. **Test** → harus muncul **Sent Successfully.**
7. **Save**.

Panel ini tidak dilindungi Cloudflare Access, jadi bisa dibuka langsung.

---

## 4. Memasang di iPhone (satu langganan baru)

Buka aplikasi **ntfy** → tab **Subscriptions** → **+**:

```
Server : https://ntfy.adminforge.de
Topic  : kuma-7m3xq9dt2v
```

Simpan. Saat iOS bertanya, pilih **Allow / Izinkan**.
(Server di atas sama dengan yang dipakai topik MikroTik — kalau iPhone sudah
berlangganan topik router di server itu, cukup tambah topik baru di server yang
sama.)

Uji tanpa menunggu gangguan: tekan **Test** di panel Kuma, atau dari komputer:

```bash
curl -s -X POST https://ntfy.adminforge.de/kuma-7m3xq9dt2v \
  -H "Title: UJI TOPIK KUMA" -H "Tags: white_check_mark" \
  -d "Kalau baris ini terlihat di HP, langganan sudah benar."
```

**Pengingat yang berlaku untuk semua topik di adminforge:** server itu
`enable_web_push:false`, jadi notifikasi iPhone muncul **saat aplikasi dibuka**,
bukan sebagai push instan. Ini keputusan yang sudah diterima; pindah ke
`https://ntfy.sh` (punya push APNs) adalah pilihan bila suatu saat ingin push
instan.

---

## 5. Kalau notifikasi tidak muncul

| Gejala | Periksa |
|---|---|
| **Test** gagal / merah | Server URL salah (paling sering mengandung nama topik). Harus **persis** `https://ntfy.adminforge.de`. |
| Test sukses tapi HP diam | Langganan iPhone: server dan topik salah ketik, atau izin notifikasi iOS belum diberikan. |
| Test sukses, HP diam, topik benar | Buka `https://ntfy.adminforge.de/kuma-7m3xq9dt2v` di **browser**. Muncul di sana? Berarti masalahnya di aplikasi (hapus lalu tambah ulang langganan). |
| Tidak ada notifikasi saat monitor down | Monitor itu belum memakai notifikasi ini — buka **Edit** monitor → bagian **Notifications** → centang `ntfy Kuma (adminforge)`. |
| Monitor down tetapi pesan kosong | Wajar untuk monitor ping/port: `heartbeatJSON.msg` memang kosong. Judulnya tetap berisi nama + status. |

Cek cepat dari terminal (juga menampilkan status terakhir tiap monitor di
halaman status):

```bash
python zima-hosting/uji-kuma-ntfy.py
```

---

## 6. Mengecek bahwa semuanya benar-benar menempel

Selain tombol **Test**, bukti yang dipakai saat pemasangan:

```bash
# 1. Notifikasi terdaftar di panel
#    Settings -> Notifications -> terlihat "ntfy Kuma (adminforge)"

# 2. Monitor benar-benar memakai notifikasi itu
#    Edit monitor -> bagian Notifications -> "ntfy Kuma (adminforge)" tercentang

# 3. Kanal ntfy hidup (pesan uji benar-benar tiba di server)
curl -s "https://ntfy.adminforge.de/kuma-7m3xq9dt2v/json?poll=1&since=10m" | tail -3
```

---

## 7. Mengubah topik / mencopot

**Ganti topik** (mis. karena nama topik bocor): panel Kuma → **Edit** pada
notifikasi → ubah **ntfy Topic** → **Test** → **Save** → tambahkan langganan
baru di iPhone dan hapus langganan lama. Setelah itu perbarui tabel di atas dan
bawaan `--server`/`--topik` di `zima-hosting/uji-kuma-ntfy.py`.

**Matikan semua notifikasi Kuma:** panel Kuma → **Edit** → hapus centang
**Default enabled** dan lepas centang notifikasi ini di tiap monitor, atau hapus
notifikasi lewat ikon hapus. Tidak ada berkas di repo yang perlu diubah — tidak
ada skrip/scheduler yang bergantung padanya.

---

## 8. Berkas terkait

- `mikrotik-ntfy/README.md` — kanal ntfy sisi router (topik `rt-7k2m9dx4q8wf`).
- `zima-hosting/uji-kuma-ntfy.py` — pemeriksa cepat kanal Kuma → ntfy
  (sekaligus menampilkan monitor mana yang sedang DOWN).
- `zima-hosting/sinkron-status-kuma.sh` — menjaga monitor baru masuk ke halaman
  status (masalah lain, tidak berkaitan dengan notifikasi).
- `zima-hosting/CATATAN-KENDALA.md` — riwayat kendala, entri 9.
