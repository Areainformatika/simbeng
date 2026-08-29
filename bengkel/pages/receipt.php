<?php
// Struk nota sederhana (tampilan cetak, tanpa sidebar)
$db = db();
$id = (int)($_GET['id'] ?? 0);
$t = $db->prepare("SELECT t.*, c.nama AS customer_nama, c.telepon, v.merek, v.model, v.plat_nomor
    FROM transactions t JOIN customers c ON c.id=t.customer_id LEFT JOIN vehicles v ON v.id=t.vehicle_id WHERE t.id=?");
$t->execute([$id]);
$t = $t->fetch(PDO::FETCH_ASSOC);
if (!$t) { echo '<p style="font-family:sans-serif">Transaksi tidak ditemukan. <a href="index.php">Kembali</a></p>'; return; }
$items = $db->prepare("SELECT * FROM transaction_items WHERE transaction_id=?");
$items->execute([$id]);
$items = $items->fetchAll(PDO::FETCH_ASSOC);
?>
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<title>Nota <?= esc($t['no_nota']) ?></title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
  body { background: #eee; font-family: monospace; }
  .nota { max-width: 380px; margin: 20px auto; background: #fff; padding: 20px; }
  .nota table { width: 100%; font-size: 13px; }
  .garansi-info { font-size: 11px; color: #444; }
  @media print { .no-print { display: none; } body { background: #fff; } .nota { margin: 0; } }
</style>
</head>
<body>
<div class="nota" data-testid="receipt">
  <div class="text-center">
    <strong style="font-size:16px"><?= esc(strtoupper(setting('nama_bengkel', 'BENGKEL MOTOR'))) ?></strong><br>
    <?php if (setting('alamat')): ?><span style="font-size:12px"><?= esc(setting('alamat')) ?><?= setting('telepon') ? ' - Telp ' . esc(setting('telepon')) : '' ?></span><br><?php endif; ?>
    <?php if (setting('nib')): ?><span style="font-size:11px">NIB: <?= esc(setting('nib')) ?></span><br><?php endif; ?>
    <?php if (setting('pemilik')): ?><span style="font-size:11px">Pemilik: <?= esc(setting('pemilik')) ?></span><br><?php endif; ?>
    <hr>
  </div>
  <table>
    <tr><td>Nota</td><td>: <?= esc($t['no_nota']) ?></td></tr>
    <tr><td>Tanggal</td><td>: <?= esc(lokal($t['created_at'])) ?> WIB</td></tr>
    <tr><td>Waktu Cetak</td><td>: <span id="waktuCetak" data-testid="waktu-cetak"></span></td></tr>
    <tr><td>Pelanggan</td><td>: <?= esc($t['customer_nama']) ?></td></tr>
    <?php if ($t['plat_nomor']): ?>
    <tr><td>Kendaraan</td><td>: <?= esc($t['merek'] . ' ' . $t['model'] . ' / ' . $t['plat_nomor']) ?></td></tr>
    <?php endif; ?>
  </table>
  <hr>
  <table>
    <?php foreach ($items as $it): ?>
    <tr>
      <td><?= esc($it['nama']) ?><?= $it['tipe']==='part' ? " x{$it['qty']}" : '' ?>
        <?php if ($it['garansi_hari'] > 0): ?>
        <div class="garansi-info">Garansi <?= $it['garansi_hari'] ?> hari s.d. <?= date('d/m/Y', strtotime(lokal($t['created_at'], 'Y-m-d') . " +{$it['garansi_hari']} days")) ?></div>
        <?php endif; ?>
      </td>
      <td class="text-end"><?= number_format($it['subtotal'], 0, ',', '.') ?></td>
    </tr>
    <?php endforeach; ?>
  </table>
  <hr>
  <table>
    <tr><td>Jasa</td><td class="text-end"><?= number_format($t['total_jasa'], 0, ',', '.') ?></td></tr>
    <tr><td>Sparepart</td><td class="text-end"><?= number_format($t['total_part'], 0, ',', '.') ?></td></tr>
    <tr><td><strong>TOTAL</strong></td><td class="text-end"><strong><?= rupiah($t['grand_total']) ?></strong></td></tr>
  </table>
  <hr>
  <p class="text-center mb-0" style="font-size:12px">Terima kasih atas kepercayaan Anda.<br>Simpan nota ini sebagai bukti garansi.</p>
  <div class="text-center mt-3 no-print">
    <button onclick="window.print()" class="btn btn-primary btn-sm" data-testid="print-btn"><i class="bi bi-printer"></i> Cetak</button>
    <a href="index.php?page=pos" class="btn btn-outline-secondary btn-sm" data-testid="new-trx-btn">Transaksi Baru</a>
    <a href="index.php" class="btn btn-outline-secondary btn-sm">Dashboard</a>
  </div>
</div>
<script>
// Waktu cetak realtime mengikuti jam perangkat pengguna
function tickWaktu() {
  const el = document.getElementById('waktuCetak');
  if (el) el.textContent = new Date().toLocaleString('id-ID', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
tickWaktu();
setInterval(tickWaktu, 1000);
</script>
</body>
</html>
