<?php
// ============================================================
// export.php - Unduh laporan dalam 3 format:
//   - Excel (.xls) : tabel HTML dengan MIME Excel, langsung terbuka di Excel
//   - Word  (.doc) : dokumen HTML dengan MIME Word
//   - PDF          : tampilan cetak -> pengguna memilih "Save as PDF"
// Tanpa library eksternal agar tetap ringan untuk cPanel/XAMPP.
// ============================================================
require_once __DIR__ . '/includes/db.php';
require_once __DIR__ . '/includes/auth.php';
require_login();
init_db();

$type   = $_GET['type'] ?? 'transactions';
$format = $_GET['format'] ?? 'xls';
// Whitelist parameter agar nilai tak dikenal tidak diproses sembarangan
if (!in_array($type, ['transactions', 'parts'], true)) $type = 'transactions';
if (!in_array($format, ['xls', 'doc', 'pdf'], true)) $format = 'pdf';
[, $dari, $sampai, $label] = resolve_periode();

// ---- Siapkan data sesuai jenis laporan ----
if ($type === 'parts') {
    $judul = 'Daftar Sparepart';
    $subjudul = 'Dicetak: ' . date('d/m/Y H:i');
    $headers = ['No','Kode','Barcode','Nama Barang','Kategori','Harga Beli','Harga Jual','Stok','Stok Min','Status'];
    $rows = db()->query("SELECT * FROM parts ORDER BY kategori, nama")->fetchAll(PDO::FETCH_ASSOC);
    $data = [];
    $no = 1;
    foreach ($rows as $r) {
        $data[] = [$no++, $r['kode'], $r['barcode'], $r['nama'], $r['kategori'],
                   rupiah($r['harga_beli']), rupiah($r['harga_jual']), $r['stok'], $r['stok_min'],
                   $r['stok'] <= $r['stok_min'] ? 'MENIPIS' : 'Aman'];
    }
    $footer = null;
    $fname = 'daftar_sparepart_' . date('Ymd');
} else {
    $judul = 'Laporan Transaksi';
    $subjudul = 'Periode: ' . $label;
    $headers = ['No','No. Nota','Tanggal','Pelanggan','Plat','Jasa','Sparepart','Total'];
    $rows = laporan_transaksi($dari, $sampai);
    $data = [];
    $no = 1; $tj = 0; $tp = 0; $ta = 0;
    foreach ($rows as $r) {
        $tj += $r['total_jasa']; $tp += $r['total_part']; $ta += $r['grand_total'];
        $data[] = [$no++, $r['no_nota'], lokal($r['created_at']), $r['customer_nama'], $r['plat_nomor'] ?: '-',
                   rupiah($r['total_jasa']), rupiah($r['total_part']), rupiah($r['grand_total'])];
    }
    $footer = ['', 'TOTAL (' . count($rows) . ' transaksi)', '', '', '', rupiah($tj), rupiah($tp), rupiah($ta)];
    $fname = 'laporan_transaksi_' . $dari . '_sd_' . $sampai;
}

// ---- Bangun tabel HTML (dipakai oleh semua format) ----
$html  = '<h2 style="margin:0">' . esc($judul) . '</h2>';
$html .= '<p style="margin:4px 0 12px">' . esc($subjudul) . ' &mdash; ' . esc(setting('nama_bengkel', 'Bengkel Motor')) . '</p>';
$html .= '<table border="1" cellspacing="0" cellpadding="6" style="border-collapse:collapse;width:100%;font-size:13px">';
$html .= '<thead><tr style="background:#1e2a38;color:#fff">';
foreach ($headers as $h) $html .= '<th>' . esc($h) . '</th>';
$html .= '</tr></thead><tbody>';
if (!$data) $html .= '<tr><td colspan="' . count($headers) . '" align="center">Tidak ada data.</td></tr>';
foreach ($data as $d) {
    $html .= '<tr>';
    foreach ($d as $c) $html .= '<td>' . esc($c) . '</td>';
    $html .= '</tr>';
}
if ($footer) {
    $html .= '<tr style="font-weight:bold;background:#eeeeee">';
    foreach ($footer as $c) $html .= '<td>' . esc($c) . '</td>';
    $html .= '</tr>';
}
$html .= '</tbody></table>';

// ---- Output sesuai format ----
if ($format === 'xls') {
    header('Content-Type: application/vnd.ms-excel; charset=UTF-8');
    header('Content-Disposition: attachment; filename="' . $fname . '.xls"');
    echo "\xEF\xBB\xBF" . $html; // BOM agar karakter UTF-8 terbaca benar di Excel
    exit;
}
if ($format === 'doc') {
    header('Content-Type: application/msword; charset=UTF-8');
    header('Content-Disposition: attachment; filename="' . $fname . '.doc"');
    echo "\xEF\xBB\xBF<html><head><meta charset=\"UTF-8\"></head><body>$html</body></html>";
    exit;
}
// format=pdf: halaman cetak (pilih "Save as PDF" pada dialog print browser)
?>
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<title><?= esc($judul) ?></title>
<style>
  body { font-family: Arial, sans-serif; padding: 24px; color: #222; }
  @media print { .no-print { display: none; } }
</style>
</head>
<body>
<div class="no-print" style="margin-bottom:14px" data-testid="pdf-toolbar">
  <button onclick="window.print()" data-testid="pdf-print-btn">Cetak / Simpan sebagai PDF</button>
  <button onclick="window.close()">Tutup</button>
  <span style="font-size:12px;color:#666">Pada dialog cetak, pilih tujuan <strong>"Save as PDF"</strong> untuk mengunduh file PDF.</span>
</div>
<?= $html ?>
<script>window.addEventListener('load', () => window.print());</script>
</body>
</html>
