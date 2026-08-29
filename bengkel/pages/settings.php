<?php
// ============================================================
// Pengaturan aplikasi (khusus admin):
// - Identitas bengkel: nama, NIB, pemilik, alamat, telepon
// - Tema warna gradasi: geser slider hue untuk mengubah warna
//   sidebar, halaman login, nota, dan laporan secara langsung
// ============================================================
require_admin();

if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'save') {
    foreach (['nama_bengkel', 'nib', 'pemilik', 'alamat', 'telepon'] as $k) {
        set_setting($k, trim($_POST[$k] ?? ''));
    }
    // Hue dibatasi 0-359 derajat
    set_setting('theme_h1', (string)min(359, max(0, (int)($_POST['theme_h1'] ?? 210))));
    set_setting('theme_h2', (string)min(359, max(0, (int)($_POST['theme_h2'] ?? 232))));
    set_flash('success', 'Pengaturan berhasil disimpan.');
    header('Location: index.php?page=settings'); exit;
}

$h1 = (int)setting('theme_h1', '210');
$h2 = (int)setting('theme_h2', '232');
?>
<form method="post" data-testid="settings-form">
<input type="hidden" name="action" value="save">
<div class="row g-3">
  <div class="col-lg-6">
    <div class="card table-card h-100"><div class="card-body">
      <h2 class="h6 mb-3"><i class="bi bi-shop me-1"></i>Identitas Bengkel</h2>
      <p class="small text-muted">Informasi ini tampil pada sidebar, halaman login, struk nota, bukti garansi, dan laporan.</p>
      <div class="mb-2"><label class="form-label small">Nama Aplikasi / Bengkel</label>
        <input name="nama_bengkel" class="form-control form-control-sm" value="<?= esc(setting('nama_bengkel')) ?>" required data-testid="setting-nama"></div>
      <div class="mb-2"><label class="form-label small">NIB (Nomor Induk Berusaha)</label>
        <input name="nib" class="form-control form-control-sm" value="<?= esc(setting('nib')) ?>" placeholder="Opsional" data-testid="setting-nib"></div>
      <div class="mb-2"><label class="form-label small">Nama Pemilik</label>
        <input name="pemilik" class="form-control form-control-sm" value="<?= esc(setting('pemilik')) ?>" data-testid="setting-pemilik"></div>
      <div class="mb-2"><label class="form-label small">Alamat</label>
        <textarea name="alamat" class="form-control form-control-sm" rows="2" data-testid="setting-alamat"><?= esc(setting('alamat')) ?></textarea></div>
      <div class="mb-3"><label class="form-label small">Telepon / WA</label>
        <input name="telepon" class="form-control form-control-sm" value="<?= esc(setting('telepon')) ?>" data-testid="setting-telepon"></div>
    </div></div>
  </div>

  <div class="col-lg-6">
    <div class="card table-card h-100"><div class="card-body">
      <h2 class="h6 mb-3"><i class="bi bi-palette me-1"></i>Tema Warna Gradasi</h2>
      <p class="small text-muted">Geser slider untuk mengubah warna dasar aplikasi. Perubahan langsung terlihat pada preview di bawah.</p>
      <div class="mb-3">
        <label class="form-label small d-flex justify-content-between">Warna Utama <span class="badge bg-secondary" id="h1Val" data-testid="h1-value"><?= $h1 ?>°</span></label>
        <input type="range" class="form-range" min="0" max="359" id="theme_h1" name="theme_h1" value="<?= $h1 ?>" data-testid="theme-h1-slider">
      </div>
      <div class="mb-3">
        <label class="form-label small d-flex justify-content-between">Warna Kedua (Gradasi) <span class="badge bg-secondary" id="h2Val" data-testid="h2-value"><?= $h2 ?>°</span></label>
        <input type="range" class="form-range" min="0" max="359" id="theme_h2" name="theme_h2" value="<?= $h2 ?>" data-testid="theme-h2-slider">
      </div>
      <div id="themePreview" class="rounded p-3 text-white mb-3" data-testid="theme-preview"
           style="background:linear-gradient(165deg, hsl(<?= $h1 ?> 60% 18%), hsl(<?= $h2 ?> 65% 32%));min-height:90px">
        <strong><?= esc(setting('nama_bengkel', 'Bengkel Motor')) ?></strong>
        <div class="small mt-1"><span class="badge rounded-pill" style="background:rgba(255,255,255,.25)">Preview Sidebar & Login</span></div>
      </div>
      <div class="d-flex flex-wrap gap-1 mb-2">
        <?php
        // Preset tema cepat: [label, hue1, hue2]
        foreach ([['Biru Gelap',210,232],['Hijau',150,170],['Merah Marun',350,15],['Ungu',265,285],['Oranye',20,40],['Toska',175,195]] as $p): ?>
        <button type="button" class="btn btn-sm btn-outline-secondary" onclick="setPreset(<?= $p[1] ?>,<?= $p[2] ?>)" data-testid="preset-<?= $p[1] ?>"><?= $p[0] ?></button>
        <?php endforeach; ?>
      </div>
    </div></div>
  </div>
</div>
<button class="btn btn-primary mt-3" data-testid="settings-submit"><i class="bi bi-check2-circle me-1"></i>Simpan Pengaturan</button>
</form>

<script>
// Live preview gradasi saat slider digeser
const h1 = document.getElementById('theme_h1'), h2 = document.getElementById('theme_h2');
const prev = document.getElementById('themePreview');
function updatePreview() {
  prev.style.background = `linear-gradient(165deg, hsl(${h1.value} 60% 18%), hsl(${h2.value} 65% 32%))`;
  document.getElementById('h1Val').textContent = h1.value + '°';
  document.getElementById('h2Val').textContent = h2.value + '°';
}
function setPreset(a, b) { h1.value = a; h2.value = b; updatePreview(); }
h1.addEventListener('input', updatePreview);
h2.addEventListener('input', updatePreview);
</script>
