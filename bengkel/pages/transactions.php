<?php
$db = db();
$q = trim($_GET['q'] ?? '');
$dari = $_GET['dari'] ?? '';
$sampai = $_GET['sampai'] ?? '';

$sql = "SELECT t.*, c.nama AS customer_nama, v.plat_nomor FROM transactions t
        JOIN customers c ON c.id=t.customer_id LEFT JOIN vehicles v ON v.id=t.vehicle_id";
$where = []; $params = [];
if ($q !== '') { $where[] = "(t.no_nota LIKE ? OR c.nama LIKE ? OR v.plat_nomor LIKE ?)"; $params = array_merge($params, ["%$q%","%$q%","%$q%"]); }
if ($dari !== '') { $where[] = "date(t.created_at) >= ?"; $params[] = $dari; }
if ($sampai !== '') { $where[] = "date(t.created_at) <= ?"; $params[] = $sampai; }
if ($where) $sql .= " WHERE " . implode(' AND ', $where);
$sql .= " ORDER BY t.id DESC LIMIT 200";
$stmt = $db->prepare($sql); $stmt->execute($params);
$rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
$total = array_sum(array_column($rows, 'grand_total'));
?>
<div class="card table-card"><div class="card-body">
  <form class="row g-2 mb-3" method="get">
    <input type="hidden" name="page" value="transactions">
    <div class="col-md-4"><input name="q" class="form-control form-control-sm" placeholder="Cari nota / pelanggan / plat..." value="<?= esc($q) ?>" data-testid="trx-search"></div>
    <div class="col-md-3"><input name="dari" type="date" class="form-control form-control-sm" value="<?= esc($dari) ?>" data-testid="trx-dari"></div>
    <div class="col-md-3"><input name="sampai" type="date" class="form-control form-control-sm" value="<?= esc($sampai) ?>" data-testid="trx-sampai"></div>
    <div class="col-md-2"><button class="btn btn-sm btn-outline-primary w-100" data-testid="trx-filter-btn"><i class="bi bi-funnel me-1"></i>Filter</button></div>
  </form>
  <div class="table-responsive">
  <table class="table table-sm align-middle" data-testid="transactions-table">
    <thead><tr><th>Nota</th><th>Pelanggan</th><th>Plat</th><th class="text-end">Jasa</th><th class="text-end">Sparepart</th><th class="text-end">Total</th><th>Tanggal</th><th></th></tr></thead>
    <tbody>
    <?php if (!$rows): ?><tr><td colspan="8" class="text-center text-muted">Tidak ada transaksi ditemukan.</td></tr><?php endif; ?>
    <?php foreach ($rows as $r): ?>
      <tr>
        <td><?= esc($r['no_nota']) ?></td>
        <td><?= esc($r['customer_nama']) ?></td>
        <td><?= esc($r['plat_nomor'] ?? '-') ?></td>
        <td class="text-end"><?= rupiah($r['total_jasa']) ?></td>
        <td class="text-end"><?= rupiah($r['total_part']) ?></td>
        <td class="text-end fw-semibold"><?= rupiah($r['grand_total']) ?></td>
        <td class="small"><?= esc($r['created_at']) ?></td>
        <td class="text-end"><a class="btn btn-sm btn-outline-primary" href="index.php?page=receipt&id=<?= $r['id'] ?>" data-testid="trx-receipt-<?= $r['id'] ?>"><i class="bi bi-printer"></i></a></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
    <?php if ($rows): ?>
    <tfoot><tr class="fw-bold"><td colspan="5">Total (<?= count($rows) ?> transaksi)</td><td class="text-end" data-testid="trx-total-sum"><?= rupiah($total) ?></td><td colspan="2"></td></tr></tfoot>
    <?php endif; ?>
  </table>
  </div>
</div></div>
