<?php
$db = db();
$action = $_POST['action'] ?? '';

// ---- Transaksi barang masuk (dari supplier) ----
if ($action === 'masuk') {
    $part_id = (int)$_POST['part_id'];
    $jumlah = max(1, (int)$_POST['jumlah']);
    $supplier_id = (int)($_POST['supplier_id'] ?? 0) ?: null;
    $ket = trim($_POST['keterangan'] ?? '');
    // Validasi sparepart harus ada agar tidak gagal foreign key
    $cek = $db->prepare("SELECT id FROM parts WHERE id=?");
    $cek->execute([$part_id]);
    if (!$cek->fetchColumn()) {
        set_flash('danger', 'Sparepart tidak ditemukan.');
        header('Location: index.php?page=stock'); exit;
    }
    try {
        $db->beginTransaction();
        $db->prepare("UPDATE parts SET stok = stok + ? WHERE id=?")->execute([$jumlah, $part_id]);
        $db->prepare("INSERT INTO stock_movements (part_id, tipe, jumlah, supplier_id, ref_type, keterangan) VALUES (?,?,?,?,?,?)")
           ->execute([$part_id, 'masuk', $jumlah, $supplier_id, 'manual', $ket]);
        $db->commit();
        set_flash('success', "Stok bertambah $jumlah unit.");
    } catch (Exception $e) {
        $db->rollBack();
        set_flash('danger', 'Gagal mencatat barang masuk: ' . $e->getMessage());
    }
    header('Location: index.php?page=stock'); exit;
}

// ---- Transaksi barang keluar (manual / penyesuaian) ----
if ($action === 'keluar') {
    $part_id = (int)$_POST['part_id'];
    $jumlah = max(1, (int)$_POST['jumlah']);
    $ket = trim($_POST['keterangan'] ?? '');
    $cekStok = $db->prepare("SELECT stok FROM parts WHERE id=?");
    $cekStok->execute([$part_id]);
    $stok = (int)$cekStok->fetchColumn();
    if ($jumlah > $stok) {
        set_flash('danger', "Stok tidak mencukupi (tersedia: $stok).");
    } else {
        $db->beginTransaction();
        $db->prepare("UPDATE parts SET stok = stok - ? WHERE id=?")->execute([$jumlah, $part_id]);
        $db->prepare("INSERT INTO stock_movements (part_id, tipe, jumlah, ref_type, keterangan) VALUES (?,?,?,?,?)")
           ->execute([$part_id, 'keluar', $jumlah, 'manual', $ket]);
        $db->commit();
        set_flash('success', "Stok berkurang $jumlah unit.");
    }
    header('Location: index.php?page=stock'); exit;
}

$parts = $db->query("SELECT id, kode, nama, stok FROM parts ORDER BY nama")->fetchAll(PDO::FETCH_ASSOC);
$suppliers = $db->query("SELECT id, nama FROM suppliers ORDER BY nama")->fetchAll(PDO::FETCH_ASSOC);
$log = $db->query("SELECT sm.*, p.kode, p.nama AS part_nama, s.nama AS supplier_nama
    FROM stock_movements sm
    JOIN parts p ON p.id = sm.part_id
    LEFT JOIN suppliers s ON s.id = sm.supplier_id
    ORDER BY sm.id DESC LIMIT 50")->fetchAll(PDO::FETCH_ASSOC);
?>
<div class="row g-3">
  <div class="col-lg-4">
    <div class="card table-card"><div class="card-body">
      <h2 class="h6 text-success"><i class="bi bi-box-arrow-in-down me-1"></i>Barang Masuk (dari Supplier)</h2>
      <form method="post" data-testid="stock-in-form">
        <input type="hidden" name="action" value="masuk">
        <div class="mb-2"><label class="form-label small">Sparepart</label>
          <select name="part_id" class="form-select form-select-sm" required data-testid="stock-in-part">
            <?php foreach ($parts as $p): ?><option value="<?= $p['id'] ?>"><?= esc($p['kode']) ?> - <?= esc($p['nama']) ?> (stok: <?= $p['stok'] ?>)</option><?php endforeach; ?>
          </select></div>
        <div class="mb-2"><label class="form-label small">Jumlah Masuk</label>
          <input name="jumlah" type="number" min="1" value="1" class="form-control form-control-sm" required data-testid="stock-in-jumlah"></div>
        <div class="mb-2"><label class="form-label small">Supplier</label>
          <select name="supplier_id" class="form-select form-select-sm" data-testid="stock-in-supplier">
            <option value="">- Pilih supplier -</option>
            <?php foreach ($suppliers as $s): ?><option value="<?= $s['id'] ?>"><?= esc($s['nama']) ?></option><?php endforeach; ?>
          </select></div>
        <div class="mb-3"><label class="form-label small">Keterangan</label>
          <input name="keterangan" class="form-control form-control-sm" placeholder="No. faktur supplier, dll." data-testid="stock-in-keterangan"></div>
        <button class="btn btn-sm btn-success w-100" data-testid="stock-in-submit">Catat Barang Masuk</button>
      </form>
    </div></div>

    <div class="card table-card mt-3"><div class="card-body">
      <h2 class="h6 text-danger"><i class="bi bi-box-arrow-up me-1"></i>Barang Keluar (Manual)</h2>
      <form method="post" data-testid="stock-out-form">
        <input type="hidden" name="action" value="keluar">
        <div class="mb-2"><label class="form-label small">Sparepart</label>
          <select name="part_id" class="form-select form-select-sm" required data-testid="stock-out-part">
            <?php foreach ($parts as $p): ?><option value="<?= $p['id'] ?>"><?= esc($p['kode']) ?> - <?= esc($p['nama']) ?> (stok: <?= $p['stok'] ?>)</option><?php endforeach; ?>
          </select></div>
        <div class="mb-2"><label class="form-label small">Jumlah Keluar</label>
          <input name="jumlah" type="number" min="1" value="1" class="form-control form-control-sm" required data-testid="stock-out-jumlah"></div>
        <div class="mb-3"><label class="form-label small">Keterangan</label>
          <input name="keterangan" class="form-control form-control-sm" placeholder="Rusak, retur, dipakai internal..." data-testid="stock-out-keterangan"></div>
        <button class="btn btn-sm btn-danger w-100" data-testid="stock-out-submit">Catat Barang Keluar</button>
      </form>
      <p class="small text-muted mt-2 mb-0">Catatan: penjualan via Kasir & penggantian garansi mengurangi stok secara otomatis.</p>
    </div></div>
  </div>

  <div class="col-lg-8">
    <div class="card table-card"><div class="card-body">
      <h2 class="h6 mb-3">Riwayat Pergerakan Stok (50 terakhir)</h2>
      <div class="table-responsive">
      <table class="table table-sm align-middle" data-testid="stock-log-table">
        <thead><tr><th>Tanggal</th><th>Barang</th><th>Tipe</th><th class="text-end">Jumlah</th><th>Supplier/Sumber</th><th>Keterangan</th></tr></thead>
        <tbody>
        <?php if (!$log): ?><tr><td colspan="6" class="text-center text-muted">Belum ada pergerakan stok.</td></tr><?php endif; ?>
        <?php foreach ($log as $l): ?>
          <tr>
            <td class="small"><?= esc($l['created_at']) ?></td>
            <td><?= esc($l['kode']) ?> - <?= esc($l['part_nama']) ?></td>
            <td><span class="badge bg-<?= $l['tipe']==='masuk' ? 'success' : 'danger' ?>"><?= strtoupper($l['tipe']) ?></span>
              <?php if ($l['ref_type'] && $l['ref_type'] !== 'manual'): ?><span class="badge bg-secondary"><?= esc($l['ref_type']) ?></span><?php endif; ?></td>
            <td class="text-end"><?= $l['jumlah'] ?></td>
            <td><?= esc($l['supplier_nama'] ?? '-') ?></td>
            <td class="small text-muted"><?= esc($l['keterangan']) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
      </div>
    </div></div>
  </div>
</div>
