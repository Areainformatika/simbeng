<?php
// ============================================================
// db.php - Koneksi SQLite & skema database aplikasi bengkel.
// File bengkel.db otomatis dibuat saat aplikasi pertama dijalankan.
// ============================================================

define('DB_PATH', __DIR__ . '/../bengkel.db');

function db(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        $pdo = new PDO('sqlite:' . DB_PATH);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $pdo->exec('PRAGMA foreign_keys = ON');
    }
    return $pdo;
}

// Buat seluruh tabel (jika belum ada) + seed akun admin default
function init_db(): void {
    $db = db();
    $db->exec("CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        nama TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'kasir',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");
    $db->exec("CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT NOT NULL,
        telepon TEXT DEFAULT '',
        alamat TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");
    $db->exec("CREATE TABLE IF NOT EXISTS vehicles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        merek TEXT NOT NULL,
        model TEXT DEFAULT '',
        plat_nomor TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");
    $db->exec("CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT NOT NULL,
        telepon TEXT DEFAULT '',
        email TEXT DEFAULT '',
        alamat TEXT DEFAULT '',
        keterangan TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");
    $db->exec("CREATE TABLE IF NOT EXISTS parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kode TEXT UNIQUE NOT NULL,
        barcode TEXT DEFAULT '',
        nama TEXT NOT NULL,
        kategori TEXT DEFAULT '',
        harga_beli REAL NOT NULL DEFAULT 0,
        harga_jual REAL NOT NULL DEFAULT 0,
        stok INTEGER NOT NULL DEFAULT 0,
        stok_min INTEGER NOT NULL DEFAULT 5,
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");
    $db->exec("CREATE TABLE IF NOT EXISTS stock_movements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        part_id INTEGER NOT NULL REFERENCES parts(id),
        tipe TEXT NOT NULL CHECK (tipe IN ('masuk','keluar')),
        jumlah INTEGER NOT NULL,
        supplier_id INTEGER REFERENCES suppliers(id),
        ref_type TEXT DEFAULT '',
        ref_id INTEGER,
        keterangan TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");
    $db->exec("CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        no_nota TEXT UNIQUE NOT NULL,
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        vehicle_id INTEGER REFERENCES vehicles(id),
        total_jasa REAL NOT NULL DEFAULT 0,
        total_part REAL NOT NULL DEFAULT 0,
        grand_total REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'selesai',
        catatan TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");
    $db->exec("CREATE TABLE IF NOT EXISTS transaction_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
        tipe TEXT NOT NULL CHECK (tipe IN ('jasa','part')),
        part_id INTEGER REFERENCES parts(id),
        nama TEXT NOT NULL,
        qty INTEGER NOT NULL DEFAULT 1,
        harga REAL NOT NULL DEFAULT 0,
        subtotal REAL NOT NULL DEFAULT 0,
        garansi_hari INTEGER NOT NULL DEFAULT 0
    )");
    // Modul garansi: klaim terkait satu item pada satu nota transaksi
    $db->exec("CREATE TABLE IF NOT EXISTS warranty_claims (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kode TEXT UNIQUE NOT NULL,
        transaction_id INTEGER NOT NULL REFERENCES transactions(id),
        transaction_item_id INTEGER NOT NULL REFERENCES transaction_items(id),
        customer_id INTEGER NOT NULL REFERENCES customers(id),
        item_nama TEXT NOT NULL,
        tgl_beli TEXT NOT NULL,
        tgl_berakhir TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','diproses','disetujui','ditolak')),
        alasan TEXT DEFAULT '',
        catatan_teknisi TEXT DEFAULT '',
        replacement_part_id INTEGER REFERENCES parts(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");
    // Master kategori jenis sparepart (dipakai dropdown saat input sparepart)
    $db->exec("CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT UNIQUE NOT NULL,
        keterangan TEXT DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )");

    // Seed akun admin default (admin / admin123) jika tabel users kosong
    if ((int) db()->query("SELECT COUNT(*) FROM users")->fetchColumn() === 0) {
        $stmt = db()->prepare("INSERT INTO users (username, password_hash, nama, role) VALUES (?,?,?,?)");
        $stmt->execute(['admin', password_hash('admin123', PASSWORD_DEFAULT), 'Administrator', 'admin']);
    }

    // Seed kategori default + serap kategori yang sudah dipakai data sparepart lama
    if ((int) db()->query("SELECT COUNT(*) FROM categories")->fetchColumn() === 0) {
        $defaults = ['Oli', 'Kampas Rem', 'Busi', 'Aki', 'Ban', 'Rantai & Gir', 'Lampu', 'Lainnya'];
        $existing = db()->query("SELECT DISTINCT kategori FROM parts WHERE kategori != ''")->fetchAll(PDO::FETCH_COLUMN);
        $ins = db()->prepare("INSERT OR IGNORE INTO categories (nama) VALUES (?)");
        foreach (array_unique(array_merge($defaults, $existing)) as $k) $ins->execute([$k]);
    }
}

// ---------- Helper umum ----------
function esc($s): string { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function rupiah($n): string { return 'Rp ' . number_format((float)$n, 0, ',', '.'); }
function set_flash(string $type, string $msg): void { $_SESSION['flash'] = ['type' => $type, 'msg' => $msg]; }
function get_flash() { $f = $_SESSION['flash'] ?? null; unset($_SESSION['flash']); return $f; }

// Generator kode berurut per bulan, misal: TRX-202606-001 / GRS-202606-001
function next_kode(string $prefix, string $table, string $col): string {
    $ym = date('Ym');
    $stmt = db()->prepare("SELECT COUNT(*) FROM $table WHERE $col LIKE ?");
    $stmt->execute(["$prefix-$ym-%"]);
    return sprintf('%s-%s-%03d', $prefix, $ym, ((int)$stmt->fetchColumn()) + 1);
}

// ============================================================
// Helper laporan: hitung rentang tanggal dari parameter periode
// (harian / mingguan / bulanan / tahunan / custom dari-sampai)
// ============================================================
// Validasi format tanggal Y-m-d (fallback dipakai bila input tidak valid)
function _valid_date($d): bool {
    return is_string($d) && preg_match('/^\d{4}-\d{2}-\d{2}$/', $d) && strtotime($d) !== false;
}

function resolve_periode(): array {
    $periode = $_GET['periode'] ?? 'harian';
    $today = date('Y-m-d');
    switch ($periode) {
        case 'mingguan':
            $base = _valid_date($_GET['tanggal'] ?? '') ? $_GET['tanggal'] : $today;
            $dari = date('Y-m-d', strtotime('monday this week', strtotime($base)));
            $sampai = date('Y-m-d', strtotime('sunday this week', strtotime($base)));
            $label = 'Mingguan (' . date('d/m/Y', strtotime($dari)) . ' - ' . date('d/m/Y', strtotime($sampai)) . ')';
            break;
        case 'bulanan':
            $bulan = preg_match('/^\d{4}-\d{2}$/', $_GET['bulan'] ?? '') ? $_GET['bulan'] : date('Y-m');
            $dari = $bulan . '-01';
            $sampai = date('Y-m-t', strtotime($dari));
            $label = 'Bulanan (' . date('m/Y', strtotime($dari)) . ')';
            break;
        case 'tahunan':
            $tahun = preg_match('/^\d{4}$/', $_GET['tahun'] ?? '') ? $_GET['tahun'] : date('Y');
            $dari = "$tahun-01-01";
            $sampai = "$tahun-12-31";
            $label = "Tahunan ($tahun)";
            break;
        case 'custom':
            $dari = _valid_date($_GET['dari'] ?? '') ? $_GET['dari'] : $today;
            $sampai = _valid_date($_GET['sampai'] ?? '') ? $_GET['sampai'] : $today;
            // Tukar otomatis bila pengguna memasukkan rentang terbalik
            if ($dari > $sampai) [$dari, $sampai] = [$sampai, $dari];
            $label = date('d/m/Y', strtotime($dari)) . ' s.d. ' . date('d/m/Y', strtotime($sampai));
            break;
        default: // harian
            $periode = 'harian';
            $dari = $sampai = _valid_date($_GET['tanggal'] ?? '') ? $_GET['tanggal'] : $today;
            $label = 'Harian (' . date('d/m/Y', strtotime($dari)) . ')';
    }
    return [$periode, $dari, $sampai, $label];
}

// Ambil daftar transaksi dalam rentang tanggal untuk laporan
function laporan_transaksi(string $dari, string $sampai): array {
    $stmt = db()->prepare("SELECT t.*, c.nama AS customer_nama, v.plat_nomor
        FROM transactions t
        JOIN customers c ON c.id = t.customer_id
        LEFT JOIN vehicles v ON v.id = t.vehicle_id
        WHERE date(t.created_at) BETWEEN ? AND ?
        ORDER BY t.created_at");
    $stmt->execute([$dari, $sampai]);
    return $stmt->fetchAll(PDO::FETCH_ASSOC);
}
