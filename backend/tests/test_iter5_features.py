"""Iteration 5 tests: Grafik Pelanggan (charts), upload logo bengkel, sticky notes."""
import os
import re
import sqlite3
import subprocess
import time
from datetime import date

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
DB = "/app/bengkel/bengkel.db"
UPLOADS = "/app/bengkel/uploads"
ADMIN = ("admin", "admin123")
KASIR_USER = "TEST_kasir_it5"
KASIR_PASS = "kasir123"

# 1x1 PNG
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


# ---------------- helpers ----------------
def dbq(sql, params=()):
    con = sqlite3.connect(DB, timeout=15)
    try:
        con.row_factory = sqlite3.Row
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def dbx(sql, params=()):
    con = sqlite3.connect(DB, timeout=15)
    try:
        cur = con.execute(sql, params)
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def login(username, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/index.php?page=login",
               data={"username": username, "password": password},
               allow_redirects=False, timeout=30)
    assert r.status_code in (302, 303), f"login status {r.status_code}: {r.text[:300]}"
    return s


def get(sess, url):
    r = sess.get(url, timeout=30)
    assert r.status_code == 200, f"{url} -> {r.status_code}"
    return r.text


def strip_tags(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def parse_chart_rows(html):
    """Return list of dicts from chart-table body."""
    m = re.search(r'data-testid="chart-table".*?<tbody>(.*?)</tbody>', html, re.S)
    if not m:
        return []
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S):
        tds = [strip_tags(td).strip() for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) >= 5:
            rows.append({
                "no": tds[0], "nama": tds[1],
                "jml": int(tds[2].replace("x", "").strip()),
                "total": int(re.sub(r"[^\d]", "", tds[3]) or 0),
                "kontribusi": float(tds[4].replace("%", "").strip()),
            })
    return rows


def agg(dari, sampai):
    return dbq("""SELECT c.nama, COUNT(t.id) jml, COALESCE(SUM(t.grand_total),0) total
                  FROM transactions t JOIN customers c ON c.id=t.customer_id
                  WHERE date(t.created_at,'+7 hours') BETWEEN ? AND ?
                  GROUP BY t.customer_id ORDER BY total DESC, jml DESC LIMIT 10""",
               (dari, sampai))


@pytest.fixture(scope="module")
def admin():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def kasir():
    h = subprocess.run(["php", "-r", "echo password_hash('%s', PASSWORD_DEFAULT);" % KASIR_PASS],
                       capture_output=True, text=True).stdout.strip()
    assert h.startswith("$2y$"), f"php hash failed: {h}"
    dbx("DELETE FROM users WHERE username=?", (KASIR_USER,))
    dbx("INSERT INTO users (username,password_hash,nama,role) VALUES (?,?,?,'kasir')",
        (KASIR_USER, h, "TEST Kasir Iter5"))
    yield login(KASIR_USER, KASIR_PASS)
    dbx("DELETE FROM users WHERE username=?", (KASIR_USER,))


# ============================================================
# Grafik Pelanggan (charts.php)
# ============================================================
class TestCharts:
    def test_nav_link_present(self, admin):
        html = get(admin, f"{BASE_URL}/index.php?page=dashboard")
        assert 'data-testid="nav-charts"' in html
        assert 'data-testid="nav-notes"' in html

    def test_bulanan_matches_sqlite(self, admin):
        bulan = date.today().strftime("%Y-%m")
        html = get(admin, f"{BASE_URL}/index.php?page=charts&periode=bulanan&bulan={bulan}")
        rows = parse_chart_rows(html)
        expected = agg(f"{bulan}-01", dbq("SELECT date(?, 'start of month','+1 month','-1 day') d",
                                          (f"{bulan}-01",))[0]["d"])
        assert len(rows) == len(expected), f"rows {rows} vs {expected}"
        for r, e in zip(rows, expected):
            assert r["nama"] == e["nama"], (r, e)
            assert r["jml"] == e["jml"], (r, e)
            assert r["total"] == int(e["total"]), (r, e)
        # ordering desc
        totals = [r["total"] for r in rows]
        assert totals == sorted(totals, reverse=True)
        # kontribusi ~100 (top10 covers all customers in this dataset)
        if len(expected) < 10:
            assert abs(sum(r["kontribusi"] for r in rows) - 100) <= 1.0, rows

    def test_charts_canvas_and_chartjs(self, admin):
        html = get(admin, f"{BASE_URL}/index.php?page=charts&periode=bulanan")
        assert 'data-testid="chart-belanja"' in html
        assert 'data-testid="chart-frekuensi"' in html
        assert "chart.umd.min.js" in html
        m = re.search(r"const DATA = (\[.*?\]);", html, re.S)
        assert m and m.group(1) != "[]", "chart JS DATA empty"

    def test_tahunan(self, admin):
        y = date.today().year
        html = get(admin, f"{BASE_URL}/index.php?page=charts&periode=tahunan&tahun={y}")
        rows = parse_chart_rows(html)
        expected = agg(f"{y}-01-01", f"{y}-12-31")
        assert len(rows) == len(expected) and len(rows) > 0
        assert rows[0]["total"] == int(expected[0]["total"])

    def test_custom_range(self, admin):
        today = date.today().isoformat()
        html = get(admin, f"{BASE_URL}/index.php?page=charts&periode=custom&dari={today}&sampai={today}")
        rows = parse_chart_rows(html)
        expected = agg(today, today)
        assert len(rows) == len(expected)
        assert 'data-testid="chart-dari"' in html

    def test_custom_reversed_range_swaps(self, admin):
        today = date.today()
        html = get(admin, f"{BASE_URL}/index.php?page=charts&periode=custom"
                          f"&dari={today.isoformat()}&sampai=2020-01-01")
        assert 'data-testid="chart-table"' in html or 'data-testid="chart-empty"' in html
        assert "Fatal error" not in html

    def test_empty_period_shows_message(self, admin):
        y = date.today().year - 3
        html = get(admin, f"{BASE_URL}/index.php?page=charts&periode=tahunan&tahun={y}")
        assert 'data-testid="chart-empty"' in html
        assert "Tidak ada transaksi" in strip_tags(html)

    def test_invalid_params_no_error(self, admin):
        html = get(admin, f"{BASE_URL}/index.php?page=charts&periode=bulanan&bulan=abcd")
        assert "Fatal error" not in html and "Warning" not in html
        html = get(admin, f"{BASE_URL}/index.php?page=charts&periode=xxx")
        assert "Fatal error" not in html

    def test_kasir_can_access_charts(self, kasir):
        html = get(kasir, f"{BASE_URL}/index.php?page=charts")
        assert "Akses ditolak" not in strip_tags(html)
        assert 'data-testid="chart-filter-form"' in html


# ============================================================
# Upload logo (settings.php)
# ============================================================
class TestLogo:
    def test_upload_valid_png(self, admin):
        r = admin.post(f"{BASE_URL}/index.php?page=settings",
                       data={"action": "upload_logo"},
                       files={"logo": ("logo.png", PNG, "image/png")},
                       allow_redirects=True, timeout=30)
        assert r.status_code == 200
        assert "berhasil diunggah" in strip_tags(r.text)
        val = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        assert val.startswith("uploads/logo_") and val.endswith(".png"), val
        assert os.path.isfile(f"/app/bengkel/{val}"), "file not on disk"
        assert 'data-testid="logo-preview"' in r.text
        assert 'data-testid="logo-remove-btn"' in r.text
        # served over HTTP
        img = admin.get(f"{BASE_URL}/{val}", timeout=30)
        assert img.status_code == 200 and img.content[:4] == b"\x89PNG"

    def test_logo_shown_in_sidebar_login_receipt_warranty(self, admin):
        val = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        assert val, "no logo set"
        for page in ["dashboard", "notes", "charts", "settings"]:
            html = get(admin, f"{BASE_URL}/index.php?page={page}")
            assert 'data-testid="sidebar-logo"' in html, f"sidebar logo missing on {page}"
        # login page (anonymous session)
        anon = requests.Session()
        html = anon.get(f"{BASE_URL}/index.php?page=login", timeout=30).text
        assert 'data-testid="login-logo"' in html
        # receipt + warranty print
        trx = dbq("SELECT id FROM transactions ORDER BY id DESC LIMIT 1")
        assert trx, "no transaction to print"
        html = get(admin, f"{BASE_URL}/index.php?page=receipt&id={trx[0]['id']}")
        assert 'data-testid="receipt-logo"' in html
        wr = dbq("SELECT id FROM warranty_claims ORDER BY id DESC LIMIT 1")
        if wr:
            html = get(admin, f"{BASE_URL}/index.php?page=warranty_print&id={wr[0]['id']}")
            assert 'data-testid="warranty-logo"' in html

    def test_replace_logo_deletes_old_file(self, admin):
        old = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        assert os.path.isfile(f"/app/bengkel/{old}")
        time.sleep(1.2)  # filename uses time(); avoid same-second collision
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
                       files={"logo": ("logo2.png", PNG, "image/png")}, timeout=30)
        assert r.status_code == 200
        new = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        assert new != old, "logo path not updated"
        assert os.path.isfile(f"/app/bengkel/{new}")
        assert not os.path.isfile(f"/app/bengkel/{old}"), "old logo file not deleted"

    def test_reject_non_image(self, admin):
        before = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
                       files={"logo": ("evil.png", b"just plain text, not an image", "image/png")},
                       timeout=30)
        assert "Format logo harus JPG" in strip_tags(r.text), strip_tags(r.text)[:400]
        assert dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"] == before

    def test_reject_oversize(self, admin):
        before = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        big = PNG + b"\x00" * (2 * 1024 * 1024 + 100)
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
                       files={"logo": ("big.png", big, "image/png")}, timeout=60)
        txt = strip_tags(r.text)
        # handler kini menangani UPLOAD_ERR_INI_SIZE -> "Ukuran logo melebihi batas 2 MB"
        assert ("melebihi batas 2 MB" in txt) or ("maksimal 2 MB" in txt), txt[:600]
        assert dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"] == before

    def test_remove_logo_falls_back_to_gear(self, admin):
        cur = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data={"action": "remove_logo"}, timeout=30)
        assert r.status_code == 200
        assert dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"] == ""
        assert not os.path.isfile(f"/app/bengkel/{cur}"), "file not removed from disk"
        assert 'data-testid="sidebar-logo"' not in r.text
        assert "bi-gear" in r.text or "bi-" in r.text
        anon = requests.Session()
        html = anon.get(f"{BASE_URL}/index.php?page=login", timeout=30).text
        assert 'data-testid="login-logo"' not in html

    def test_kasir_cannot_upload_logo(self, kasir):
        r = kasir.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
                       files={"logo": ("logo.png", PNG, "image/png")}, timeout=30)
        assert dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"] == "", "kasir bypassed admin guard"
        assert "Akses ditolak" in strip_tags(r.text)

    def test_zz_restore_logo(self, admin):
        """Leave the app with a logo uploaded (nice preview for user)."""
        time.sleep(1.2)
        admin.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
                   files={"logo": ("logo.png", PNG, "image/png")}, timeout=30)
        assert dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"] != ""


# ============================================================
# Sticky notes (notes.php)
# ============================================================
class TestNotes:
    created = []

    @classmethod
    def teardown_class(cls):
        for nid in cls.created:
            dbx("DELETE FROM notes WHERE id=?", (nid,))
        dbx("DELETE FROM notes WHERE isi LIKE 'TEST_%'")

    def test_notes_table_schema(self):
        cols = {c["name"] for c in dbq("PRAGMA table_info(notes)")}
        assert {"id", "isi", "warna", "created_at", "updated_at"} <= cols, cols

    @pytest.mark.parametrize("warna,bg", [("kuning", "#fff3bf"), ("hijau", "#d3f9d8"),
                                          ("biru", "#dbe4ff"), ("pink", "#ffdeeb"),
                                          ("putih", "#ffffff")])
    def test_add_note_each_color(self, admin, warna, bg):
        isi = f"TEST_note_{warna}"
        r = admin.post(f"{BASE_URL}/index.php?page=notes",
                       data={"action": "add", "isi": isi, "warna": warna}, timeout=30)
        assert r.status_code == 200
        assert "Catatan ditambahkan" in strip_tags(r.text)
        row = dbq("SELECT * FROM notes WHERE isi=? ORDER BY id DESC LIMIT 1", (isi,))
        assert row, "note not persisted"
        TestNotes.created.append(row[0]["id"])
        assert row[0]["warna"] == warna
        card = re.search(r'data-testid="note-card-%d".*?</div>\s*</div>' % row[0]["id"], r.text, re.S)
        assert card, "card not rendered"
        assert f"background:{bg}" in card.group(0), card.group(0)[:300]
        assert f'data-testid="note-isi-{row[0]["id"]}"' in r.text

    def test_add_empty_rejected(self, admin):
        before = dbq("SELECT COUNT(*) c FROM notes")[0]["c"]
        r = admin.post(f"{BASE_URL}/index.php?page=notes",
                       data={"action": "add", "isi": "   ", "warna": "biru"}, timeout=30)
        assert "tidak boleh kosong" in strip_tags(r.text)
        assert dbq("SELECT COUNT(*) c FROM notes")[0]["c"] == before

    def test_invalid_color_defaults_kuning(self, admin):
        isi = "TEST_note_badcolor"
        admin.post(f"{BASE_URL}/index.php?page=notes",
                   data={"action": "add", "isi": isi, "warna": "hitam"}, timeout=30)
        row = dbq("SELECT * FROM notes WHERE isi=? ORDER BY id DESC LIMIT 1", (isi,))
        assert row and row[0]["warna"] == "kuning", row

    def test_edit_note_updates_content_color_and_timestamp(self, admin):
        isi = "TEST_note_edit_src"
        admin.post(f"{BASE_URL}/index.php?page=notes",
                   data={"action": "add", "isi": isi, "warna": "kuning"}, timeout=30)
        row = dbq("SELECT * FROM notes WHERE isi=? ORDER BY id DESC LIMIT 1", (isi,))[0]
        nid = row["id"]
        TestNotes.created.append(nid)
        time.sleep(1.2)
        r = admin.post(f"{BASE_URL}/index.php?page=notes",
                       data={"action": "save", "id": nid, "isi": "TEST_note_edited", "warna": "pink"},
                       timeout=30)
        assert "Catatan diperbarui" in strip_tags(r.text)
        after = dbq("SELECT * FROM notes WHERE id=?", (nid,))[0]
        assert after["isi"] == "TEST_note_edited"
        assert after["warna"] == "pink"
        assert after["updated_at"] > row["updated_at"], (row["updated_at"], after["updated_at"])
        assert f'data-testid="note-edit-isi-{nid}"' in r.text
        assert "TEST_note_edited" in r.text

    def test_edit_empty_is_ignored(self, admin):
        isi = "TEST_note_edit_empty"
        admin.post(f"{BASE_URL}/index.php?page=notes",
                   data={"action": "add", "isi": isi, "warna": "biru"}, timeout=30)
        nid = dbq("SELECT id FROM notes WHERE isi=? ORDER BY id DESC LIMIT 1", (isi,))[0]["id"]
        TestNotes.created.append(nid)
        admin.post(f"{BASE_URL}/index.php?page=notes",
                   data={"action": "save", "id": nid, "isi": "  ", "warna": "biru"}, timeout=30)
        assert dbq("SELECT isi FROM notes WHERE id=?", (nid,))[0]["isi"] == isi

    def test_xss_escaped(self, admin):
        isi = "TEST_<script>alert(1)</script>"
        r = admin.post(f"{BASE_URL}/index.php?page=notes",
                       data={"action": "add", "isi": isi, "warna": "hijau"}, timeout=30)
        nid = dbq("SELECT id FROM notes WHERE isi=? ORDER BY id DESC LIMIT 1", (isi,))[0]["id"]
        TestNotes.created.append(nid)
        assert "<script>alert(1)</script>" not in r.text
        assert "&lt;script&gt;" in r.text

    def test_delete_note(self, admin):
        isi = "TEST_note_delete"
        admin.post(f"{BASE_URL}/index.php?page=notes",
                   data={"action": "add", "isi": isi, "warna": "putih"}, timeout=30)
        nid = dbq("SELECT id FROM notes WHERE isi=? ORDER BY id DESC LIMIT 1", (isi,))[0]["id"]
        r = admin.post(f"{BASE_URL}/index.php?page=notes",
                       data={"action": "delete", "id": nid}, timeout=30)
        assert "Catatan dihapus" in strip_tags(r.text)
        assert dbq("SELECT id FROM notes WHERE id=?", (nid,)) == []
        assert f'data-testid="note-card-{nid}"' not in r.text

    def test_kasir_can_use_notes(self, kasir):
        isi = "TEST_note_kasir"
        r = kasir.post(f"{BASE_URL}/index.php?page=notes",
                       data={"action": "add", "isi": isi, "warna": "biru"}, timeout=30)
        assert "Akses ditolak" not in strip_tags(r.text)
        rows = dbq("SELECT id FROM notes WHERE isi=?", (isi,))
        assert rows, "kasir could not add note"
        TestNotes.created.append(rows[0]["id"])

    def test_notes_requires_login(self):
        anon = requests.Session()
        r = anon.get(f"{BASE_URL}/index.php?page=notes", allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303) and "login" in r.headers.get("Location", "")


# ============================================================
# Regression
# ============================================================
class TestRegression:
    @pytest.mark.parametrize("page", ["dashboard", "customers", "parts", "pos", "transactions",
                                      "reports", "stock", "warranty", "users", "settings",
                                      "charts", "notes"])
    def test_pages_load(self, admin, page):
        html = get(admin, f"{BASE_URL}/index.php?page={page}")
        assert "Fatal error" not in html and "Parse error" not in html

    def test_settings_identity_and_theme_save(self, admin):
        cur = {r["key"]: r["value"] for r in dbq("SELECT key,value FROM settings")}
        payload = {"action": "save", "nama_bengkel": cur.get("nama_bengkel", "99 JAYA MOTOR"),
                   "nib": cur.get("nib", ""), "pemilik": cur.get("pemilik", ""),
                   "alamat": cur.get("alamat", ""), "telepon": cur.get("telepon", ""),
                   "theme_h1": "200", "theme_h2": "240"}
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data=payload, timeout=30)
        assert r.status_code == 200
        now = {x["key"]: x["value"] for x in dbq("SELECT key,value FROM settings")}
        assert now["theme_h1"] == "200" and now["theme_h2"] == "240"
        # restore
        payload.update({"theme_h1": cur.get("theme_h1", "210"), "theme_h2": cur.get("theme_h2", "232")})
        admin.post(f"{BASE_URL}/index.php?page=settings", data=payload, timeout=30)

    def test_pos_create_transaction(self, admin):
        cid = dbx("INSERT INTO customers (nama,telepon,alamat) VALUES ('TEST_Pelanggan_Iter5','08110005','Jl Test')")
        pid = dbx("INSERT INTO parts (kode,barcode,nama,kategori,harga_beli,harga_jual,stok,stok_min) "
                  "VALUES ('TESTP5','TESTBC5','TEST_Part_Iter5','Oli',30000,50000,20,2)")
        try:
            r = admin.post(f"{BASE_URL}/index.php?page=pos", data={
                "action": "save_trx", "customer_id": cid,
                "jasa_nama[]": "TEST_jasa_iter5", "jasa_biaya[]": "20000", "jasa_garansi[]": "0",
                "part_id[]": pid, "part_qty[]": "2", "part_garansi[]": "0",
            }, allow_redirects=False, timeout=30)
            assert r.status_code in (302, 303), f"{r.status_code} {r.text[:300]}"
            assert "page=receipt" in r.headers.get("Location", ""), r.headers
            trx = dbq("SELECT * FROM transactions WHERE customer_id=?", (cid,))
            assert trx, f"transaction not created: {strip_tags(r.text)[:300]}"
            assert int(trx[0]["grand_total"]) == 120000, trx[0]
            assert dbq("SELECT stok FROM parts WHERE id=?", (pid,))[0]["stok"] == 18
        finally:
            for t in dbq("SELECT id FROM transactions WHERE customer_id=?", (cid,)):
                dbx("DELETE FROM transaction_items WHERE transaction_id=?", (t["id"],))
                dbx("DELETE FROM transactions WHERE id=?", (t["id"],))
            dbx("DELETE FROM parts WHERE id=?", (pid,))
            dbx("DELETE FROM customers WHERE id=?", (cid,))
