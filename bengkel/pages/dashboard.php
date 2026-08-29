<?php
// Statistik ringkas dashboard
$db = db();
$pendapatan_hari_ini = (float)$db->query("SELECT COALESCE(SUM(grand_total),0) FROM transactions WHERE date(created_at,'+7 hours')=date('now','+7 hours')")->fetchColumn();
$servis_hari_ini     = (int)$db->query("SELECT COUNT(*) FROM transactions WHERE date(created_at,'+7 hours')=date('now','+7 hours')")->fetchColumn();
$servis_total        = (int)$db->query("SELECT COUNT(*) FROM transactions WHERE status='selesai'")->fetchColumn();
$stok_menipis        = (int)$db->query("SELECT COUNT(*) FROM parts WHERE stok <= stok_min")->fetchColumn();
$total_pelanggan     = (int)$db->query("SELECT COUNT(*) FROM customers")->fetchColumn();
$garansi_aktif       = (int)$db->query("SELECT COUNT(*) FROM warranty_claims WHERE status IN ('pending','diproses')")->fetchColumn();

$recent = $db->query("SELECT t.*, c.nama AS customer_nama, v.plat_nomor
    FROM transactions t
    JOIN customers c ON c.id = t.customer_id
    LEFT JOIN vehicles v ON v.id = t.vehicle_id
    ORDER BY t.id DESC LIMIT 8")->fetchAll(PDO::FETCH_ASSOC);

$low_parts = $db->query("SELECT * FROM parts WHERE stok <= stok_min ORDER BY stok ASC LIMIT 8")->fetchAll(PDO::FETCH_ASSOC);
?>
<div class="row row-cols-2 row-cols-md-3 row-cols-xl-5 g-3 mb-4">
  <div class="col">
    <div class="card stat-card"><div class="card-body" data-testid="stat-pendapatan">
      <div class="text-muted small">Pendapatan Hari Ini</div>
      <div class="fs-4 fw-bold text-success"><?= rupiah($pendapatan_hari_ini) ?></div>
    </div></div>
  </div>
  <div class="col">
    <div class="card stat-card"><div class="card-body" data-testid="stat-servis">
      <div class="text-muted small">Servis Selesai</div>
      <div class="fs-4 fw-bold text-primary"><?= $servis_total ?> <span class="fs-6 text-muted fw-normal">(+<?= $servis_hari_ini ?> hari ini)</span></div>
    </div></div>
  </div>
  <div class="col">
    <div class="card stat-card"><div class="card-body" data-testid="stat-stok-menipis">
      <div class="text-muted small">Stok Menipis</div>
      <div class="fs-4 fw-bold <?= $stok_menipis ? 'text-danger' : 'text-success' ?>"><?= $stok_menipis ?> item</div>
    </div></div>
  </div>
  <div class="col">
    <div class="card stat-card"><div class="card-body" data-testid="stat-pelanggan">
      <div class="text-muted small">Total Pelanggan</div>
      <div class="fs-4 fw-bold text-info"><?= $total_pelanggan ?></div>
    </div></div>
  </div>
  <div class="col">
    <div class="card stat-card"><div class="card-body" data-testid="stat-garansi">
      <div class="text-muted small">Klaim Garansi Aktif</div>
      <div class="fs-4 fw-bold <?= $garansi_aktif ? 'text-warning' : 'text-success' ?>"><?= $garansi_aktif ?> klaim</div>
      <a href="index.php?page=warranty" class="small">Kelola garansi &raquo;</a>
    </div></div>
  </div>
</div>

<div class="row g-3">
  <div class="col-lg-7">
    <div class="card table-card"><div class="card-body">
      <h2 class="h6 mb-3">Transaksi Terbaru</h2>
      <div class="table-responsive">
      <table class="table table-sm align-middle" data-testid="recent-transactions">
        <thead><tr><th>Nota</th><th>Pelanggan</th><th>Plat</th><th class="text-end">Total</th><th>Tanggal</th></tr></thead>
        <tbody>
        <?php if (!$recent): ?><tr><td colspan="5" class="text-center text-muted">Belum ada transaksi.</td></tr><?php endif; ?>
        <?php foreach ($recent as $t): ?>
          <tr>
            <td><a href="index.php?page=receipt&id=<?= $t['id'] ?>"><?= esc($t['no_nota']) ?></a></td>
            <td><?= esc($t['customer_nama']) ?></td>
            <td><?= esc($t['plat_nomor'] ?? '-') ?></td>
            <td class="text-end"><?= rupiah($t['grand_total']) ?></td>
            <td><?= esc(lokal($t['created_at'])) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
      </div>
    </div></div>
  </div>
  <div class="col-lg-5">
    <div class="card table-card"><div class="card-body">
      <h2 class="h6 mb-3 text-danger"><i class="bi bi-exclamation-triangle me-1"></i>Peringatan Stok Menipis</h2>
      <div class="table-responsive">
      <table class="table table-sm align-middle" data-testid="low-stock-list">
        <thead><tr><th>Kode</th><th>Barang</th><th class="text-end">Stok</th><th class="text-end">Min</th></tr></thead>
        <tbody>
        <?php if (!$low_parts): ?><tr><td colspan="4" class="text-center text-muted">Semua stok aman.</td></tr><?php endif; ?>
        <?php foreach ($low_parts as $p): ?>
          <tr>
            <td><?= esc($p['kode']) ?></td>
            <td><?= esc($p['nama']) ?></td>
            <td class="text-end"><span class="badge bg-danger"><?= $p['stok'] ?></span></td>
            <td class="text-end"><?= $p['stok_min'] ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
      </div>
    </div></div>
  </div>
</div>
