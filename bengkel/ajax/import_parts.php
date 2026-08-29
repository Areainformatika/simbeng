<?php
// ============================================================
// import_parts.php - Import massal sparepart dari Excel/CSV
// Menerima JSON: { rows: [ {kode, nama, kategori, harga_beli,
// harga_jual, stok, stok_min, barcode}, ... ] }
// Upsert berdasarkan kolom "kode".
// ============================================================
require_once __DIR__ . '/../includes/db.php';
require_once __DIR__ . '/../includes/auth.php';
require_login();
init_db();
header('Content-Type: application/json');

$payload = json_decode(file_get_contents('php://input'), true);
$rows = $payload['rows'] ?? [];
if (!$rows) { echo json_encode(['ok' => false, 'message' => 'File kosong atau format tidak dikenali.']); exit; }

$db = db();
$find = $db->prepare("SELECT id FROM parts WHERE kode = ?");
$ins  = $db->prepare("INSERT INTO parts (kode, nama, kategori, harga_beli, harga_jual, stok, stok_min, barcode) VALUES (?,?,?,?,?,?,?,?)");
$upd  = $db->prepare("UPDATE parts SET nama=?, kategori=?, harga_beli=?, harga_jual=?, stok=?, stok_min=?, barcode=? WHERE kode=?");

$inserted = 0; $updated = 0; $skipped = 0;
$db->beginTransaction();
foreach ($rows as $r) {
    // Normalisasi nama kolom (dukung variasi huruf besar/kecil & spasi)
    $row = [];
    foreach ($r as $k => $v) $row[strtolower(trim((string)$k))] = $v;
    $kode = strtoupper(trim((string)($row['kode'] ?? '')));
    $nama = trim((string)($row['nama'] ?? ''));
    if ($kode === '' || $nama === '') { $skipped++; continue; }
    $vals = [
        $nama,
        trim((string)($row['kategori'] ?? '')),
        (float)($row['harga_beli'] ?? 0),
        (float)($row['harga_jual'] ?? 0),
        (int)($row['stok'] ?? 0),
        (int)($row['stok_min'] ?? 5),
        trim((string)($row['barcode'] ?? '')),
    ];
    $find->execute([$kode]);
    if ($find->fetchColumn()) {
        $upd->execute([...$vals, $kode]);
        $updated++;
    } else {
        $ins->execute([$kode, ...$vals]);
        $inserted++;
    }
}
$db->commit();
echo json_encode(['ok' => true, 'message' => "Import selesai: $inserted ditambah, $updated diperbarui, $skipped dilewati."]);
