<?php
$db = db();

// ---- Simpan transaksi servis / penjualan (baru atau edit) ----
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'save_trx') {
    $edit_id     = (int)($_POST['edit_id'] ?? 0);
    $customer_id = (int)$_POST['customer_id'];
    $vehicle_id  = (int)($_POST['vehicle_id'] ?? 0) ?: null;
    $jasa_nama   = $_POST['jasa_nama'] ?? [];
    $jasa_biaya  = $_POST['jasa_biaya'] ?? [];
    $jasa_garansi= $_POST['jasa_garansi'] ?? [];
    $part_id     = $_POST['part_id'] ?? [];
    $part_qty    = $_POST['part_qty'] ?? [];
    $part_garansi= $_POST['part_garansi'] ?? [];
    $back = $edit_id ? "index.php?page=pos&edit=$edit_id" : "index.php?page=pos";

    // Saat edit: tolak bila ada klaim garansi, dan stok item lama dianggap tersedia kembali
    $old_qty_map = [];
    if ($edit_id) {
        $kl = $db->prepare("SELECT COUNT(*) FROM warranty_claims WHERE transaction_id=?");
        $kl->execute([$edit_id]);
        if ((int)$kl->fetchColumn() > 0) {
            set_flash('danger', 'Transaksi ini memiliki klaim garansi terkait dan tidak dapat diedit.');
            header('Location: index.php?page=transactions'); exit;
        }
        $oq = $db->prepare("SELECT part_id, SUM(qty) FROM transaction_items WHERE transaction_id=? AND tipe='part' GROUP BY part_id");
        $oq->execute([$edit_id]);
        foreach ($oq->fetchAll(PDO::FETCH_KEY_PAIR) as $pid => $q) $old_qty_map[(int)$pid] = (int)$q;
    }

    // Kumpulkan item jasa
    $items = [];
    $total_jasa = 0;
    foreach ($jasa_nama as $i => $nm) {
        $nm = trim($nm);
        $biaya = (float)($jasa_biaya[$i] ?? 0);
        if ($nm === '' || $biaya <= 0) continue;
        $items[] = ['tipe'=>'jasa', 'part_id'=>null, 'nama'=>$nm, 'qty'=>1, 'harga'=>$biaya, 'subtotal'=>$biaya, 'garansi_hari'=>(int)($jasa_garansi[$i] ?? 0)];
        $total_jasa += $biaya;
    }
    // Kumpulkan item sparepart
    $total_part = 0;
    foreach ($part_id as $i => $pid) {
        $pid = (int)$pid; $qty = max(1, (int)($part_qty[$i] ?? 1));
        if (!$pid) continue;
        $p = $db->prepare("SELECT * FROM parts WHERE id=?"); $p->execute([$pid]);
        $p = $p->fetch(PDO::FETCH_ASSOC);
        if (!$p) continue;
        $tersedia = (int)$p['stok'] + ($old_qty_map[$pid] ?? 0);
        if ($qty > $tersedia) {
            set_flash('danger', "Stok {$p['nama']} tidak mencukupi (sisa {$p['stok']}).");
            header("Location: $back"); exit;
        }
        $sub = $qty * (float)$p['harga_jual'];
        $items[] = ['tipe'=>'part', 'part_id'=>$pid, 'nama'=>$p['nama'], 'qty'=>$qty, 'harga'=>(float)$p['harga_jual'], 'subtotal'=>$sub, 'garansi_hari'=>(int)($part_garansi[$i] ?? 0)];
        $total_part += $sub;
    }

    if (!$customer_id || !$items) {
        set_flash('danger', 'Pilih pelanggan dan tambahkan minimal 1 item jasa/sparepart.');
        header("Location: $back"); exit;
    }

    // Diskon: nominal (Rp) atau persen (%) dari subtotal, maksimal sebesar subtotal
    $subtotal = $total_jasa + $total_part;
    $diskon_jenis = $_POST['diskon_jenis'] ?? '';
    $diskon_nilai = (float)($_POST['diskon_nilai'] ?? 0);
    $diskon = 0;
    if ($diskon_jenis === 'nominal') $diskon = min(max($diskon_nilai, 0), $subtotal);
    elseif ($diskon_jenis === 'persen') $diskon = $subtotal * min(max($diskon_nilai, 0), 100) / 100;
    $grand = $subtotal - $diskon;

    // Simpan transaksi + sesuaikan stok dalam satu transaksi database
    $db->beginTransaction();
    try {
        if ($edit_id) {
            $st = $db->prepare("SELECT no_nota FROM transactions WHERE id=?");
            $st->execute([$edit_id]);
            $no_nota = $st->fetchColumn();
            if (!$no_nota) throw new Exception('Transaksi tidak ditemukan.');
            // Kembalikan stok item lama, lalu hapus item & pergerakan stok lama
            $old = $db->prepare("SELECT part_id, qty FROM transaction_items WHERE transaction_id=? AND tipe='part'");
            $old->execute([$edit_id]);
            foreach ($old->fetchAll(PDO::FETCH_ASSOC) as $o) {
                $db->prepare("UPDATE parts SET stok = stok + ? WHERE id=?")->execute([$o['qty'], $o['part_id']]);
            }
            $db->prepare("DELETE FROM stock_movements WHERE ref_type='penjualan' AND ref_id=?")->execute([$edit_id]);
            $db->prepare("DELETE FROM transaction_items WHERE transaction_id=?")->execute([$edit_id]);
            $db->prepare("UPDATE transactions SET customer_id=?, vehicle_id=?, total_jasa=?, total_part=?, diskon=?, grand_total=? WHERE id=?")
               ->execute([$customer_id, $vehicle_id, $total_jasa, $total_part, $diskon, $grand, $edit_id]);
            $trx_id = $edit_id;
        } else {
            $no_nota = next_kode('TRX', 'transactions', 'no_nota');
            $db->prepare("INSERT INTO transactions (no_nota, customer_id, vehicle_id, total_jasa, total_part, diskon, grand_total, status) VALUES (?,?,?,?,?,?,?, 'selesai')")
               ->execute([$no_nota, $customer_id, $vehicle_id, $total_jasa, $total_part, $diskon, $grand]);
            $trx_id = (int)$db->lastInsertId();
        }
        $insItem = $db->prepare("INSERT INTO transaction_items (transaction_id, tipe, part_id, nama, qty, harga, subtotal, garansi_hari) VALUES (?,?,?,?,?,?,?,?)");
        $updStok = $db->prepare("UPDATE parts SET stok = stok - ? WHERE id=?");
        $insMov  = $db->prepare("INSERT INTO stock_movements (part_id, tipe, jumlah, ref_type, ref_id, keterangan) VALUES (?,?,?,?,?,?)");
        foreach ($items as $it) {
            $insItem->execute([$trx_id, $it['tipe'], $it['part_id'], $it['nama'], $it['qty'], $it['harga'], $it['subtotal'], $it['garansi_hari']]);
            if ($it['tipe'] === 'part') {
                $updStok->execute([$it['qty'], $it['part_id']]);
                $insMov->execute([$it['part_id'], 'keluar', $it['qty'], 'penjualan', $trx_id, "Nota $no_nota"]);
            }
        }
        $db->commit();
        header('Location: index.php?page=receipt&id=' . $trx_id); exit;
    } catch (Exception $e) {
        $db->rollBack();
        set_flash('danger', 'Gagal menyimpan transaksi: ' . $e->getMessage());
        header("Location: $back"); exit;
    }
}

// ---- Mode edit: muat transaksi lama ke dalam form kasir ----
$edit_trx = null;
$edit_items = [];
if (isset($_GET['edit'])) {
    $eid = (int)$_GET['edit'];
    $s = $db->prepare("SELECT * FROM transactions WHERE id=?");
    $s->execute([$eid]);
    $edit_trx = $s->fetch(PDO::FETCH_ASSOC);
    if (!$edit_trx) {
        set_flash('danger', 'Transaksi tidak ditemukan.');
        header('Location: index.php?page=transactions'); exit;
    }
    $kl = $db->prepare("SELECT COUNT(*) FROM warranty_claims WHERE transaction_id=?");
    $kl->execute([$eid]);
    if ((int)$kl->fetchColumn() > 0) {
        set_flash('danger', 'Transaksi ini memiliki klaim garansi terkait dan tidak dapat diedit.');
        header('Location: index.php?page=transactions'); exit;
    }
    $si = $db->prepare("SELECT * FROM transaction_items WHERE transaction_id=?");
    $si->execute([$eid]);
    $edit_items = $si->fetchAll(PDO::FETCH_ASSOC);
}

$customers = $db->query("SELECT id, nama, telepon FROM customers ORDER BY nama")->fetchAll(PDO::FETCH_ASSOC);
$parts = $db->query("SELECT id, kode, barcode, nama, harga_jual, stok FROM parts ORDER BY nama")->fetchAll(PDO::FETCH_ASSOC);
?>
<?php if (!$customers): ?>
<div class="alert alert-warning" data-testid="pos-no-customer">Belum ada pelanggan. <a href="index.php?page=customers">Tambah pelanggan dulu</a> sebelum membuat transaksi.</div>
<?php endif; ?>
<?php if ($edit_trx): ?>
<div class="alert alert-info" data-testid="pos-edit-banner"><i class="bi bi-pencil-square me-1"></i>Mode Edit transaksi <strong><?= esc($edit_trx['no_nota']) ?></strong>. Stok sparepart lama akan dikembalikan lalu dihitung ulang saat disimpan. <a href="index.php?page=transactions" data-testid="pos-edit-cancel">Batalkan edit</a></div>
<?php endif; ?>
<div class="card table-card"><div class="card-body">
<form method="post" data-testid="pos-form">
  <input type="hidden" name="action" value="save_trx">
  <input type="hidden" name="edit_id" value="<?= $edit_trx['id'] ?? 0 ?>">
  <div class="row g-3 mb-4">
    <div class="col-md-5">
      <label class="form-label fw-semibold">Pelanggan</label>
      <select name="customer_id" id="posCustomer" class="form-select" required data-testid="pos-customer">
        <option value="">- Pilih pelanggan -</option>
        <?php foreach ($customers as $c): ?><option value="<?= $c['id'] ?>" <?= ($edit_trx && (int)$edit_trx['customer_id'] === (int)$c['id']) ? 'selected' : '' ?>><?= esc($c['nama']) ?> (<?= esc($c['telepon']) ?>)</option><?php endforeach; ?>
      </select>
    </div>
    <div class="col-md-4">
      <label class="form-label fw-semibold">Kendaraan</label>
      <select name="vehicle_id" id="posVehicle" class="form-select" data-testid="pos-vehicle">
        <option value="">- Pilih pelanggan dulu -</option>
      </select>
    </div>
    <div class="col-md-3 d-flex align-items-end">
      <button type="button" class="btn btn-outline-primary w-100" data-bs-toggle="modal" data-bs-target="#scanModal" data-testid="pos-scan-btn"><i class="bi bi-upc-scan me-1"></i>Scan Barcode Part</button>
    </div>
  </div>

  <h2 class="h6">Jasa Servis</h2>
  <div id="jasaRows"></div>
  <button type="button" class="btn btn-sm btn-outline-secondary mb-4" onclick="addJasa()" data-testid="add-jasa-btn"><i class="bi bi-plus-lg me-1"></i>Tambah Jasa</button>

  <h2 class="h6">Sparepart Digunakan / Dijual</h2>
  <div id="partRows"></div>
  <button type="button" class="btn btn-sm btn-outline-secondary mb-4" onclick="addPart()" data-testid="add-part-btn"><i class="bi bi-plus-lg me-1"></i>Tambah Sparepart</button>

  <div class="row justify-content-end mb-2">
    <div class="col-md-4">
      <label class="form-label fw-semibold"><i class="bi bi-percent me-1"></i>Diskon (opsional)</label>
      <div class="input-group input-group-sm">
        <select name="diskon_jenis" id="diskonJenis" class="form-select" onchange="hitung()" data-testid="diskon-jenis">
          <option value="">Tanpa Diskon</option>
          <option value="nominal">Nominal (Rp)</option>
          <option value="persen">Persen (%)</option>
        </select>
        <input name="diskon_nilai" id="diskonNilai" type="number" min="0" step="any" class="form-control" placeholder="0" oninput="hitung()" data-testid="diskon-nilai">
      </div>
    </div>
  </div>

  <div class="row justify-content-end">
    <div class="col-md-4">
      <table class="table table-sm">
        <tr><td>Total Jasa</td><td class="text-end" id="totalJasa" data-testid="total-jasa">Rp 0</td></tr>
        <tr><td>Total Sparepart</td><td class="text-end" id="totalPart" data-testid="total-part">Rp 0</td></tr>
        <tr><td>Diskon</td><td class="text-end text-danger" id="totalDiskon" data-testid="total-diskon">- Rp 0</td></tr>
        <tr class="fw-bold fs-5"><td>Grand Total</td><td class="text-end text-success" id="grandTotal" data-testid="grand-total">Rp 0</td></tr>
      </table>
      <button class="btn btn-success w-100" data-testid="pos-submit"><i class="bi bi-check2-circle me-1"></i><?= $edit_trx ? 'Simpan Perubahan & Cetak Nota' : 'Simpan & Cetak Nota' ?></button>
    </div>
  </div>
</form>
</div></div>

<!-- Modal scan barcode -->
<div class="modal fade" id="scanModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title">Scan Barcode Sparepart</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <div class="modal-body"><div id="scanner" style="width:100%"></div>
      <div class="mt-2"><label class="form-label small">Atau ketik kode/barcode (scanner USB):</label>
      <input id="scanInput" class="form-control" placeholder="Scan / ketik lalu Enter" data-testid="pos-scan-input"></div>
    </div>
  </div></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<script>
const PARTS = <?= json_encode($parts, JSON_UNESCAPED_UNICODE) ?>;
const rupiah = n => 'Rp ' + Math.round(n).toLocaleString('id-ID');

// Muat kendaraan sesuai pelanggan yang dipilih
document.getElementById('posCustomer').addEventListener('change', async function() {
  const sel = document.getElementById('posVehicle');
  sel.innerHTML = '<option value="">- Tanpa kendaraan -</option>';
  if (!this.value) return;
  const res = await fetch('ajax/lookup.php?action=vehicles&customer_id=' + this.value);
  (await res.json()).forEach(v => {
    sel.innerHTML += `<option value="${v.id}">${v.merek} ${v.model} - ${v.plat_nomor}</option>`;
  });
});

function addJasa(nama = '', biaya = '', garansi = 0) {
  const idx = document.querySelectorAll('.jasa-row').length;
  const div = document.createElement('div');
  div.className = 'row g-2 mb-2 align-items-center jasa-row';
  div.innerHTML = `
    <div class="col-md-5"><input name="jasa_nama[]" class="form-control form-control-sm" placeholder="Ganti oli, tune-up, ganti kampas..." value="${nama}" data-testid="jasa-nama-${idx}"></div>
    <div class="col-md-3"><input name="jasa_biaya[]" type="number" min="0" class="form-control form-control-sm jasa-biaya" placeholder="Biaya jasa" value="${biaya}" oninput="hitung()" data-testid="jasa-biaya-${idx}"></div>
    <div class="col-md-3"><input name="jasa_garansi[]" type="number" min="0" class="form-control form-control-sm" placeholder="Garansi (hari, 0=tanpa)" value="${garansi}" data-testid="jasa-garansi-${idx}"></div>
    <div class="col-md-1"><button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.jasa-row').remove();hitung()" data-testid="jasa-remove-${idx}"><i class="bi bi-x"></i></button></div>`;
  document.getElementById('jasaRows').appendChild(div);
}

function addPart(pid = '', qty = 1, garansi = 0) {
  const idx = document.querySelectorAll('.part-row').length;
  const div = document.createElement('div');
  div.className = 'row g-2 mb-2 align-items-center part-row';
  const opts = PARTS.map(p => `<option value="${p.id}" data-harga="${p.harga_jual}" ${p.id == pid ? 'selected' : ''}>${p.kode} - ${p.nama} (${rupiah(p.harga_jual)}, stok ${p.stok})</option>`).join('');
  div.innerHTML = `
    <div class="col-md-6"><select name="part_id[]" class="form-select form-select-sm part-select" onchange="hitung()" data-testid="part-select-${idx}"><option value="">- Pilih sparepart -</option>${opts}</select></div>
    <div class="col-md-2"><input name="part_qty[]" type="number" min="1" class="form-control form-control-sm part-qty" value="${qty}" oninput="hitung()" data-testid="part-qty-${idx}"></div>
    <div class="col-md-3"><input name="part_garansi[]" type="number" min="0" class="form-control form-control-sm" placeholder="Garansi (hari)" value="${garansi}" data-testid="part-garansi-${idx}"></div>
    <div class="col-md-1"><button type="button" class="btn btn-sm btn-outline-danger" onclick="this.closest('.part-row').remove();hitung()" data-testid="part-remove-${idx}"><i class="bi bi-x"></i></button></div>`;
  document.getElementById('partRows').appendChild(div);
}

// Hitung total otomatis (jasa + sparepart - diskon)
function hitung() {
  let tj = 0, tp = 0;
  document.querySelectorAll('.jasa-biaya').forEach(i => tj += parseFloat(i.value) || 0);
  document.querySelectorAll('.part-row').forEach(r => {
    const sel = r.querySelector('.part-select');
    const harga = parseFloat(sel.selectedOptions[0]?.dataset.harga || 0);
    const qty = parseInt(r.querySelector('.part-qty').value) || 0;
    tp += harga * qty;
  });
  const sub = tj + tp;
  const jenis = document.getElementById('diskonJenis').value;
  const nilai = parseFloat(document.getElementById('diskonNilai').value) || 0;
  let diskon = 0;
  if (jenis === 'nominal') diskon = Math.min(nilai, sub);
  else if (jenis === 'persen') diskon = sub * Math.min(nilai, 100) / 100;
  document.getElementById('totalJasa').textContent = rupiah(tj);
  document.getElementById('totalPart').textContent = rupiah(tp);
  document.getElementById('totalDiskon').textContent = '- ' + rupiah(diskon);
  document.getElementById('grandTotal').textContent = rupiah(sub - diskon);
}

// Scanner kamera + input scanner USB (bertindak seperti keyboard)
let scannerObj = null;
const scanModal = document.getElementById('scanModal');
function pilihDariScan(text) {
  const p = PARTS.find(x => x.barcode === text || x.kode.toUpperCase() === text.toUpperCase());
  if (p) { addPart(p.id, 1, 0); hitung(); bootstrap.Modal.getInstance(scanModal).hide(); }
  else alert('Sparepart dengan kode/barcode "' + text + '" tidak ditemukan.');
}
scanModal.addEventListener('shown.bs.modal', () => {
  document.getElementById('scanInput').focus();
  scannerObj = new Html5Qrcode("scanner");
  scannerObj.start({ facingMode: "environment" }, { fps: 10, qrbox: 250 }, pilihDariScan, () => {});
});
scanModal.addEventListener('hidden.bs.modal', () => { if (scannerObj) scannerObj.stop().catch(()=>{}); });
document.getElementById('scanInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); pilihDariScan(e.target.value.trim()); e.target.value = ''; }
});

<?php if ($edit_trx): ?>
// Mode edit: isi form dengan item transaksi lama
const EDIT_ITEMS = <?= json_encode($edit_items, JSON_UNESCAPED_UNICODE) ?>;
EDIT_ITEMS.forEach(it => {
  if (it.tipe === 'jasa') addJasa(it.nama, it.harga, it.garansi_hari);
  else addPart(it.part_id, it.qty, it.garansi_hari);
});
<?php if ((float)$edit_trx['diskon'] > 0): ?>
document.getElementById('diskonJenis').value = 'nominal';
document.getElementById('diskonNilai').value = <?= (float)$edit_trx['diskon'] ?>;
<?php endif; ?>
// Mode edit: selalu muat daftar kendaraan pelanggan (walau transaksi lama tanpa kendaraan)
(async () => {
  const res = await fetch('ajax/lookup.php?action=vehicles&customer_id=<?= (int)$edit_trx['customer_id'] ?>');
  const sel = document.getElementById('posVehicle');
  sel.innerHTML = '<option value="">- Tanpa kendaraan -</option>';
  (await res.json()).forEach(v => { sel.innerHTML += `<option value="${v.id}">${v.merek} ${v.model} - ${v.plat_nomor}</option>`; });
  <?php if ($edit_trx['vehicle_id']): ?>sel.value = '<?= (int)$edit_trx['vehicle_id'] ?>';<?php endif; ?>
})();
hitung();
<?php else: ?>
addJasa(); addPart();
<?php endif; ?>
</script>
