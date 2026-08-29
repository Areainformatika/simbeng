"""Iteration 3 tests: waktu WIB pada cetakan + fitur Pengaturan (identitas & tema)."""
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timedelta

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
KASIR_USER = "TEST_kasir_it3"
KASIR_PASS = "kasir123"


def dbq(sql, params=()):
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(sql, params).fetchall()
    con.close()
    return [dict(r) for r in rows]


def login(username, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/index.php?page=login",
               data={"username": username, "password": password},
               allow_redirects=False, timeout=30)
    assert r.status_code in (302, 303), f"login status {r.status_code}"
    assert "index.php" in r.headers.get("Location", ""), r.headers
    return s


@pytest.fixture(scope="module")
def admin():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def kasir():
    """Buat user kasir (hash via PHP) lalu login."""
    h = subprocess.run(
        ["php", "-r", "echo password_hash('%s', PASSWORD_DEFAULT);" % KASIR_PASS],
        capture_output=True, text=True).stdout.strip()
    assert h.startswith("$2y$"), f"php hash failed: {h}"
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM users WHERE username=?", (KASIR_USER,))
    con.execute("INSERT INTO users (username,password_hash,nama,role) VALUES (?,?,?,'kasir')",
                (KASIR_USER, h, "TEST Kasir Iter3"))
    con.commit()
    con.close()
    yield login(KASIR_USER, KASIR_PASS)
    con = sqlite3.connect(DB)
    con.execute("DELETE FROM users WHERE username=?", (KASIR_USER,))
    con.commit()
    con.close()


@pytest.fixture(scope="module")
def original_settings():
    rows = dbq("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


# ---------- (A) BUG FIX WAKTU ----------
class TestWaktuCetakan:
    def test_receipt_tanggal_is_utc_plus_7(self, admin):
        trx = dbq("SELECT id, no_nota, created_at FROM transactions ORDER BY id DESC LIMIT 1")
        assert trx, "no transactions seeded"
        t = trx[0]
        r = admin.get(f"{BASE_URL}/index.php?page=receipt&id={t['id']}", timeout=30)
        assert r.status_code == 200
        html = r.text
        assert t["no_nota"] in html
        expected = (datetime.strptime(t["created_at"], "%Y-%m-%d %H:%M:%S")
                    + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")
        m = re.search(r"Tanggal</td><td>:\s*([0-9/]+\s[0-9:]+)\s*WIB", html)
        assert m, "Tanggal WIB row not found in receipt"
        assert m.group(1) == expected, f"got {m.group(1)}, expected {expected} (raw {t['created_at']})"

    def test_receipt_has_waktu_cetak_realtime_script(self, admin):
        tid = dbq("SELECT id FROM transactions ORDER BY id DESC LIMIT 1")[0]["id"]
        html = admin.get(f"{BASE_URL}/index.php?page=receipt&id={tid}", timeout=30).text
        assert 'data-testid="waktu-cetak"' in html
        assert "setInterval(tickWaktu, 1000)" in html
        assert "toLocaleString('id-ID'" in html

    def test_warranty_print_tanggal_wib(self, admin):
        c = dbq("SELECT id, kode, created_at FROM warranty_claims ORDER BY id LIMIT 1")
        assert c, "no warranty claims"
        c = c[0]
        html = admin.get(f"{BASE_URL}/index.php?page=warranty_print&id={c['id']}", timeout=30).text
        expected = (datetime.strptime(c["created_at"], "%Y-%m-%d %H:%M:%S")
                    + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")
        m = re.search(r"Tanggal Pengajuan</td><td>:\s*([0-9/]+\s[0-9:]+)\s*WIB", html)
        assert m, "Tanggal Pengajuan WIB row not found"
        assert m.group(1) == expected
        assert 'data-testid="waktu-cetak"' in html
        assert "setInterval(tickWaktu, 1000)" in html

    @pytest.mark.parametrize("fmt", ["pdf", "xls"])
    def test_export_transactions_uses_lokal_and_shop_name(self, admin, fmt):
        # rentang lebar agar transaksi lama ikut
        r = admin.get(f"{BASE_URL}/export.php?type=transactions&format={fmt}"
                      f"&periode=custom&dari=2020-01-01&sampai=2030-12-31", timeout=60)
        assert r.status_code == 200
        html = r.text
        nama = dbq("SELECT value FROM settings WHERE key='nama_bengkel'")[0]["value"]
        assert nama in html, "nama bengkel dari pengaturan tidak muncul di header laporan"
        trx = dbq("SELECT no_nota, created_at FROM transactions ORDER BY id DESC LIMIT 1")[0]
        expected = (datetime.strptime(trx["created_at"], "%Y-%m-%d %H:%M:%S")
                    + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")
        assert expected in html, f"tanggal lokal {expected} tidak ada di export {fmt}"


# ---------- (B) PENGATURAN ----------
class TestPengaturan:
    def test_admin_can_open_settings(self, admin):
        r = admin.get(f"{BASE_URL}/index.php?page=settings", timeout=30)
        assert r.status_code == 200
        for tid in ["settings-form", "setting-nama", "setting-nib", "setting-pemilik",
                    "setting-alamat", "setting-telepon", "theme-h1-slider",
                    "theme-h2-slider", "theme-preview", "settings-submit"]:
            assert f'data-testid="{tid}"' in r.text, f"missing {tid}"
        assert 'data-testid="nav-settings"' in r.text

    def test_save_settings_persists_and_propagates(self, admin, original_settings):
        payload = {
            "action": "save",
            "nama_bengkel": "TEST Bengkel Iter3",
            "nib": "9998887776665",
            "pemilik": "TEST Pemilik",
            "alamat": "Jl. Pengujian No. 7",
            "telepon": "0899-1111-2222",
            "theme_h1": "350",
            "theme_h2": "15",
        }
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data=payload,
                       allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303)
        stored = {x["key"]: x["value"] for x in dbq("SELECT key, value FROM settings")}
        for k in ["nama_bengkel", "nib", "pemilik", "alamat", "telepon", "theme_h1", "theme_h2"]:
            assert stored[k] == payload[k], f"{k}={stored[k]} expected {payload[k]}"

        # sidebar brand + title
        dash = admin.get(f"{BASE_URL}/index.php", timeout=30).text
        assert "TEST Bengkel Iter3" in dash
        assert "linear-gradient(165deg, hsl(350 60% 18%) 0%, hsl(15 65% 32%) 100%)" in dash

        # receipt identitas
        tid = dbq("SELECT id FROM transactions ORDER BY id DESC LIMIT 1")[0]["id"]
        rec = admin.get(f"{BASE_URL}/index.php?page=receipt&id={tid}", timeout=30).text
        assert "TEST BENGKEL ITER3" in rec
        assert "9998887776665" in rec and "TEST Pemilik" in rec
        assert "Jl. Pengujian No. 7" in rec and "0899-1111-2222" in rec

        # warranty print identitas
        wid = dbq("SELECT id FROM warranty_claims ORDER BY id LIMIT 1")[0]["id"]
        wp = admin.get(f"{BASE_URL}/index.php?page=warranty_print&id={wid}", timeout=30).text
        assert "TEST BENGKEL ITER3" in wp and "9998887776665" in wp

        # login page (unauthenticated) memakai nama + tema baru
        lg = requests.get(f"{BASE_URL}/index.php?page=login", timeout=30).text
        assert "TEST Bengkel Iter3" in lg
        assert "linear-gradient(150deg, hsl(350 60% 18%), hsl(15 65% 32%))" in lg

    def test_theme_hue_clamped(self, admin):
        admin.post(f"{BASE_URL}/index.php?page=settings",
                   data={"action": "save", "nama_bengkel": "TEST Bengkel Iter3",
                         "nib": "", "pemilik": "", "alamat": "a", "telepon": "b",
                         "theme_h1": "999", "theme_h2": "-40"},
                   allow_redirects=False, timeout=30)
        stored = {x["key"]: x["value"] for x in dbq("SELECT key, value FROM settings")}
        assert stored["theme_h1"] == "359"
        assert stored["theme_h2"] == "0"

    def test_kasir_cannot_access_settings(self, kasir):
        dash = kasir.get(f"{BASE_URL}/index.php", timeout=30).text
        assert 'data-testid="nav-settings"' not in dash, "kasir sees Pengaturan menu"
        r = kasir.get(f"{BASE_URL}/index.php?page=settings", allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303), f"expected redirect, got {r.status_code}"
        follow = kasir.get(f"{BASE_URL}/index.php", timeout=30).text
        assert re.search(r"akses|ditolak|Akses", follow), "no access-denied flash shown"

    def test_restore_settings(self, admin, original_settings):
        payload = {"action": "save"}
        for k in ["nama_bengkel", "nib", "pemilik", "alamat", "telepon", "theme_h1", "theme_h2"]:
            payload[k] = original_settings.get(k, "")
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data=payload,
                       allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303)
        stored = {x["key"]: x["value"] for x in dbq("SELECT key, value FROM settings")}
        assert stored["nama_bengkel"] == original_settings["nama_bengkel"]


# ---------- Regresi cepat ----------
class TestRegresi:
    def test_dashboard_and_key_pages(self, admin):
        for page in ["", "?page=pos", "?page=transactions", "?page=reports",
                     "?page=parts", "?page=warranty", "?page=users", "?page=settings"]:
            r = admin.get(f"{BASE_URL}/index.php{page}", timeout=30)
            assert r.status_code == 200, f"{page} -> {r.status_code}"
            assert "Fatal error" not in r.text and "Warning:" not in r.text, f"php error on {page}"

    def test_create_transaction_and_receipt_time(self, admin):
        cust = dbq("SELECT id FROM customers ORDER BY id LIMIT 1")
        assert cust, "no customers"
        payload = [
            ("action", "save_trx"),
            ("customer_id", str(cust[0]["id"])),
            ("vehicle_id", "0"),
            ("jasa_nama[]", "TEST Jasa Servis"),
            ("jasa_biaya[]", "50000"),
            ("jasa_garansi[]", "7"),
        ]
        r = admin.post(f"{BASE_URL}/index.php?page=pos", data=payload,
                       allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303), r.text[:300]
        loc = r.headers.get("Location", "")
        m = re.search(r"page=receipt&id=(\d+)", loc)
        assert m, f"expected redirect to receipt, got {loc}"
        tid = int(m.group(1))
        raw = dbq("SELECT created_at, no_nota FROM transactions WHERE id=?", (tid,))[0]
        html = admin.get(f"{BASE_URL}/index.php?page=receipt&id={tid}", timeout=30).text
        expected = (datetime.strptime(raw["created_at"], "%Y-%m-%d %H:%M:%S")
                    + timedelta(hours=7)).strftime("%d/%m/%Y %H:%M")
        assert expected in html, f"receipt tanggal mismatch, expected {expected}"
        assert 'data-testid="waktu-cetak"' in html
