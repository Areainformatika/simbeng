<?php
$db = db();
$action = $_POST['action'] ?? '';

// ---- Simpan (tambah / edit) sparepart ----
if ($action === 'save') {
    $id = (int)($_POST['id'] ?? 0);
    $kode = strtoupper(trim($_POST['kode'] ?? ''));
    $data = [
        $kode,
        trim($_POST['barcode'] ?? ''),
        trim($_POST['nama'] ?? ''),
        trim($_POST['kategori'] ?? ''),
        (float)($_POST['harga_beli'] ?? 0),
        (float)($_POST['harga_jual'] ?? 0),
        (int)($_POST['stok'] ?? 0),
        (int)($_POST['stok_min'] ?? 5),
    ];
    if ($kode !== '' && $data[2] !== '') {
        try {
            if ($id) {
                $db->prepare("UPDATE parts SET kode=?, barcode=?, nama=?, kategori=?, harga_beli=?, harga_jual=?, stok=?, stok_min=? WHERE id=?")
                   ->execute([...$data, $id]);
                set_flash('success', 'Data sparepart diperbarui.');
            } else {
                $db->prepare("INSERT INTO parts (kode, barcode, nama, kategori, harga_beli, harga_jual, stok, stok_min) VALUES (?,?,?,?,?,?,?,?)")
                   ->execute($data);
                set_flash('success', 'Sparepart baru ditambahkan.');
            }
        } catch (PDOException $e) {
            set_flash('danger', 'Gagal menyimpan: kode sparepart sudah digunakan.');
        }
    }
    header('Location: index.php?page=parts'); exit;
}
if ($action === 'delete') {
    $db->prepare("DELETE FROM parts WHERE id=?")->execute([(int)$_POST['id']]);
    set_flash('success', 'Sparepart dihapus.');
    header('Location: index.php?page=parts'); exit;
}

$q = trim($_GET['q'] ?? '');
$filter = $_GET['filter'] ?? '';
$sql = "SELECT * FROM parts";
$where = []; $params = [];
if ($q !== '') { $where[] = "(nama LIKE ? OR kode LIKE ? OR barcode LIKE ?)"; $params = ["%$q%", "%$q%", "%$q%"]; }
if ($filter === 'low') { $where[] = "stok <= stok_min"; }
if ($where) $sql .= " WHERE " . implode(' AND ', $where);
$sql .= " ORDER BY id DESC";
$stmt = $db->prepare($sql); $stmt->execute($params);
$rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

$edit = null;
if (isset($_GET['edit'])) {
    $s = $db->prepare("SELECT * FROM parts WHERE id=?"); $s->execute([(int)$_GET['edit']]);
    $edit = $s->fetch(PDO::FETCH_ASSOC);
}
// Master kategori untuk dropdown pada form input sparepart
$categories = $db->query("SELECT nama FROM categories ORDER BY nama")->fetchAll(PDO::FETCH_COLUMN);
?>
<div class="row g-3">
  <div class="col-lg-4">
    <div class="card table-card"><div class="card-body">
      <h2 class="h6"><?= $edit ? 'Edit Sparepart' : 'Tambah Sparepart' ?></h2>
      <form method="post" data-testid="part-form">
        <input type="hidden" name="action" value="save">
        <input type="hidden" name="id" value="<?= $edit['id'] ?? 0 ?>">
        <div class="row g-2">
          <div class="col-6 mb-2"><label class="form-label small">Kode Sparepart</label>
            <input name="kode" class="form-control form-control-sm" required value="<?= esc($edit['kode'] ?? '') ?>" data-testid="part-kode"></div>
          <div class="col-6 mb-2"><label class="form-label small">Barcode <button type="button" class="btn btn-sm btn-outline-secondary py-0 px-1" data-bs-toggle="modal" data-bs-target="#scanModal" data-scan-target="part-barcode" data-testid="part-scan-btn"><i class="bi bi-upc-scan"></i></button></label>
            <input name="barcode" id="part-barcode" class="form-control form-control-sm" value="<?= esc($edit['barcode'] ?? '') ?>" data-testid="part-barcode"></div>
          <div class="col-12 mb-2"><label class="form-label small">Nama Barang</label>
            <input name="nama" class="form-control form-control-sm" required value="<?= esc($edit['nama'] ?? '') ?>" data-testid="part-nama"></div>
          <div class="col-12 mb-2"><label class="form-label small">Kategori <a href="index.php?page=categories" class="text-decoration-none">(kelola kategori)</a></label>
            <select name="kategori" class="form-select form-select-sm" data-testid="part-kategori">
              <option value="">- Tanpa kategori -</option>
              <?php $katEdit = $edit['kategori'] ?? ''; $katAda = in_array($katEdit, $categories, true); ?>
              <?php foreach ($categories as $cat): ?>
              <option value="<?= esc($cat) ?>" <?= $katEdit === $cat ? 'selected' : '' ?>><?= esc($cat) ?></option>
              <?php endforeach; ?>
              <?php if ($katEdit !== '' && !$katAda): ?><option value="<?= esc($katEdit) ?>" selected><?= esc($katEdit) ?> (lama)</option><?php endif; ?>
            </select></div>
          <div class="col-6 mb-2"><label class="form-label small">Harga Beli</label>
            <input name="harga_beli" type="number" min="0" class="form-control form-control-sm" value="<?= esc($edit['harga_beli'] ?? 0) ?>" data-testid="part-harga-beli"></div>
          <div class="col-6 mb-2"><label class="form-label small">Harga Jual</label>
            <input name="harga_jual" type="number" min="0" class="form-control form-control-sm" value="<?= esc($edit['harga_jual'] ?? 0) ?>" data-testid="part-harga-jual"></div>
          <div class="col-6 mb-2"><label class="form-label small">Stok Saat Ini</label>
            <input name="stok" type="number" min="0" class="form-control form-control-sm" value="<?= esc($edit['stok'] ?? 0) ?>" data-testid="part-stok"></div>
          <div class="col-6 mb-3"><label class="form-label small">Stok Minimum (alert)</label>
            <input name="stok_min" type="number" min="0" class="form-control form-control-sm" value="<?= esc($edit['stok_min'] ?? 5) ?>" data-testid="part-stok-min"></div>
        </div>
        <button class="btn btn-sm btn-primary w-100" data-testid="part-submit"><?= $edit ? 'Simpan Perubahan' : 'Tambah Sparepart' ?></button>
        <?php if ($edit): ?><a href="index.php?page=parts" class="btn btn-sm btn-outline-secondary w-100 mt-2">Batal</a><?php endif; ?>
      </form>
    </div></div>

    <div class="card table-card mt-3"><div class="card-body">
      <h2 class="h6">Import Excel / CSV</h2>
      <p class="small text-muted mb-2">Format kolom: <code>kode, nama, kategori, harga_beli, harga_jual, stok, stok_min, barcode</code>. Kode yang sudah ada akan diperbarui.</p>
      <input type="file" id="importFile" accept=".xlsx,.xls,.csv" class="form-control form-control-sm mb-2" data-testid="import-file">
      <div id="importResult" class="small" data-testid="import-result"></div>
      <button type="button" class="btn btn-sm btn-outline-success w-100 mt-1" onclick="downloadTemplate()" data-testid="import-template-btn"><i class="bi bi-download me-1"></i>Download Template CSV</button>
    </div></div>
  </div>

  <div class="col-lg-8">
    <div class="card table-card"><div class="card-body">
      <div class="d-flex justify-content-end gap-1 mb-2" data-testid="parts-export-buttons">
        <a class="btn btn-sm btn-outline-danger" target="_blank" href="export.php?type=parts&format=pdf" data-testid="parts-export-pdf"><i class="bi bi-file-earmark-pdf me-1"></i>PDF</a>
        <a class="btn btn-sm btn-outline-success" href="export.php?type=parts&format=xls" data-testid="parts-export-xls"><i class="bi bi-file-earmark-excel me-1"></i>Excel</a>
        <a class="btn btn-sm btn-outline-primary" href="export.php?type=parts&format=doc" data-testid="parts-export-doc"><i class="bi bi-file-earmark-word me-1"></i>Word</a>
      </div>
      <form class="d-flex mb-3" method="get">
        <input type="hidden" name="page" value="parts">
        <input name="q" class="form-control form-control-sm me-2" placeholder="Cari nama / kode / barcode..." value="<?= esc($q) ?>" data-testid="part-search">
        <button class="btn btn-sm btn-outline-primary me-2" data-testid="part-search-btn"><i class="bi bi-search"></i></button>
        <a href="index.php?page=parts&filter=low" class="btn btn-sm btn-outline-danger text-nowrap" data-testid="part-low-filter"><i class="bi bi-exclamation-triangle me-1"></i>Stok Menipis</a>
      </form>
      <div class="table-responsive">
      <table class="table table-sm align-middle" data-testid="parts-table">
        <thead><tr><th>Kode</th><th>Nama</th><th>Kategori</th><th class="text-end">H. Beli</th><th class="text-end">H. Jual</th><th class="text-end">Stok</th><th class="text-end">Aksi</th></tr></thead>
        <tbody>
        <?php if (!$rows): ?><tr><td colspan="7" class="text-center text-muted">Belum ada data sparepart.</td></tr><?php endif; ?>
        <?php foreach ($rows as $r): $low = $r['stok'] <= $r['stok_min']; ?>
          <tr class="<?= $low ? 'table-danger' : '' ?>">
            <td><?= esc($r['kode']) ?></td>
            <td><?= esc($r['nama']) ?><?php if ($r['barcode']): ?> <i class="bi bi-upc text-muted" title="<?= esc($r['barcode']) ?>"></i><?php endif; ?></td>
            <td><?= esc($r['kategori']) ?></td>
            <td class="text-end"><?= rupiah($r['harga_beli']) ?></td>
            <td class="text-end"><?= rupiah($r['harga_jual']) ?></td>
            <td class="text-end"><span class="badge bg-<?= $low ? 'danger' : 'success' ?>" data-testid="part-stok-badge-<?= $r['id'] ?>"><?= $r['stok'] ?></span></td>
            <td class="text-end text-nowrap">
              <a class="btn btn-sm btn-outline-primary" href="index.php?page=parts&edit=<?= $r['id'] ?>" data-testid="part-edit-<?= $r['id'] ?>"><i class="bi bi-pencil"></i></a>
              <form method="post" class="d-inline" onsubmit="return confirm('Hapus sparepart ini?')">
                <input type="hidden" name="action" value="delete"><input type="hidden" name="id" value="<?= $r['id'] ?>">
                <button class="btn btn-sm btn-outline-danger" data-testid="part-delete-<?= $r['id'] ?>"><i class="bi bi-trash"></i></button>
              </form>
            </td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
      </div>
    </div></div>
  </div>
</div>

<!-- Modal scan barcode via kamera HP -->
<div class="modal fade" id="scanModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title">Scan Barcode</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <div class="modal-body"><div id="scanner" style="width:100%"></div></div>
  </div></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<script>
let scannerObj = null, scanTarget = null;
const scanModal = document.getElementById('scanModal');
scanModal.addEventListener('shown.bs.modal', e => {
  scanTarget = e.relatedTarget.dataset.scanTarget;
  scannerObj = new Html5Qrcode("scanner");
  scannerObj.start({ facingMode: "environment" }, { fps: 10, qrbox: 250 }, text => {
    document.getElementById(scanTarget).value = text;
    bootstrap.Modal.getInstance(scanModal).hide();
  }, () => {});
});
scanModal.addEventListener('hidden.bs.modal', () => { if (scannerObj) scannerObj.stop().catch(()=>{}); });

// Import Excel/CSV di sisi browser (SheetJS), hasil dikirim JSON ke server
document.getElementById('importFile').addEventListener('change', function() {
  const f = this.files[0]; if (!f) return;
  const reader = new FileReader();
  reader.onload = async e => {
    const wb = XLSX.read(e.target.result, { type: 'array' });
    const rows = XLSX.utils.sheet_to_json(wb.Sheets[wb.SheetNames[0]]);
    const res = await fetch('ajax/import_parts.php', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows })
    });
    const data = await res.json();
    const el = document.getElementById('importResult');
    el.innerHTML = '<div class="alert alert-' + (data.ok ? 'success' : 'danger') + ' py-2">' + data.message + '</div>';
    if (data.ok) setTimeout(() => location.reload(), 1500);
  };
  reader.readAsArrayBuffer(f);
});

function downloadTemplate() {
  const csv = "kode,nama,kategori,harga_beli,harga_jual,stok,stok_min,barcode\nOLI-MPX,Oli MPX 0.8L,Oli,35000,45000,10,5,899123456001\n";
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = 'template_sparepart.csv'; a.click();
}
</script>
