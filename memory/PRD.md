# PRD - Sistem Manajemen Bengkel Motor

## Problem Statement (Ringkasan)
Aplikasi web manajemen bengkel motor: PHP native + SQLite (bengkel.db auto-create), Bootstrap 5 via CDN, siap hosting cPanel/XAMPP. Modul: Dashboard statistik, Pelanggan & Kendaraan, Inventory Sparepart (input manual, import Excel, scan barcode kamera/USB, barang masuk/keluar, low stock alert), Kasir/POS + cetak struk, Data Supplier, Klaim Garansi (kode GRS-, cari nota, ubah status, penggantian part otomatis potong stok, cetak bukti), login multi-user.

## Arsitektur
- PHP 8.2 native (tanpa framework), PDO SQLite, session-based auth (password_hash).
- Router tunggal `index.php?page=...`; layout sidebar di `includes/header.php`.
- Lokasi kode: `/app/bengkel/` (includes/, pages/, ajax/, bengkel.db, README.md).
- Preview: PHP built-in server di port 3000 (`php -S 0.0.0.0:3000 -t /app/bengkel`); frontend React dihentikan. Endpoint AJAX di `/ajax/` (bukan `/api/` karena ingress mengarahkan /api ke FastAPI:8001).
- DB SQLite: `/app/bengkel/bengkel.db` (auto-create + seed admin).

## User Personas
- Admin: kelola semua modul + manajemen pengguna.
- Kasir: transaksi POS, pelanggan, garansi.
- Mekanik: role tersedia (akses sama seperti kasir saat ini).

## Core Requirements (Static)
1. Login username/password, mudah dikelola (multi-user, role).
2. Dashboard: pendapatan hari ini, servis selesai, stok menipis, total pelanggan, klaim garansi aktif.
3. Pelanggan + kendaraan (merek/model/plat) + riwayat servis.
4. Sparepart: CRUD, import Excel/CSV, scan barcode, barang masuk/keluar, low stock alert.
5. POS: jasa + sparepart, stok otomatis berkurang, total otomatis, cetak nota.
6. Supplier CRUD.
7. Klaim garansi: GRS-YYYYMM-NNN, cari nota (nota/plat/nama), status pending/diproses/disetujui/ditolak, part pengganti potong stok, cetak bukti klaim.

## Yang Sudah Diimplementasikan (2026-06)
- Seluruh 7 modul core di atas, dalam PHP native + SQLite.
- Master Kategori Sparepart: CRUD kategori (pages/categories.php), dropdown kategori pada form sparepart, auto-register kategori baru saat import Excel.
- Rekap & Laporan (pages/reports.php): filter harian/mingguan/bulanan/tahunan/custom (dari-sampai tanggal), ringkasan jumlah transaksi + total jasa/sparepart/pendapatan.
- Export laporan (export.php): transaksi & daftar sparepart dalam format Excel (.xls), Word (.doc), PDF (print-view Save as PDF) — tanpa library eksternal agar tetap kompatibel cPanel/XAMPP.
- Pengaturan (pages/settings.php, admin): identitas bengkel (nama, NIB, pemilik, alamat, telepon) tampil di sidebar/login/nota/bukti garansi/laporan; tema warna gradasi via slider hue + live preview + preset, tersimpan di tabel settings.
- Perbaikan waktu cetakan: timestamp nota/bukti garansi/laporan dikonversi UTC→WIB (helper lokal()), ditambah "Waktu Cetak" realtime mengikuti jam perangkat (JS toLocaleString, tick tiap detik).
- Export laporan stok (export.php?type=stock): filter jenis (semua/masuk/keluar/penjualan/garansi) + rentang tanggal, format PDF/Excel/Word, tombol unduh di halaman Stok Masuk/Keluar.
- Diskon POS: nominal Rp / persen % sebelum simpan, tersimpan di kolom transactions.diskon (migrasi otomatis), tampil di struk nota & mempengaruhi grand total.
- Edit & hapus transaksi di Riwayat: edit memakai form kasir terisi (stok lama dikembalikan lalu dihitung ulang, nota tetap), hapus mengembalikan stok & menghapus movement; keduanya ditolak bila transaksi punya klaim garansi.
- Auth multi-user (admin/kasir/mekanik), seed admin/admin123.
- AJAX: lookup kendaraan per pelanggan, pencarian nota untuk garansi, import Excel via SheetJS.
- Barcode: kamera HP (html5-qrcode) + scanner USB (keyboard input) di halaman Sparepart & POS.
- Cetak struk nota & bukti klaim garansi (tampilan print-friendly).

## Backlog / Next Tasks
- P0: (menunggu hasil testing agent — perbaikan bug bila ada)
- P1: Pagination di tabel besar; laporan pendapatan per periode (export CSV); edit/batal transaksi.
- P2: Hak akses granular per role (mekanik hanya lihat garansi), backup database via UI, pencetakan barcode label.
