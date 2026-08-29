"""
Iterasi 2: tes fitur baru aplikasi Bengkel Motor (PHP native + SQLite)
Modul yang diuji:
  - Master Kategori (index.php?page=categories) CRUD + validasi duplikat
  - Dropdown kategori pada form sparepart (index.php?page=parts)
  - Auto-create kategori saat import (ajax/import_parts.php)
  - Rekap & Laporan (index.php?page=reports) filter periode + ringkasan
  - export.php: type=transactions|parts, format=xls|doc|pdf
"""
import os
import re
import sqlite3
import uuid
from datetime import date, timedelta

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL is missing")
BASE_URL = base_url.rstrip("/")
DB_PATH = "/app/bengkel/bengkel.db"
CREDS = {"username": "admin", "password": "admin123"}

TODAY = date.today()
THIS_MONTH = TODAY.strftime("%Y-%m")
THIS_YEAR = TODAY.strftime("%Y")


def db_query(sql, params=()):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def rupiah(n):
    return "Rp " + f"{int(round(float(n))):,}".replace(",", ".")


@pytest.fixture(scope="session")
def sfx():
    return uuid.uuid4().hex[:6].upper()


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/index.php?page=login", data=CREDS, allow_redirects=False)
    if r.status_code not in (302, 303):
        pytest.fail(f"Login admin gagal: {r.status_code} {r.text[:300]}")
    return s


# ---------------- Modul: Master Kategori ----------------
class TestCategories:
    def test_page_loads_and_nav(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=categories")
        assert r.status_code == 200
        assert 'data-testid="categories-table"' in r.text
        assert 'data-testid="category-form"' in r.text
        assert 'data-testid="nav-categories"' in r.text
        assert 'data-testid="nav-reports"' in r.text

    def test_create_edit_duplicate_delete(self, client, sfx):
        nama = f"TEST_KAT_{sfx}"
        # CREATE
        r = client.post(f"{BASE_URL}/index.php?page=categories",
                        data={"action": "save", "id": "0", "nama": nama, "keterangan": "ket awal"})
        assert r.status_code == 200
        rows = db_query("SELECT * FROM categories WHERE nama=?", (nama,))
        assert len(rows) == 1, "Kategori baru tidak tersimpan"
        cid = rows[0]["id"]
        assert rows[0]["keterangan"] == "ket awal"
        # tampil di tabel
        page = client.get(f"{BASE_URL}/index.php?page=categories").text
        assert nama in page and f'data-testid="category-edit-{cid}"' in page

        # DUPLICATE -> flash error
        r = client.post(f"{BASE_URL}/index.php?page=categories",
                        data={"action": "save", "id": "0", "nama": nama, "keterangan": ""})
        assert "sudah ada" in r.text, "Validasi duplikat kategori tidak memunculkan flash error"
        assert len(db_query("SELECT * FROM categories WHERE nama=?", (nama,))) == 1

        # EDIT form pre-fill
        ef = client.get(f"{BASE_URL}/index.php?page=categories&edit={cid}").text
        assert f'value="{nama}"' in ef
        # UPDATE
        nama2 = nama + "_UP"
        client.post(f"{BASE_URL}/index.php?page=categories",
                    data={"action": "save", "id": str(cid), "nama": nama2, "keterangan": "ket baru"})
        row = db_query("SELECT * FROM categories WHERE id=?", (cid,))[0]
        assert row["nama"] == nama2 and row["keterangan"] == "ket baru"

        # DELETE
        r = client.post(f"{BASE_URL}/index.php?page=categories", data={"action": "delete", "id": str(cid)})
        assert r.status_code == 200
        assert db_query("SELECT * FROM categories WHERE id=?", (cid,)) == []

    def test_part_count_column(self, client, sfx):
        kat = f"TEST_KATCNT_{sfx}"
        kode = f"TEST-PC-{sfx}"
        client.post(f"{BASE_URL}/index.php?page=categories",
                    data={"action": "save", "id": "0", "nama": kat, "keterangan": ""})
        client.post(f"{BASE_URL}/index.php?page=parts",
                    data={"action": "save", "id": "", "kode": kode, "barcode": "", "nama": f"TEST_Part_{sfx}",
                          "kategori": kat, "harga_beli": "1000", "harga_jual": "2000", "stok": "3", "stok_min": "5"})
        parts = db_query("SELECT * FROM parts WHERE kode=?", (kode,))
        assert len(parts) == 1 and parts[0]["kategori"] == kat
        page = client.get(f"{BASE_URL}/index.php?page=categories").text
        m = re.search(re.escape(kat) + r'</td>.*?<span class="badge bg-secondary">(\d+)</span>', page, re.S)
        assert m, "Baris kategori/kolom jumlah sparepart tidak ditemukan"
        assert m.group(1) == "1", f"Jumlah sparepart per kategori salah: {m.group(1)}"


# ---------------- Modul: Dropdown kategori pada form sparepart ----------------
class TestPartsCategoryDropdown:
    def test_dropdown_contains_master_categories(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=parts")
        assert r.status_code == 200
        assert 'data-testid="part-kategori"' in r.text
        sel = r.text.split('data-testid="part-kategori"')[1].split("</select>")[0]
        for kat in [c["nama"] for c in db_query("SELECT nama FROM categories ORDER BY nama LIMIT 5")]:
            assert f">{kat}<" in sel, f"Kategori {kat} tidak ada di dropdown"

    def test_edit_part_preselects_category(self, client, sfx):
        kat = "Oli"
        kode = f"TEST-DD-{sfx}"
        client.post(f"{BASE_URL}/index.php?page=parts",
                    data={"action": "save", "id": "", "kode": kode, "barcode": "", "nama": f"TEST_Oli_{sfx}",
                          "kategori": kat, "harga_beli": "1000", "harga_jual": "2000", "stok": "9", "stok_min": "2"})
        pid = db_query("SELECT id FROM parts WHERE kode=?", (kode,))[0]["id"]
        page = client.get(f"{BASE_URL}/index.php?page=parts&edit={pid}").text
        sel = page.split('data-testid="part-kategori"')[1].split("</select>")[0]
        m = re.search(r'<option value="([^"]*)"\s+selected', sel)
        assert m, f"Tidak ada option selected pada dropdown kategori: {sel[:400]}"
        assert m.group(1) == kat

    def test_import_auto_registers_category(self, client, sfx):
        kat = f"TEST_IMPKAT_{sfx}"
        kode = f"TEST-IMP-{sfx}"
        r = client.post(f"{BASE_URL}/ajax/import_parts.php", json={"rows": [
            {"kode": kode, "nama": f"TEST_Imported_{sfx}", "kategori": kat,
             "harga_beli": 5000, "harga_jual": 7000, "stok": 4, "stok_min": 2, "barcode": ""}
        ]})
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("ok") is True, r.text[:300]
        assert len(db_query("SELECT * FROM categories WHERE nama=?", (kat,))) == 1, \
            "Kategori baru dari import tidak otomatis terdaftar"
        page = client.get(f"{BASE_URL}/index.php?page=categories").text
        assert kat in page


# ---------------- Modul: Rekap & Laporan ----------------
class TestReports:
    def test_daily_report(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=reports",
                       params={"periode": "harian", "tanggal": TODAY.isoformat()})
        assert r.status_code == 200
        assert 'data-testid="report-table"' in r.text
        expected = db_query("SELECT * FROM transactions WHERE date(created_at)=?", (TODAY.isoformat(),))
        count = re.search(r'data-testid="summary-count">(\d+)<', r.text).group(1)
        assert int(count) == len(expected), f"summary-count {count} != DB {len(expected)}"
        for t in expected:
            assert t["no_nota"] in r.text
        assert TODAY.strftime("Harian (%d/%m/%Y)") in r.text

    def test_monthly_report_totals(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=reports",
                       params={"periode": "bulanan", "bulan": THIS_MONTH})
        assert r.status_code == 200
        rows = db_query("SELECT * FROM transactions WHERE strftime('%Y-%m', created_at)=?", (THIS_MONTH,))
        assert int(re.search(r'data-testid="summary-count">(\d+)<', r.text).group(1)) == len(rows)
        for key, col in [("summary-jasa", "total_jasa"), ("summary-part", "total_part"),
                         ("summary-total", "grand_total")]:
            shown = re.search(f'data-testid="{key}">([^<]+)<', r.text).group(1)
            assert shown == rupiah(sum(x[col] for x in rows)), f"{key}: {shown}"
        for t in rows:
            assert t["no_nota"] in r.text
        assert "TOTAL" in r.text if rows else True

    def test_yearly_and_custom_report(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=reports",
                       params={"periode": "tahunan", "tahun": THIS_YEAR})
        assert r.status_code == 200
        rows = db_query("SELECT * FROM transactions WHERE strftime('%Y', created_at)=?", (THIS_YEAR,))
        assert int(re.search(r'data-testid="summary-count">(\d+)<', r.text).group(1)) == len(rows)
        assert f"Tahunan ({THIS_YEAR})" in r.text

        dari = (TODAY - timedelta(days=7)).isoformat()
        r2 = client.get(f"{BASE_URL}/index.php?page=reports",
                        params={"periode": "custom", "dari": dari, "sampai": TODAY.isoformat()})
        assert r2.status_code == 200
        rows2 = db_query("SELECT * FROM transactions WHERE date(created_at) BETWEEN ? AND ?",
                         (dari, TODAY.isoformat()))
        assert int(re.search(r'data-testid="summary-count">(\d+)<', r2.text).group(1)) == len(rows2)
        assert "s.d." in r2.text

    def test_filter_inputs_present(self, client):
        t = client.get(f"{BASE_URL}/index.php?page=reports").text
        for tid in ["report-periode", "report-tanggal", "report-bulan", "report-tahun",
                    "report-dari", "report-sampai", "report-filter-btn"]:
            assert f'data-testid="{tid}"' in t, f"{tid} tidak ada"
        assert 'data-periode="harian mingguan"' in t and 'data-periode="custom"' in t

    def test_weekly_report(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=reports",
                       params={"periode": "mingguan", "tanggal": TODAY.isoformat()})
        assert r.status_code == 200
        monday = TODAY - timedelta(days=TODAY.weekday())
        sunday = monday + timedelta(days=6)
        rows = db_query("SELECT * FROM transactions WHERE date(created_at) BETWEEN ? AND ?",
                        (monday.isoformat(), sunday.isoformat()))
        assert int(re.search(r'data-testid="summary-count">(\d+)<', r.text).group(1)) == len(rows), \
            f"Mingguan salah, rentang {monday}..{sunday}"


# ---------------- Modul: export.php ----------------
class TestExport:
    def test_transactions_xls(self, client):
        r = client.get(f"{BASE_URL}/export.php",
                       params={"type": "transactions", "format": "xls", "periode": "bulanan", "bulan": THIS_MONTH})
        assert r.status_code == 200
        assert "application/vnd.ms-excel" in r.headers.get("Content-Type", "")
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd and cd.strip().endswith('.xls"'), cd
        assert "Laporan Transaksi" in r.text
        assert "TRX-" in r.text
        assert "TOTAL" in r.text

    def test_transactions_doc(self, client):
        r = client.get(f"{BASE_URL}/export.php",
                       params={"type": "transactions", "format": "doc", "periode": "bulanan", "bulan": THIS_MONTH})
        assert r.status_code == 200
        assert "application/msword" in r.headers.get("Content-Type", "")
        assert '.doc"' in r.headers.get("Content-Disposition", "")
        assert "TRX-" in r.text

    def test_transactions_pdf_printview(self, client):
        r = client.get(f"{BASE_URL}/export.php",
                       params={"type": "transactions", "format": "pdf", "periode": "bulanan", "bulan": THIS_MONTH})
        assert r.status_code == 200
        assert "text/html" in r.headers.get("Content-Type", "")
        assert "attachment" not in r.headers.get("Content-Disposition", "")
        assert "window.print" in r.text
        assert "Laporan Transaksi" in r.text
        assert 'data-testid="pdf-print-btn"' in r.text

    def test_parts_exports(self, client):
        kode_list = [p["kode"] for p in db_query("SELECT kode FROM parts LIMIT 3")]
        r = client.get(f"{BASE_URL}/export.php", params={"type": "parts", "format": "xls"})
        assert r.status_code == 200
        assert "application/vnd.ms-excel" in r.headers.get("Content-Type", "")
        assert "daftar_sparepart" in r.headers.get("Content-Disposition", "")
        assert "Daftar Sparepart" in r.text
        for k in kode_list:
            assert k in r.text
        assert ("MENIPIS" in r.text) or ("Aman" in r.text)

        rd = client.get(f"{BASE_URL}/export.php", params={"type": "parts", "format": "doc"})
        assert rd.status_code == 200 and "application/msword" in rd.headers.get("Content-Type", "")
        rp = client.get(f"{BASE_URL}/export.php", params={"type": "parts", "format": "pdf"})
        assert rp.status_code == 200 and "window.print" in rp.text

    def test_export_respects_filter(self, client):
        yesterday = (TODAY - timedelta(days=1)).isoformat()
        today_notas = [t["no_nota"] for t in
                       db_query("SELECT no_nota FROM transactions WHERE date(created_at)=?", (TODAY.isoformat(),))]
        r = client.get(f"{BASE_URL}/export.php",
                       params={"type": "transactions", "format": "xls", "periode": "harian", "tanggal": yesterday})
        assert r.status_code == 200
        for n in today_notas:
            assert n not in r.text, f"Export periode {yesterday} berisi transaksi hari ini {n}"

    def test_export_requires_login(self):
        r = requests.get(f"{BASE_URL}/export.php", params={"type": "parts", "format": "xls"},
                         allow_redirects=False)
        assert r.status_code in (302, 303), f"export.php dapat diakses tanpa login: {r.status_code}"


# ---------------- Regresi cepat ----------------
class TestRegression:
    def test_dashboard_and_pos_pages(self, client):
        for page in ["dashboard", "pos", "parts", "customers", "warranty"]:
            r = client.get(f"{BASE_URL}/index.php?page={page}")
            assert r.status_code == 200, f"page={page} -> {r.status_code}"

    def test_create_transaction(self, client, sfx):
        nama = f"TEST_R2_Cust_{sfx}"
        client.post(f"{BASE_URL}/index.php?page=customers",
                    data={"action": "save", "id": "", "nama": nama, "telepon": "0812", "alamat": "Jl"})
        cust = db_query("SELECT * FROM customers WHERE nama=?", (nama,))
        assert cust, "Pelanggan uji gagal dibuat"
        cid = cust[0]["id"]
        r = client.post(f"{BASE_URL}/index.php?page=pos", data={
            "action": "save_trx", "customer_id": str(cid), "vehicle_id": "0",
            "jasa_nama[]": "TEST_Jasa Servis", "jasa_biaya[]": "50000", "jasa_garansi[]": "0",
        })
        assert r.status_code == 200, f"POS save_trx gagal: {r.status_code} {r.text[:300]}"
        trx = db_query("SELECT * FROM transactions WHERE customer_id=? ORDER BY id DESC", (cid,))
        assert trx and trx[0]["grand_total"] == 50000
        # transaksi baru muncul di laporan harian
        rep = client.get(f"{BASE_URL}/index.php?page=reports",
                         params={"periode": "harian", "tanggal": TODAY.isoformat()}).text
        assert trx[0]["no_nota"] in rep
