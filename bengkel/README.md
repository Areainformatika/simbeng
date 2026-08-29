# Sistem Manajemen Bengkel Motor (PHP Native + SQLite)

Aplikasi web manajemen bengkel motor: dashboard, pelanggan & kendaraan, inventory sparepart (barang masuk/keluar, import Excel, scan barcode), kasir/POS dengan cetak struk, data supplier, dan klaim garansi.

## Kebutuhan
- PHP 7.4+ (atau PHP 8.x) dengan ekstensi `pdo_sqlite` / `sqlite3`
- Tidak butuh MySQL, tidak butuh Composer

## Cara Menjalankan

### A. XAMPP (Windows/Mac/Linux)
1. Install XAMPP, pastikan ekstensi SQLite aktif (default sudah aktif di `php.ini`: `extension=pdo_sqlite` dan `extension=sqlite3`).
2. Salin seluruh folder `bengkel/` ke `C:\xampp\htdocs\bengkel`.
3. Jalankan Apache dari XAMPP Control Panel.
4. Buka browser: `http://localhost/bengkel/`

### B. cPanel / Shared Hosting
1. Upload seluruh isi folder `bengkel/` ke `public_html/` (atau subfolder, misal `public_html/bengkel/`).
2. Pastikan versi PHP di cPanel >= 7.4 dan ekstensi SQLite aktif (menu "Select PHP Version" > centang `sqlite3` / `pdo_sqlite`).
3. Pastikan folder aplikasi writable (permission 755/775) agar file `bengkel.db` bisa dibuat otomatis.
4. Akses `https://domainanda.com/` atau `https://domainanda.com/bengkel/`.

### C. Tanpa web server (PHP built-in, untuk tes lokal)
```bash
cd bengkel
php -S localhost:8000
```
Buka `http://localhost:8000`.

## Login Default
- Username: `admin`
- Password: `admin123`

Segera ganti password melalui menu **Pengguna** setelah login pertama. Database `bengkel.db` otomatis dibuat beserta akun admin saat aplikasi pertama kali diakses.

## Struktur Folder
```
bengkel/
├── index.php            # Router utama
├── bengkel.db           # Database SQLite (auto-create)
├── includes/
│   ├── db.php           # Koneksi + skema database + helper
│   ├── auth.php         # Manajemen sesi login
│   ├── header.php       # Layout + sidebar
│   └── footer.php
├── pages/               # Halaman: login, dashboard, customers, parts,
│                        # stock, pos, receipt, transactions, suppliers,
│                        # warranty, warranty_print, users
└── ajax/                # Endpoint JSON (lookup kendaraan, cari nota, import Excel)
```

## Fitur
- **Dashboard**: pendapatan hari ini, servis selesai, stok menipis, total pelanggan, klaim garansi aktif.
- **Pelanggan**: CRUD pelanggan + kendaraan (merek, model, plat) + riwayat servis per pelanggan.
- **Sparepart**: CRUD, low stock alert, import Excel/CSV (SheetJS), scan barcode via kamera HP / scanner USB.
- **Stok Masuk/Keluar**: pencatatan dari supplier, barang keluar manual, riwayat pergerakan stok.
- **Kasir/POS**: pilih pelanggan & kendaraan, item jasa + sparepart, stok berkurang otomatis, cetak struk nota.
- **Supplier**: CRUD data supplier.
- **Klaim Garansi**: kode otomatis (GRS-YYYYMM-NNN), pencarian nota, pengajuan klaim, update status (pending/diproses/disetujui/ditolak), penggantian part otomatis mengurangi stok, cetak bukti klaim.
- **Pengguna**: manajemen multi-user dengan role admin/kasir/mekanik (khusus admin).
