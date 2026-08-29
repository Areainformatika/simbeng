"""
HTTP-level tests untuk aplikasi PHP native "Bengkel Motor" (SQLite).
Aplikasi dijalankan via `php -S 0.0.0.0:3000` di docroot /app/bengkel dan diakses
melalui URL preview (REACT_APP_BACKEND_URL).

Catatan: pytest.ini memakai xdist `-n 2 --dist loadscope`, sehingga setiap kelas
harus mandiri. Semua prasyarat data dibuat oleh fixture ber-suffix unik per worker.
"""
import os
import re
import sqlite3
import uuid

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


def db_query(sql, params=()):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


@pytest.fixture(scope="session")
def sfx():
    """Suffix unik agar data uji tidak bertabrakan antar worker xdist."""
    return uuid.uuid4().hex[:6].upper()


@pytest.fixture(scope="session")
def client():
    """Session HTTP yang sudah login sebagai admin."""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/index.php?page=login", data=CREDS, allow_redirects=False)
    if r.status_code not in (302, 303):
        pytest.fail(f"Login admin gagal: status {r.status_code}, body {r.text[:300]}")
    return s


@pytest.fixture(scope="session")
def customer(client, sfx):
    """Pelanggan + 1 kendaraan."""
    nama = f"TEST_Pelanggan_{sfx}"
    client.post(f"{BASE_URL}/index.php?page=customers",
                data={"action": "save", "id": "", "nama": nama,
                      "telepon": "08123456789", "alamat": "Jl. Test 1"})
    rows = db_query("SELECT * FROM customers WHERE nama=?", (nama,))
    assert rows, "Fixture: pelanggan gagal dibuat"
    cid = rows[-1]["id"]
    plat = f"TEST {sfx}"
    client.post(f"{BASE_URL}/index.php?page=customers&view={cid}",
                data={"action": "save_vehicle", "customer_id": cid,
                      "merek": "Honda", "model": "Vario", "plat_nomor": plat})
    veh = db_query("SELECT * FROM vehicles WHERE customer_id=?", (cid,))
    assert veh, "Fixture: kendaraan gagal dibuat"
    return {"id": cid, "nama": nama, "plat": plat, "vehicle_id": veh[0]["id"]}


@pytest.fixture(scope="session")
def supplier(client, sfx):
    nama = f"TEST_Supplier_{sfx}"
    client.post(f"{BASE_URL}/index.php?page=suppliers",
                data={"action": "save", "id": "", "nama": nama, "telepon": "0219999",
                      "email": "s@test.id", "alamat": "Jl. Supplier", "keterangan": "qa"})
    rows = db_query("SELECT * FROM suppliers WHERE nama=?", (nama,))
    assert rows, "Fixture: supplier gagal dibuat"
    return rows[-1]


@pytest.fixture
def make_part(client, sfx):
    """Factory membuat sparepart baru dengan stok tertentu."""
    def _make(stok=50, harga_jual=55000, tag="P"):
        kode = f"TEST-{tag}-{sfx}-{uuid.uuid4().hex[:4].upper()}"
        client.post(f"{BASE_URL}/index.php?page=parts",
                    data={"action": "save", "id": "", "kode": kode,
                          "barcode": f"BC{uuid.uuid4().hex[:8]}",
                          "nama": f"TEST Part {kode}", "kategori": "Oli",
                          "harga_beli": 40000, "harga_jual": harga_jual,
                          "stok": stok, "stok_min": 3})
        rows = db_query("SELECT * FROM parts WHERE kode=?", (kode,))
        assert rows, f"Fixture: part {kode} gagal dibuat"
        return rows[0]
    return _make


def create_transaction(client, customer, part, jasa_biaya=50000, jasa_garansi=30, part_garansi=60):
    data = {
        "action": "save_trx",
        "customer_id": customer["id"],
        "vehicle_id": customer["vehicle_id"],
        "jasa_nama[]": "TEST Ganti Oli",
        "jasa_biaya[]": str(jasa_biaya),
        "jasa_garansi[]": str(jasa_garansi),
        "part_id[]": part["id"],
        "part_qty[]": "1",
        "part_garansi[]": str(part_garansi),
    }
    r = client.post(f"{BASE_URL}/index.php?page=pos", data=data, allow_redirects=False)
    assert r.status_code in (302, 303), f"POS gagal: {r.status_code} {r.text[:300]}"
    loc = r.headers.get("Location", "")
    assert "page=receipt" in loc, loc
    return int(re.search(r"id=(\d+)", loc).group(1))


# ---------------- Auth ----------------
class TestAuth:
    def test_login_page_loads(self):
        r = requests.get(f"{BASE_URL}/index.php?page=login")
        assert r.status_code == 200
        assert 'data-testid="login-form"' in r.text
        assert 'data-testid="login-username"' in r.text

    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/index.php?page=login",
                          data={"username": "admin", "password": "wrong"}, allow_redirects=False)
        assert r.status_code == 200
        assert "Username atau password salah" in r.text
        assert 'data-testid="login-error"' in r.text

    def test_login_valid_redirects(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/index.php?page=login", data=CREDS, allow_redirects=False)
        assert r.status_code in (302, 303)
        assert "index.php" in r.headers.get("Location", "")
        home = s.get(f"{BASE_URL}/index.php")
        assert home.status_code == 200
        assert "Administrator" in home.text
        assert 'data-testid="stat-pendapatan"' in home.text

    def test_protected_page_requires_login(self):
        r = requests.get(f"{BASE_URL}/index.php?page=users", allow_redirects=False)
        assert r.status_code in (302, 303)
        assert "page=login" in r.headers.get("Location", "")

    def test_ajax_requires_login(self):
        r = requests.get(f"{BASE_URL}/ajax/lookup.php?action=vehicles&customer_id=1",
                         allow_redirects=False)
        assert r.status_code in (302, 303), r.status_code

    def test_logout(self):
        s = requests.Session()
        s.post(f"{BASE_URL}/index.php?page=login", data=CREDS)
        r = s.get(f"{BASE_URL}/index.php?page=logout", allow_redirects=False)
        assert r.status_code in (302, 303)
        r2 = s.get(f"{BASE_URL}/index.php?page=dashboard", allow_redirects=False)
        assert r2.status_code in (302, 303)


# ---------------- Semua halaman render tanpa error ----------------
class TestPages:
    @pytest.mark.parametrize("page", [
        "dashboard", "customers", "suppliers", "parts", "stock",
        "pos", "transactions", "warranty", "users",
    ])
    def test_page_renders(self, client, page):
        r = client.get(f"{BASE_URL}/index.php?page={page}")
        assert r.status_code == 200, r.text[:300]
        low = r.text.lower()
        assert "fatal error" not in low and "pdoexception" not in low and "warning:" not in low

    def test_dashboard_stat_cards(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=dashboard")
        for tid in ["stat-pendapatan", "stat-servis", "stat-stok-menipis",
                    "stat-pelanggan", "stat-garansi"]:
            assert f'data-testid="{tid}"' in r.text, tid

    def test_unknown_page_falls_back(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=../../etc/passwd")
        assert r.status_code == 200
        assert "root:" not in r.text


# ---------------- Master data ----------------
class TestMasterData:
    def test_customer_and_vehicle_persisted(self, client, customer):
        assert customer["nama"] in client.get(f"{BASE_URL}/index.php?page=customers").text
        j = client.get(f"{BASE_URL}/ajax/lookup.php?action=vehicles&customer_id={customer['id']}").json()
        assert any(v["plat_nomor"] == customer["plat"] for v in j), j
        detail = client.get(f"{BASE_URL}/index.php?page=customers&view={customer['id']}")
        assert customer["plat"] in detail.text

    def test_customer_update(self, client, customer):
        r = client.post(f"{BASE_URL}/index.php?page=customers",
                        data={"action": "save", "id": customer["id"], "nama": customer["nama"],
                              "telepon": "0811222333", "alamat": "Jl. Test Updated"})
        assert r.status_code == 200
        row = db_query("SELECT * FROM customers WHERE id=?", (customer["id"],))[0]
        assert row["telepon"] == "0811222333"
        assert row["alamat"] == "Jl. Test Updated"

    def test_create_part(self, client, make_part):
        part = make_part(stok=10)
        assert part["harga_jual"] == 55000
        assert part["stok"] == 10
        assert part["kode"] in client.get(f"{BASE_URL}/index.php?page=parts").text

    def test_create_supplier(self, client, supplier):
        assert supplier["nama"] in client.get(f"{BASE_URL}/index.php?page=suppliers").text
        assert supplier["email"] == "s@test.id"


# ---------------- Import sparepart (AJAX) ----------------
class TestImportParts:
    def test_import_rows(self, client, sfx):
        k1, k2 = f"TEST-IMP1-{sfx}", f"TEST-IMP2-{sfx}"
        payload = {"rows": [
            {"kode": k1, "nama": "TEST Kampas Rem", "kategori": "Rem",
             "harga_beli": 20000, "harga_jual": 35000, "stok": 7, "stok_min": 2,
             "barcode": f"BCI{sfx}"},
            {"kode": k2.lower(), "Nama": "TEST Busi", "harga_jual": 25000, "stok": 12},
            {"kode": "", "nama": "tanpa kode"},
        ]}
        r = client.post(f"{BASE_URL}/ajax/import_parts.php", json=payload)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("ok") is True, data
        assert "2 ditambah" in data["message"] and "1 dilewati" in data["message"], data
        rows = db_query("SELECT * FROM parts WHERE kode IN (?,?)", (k1, k2))
        assert len(rows) == 2, rows
        by_kode = {x["kode"]: x for x in rows}
        assert by_kode[k1]["stok"] == 7 and by_kode[k1]["harga_jual"] == 35000
        assert by_kode[k2]["nama"] == "TEST Busi"  # normalisasi header "Nama"
        assert k1 in client.get(f"{BASE_URL}/index.php?page=parts&q={k1}").text

    def test_import_upsert_updates_existing(self, client, sfx):
        k1 = f"TEST-IMP1-{sfx}"
        client.post(f"{BASE_URL}/ajax/import_parts.php",
                    json={"rows": [{"kode": k1, "nama": "TEST Kampas Rem", "stok": 7}]})
        data = client.post(f"{BASE_URL}/ajax/import_parts.php", json={"rows": [
            {"kode": k1, "nama": "TEST Kampas Rem v2", "harga_jual": 40000,
             "stok": 9, "stok_min": 2}]}).json()
        assert data.get("ok") is True
        assert "1 diperbarui" in data["message"], data
        row = db_query("SELECT * FROM parts WHERE kode=?", (k1,))[0]
        assert row["nama"] == "TEST Kampas Rem v2" and row["stok"] == 9

    def test_import_empty_payload(self, client):
        data = client.post(f"{BASE_URL}/ajax/import_parts.php", json={"rows": []}).json()
        assert data.get("ok") is False


# ---------------- Stok masuk / keluar ----------------
class TestStock:
    def test_stock_in_increases(self, client, make_part, supplier):
        part = make_part(stok=10)
        r = client.post(f"{BASE_URL}/index.php?page=stock",
                        data={"action": "masuk", "part_id": part["id"], "jumlah": 5,
                              "supplier_id": supplier["id"], "keterangan": "TEST faktur masuk"})
        assert r.status_code == 200
        after = db_query("SELECT stok FROM parts WHERE id=?", (part["id"],))[0]["stok"]
        assert after == 15, f"10 -> {after}"
        mov = db_query("SELECT * FROM stock_movements WHERE part_id=? AND tipe='masuk' ORDER BY id DESC LIMIT 1",
                       (part["id"],))[0]
        assert mov["jumlah"] == 5 and mov["supplier_id"] == supplier["id"]
        assert "TEST faktur masuk" in r.text  # tampil di riwayat pergerakan

    def test_stock_out_decreases(self, client, make_part):
        part = make_part(stok=10)
        r = client.post(f"{BASE_URL}/index.php?page=stock",
                        data={"action": "keluar", "part_id": part["id"], "jumlah": 2,
                              "keterangan": "TEST rusak"})
        assert r.status_code == 200
        after = db_query("SELECT stok FROM parts WHERE id=?", (part["id"],))[0]["stok"]
        assert after == 8

    def test_stock_out_insufficient_rejected(self, client, make_part):
        part = make_part(stok=3)
        r = client.post(f"{BASE_URL}/index.php?page=stock",
                        data={"action": "keluar", "part_id": part["id"], "jumlah": 500,
                              "keterangan": "TEST over"})
        assert "Stok tidak mencukupi" in r.text
        after = db_query("SELECT stok FROM parts WHERE id=?", (part["id"],))[0]["stok"]
        assert after == 3, "Stok berubah padahal seharusnya ditolak"


# ---------------- POS / transaksi ----------------
class TestPOS:
    def test_create_transaction_reduces_stock(self, client, customer, make_part):
        part = make_part(stok=10)
        trx_id = create_transaction(client, customer, part)

        trx = db_query("SELECT * FROM transactions WHERE id=?", (trx_id,))[0]
        assert trx["total_jasa"] == 50000
        assert trx["total_part"] == part["harga_jual"]
        assert trx["grand_total"] == 50000 + part["harga_jual"]
        assert trx["status"] == "selesai"
        items = db_query("SELECT * FROM transaction_items WHERE transaction_id=?", (trx_id,))
        assert len(items) == 2
        assert any(i["tipe"] == "jasa" and i["garansi_hari"] == 30 for i in items)
        assert any(i["tipe"] == "part" and i["garansi_hari"] == 60 for i in items)

        stok_after = db_query("SELECT stok FROM parts WHERE id=?", (part["id"],))[0]["stok"]
        assert stok_after == 9, f"10 -> {stok_after}"
        mov = db_query("SELECT * FROM stock_movements WHERE part_id=? ORDER BY id DESC LIMIT 1",
                       (part["id"],))[0]
        assert mov["tipe"] == "keluar" and mov["ref_type"] == "penjualan"

        # Struk nota
        rec = client.get(f"{BASE_URL}/index.php?page=receipt&id={trx_id}")
        assert rec.status_code == 200
        assert trx["no_nota"] in rec.text
        assert "TEST Ganti Oli" in rec.text
        assert 'data-testid="print-btn"' in rec.text

        # Riwayat transaksi
        hist = client.get(f"{BASE_URL}/index.php?page=transactions")
        assert trx["no_nota"] in hist.text

    def test_transaction_without_items_rejected(self, client, customer):
        count_before = db_query("SELECT COUNT(*) c FROM transactions")[0]["c"]
        r = client.post(f"{BASE_URL}/index.php?page=pos",
                        data={"action": "save_trx", "customer_id": customer["id"]})
        assert r.status_code == 200
        assert "Pilih pelanggan dan tambahkan minimal 1 item" in r.text
        assert db_query("SELECT COUNT(*) c FROM transactions")[0]["c"] == count_before

    def test_transaction_insufficient_stock_rejected(self, client, customer, make_part):
        part = make_part(stok=2)
        count_before = db_query("SELECT COUNT(*) c FROM transactions")[0]["c"]
        r = client.post(f"{BASE_URL}/index.php?page=pos", data={
            "action": "save_trx", "customer_id": customer["id"],
            "part_id[]": part["id"], "part_qty[]": 100, "part_garansi[]": 0})
        assert "tidak mencukupi" in r.text
        assert db_query("SELECT COUNT(*) c FROM transactions")[0]["c"] == count_before
        assert db_query("SELECT stok FROM parts WHERE id=?", (part["id"],))[0]["stok"] == 2


# ---------------- Klaim garansi ----------------
class TestWarranty:
    def test_search_trx_ajax(self, client, customer, make_part):
        part = make_part(stok=5)
        trx_id = create_transaction(client, customer, part)
        no_nota = db_query("SELECT no_nota FROM transactions WHERE id=?", (trx_id,))[0]["no_nota"]

        j = client.get(f"{BASE_URL}/ajax/lookup.php?action=search_trx&q={no_nota}").json()
        assert isinstance(j, list) and j, j
        assert j[0]["no_nota"] == no_nota
        assert len(j[0]["items"]) == 2, j[0]

        j1 = client.get(f"{BASE_URL}/ajax/lookup.php?action=search_trx",
                        params={"q": customer["plat"]}).json()
        assert any(x["id"] == trx_id for x in j1), "pencarian via plat gagal"
        j2 = client.get(f"{BASE_URL}/ajax/lookup.php?action=search_trx",
                        params={"q": customer["nama"]}).json()
        assert any(x["id"] == trx_id for x in j2), "pencarian via nama pelanggan gagal"

    def test_claim_flow_approve_reduces_replacement_stock(self, client, customer, make_part):
        part = make_part(stok=5)
        trx_id = create_transaction(client, customer, part)
        item = db_query("SELECT * FROM transaction_items WHERE transaction_id=? AND tipe='part'",
                        (trx_id,))[0]

        r = client.post(f"{BASE_URL}/index.php?page=warranty",
                        data={"action": "create", "transaction_item_id": item["id"],
                              "alasan": "TEST bunyi kasar setelah 1 minggu"})
        assert r.status_code == 200
        claim = db_query("SELECT * FROM warranty_claims WHERE transaction_item_id=?",
                         (item["id"],))[0]
        assert claim["status"] == "pending"
        assert re.match(r"^GRS-\d{6}-\d{3}$", claim["kode"]), claim["kode"]
        assert claim["kode"] in r.text  # muncul di daftar klaim

        detail = client.get(f"{BASE_URL}/index.php?page=warranty&claim={claim['id']}")
        assert detail.status_code == 200
        assert 'data-testid="claim-update-form"' in detail.text
        assert claim["kode"] in detail.text

        repl = make_part(stok=4, tag="REPL")
        r = client.post(f"{BASE_URL}/index.php?page=warranty",
                        data={"action": "update_status", "claim_id": claim["id"],
                              "status": "disetujui", "replacement_part_id": repl["id"],
                              "catatan_teknisi": "TEST diganti unit baru"})
        assert r.status_code == 200
        upd = db_query("SELECT * FROM warranty_claims WHERE id=?", (claim["id"],))[0]
        assert upd["status"] == "disetujui"
        assert upd["replacement_part_id"] == repl["id"]
        stok_after = db_query("SELECT stok FROM parts WHERE id=?", (repl["id"],))[0]["stok"]
        assert stok_after == 3, f"4 -> {stok_after}"
        mov = db_query("SELECT * FROM stock_movements WHERE ref_type='garansi' AND part_id=? ORDER BY id DESC LIMIT 1",
                       (repl["id"],))[0]
        assert mov["jumlah"] == 1 and mov["tipe"] == "keluar"

        pr = client.get(f"{BASE_URL}/index.php?page=warranty_print&id={claim['id']}")
        assert pr.status_code == 200
        assert claim["kode"] in pr.text

    def test_claim_requires_reason(self, client, customer, make_part):
        part = make_part(stok=5)
        trx_id = create_transaction(client, customer, part)
        item = db_query("SELECT * FROM transaction_items WHERE transaction_id=? LIMIT 1",
                        (trx_id,))[0]
        before = db_query("SELECT COUNT(*) c FROM warranty_claims")[0]["c"]
        r = client.post(f"{BASE_URL}/index.php?page=warranty",
                        data={"action": "create", "transaction_item_id": item["id"], "alasan": ""})
        assert "Lengkapi item yang diklaim" in r.text
        assert db_query("SELECT COUNT(*) c FROM warranty_claims")[0]["c"] == before

    def test_claim_approve_without_stock_fails_gracefully(self, client, customer, make_part):
        """Part pengganti dengan stok 0 harus ditolak dan status tidak berubah."""
        part = make_part(stok=5)
        trx_id = create_transaction(client, customer, part)
        item = db_query("SELECT * FROM transaction_items WHERE transaction_id=? AND tipe='part'",
                        (trx_id,))[0]
        client.post(f"{BASE_URL}/index.php?page=warranty",
                    data={"action": "create", "transaction_item_id": item["id"],
                          "alasan": "TEST klaim kedua"})
        claim = db_query("SELECT * FROM warranty_claims WHERE transaction_item_id=? ORDER BY id DESC LIMIT 1",
                         (item["id"],))[0]
        empty = make_part(stok=0, tag="EMPTY")
        r = client.post(f"{BASE_URL}/index.php?page=warranty",
                        data={"action": "update_status", "claim_id": claim["id"],
                              "status": "disetujui", "replacement_part_id": empty["id"],
                              "catatan_teknisi": "TEST stok habis"})
        assert r.status_code == 200
        assert "Stok sparepart pengganti habis" in r.text, r.text[:500]
        upd = db_query("SELECT * FROM warranty_claims WHERE id=?", (claim["id"],))[0]
        assert upd["status"] == "pending", "Status berubah walau stok pengganti habis"
        assert db_query("SELECT stok FROM parts WHERE id=?", (empty["id"],))[0]["stok"] == 0

    def test_warranty_filter_status(self, client):
        r = client.get(f"{BASE_URL}/index.php?page=warranty&status=disetujui")
        assert r.status_code == 200
        assert 'data-testid="claims-table"' in r.text


# ---------------- Manajemen pengguna & role ----------------
class TestUsers:
    def test_create_kasir_and_role_menu(self, client, sfx):
        uname = f"test_kasir_{sfx.lower()}"
        r = client.post(f"{BASE_URL}/index.php?page=users",
                        data={"action": "save", "id": "", "username": uname,
                              "nama": "TEST Kasir", "role": "kasir", "password": "kasir123"})
        assert r.status_code == 200
        rows = db_query("SELECT * FROM users WHERE username=?", (uname,))
        assert rows, "User kasir tidak tersimpan"
        assert rows[0]["role"] == "kasir"
        assert uname in r.text

        s = requests.Session()
        lr = s.post(f"{BASE_URL}/index.php?page=login",
                    data={"username": uname, "password": "kasir123"}, allow_redirects=False)
        assert lr.status_code in (302, 303), "Login user kasir baru gagal"
        home = s.get(f"{BASE_URL}/index.php")
        assert 'data-testid="nav-users"' not in home.text, "Menu Pengguna tampil untuk role kasir"
        assert 'data-testid="nav-pos"' in home.text
        # Proteksi server-side halaman users untuk non-admin
        ur = s.get(f"{BASE_URL}/index.php?page=users", allow_redirects=False)
        assert ur.status_code in (302, 303) or "Akses" in ur.text, \
            "Role kasir dapat mengakses halaman Manajemen Pengguna (tidak ada proteksi server-side)"

    def test_duplicate_username_rejected(self, client, sfx):
        uname = f"test_dupe_{sfx.lower()}"
        client.post(f"{BASE_URL}/index.php?page=users",
                    data={"action": "save", "id": "", "username": uname,
                          "nama": "TEST Dup", "role": "kasir", "password": "abc12345"})
        before = db_query("SELECT COUNT(*) c FROM users")[0]["c"]
        r = client.post(f"{BASE_URL}/index.php?page=users",
                        data={"action": "save", "id": "", "username": uname,
                              "nama": "TEST Duplikat", "role": "kasir", "password": "abc12345"})
        assert r.status_code == 200
        assert "fatal error" not in r.text.lower()
        assert "sudah digunakan" in r.text
        assert db_query("SELECT COUNT(*) c FROM users")[0]["c"] == before

    def test_new_user_requires_password(self, client, sfx):
        uname = f"test_nopass_{sfx.lower()}"
        r = client.post(f"{BASE_URL}/index.php?page=users",
                        data={"action": "save", "id": "", "username": uname,
                              "nama": "TEST NoPass", "role": "kasir", "password": ""})
        assert "Password wajib diisi" in r.text
        assert not db_query("SELECT * FROM users WHERE username=?", (uname,))
