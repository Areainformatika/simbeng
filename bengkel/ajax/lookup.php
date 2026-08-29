<?php
// ============================================================
// lookup.php - Endpoint JSON untuk kebutuhan AJAX halaman
// ?action=vehicles&customer_id=..   -> kendaraan milik pelanggan
// ?action=search_trx&q=..           -> cari nota (garansi)
// ============================================================
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';
require_login();
init_db();
header('Content-Type: application/json');

$db = db();
$action = $_GET['action'] ?? '';

if ($action === 'vehicles') {
    $stmt = $db->prepare("SELECT id, merek, model, plat_nomor FROM vehicles WHERE customer_id=? ORDER BY id DESC");
    $stmt->execute([(int)($_GET['customer_id'] ?? 0)]);
    echo json_encode($stmt->fetchAll(PDO::FETCH_ASSOC));
    exit;
}

// Cari transaksi berdasarkan no nota / plat / nama pelanggan (modul garansi)
if ($action === 'search_trx') {
    $q = trim($_GET['q'] ?? '');
    $stmt = $db->prepare("SELECT t.id, t.no_nota, t.created_at, c.nama AS customer_nama, v.plat_nomor
        FROM transactions t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN vehicles v ON v.id = t.vehicle_id
        WHERE t.no_nota LIKE ? OR c.nama LIKE ? OR v.plat_nomor LIKE ?
        ORDER BY t.id DESC LIMIT 10");
    $stmt->execute(["%$q%", "%$q%", "%$q%"]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $itemStmt = $db->prepare("SELECT id, tipe, nama, qty, harga, subtotal, garansi_hari FROM transaction_items WHERE transaction_id=?");
    foreach ($rows as &$r) {
        $itemStmt->execute([$r['id']]);
        $r['items'] = $itemStmt->fetchAll(PDO::FETCH_ASSOC);
        // Sediakan versi WIB untuk tampilan & perhitungan masa garansi di browser
        $r['created_at_wib'] = lokal($r['created_at']);
        $r['tgl_beli_wib'] = lokal($r['created_at'], 'Y-m-d');
    }
    echo json_encode($rows);
    exit;
}

echo json_encode(['error' => 'unknown action']);
