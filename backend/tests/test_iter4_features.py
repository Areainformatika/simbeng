"""Iteration 4 tests: export laporan stok, diskon POS, edit & hapus transaksi."""
import os
import re
import sqlite3

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
DB = "/app/bengkel/bengkel.db"
ADMIN = ("admin", "admin123")


# ---------- helpers ----------
def dbq(sql, params=()):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [dict(r) for r in rows]


def dbx(sql, params=()):
    con = sqlite3.connect(DB, timeout=10)
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
    assert r.status_code in (302, 303), f"login status {r.status_code}"
    return s


@pytest.fixture(scope="module")
def admin():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def seed():
    """Pelanggan + sparepart khusus test (harga 50.000, stok 20)."""
    cid = dbx("INSERT INTO customers (nama, telepon, alamat) VALUES ('TEST_Pelanggan_Iter4','08111000444','Jl Test')")
    pid = dbx("INSERT INTO parts (kode,barcode,nama,kategori,harga_beli,harga_jual,stok,stok_min) "
              "VALUES ('TESTP4','TESTBC4','TEST_Part_Iter4','Oli',30000,50000,20,2)")
    yield {"customer_id": cid, "part_id": pid}
    trx = dbq("SELECT id FROM transactions WHERE customer_id=?", (cid,))
    for t in trx:
        dbx("DELETE FROM warranty_claims WHERE transaction_id=?", (t["id"],))
        dbx("DELETE FROM transaction_items WHERE transaction_id=?", (t["id"],))
        dbx("DELETE FROM stock_movements WHERE ref_type='penjualan' AND ref_id=?", (t["id"],))
        dbx("DELETE FROM transactions WHERE id=?", (t["id"],))
    dbx("DELETE FROM stock_movements WHERE part_id=?", (pid,))
    dbx("DELETE FROM parts WHERE id=?", (pid,))
    dbx("DELETE FROM customers WHERE id=?", (cid,))


def stok(pid):
    return dbq("SELECT stok FROM parts WHERE id=?", (pid,))[0]["stok"]


def save_trx(sess, seed, jasa_biaya=None, part_qty=None, diskon_jenis="", diskon_nilai="",
             edit_id=0, jasa_nama="TEST Jasa Iter4"):
    data = {
        "action": "save_trx",
        "edit_id": str(edit_id),
        "customer_id": str(seed["customer_id"]),
        "vehicle_id": "",
        "diskon_jenis": diskon_jenis,
        "diskon_nilai": str(diskon_nilai),
    }
    if jasa_biaya is not None:
        data["jasa_nama[]"] = jasa_nama
        data["jasa_biaya[]"] = str(jasa_biaya)
        data["jasa_garansi[]"] = "0"
    if part_qty is not None:
        data["part_id[]"] = str(seed["part_id"])
        data["part_qty[]"] = str(part_qty)
        data["part_garansi[]"] = "0"
    r = sess.post(f"{BASE_URL}/index.php?page=pos", data=data, allow_redirects=False, timeout=30)
    assert r.status_code in (302, 303), r.status_code
    return r.headers.get("Location", "")


def trx_id_from(loc):
    m = re.search(r"id=(\d+)", loc)
    assert m, f"tidak ada id transaksi pada redirect: {loc}"
    return int(m.group(1))


def count_rows(html):
    """Jumlah baris data pada tabel export (tanpa header & tanpa baris TOTAL)."""
    body = html.split("<tbody>")[1].split("</tbody>")[0]
    trs = re.findall(r"<tr[^>]*>.*?</tr>", body, re.S)
    data_rows = [t for t in trs if "TOTAL" not in t and "Tidak ada data" not in t]
    return len(data_rows)


# ================= Export laporan stok =================
class TestStockExport:
    DARI = "2000-01-01"
    SAMPAI = "2099-12-31"

    def _expected(self, jenis):
        where = "date(sm.created_at,'+7 hours') BETWEEN ? AND ?"
        params = [self.DARI, self.SAMPAI]
        if jenis == "masuk":
            where += " AND sm.tipe='masuk'"
        elif jenis == "keluar":
            where += " AND sm.tipe='keluar'"
        elif jenis == "penjualan":
            where += " AND sm.ref_type='penjualan'"
        elif jenis == "garansi":
            where += " AND sm.ref_type='garansi'"
        rows = dbq(f"SELECT sm.jumlah FROM stock_movements sm JOIN parts p ON p.id=sm.part_id WHERE {where}", params)
        return len(rows), sum(r["jumlah"] for r in rows)

    @pytest.mark.parametrize("jenis", ["semua", "masuk", "keluar", "penjualan", "garansi"])
    def test_xls_rows_match_sqlite(self, admin, jenis):
        r = admin.get(f"{BASE_URL}/export.php", params={
            "type": "stock", "format": "xls", "jenis": jenis,
            "dari": self.DARI, "sampai": self.SAMPAI}, timeout=60)
        assert r.status_code == 200
        assert "application/vnd.ms-excel" in r.headers.get("Content-Type", "")
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd and cd.endswith('.xls"'), cd
        assert f"laporan_stok_{jenis}" in cd
        html = r.text
        for h in ["Tanggal", "Kode", "Nama Barang", "Tipe", "Sumber", "Jumlah", "Supplier", "Keterangan"]:
            assert h in html, f"kolom {h} hilang"
        assert "TOTAL" in html
        exp_rows, exp_sum = self._expected(jenis)
        assert count_rows(html) == exp_rows, f"jenis={jenis} baris export {count_rows(html)} != db {exp_rows}"
        # baris TOTAL berisi jumlah agregat
        total_tr = [t for t in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S) if "TOTAL" in t][-1]
        assert f">{exp_sum}<" in total_tr, f"TOTAL jumlah tidak cocok, harap {exp_sum}: {total_tr}"

    def test_doc_format(self, admin):
        r = admin.get(f"{BASE_URL}/export.php", params={
            "type": "stock", "format": "doc", "jenis": "masuk",
            "dari": self.DARI, "sampai": self.SAMPAI}, timeout=60)
        assert r.status_code == 200
        assert "application/msword" in r.headers.get("Content-Type", "")
        assert r.headers.get("Content-Disposition", "").endswith('.doc"')
        assert "Laporan Stok" in r.text and "Stok Masuk" in r.text

    def test_pdf_print_view(self, admin):
        r = admin.get(f"{BASE_URL}/export.php", params={
            "type": "stock", "format": "pdf", "jenis": "semua",
            "dari": self.DARI, "sampai": self.SAMPAI}, timeout=60)
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")
        assert "window.print()" in r.text
        assert "Laporan Stok" in r.text

    def test_reversed_date_range_swapped(self, admin):
        r = admin.get(f"{BASE_URL}/export.php", params={
            "type": "stock", "format": "xls", "jenis": "semua",
            "dari": self.SAMPAI, "sampai": self.DARI}, timeout=60)
        assert r.status_code == 200
        exp_rows, _ = self._expected("semua")
        assert count_rows(r.text) == exp_rows

    def test_narrow_range_filters(self, admin):
        r = admin.get(f"{BASE_URL}/export.php", params={
            "type": "stock", "format": "xls", "jenis": "semua",
            "dari": "1999-01-01", "sampai": "1999-01-02"}, timeout=60)
        assert r.status_code == 200
        assert "Tidak ada data" in r.text
        assert count_rows(r.text) == 0

    def test_invalid_jenis_falls_back(self, admin):
        r = admin.get(f"{BASE_URL}/export.php", params={
            "type": "stock", "format": "xls", "jenis": "'; DROP TABLE parts;--",
            "dari": self.DARI, "sampai": self.SAMPAI}, timeout=60)
        assert r.status_code == 200
        exp_rows, _ = self._expected("semua")
        assert count_rows(r.text) == exp_rows
        assert dbq("SELECT count(*) c FROM parts")[0]["c"] > 0

    def test_export_requires_login(self):
        s = requests.Session()
        r = s.get(f"{BASE_URL}/export.php", params={"type": "stock", "format": "xls"},
                  allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303), f"export tanpa login harus redirect, dapat {r.status_code}"
        assert "login" in r.headers.get("Location", "")


# ================= Diskon POS =================
class TestDiskonPOS:
    def test_diskon_persen(self, admin, seed):
        st0 = stok(seed["part_id"])
        loc = save_trx(admin, seed, jasa_biaya=100000, part_qty=2, diskon_jenis="persen", diskon_nilai=10)
        tid = trx_id_from(loc)
        t = dbq("SELECT * FROM transactions WHERE id=?", (tid,))[0]
        sub = 100000 + 2 * 50000
        assert t["total_jasa"] == 100000 and t["total_part"] == 100000
        assert t["diskon"] == pytest.approx(sub * 0.1)
        assert t["grand_total"] == pytest.approx(sub - sub * 0.1)
        assert stok(seed["part_id"]) == st0 - 2
        rc = admin.get(f"{BASE_URL}/index.php?page=receipt&id={tid}", timeout=30).text
        assert "Diskon" in rc and "-20.000" in rc, "struk tidak menampilkan baris diskon"
        assert "180.000" in rc

    def test_diskon_nominal(self, admin, seed):
        loc = save_trx(admin, seed, jasa_biaya=50000, part_qty=1, diskon_jenis="nominal", diskon_nilai=5000)
        tid = trx_id_from(loc)
        t = dbq("SELECT * FROM transactions WHERE id=?", (tid,))[0]
        assert t["diskon"] == 5000
        assert t["grand_total"] == 95000
        rc = admin.get(f"{BASE_URL}/index.php?page=receipt&id={tid}", timeout=30).text
        assert "-5.000" in rc

    def test_diskon_nominal_capped_at_subtotal(self, admin, seed):
        loc = save_trx(admin, seed, jasa_biaya=40000, diskon_jenis="nominal", diskon_nilai=999999)
        tid = trx_id_from(loc)
        t = dbq("SELECT * FROM transactions WHERE id=?", (tid,))[0]
        assert t["diskon"] == 40000, "diskon nominal harus di-cap sebesar subtotal"
        assert t["grand_total"] == 0

    def test_diskon_persen_over_100_capped(self, admin, seed):
        loc = save_trx(admin, seed, jasa_biaya=40000, diskon_jenis="persen", diskon_nilai=250)
        t = dbq("SELECT * FROM transactions WHERE id=?", (trx_id_from(loc),))[0]
        assert t["diskon"] == 40000 and t["grand_total"] == 0

    def test_diskon_negatif_diabaikan(self, admin, seed):
        loc = save_trx(admin, seed, jasa_biaya=40000, diskon_jenis="nominal", diskon_nilai=-5000)
        t = dbq("SELECT * FROM transactions WHERE id=?", (trx_id_from(loc),))[0]
        assert t["diskon"] == 0 and t["grand_total"] == 40000

    def test_tanpa_diskon(self, admin, seed):
        loc = save_trx(admin, seed, jasa_biaya=30000)
        tid = trx_id_from(loc)
        t = dbq("SELECT * FROM transactions WHERE id=?", (tid,))[0]
        assert t["diskon"] == 0 and t["grand_total"] == 30000
        rc = admin.get(f"{BASE_URL}/index.php?page=receipt&id={tid}", timeout=30).text
        body = rc.split("<table")[-1]
        assert "Diskon" not in body, "struk tanpa diskon tidak boleh menampilkan baris Diskon"

    def test_dashboard_pendapatan_pakai_net(self, admin, seed):
        expected = dbq("SELECT COALESCE(SUM(grand_total),0) s FROM transactions "
                       "WHERE date(created_at,'+7 hours')=date('now','+7 hours')")[0]["s"]
        html = admin.get(f"{BASE_URL}/index.php?page=dashboard", timeout=30).text
        m = re.search(r'data-testid="stat-pendapatan".*?Rp ([\d\.]+)', html, re.S)
        assert m, "stat pendapatan tidak ditemukan"
        shown = int(m.group(1).replace(".", ""))
        assert shown == int(round(expected)), f"dashboard {shown} != sum grand_total net {expected}"


# ================= Edit & Hapus transaksi =================
class TestEditHapusTransaksi:
    def test_edit_prefill_form(self, admin, seed):
        loc = save_trx(admin, seed, jasa_biaya=60000, part_qty=2, diskon_jenis="nominal", diskon_nilai=10000)
        tid = trx_id_from(loc)
        html = admin.get(f"{BASE_URL}/index.php?page=pos&edit={tid}", timeout=30).text
        assert 'data-testid="pos-edit-banner"' in html
        assert f'name="edit_id" value="{tid}"' in html
        assert f'<option value="{seed["customer_id"]}" selected' in html
        assert "EDIT_ITEMS" in html
        assert "'nominal'" in html and "10000" in html, "diskon lama tidak diprefill"
        assert "TEST Jasa Iter4" in html

    def test_edit_updates_stock_and_totals(self, admin, seed):
        pid = seed["part_id"]
        st_before = stok(pid)
        loc = save_trx(admin, seed, jasa_biaya=60000, part_qty=2)
        tid = trx_id_from(loc)
        no_nota = dbq("SELECT no_nota FROM transactions WHERE id=?", (tid,))[0]["no_nota"]
        assert stok(pid) == st_before - 2
        st_lama = stok(pid)

        loc2 = save_trx(admin, seed, jasa_biaya=70000, part_qty=1,
                        diskon_jenis="nominal", diskon_nilai=5000, edit_id=tid)
        assert f"page=receipt&id={tid}" in loc2, f"edit harus redirect ke struk nota sama: {loc2}"
        t = dbq("SELECT * FROM transactions WHERE id=?", (tid,))[0]
        assert t["no_nota"] == no_nota, "no nota berubah setelah edit"
        assert t["total_jasa"] == 70000 and t["total_part"] == 50000
        assert t["diskon"] == 5000 and t["grand_total"] == 115000
        assert stok(pid) == st_lama + 2 - 1, "stok setelah edit tidak sesuai (stok_lama+qty_lama-qty_baru)"
        movs = dbq("SELECT * FROM stock_movements WHERE ref_type='penjualan' AND ref_id=?", (tid,))
        assert len(movs) == 1, f"harus ada 1 movement penjualan, ada {len(movs)}"
        assert movs[0]["jumlah"] == 1 and movs[0]["tipe"] == "keluar"
        items = dbq("SELECT * FROM transaction_items WHERE transaction_id=?", (tid,))
        assert len(items) == 2, f"item lama tidak terhapus: {items}"

    def test_edit_over_stock_rejected(self, admin, seed):
        pid = seed["part_id"]
        loc = save_trx(admin, seed, jasa_biaya=60000, part_qty=1)
        tid = trx_id_from(loc)
        st = stok(pid)
        before = dbq("SELECT * FROM transactions WHERE id=?", (tid,))[0]
        loc2 = save_trx(admin, seed, jasa_biaya=60000, part_qty=st + 5, edit_id=tid)
        assert f"page=pos&edit={tid}" in loc2, f"seharusnya kembali ke form edit: {loc2}"
        assert stok(pid) == st, "stok berubah padahal edit ditolak"
        after = dbq("SELECT * FROM transactions WHERE id=?", (tid,))[0]
        assert after["grand_total"] == before["grand_total"]
        page = admin.get(f"{BASE_URL}{'/' + loc2.lstrip('/')}", timeout=30).text
        assert "tidak mencukupi" in page, "flash error stok tidak tampil"

    def test_delete_restores_stock(self, admin, seed):
        pid = seed["part_id"]
        st_before = stok(pid)
        loc = save_trx(admin, seed, jasa_biaya=60000, part_qty=3)
        tid = trx_id_from(loc)
        assert stok(pid) == st_before - 3
        r = admin.post(f"{BASE_URL}/index.php?page=transactions",
                       data={"action": "delete", "id": str(tid)}, allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303)
        assert dbq("SELECT * FROM transactions WHERE id=?", (tid,)) == []
        assert dbq("SELECT * FROM transaction_items WHERE transaction_id=?", (tid,)) == []
        assert dbq("SELECT * FROM stock_movements WHERE ref_type='penjualan' AND ref_id=?", (tid,)) == []
        assert stok(pid) == st_before, "stok tidak kembali setelah hapus transaksi"
        page = admin.get(f"{BASE_URL}/index.php?page=transactions", timeout=30).text
        assert "stok sparepart dikembalikan" in page

    def test_delete_and_edit_blocked_when_warranty_claim(self, admin, seed):
        pid = seed["part_id"]
        loc = save_trx(admin, seed, jasa_biaya=60000, part_qty=1)
        tid = trx_id_from(loc)
        item = dbq("SELECT * FROM transaction_items WHERE transaction_id=? AND tipe='part'", (tid,))[0]
        dbx("INSERT INTO warranty_claims (kode,transaction_id,transaction_item_id,customer_id,item_nama,"
            "tgl_beli,tgl_berakhir,status,alasan) VALUES ('TEST_CLM4',?,?,?,?,date('now'),date('now','+30 day'),"
            "'pending','TEST alasan')", (tid, item["id"], seed["customer_id"], item["nama"]))
        st = stok(pid)

        # hapus ditolak
        r = admin.post(f"{BASE_URL}/index.php?page=transactions",
                       data={"action": "delete", "id": str(tid)}, allow_redirects=True, timeout=30)
        assert "klaim garansi" in r.text
        assert dbq("SELECT * FROM transactions WHERE id=?", (tid,)), "transaksi terhapus padahal ada klaim"
        assert stok(pid) == st

        # buka form edit ditolak
        r2 = admin.get(f"{BASE_URL}/index.php?page=pos&edit={tid}", allow_redirects=False, timeout=30)
        assert r2.status_code in (302, 303)
        assert "page=transactions" in r2.headers.get("Location", "")

        # submit edit langsung juga ditolak
        loc3 = save_trx(admin, seed, jasa_biaya=1, part_qty=1, edit_id=tid)
        assert "page=transactions" in loc3
        t = dbq("SELECT * FROM transactions WHERE id=?", (tid,))[0]
        assert t["total_jasa"] == 60000, "transaksi berubah padahal edit ditolak"
        assert stok(pid) == st

        dbx("DELETE FROM warranty_claims WHERE kode='TEST_CLM4'")

    def test_edit_nonexistent_transaction(self, admin, seed):
        r = admin.get(f"{BASE_URL}/index.php?page=pos&edit=99999999", allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303)
        assert "page=transactions" in r.headers.get("Location", "")

    def test_transactions_list_has_action_buttons(self, admin, seed):
        loc = save_trx(admin, seed, jasa_biaya=25000)
        tid = trx_id_from(loc)
        html = admin.get(f"{BASE_URL}/index.php?page=transactions", timeout=30).text
        assert f'data-testid="trx-edit-{tid}"' in html
        assert f'data-testid="trx-delete-{tid}"' in html
