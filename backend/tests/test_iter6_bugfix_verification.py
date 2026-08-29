"""Iteration 6: verifikasi perbaikan bug kritis.

Cakupan:
 1. next_kode() MAX-based -> POS checkout berulang & setelah penghapusan transaksi (no_nota unik)
 2. next_kode() untuk kode klaim garansi (GRS)
 3. PRG: semua handler POST harus mengembalikan 302 + tidak duplikasi saat refresh
 4. Upload logo: file >2MB -> flash 'Ukuran logo melebihi batas 2 MB', nama file hex random,
    logo lama dihapus dari disk
"""
import os
import re
import sqlite3
import zlib
import struct

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


# ---------------- helpers (selalu tutup koneksi sqlite di finally) ----------------
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


def strip_tags(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def make_png(size_bytes=0, w=8, h=8):
    """PNG valid (mime image/png) yang bisa dibesarkan dengan chunk noise."""
    raw = b"".join(b"\x00" + bytes([(x * 31) % 256 for x in range(w * 3)]) for _ in range(h))

    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    if size_bytes and size_bytes > len(png) + 200:
        pad = os.urandom(size_bytes - len(png) - 12 - 4 - 12)
        png += chunk(b"teXt", b"pad\x00" + pad)
    png += chunk(b"IEND", b"")
    return png


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/index.php?page=login", data={"username": ADMIN[0], "password": ADMIN[1]},
               allow_redirects=False, timeout=30)
    assert r.status_code in (302, 303), f"login gagal: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def seed():
    cid = dbx("INSERT INTO customers (nama, telepon, alamat) VALUES ('TEST_Iter6_Cust','081200006','Jl Test 6')")
    pid = dbx("INSERT INTO parts (kode,nama,kategori,harga_beli,harga_jual,stok,stok_min) "
              "VALUES ('TEST-IT6-01','TEST_Part_Iter6','Oli',20000,50000,500,5)")
    yield {"customer_id": cid, "part_id": pid}
    # cleanup: hapus semua data yang dibuat test ini
    tids = [r["id"] for r in dbq("SELECT id FROM transactions WHERE customer_id=?", (cid,))]
    for tid in tids:
        dbx("DELETE FROM warranty_claims WHERE transaction_id=?", (tid,))
        dbx("DELETE FROM transaction_items WHERE transaction_id=?", (tid,))
        dbx("DELETE FROM stock_movements WHERE ref_type='penjualan' AND ref_id=?", (tid,))
        dbx("DELETE FROM transactions WHERE id=?", (tid,))
    dbx("DELETE FROM stock_movements WHERE part_id=?", (pid,))
    dbx("DELETE FROM parts WHERE id=?", (pid,))
    dbx("DELETE FROM vehicles WHERE customer_id=?", (cid,))
    dbx("DELETE FROM customers WHERE id=?", (cid,))


def save_trx(sess, seed, jasa_biaya=75000, part_qty=1, garansi=0):
    data = {
        "action": "save_trx", "edit_id": "0",
        "customer_id": str(seed["customer_id"]), "vehicle_id": "",
        "diskon_jenis": "", "diskon_nilai": "",
        "jasa_nama[]": "TEST Jasa Iter6", "jasa_biaya[]": str(jasa_biaya), "jasa_garansi[]": "0",
        "part_id[]": str(seed["part_id"]), "part_qty[]": str(part_qty),
        "part_garansi[]": str(garansi),
    }
    r = sess.post(f"{BASE_URL}/index.php?page=pos", data=data, allow_redirects=False, timeout=30)
    assert r.status_code in (302, 303), f"POS POST bukan redirect: {r.status_code}"
    loc = r.headers.get("Location", "")
    m = re.search(r"id=(\d+)", loc)
    if not m:
        page = sess.get(f"{BASE_URL}/index.php?page=pos", timeout=30).text
        pytest.fail(f"checkout gagal, redirect={loc}; flash={strip_tags(page)[:400]}")
    return int(m.group(1))


def nota_seq(nota):
    return int(nota.split("-")[-1])


def max_seq():
    rows = dbq("SELECT no_nota FROM transactions WHERE no_nota LIKE ?", ("TRX-%",))
    return max([nota_seq(r["no_nota"]) for r in rows] or [0])


# ============ 1. BUG KRITIS: next_kode / no_nota ============
class TestNoNotaCritical:
    def test_three_consecutive_checkouts(self, admin, seed):
        start = max_seq()
        notas = []
        for i in range(3):
            tid = save_trx(admin, seed, jasa_biaya=50000 + i * 1000, part_qty=1)
            row = dbq("SELECT no_nota FROM transactions WHERE id=?", (tid,))[0]
            notas.append(row["no_nota"])
        assert len(set(notas)) == 3, f"no_nota tidak unik: {notas}"
        assert [nota_seq(n) for n in notas] == [start + 1, start + 2, start + 3], notas

    def test_checkout_after_delete_no_unique_error(self, admin, seed):
        # buat 2 transaksi, hapus yang terakhir -> membuat gap
        t1 = save_trx(admin, seed, jasa_biaya=40000)
        t2 = save_trx(admin, seed, jasa_biaya=41000)
        seq2 = nota_seq(dbq("SELECT no_nota FROM transactions WHERE id=?", (t2,))[0]["no_nota"])
        r = admin.post(f"{BASE_URL}/index.php?page=transactions",
                       data={"action": "delete", "id": str(t2)}, allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303)
        assert dbq("SELECT id FROM transactions WHERE id=?", (t2,)) == []

        # setelah gap, checkout harus tetap berhasil (bug lama: UNIQUE constraint)
        t3 = save_trx(admin, seed, jasa_biaya=42000)
        nota3 = dbq("SELECT no_nota FROM transactions WHERE id=?", (t3,))[0]["no_nota"]
        assert nota_seq(nota3) == seq2, f"nomor tidak mengisi ulang dari MAX: {nota3} (seq dihapus={seq2})"
        assert t1 != t3

        # tidak ada pesan error UNIQUE pada halaman POS
        page = strip_tags(admin.get(f"{BASE_URL}/index.php?page=pos", timeout=30).text)
        assert "UNIQUE constraint" not in page

    def test_all_nota_unique_in_db(self):
        rows = dbq("SELECT no_nota FROM transactions")
        notas = [r["no_nota"] for r in rows]
        assert len(notas) == len(set(notas)), "ada no_nota duplikat di database"


# ============ 2. Kode GRS klaim garansi ============
class TestWarrantyKode:
    def test_create_claim_generates_unique_grs(self, admin, seed):
        before = [r["kode"] for r in dbq("SELECT kode FROM warranty_claims")]
        tid = save_trx(admin, seed, jasa_biaya=60000, part_qty=1, garansi=30)
        item = dbq("SELECT * FROM transaction_items WHERE transaction_id=? AND tipe='part'", (tid,))[0]
        r = admin.post(f"{BASE_URL}/index.php?page=warranty",
                       data={"action": "create", "transaction_item_id": item["id"],
                             "alasan": "TEST_Iter6 verifikasi kode GRS"},
                       allow_redirects=False, timeout=30)
        assert r.status_code in (302, 303), f"POST warranty create bukan 302: {r.status_code}"
        claim = dbq("SELECT * FROM warranty_claims WHERE transaction_item_id=?", (item["id"],))
        assert claim, "klaim garansi tidak tersimpan"
        kode = claim[0]["kode"]
        assert re.match(r"^GRS-\d{6}-\d{3}$", kode), kode
        assert kode not in before, f"kode GRS duplikat: {kode}"
        all_kode = [x["kode"] for x in dbq("SELECT kode FROM warranty_claims")]
        assert len(all_kode) == len(set(all_kode)), "kode GRS duplikat di DB"
        dbx("DELETE FROM warranty_claims WHERE id=?", (claim[0]["id"],))


# ============ 3. PRG: semua POST harus 302 ============
class TestPRG:
    def _post(self, admin, page, data):
        return admin.post(f"{BASE_URL}/index.php?page={page}", data=data,
                          allow_redirects=False, timeout=30)

    def test_notes_add_is_302_and_no_duplicate_on_refresh(self, admin):
        isi = "TEST_Iter6 catatan PRG"
        r = self._post(admin, "notes", {"action": "add", "isi": isi, "warna": "kuning"})
        assert r.status_code in (302, 303), f"notes add status {r.status_code} (harus 302)"
        assert "Location" in r.headers
        rows = dbq("SELECT id FROM notes WHERE isi=?", (isi,))
        assert len(rows) == 1, f"jumlah catatan setelah 1 POST = {len(rows)}"
        # refresh (GET pada Location) tidak boleh menduplikasi
        admin.get(f"{BASE_URL}/index.php?page=notes", timeout=30)
        assert len(dbq("SELECT id FROM notes WHERE isi=?", (isi,))) == 1
        for row in rows:
            self._post(admin, "notes", {"action": "delete", "id": str(row["id"])})
        assert dbq("SELECT id FROM notes WHERE isi=?", (isi,)) == []

    def test_settings_save_is_302_always(self, admin):
        cur = {r["key"]: r["value"] for r in dbq("SELECT key,value FROM settings")}
        payload = {"action": "save", "nama_bengkel": cur.get("nama_bengkel", ""),
                   "nib": cur.get("nib", ""), "pemilik": cur.get("pemilik", ""),
                   "alamat": cur.get("alamat", ""), "telepon": cur.get("telepon", ""),
                   "theme_h1": cur.get("theme_h1", "210"), "theme_h2": cur.get("theme_h2", "232")}
        for i in range(3):
            r = self._post(admin, "settings", payload)
            assert r.status_code in (302, 303), f"settings save #{i + 1} status {r.status_code}"
        after = {r["key"]: r["value"] for r in dbq("SELECT key,value FROM settings")}
        assert after.get("nama_bengkel") == cur.get("nama_bengkel"), "settings berubah tak terduga"

    def test_customer_supplier_part_stock_posts_are_302(self, admin, seed):
        # pelanggan
        r = self._post(admin, "customers", {"action": "save", "id": "0", "nama": "TEST_Iter6_PRG_Cust",
                                            "telepon": "0812", "alamat": "Jl PRG"})
        assert r.status_code in (302, 303), f"customers save {r.status_code}"
        c = dbq("SELECT id FROM customers WHERE nama='TEST_Iter6_PRG_Cust'")
        assert len(c) == 1
        # supplier
        r = self._post(admin, "suppliers", {"action": "save", "id": "0", "nama": "TEST_Iter6_PRG_Sup",
                                            "telepon": "0813", "email": "", "alamat": "", "keterangan": ""})
        assert r.status_code in (302, 303), f"suppliers save {r.status_code}"
        s = dbq("SELECT id FROM suppliers WHERE nama='TEST_Iter6_PRG_Sup'")
        assert len(s) == 1
        # sparepart
        r = self._post(admin, "parts", {"action": "save", "id": "0", "kode": "TEST-IT6-PRG",
                                        "barcode": "", "nama": "TEST_Iter6_PRG_Part", "kategori": "Oli",
                                        "harga_beli": "1000", "harga_jual": "2000", "stok": "10", "stok_min": "2"})
        assert r.status_code in (302, 303), f"parts save {r.status_code}"
        p = dbq("SELECT id,stok FROM parts WHERE kode='TEST-IT6-PRG'")
        assert len(p) == 1
        # stok masuk
        r = self._post(admin, "stock", {"action": "masuk", "part_id": str(p[0]["id"]), "jumlah": "5",
                                        "supplier_id": str(s[0]["id"]), "keterangan": "TEST_Iter6 PRG"})
        assert r.status_code in (302, 303), f"stock masuk {r.status_code}"
        assert dbq("SELECT stok FROM parts WHERE id=?", (p[0]["id"],))[0]["stok"] == 15
        # refresh tidak menduplikasi
        admin.get(f"{BASE_URL}/index.php?page=stock", timeout=30)
        assert dbq("SELECT stok FROM parts WHERE id=?", (p[0]["id"],))[0]["stok"] == 15
        # cleanup
        dbx("DELETE FROM stock_movements WHERE part_id=?", (p[0]["id"],))
        dbx("DELETE FROM parts WHERE id=?", (p[0]["id"],))
        dbx("DELETE FROM suppliers WHERE id=?", (s[0]["id"],))
        dbx("DELETE FROM customers WHERE id=?", (c[0]["id"],))


# ============ 4. Upload logo ============
class TestLogoUpload:
    def test_oversize_rejected_with_message_and_logo_unchanged(self, admin):
        before = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        big = make_png(size_bytes=3 * 1024 * 1024)
        assert len(big) > 2 * 1024 * 1024
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
                       files={"logo": ("TEST_big.png", big, "image/png")},
                       allow_redirects=True, timeout=90)
        txt = strip_tags(r.text)
        assert "melebihi batas 2 MB" in txt or "maksimal 2 MB" in txt, \
            f"tidak ada pesan error ukuran logo. cuplikan: {txt[:600]}"
        after = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        assert after == before, "logo berubah padahal upload harus ditolak"
        if before:
            assert os.path.isfile(f"/app/bengkel/{before}"), "file logo lama hilang"

    def test_valid_upload_uses_random_hex_name_and_deletes_old(self, admin):
        old = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        r = admin.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
                       files={"logo": ("TEST_logo.png", make_png(w=64, h=64), "image/png")},
                       allow_redirects=True, timeout=60)
        assert "berhasil diunggah" in strip_tags(r.text), strip_tags(r.text)[:400]
        new = dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"]
        assert new != old
        m = re.match(r"^uploads/logo_([0-9a-f]{12})\.png$", new)
        assert m, f"nama file bukan hex random 12 karakter: {new}"
        assert not re.match(r"^\d{9,}$", m.group(1)), "masih memakai timestamp"
        assert os.path.isfile(f"/app/bengkel/{new}")
        if old:
            assert not os.path.isfile(f"/app/bengkel/{old}"), "logo lama tidak dihapus dari disk"
        # logo tampil di sidebar
        html = admin.get(f"{BASE_URL}/index.php?page=dashboard", timeout=30).text
        assert new in html, "logo baru tidak tampil di layout"

    def test_two_uploads_produce_different_names(self, admin):
        names = set()
        for _ in range(2):
            admin.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
                       files={"logo": ("TEST_logo.png", make_png(w=48, h=48), "image/png")},
                       allow_redirects=True, timeout=60)
            names.add(dbq("SELECT value FROM settings WHERE key='logo'")[0]["value"])
        assert len(names) == 2, f"nama file logo bertabrakan: {names}"
        files = [f for f in os.listdir("/app/bengkel/uploads") if f.startswith("logo_")]
        assert len(files) == 1, f"file logo menumpuk di disk: {files}"
