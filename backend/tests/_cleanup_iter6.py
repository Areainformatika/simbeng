"""Bersihkan data uji (TEST_*/UI_*) dari bengkel.db & pasang kembali logo yang layak.
Dipakai manual setelah suite pytest selesai (bukan test)."""
import os
import re
import sqlite3
import struct
import zlib

import requests
from dotenv import dotenv_values

DB = "/app/bengkel/bengkel.db"
BASE_URL = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")

con = sqlite3.connect(DB, timeout=20)
try:
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # 1. transaksi milik pelanggan uji atau berisi item uji
    test_cust = [r["id"] for r in cur.execute(
        "SELECT id FROM customers WHERE nama LIKE 'TEST%' OR nama LIKE 'UI %'").fetchall()]
    tids = set()
    if test_cust:
        q = "SELECT id FROM transactions WHERE customer_id IN (%s)" % ",".join("?" * len(test_cust))
        tids |= {r["id"] for r in cur.execute(q, test_cust).fetchall()}
    tids |= {r["transaction_id"] for r in cur.execute(
        "SELECT DISTINCT transaction_id FROM transaction_items "
        "WHERE nama LIKE 'TEST%' OR nama LIKE 'UI Jasa%' OR nama LIKE 'UI %'").fetchall()}

    for tid in tids:
        cur.execute("DELETE FROM warranty_claims WHERE transaction_id=?", (tid,))
        cur.execute("DELETE FROM transaction_items WHERE transaction_id=?", (tid,))
        cur.execute("DELETE FROM stock_movements WHERE ref_type='penjualan' AND ref_id=?", (tid,))
        cur.execute("DELETE FROM transactions WHERE id=?", (tid,))

    # 2. klaim garansi uji
    cur.execute("DELETE FROM warranty_claims WHERE kode LIKE 'TEST%' OR item_nama LIKE 'TEST%'"
                " OR alasan LIKE 'TEST%'")

    # 3. pelanggan + kendaraan uji
    for cid in test_cust:
        if not cur.execute("SELECT 1 FROM transactions WHERE customer_id=?", (cid,)).fetchone():
            cur.execute("DELETE FROM vehicles WHERE customer_id=?", (cid,))
            cur.execute("DELETE FROM customers WHERE id=?", (cid,))

    # 4. sparepart uji (hanya jika tidak dipakai transaksi tersisa)
    for p in cur.execute("SELECT id FROM parts WHERE kode LIKE 'TEST%' OR nama LIKE 'TEST%'"
                         " OR nama LIKE 'UI %'").fetchall():
        used = cur.execute("SELECT 1 FROM transaction_items WHERE part_id=?", (p["id"],)).fetchone()
        ref = cur.execute("SELECT 1 FROM warranty_claims WHERE replacement_part_id=?", (p["id"],)).fetchone()
        if not used and not ref:
            cur.execute("DELETE FROM stock_movements WHERE part_id=?", (p["id"],))
            cur.execute("DELETE FROM parts WHERE id=?", (p["id"],))

    # 5. catatan uji + catatan verifikasi manual
    cur.execute("DELETE FROM notes WHERE isi LIKE 'TEST%' OR isi LIKE 'UI %'"
                " OR isi LIKE 'Catatan verifikasi PRG%'")

    # 6. user uji
    cur.execute("DELETE FROM users WHERE username LIKE 'TEST%'")

    # 7. supplier & kategori uji
    cur.execute("DELETE FROM suppliers WHERE nama LIKE 'TEST%' OR nama LIKE 'UI %'")
    cur.execute("DELETE FROM categories WHERE nama LIKE 'TEST%'")
    con.commit()

    print("customers:", [dict(r) for r in cur.execute("SELECT id,nama FROM customers")])
    print("parts:", [dict(r) for r in cur.execute("SELECT kode,nama,stok FROM parts")])
    print("transactions:", [dict(r) for r in cur.execute(
        "SELECT no_nota,grand_total FROM transactions ORDER BY id")])
    print("claims:", [dict(r) for r in cur.execute("SELECT kode,status FROM warranty_claims")])
    print("notes:", [dict(r) for r in cur.execute("SELECT id,isi FROM notes")])
    print("users:", [dict(r) for r in cur.execute("SELECT username,role FROM users")])
finally:
    con.close()


# ---- pasang logo 300x300 (gradasi biru + kotak putih) ----
def png(w, h):
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            inner = 100 < x < 200 and 100 < y < 200
            if inner:
                row += bytes((255, 255, 255))
            else:
                row += bytes((20 + x // 3, 60 + y // 4, 160))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


s = requests.Session()
r = s.post(f"{BASE_URL}/index.php?page=login", data={"username": "admin", "password": "admin123"},
           timeout=30)
r = s.post(f"{BASE_URL}/index.php?page=settings", data={"action": "upload_logo"},
           files={"logo": ("logo_bengkel.png", png(300, 300), "image/png")}, timeout=60)
print("upload logo ok:", "berhasil diunggah" in re.sub(r"<[^>]+>", " ", r.text))

con = sqlite3.connect(DB, timeout=20)
try:
    print("logo setting:", con.execute("SELECT value FROM settings WHERE key='logo'").fetchone())
finally:
    con.close()
print("uploads dir:", os.listdir("/app/bengkel/uploads"))
