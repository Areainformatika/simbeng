<?php
// ============================================================
// index.php - Front controller (router) aplikasi bengkel motor
// ============================================================
require_once __DIR__ . '/includes/db.php';
require_once __DIR__ . '/includes/auth.php';

init_db();

$page = $_GET['page'] ?? 'dashboard';

if ($page === 'logout') logout();

if ($page === 'login') {
    if (is_logged_in()) { header('Location: index.php'); exit; }
    require __DIR__ . '/pages/login.php';
    exit;
}

require_login();

// Daftar halaman yang diizinkan beserta judulnya
$routes = [
    'dashboard'      => 'Dashboard',
    'customers'      => 'Manajemen Pelanggan',
    'suppliers'      => 'Data Supplier',
    'parts'          => 'Inventory Sparepart',
    'stock'          => 'Barang Masuk & Keluar',
    'pos'            => 'Kasir / Transaksi Servis',
    'transactions'   => 'Riwayat Transaksi',
    'receipt'        => 'Struk Nota',
    'warranty'       => 'Klaim Garansi',
    'warranty_print' => 'Bukti Klaim Garansi',
    'users'          => 'Manajemen Pengguna',
];
if (!isset($routes[$page])) $page = 'dashboard';

// Halaman cetak tampil tanpa sidebar (bare)
$bare = in_array($page, ['receipt', 'warranty_print'], true);

$title = $routes[$page];
if (!$bare) require __DIR__ . '/includes/header.php';
require __DIR__ . '/pages/' . $page . '.php';
if (!$bare) require __DIR__ . '/includes/footer.php';
