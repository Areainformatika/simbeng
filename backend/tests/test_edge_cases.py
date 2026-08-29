"""Edge case / robustness checks (parameter tidak valid)."""
import os
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
CREDS = {"username": "admin", "password": "admin123"}


def _client():
    s = requests.Session()
    s.post(f"{BASE_URL}/index.php?page=login", data=CREDS)
    return s


class TestEdgeCases:
    def test_stock_in_invalid_part(self):
        c = _client()
        r = c.post(f"{BASE_URL}/index.php?page=stock",
                   data={"action": "masuk", "part_id": 999999, "jumlah": 3, "keterangan": "TEST bogus"})
        body = r.text.lower()
        assert r.status_code == 200, r.status_code
        assert "fatal error" not in body and "pdoexception" not in body and "uncaught" not in body, \
            f"Unhandled PHP error saat part_id tidak valid: {r.text[:400]}"

    def test_stock_out_invalid_part(self):
        c = _client()
        r = c.post(f"{BASE_URL}/index.php?page=stock",
                   data={"action": "keluar", "part_id": 999999, "jumlah": 1, "keterangan": "TEST bogus"})
        body = r.text.lower()
        assert "fatal error" not in body and "pdoexception" not in body and "uncaught" not in body, \
            f"Unhandled PHP error: {r.text[:400]}"

    def test_pos_invalid_customer(self):
        c = _client()
        r = c.post(f"{BASE_URL}/index.php?page=pos",
                   data={"action": "save_trx", "customer_id": 999999,
                         "jasa_nama[]": "TEST X", "jasa_biaya[]": "1000", "jasa_garansi[]": "0"})
        body = r.text.lower()
        assert "fatal error" not in body and "uncaught" not in body, r.text[:400]

    def test_receipt_invalid_id(self):
        c = _client()
        r = c.get(f"{BASE_URL}/index.php?page=receipt&id=999999")
        body = r.text.lower()
        assert "fatal error" not in body and "uncaught" not in body, r.text[:400]

    def test_warranty_print_invalid_id(self):
        c = _client()
        r = c.get(f"{BASE_URL}/index.php?page=warranty_print&id=999999")
        body = r.text.lower()
        assert "fatal error" not in body and "uncaught" not in body, r.text[:400]

    def test_warranty_claim_invalid_item(self):
        c = _client()
        r = c.post(f"{BASE_URL}/index.php?page=warranty",
                   data={"action": "create", "transaction_item_id": 999999, "alasan": "TEST"})
        body = r.text.lower()
        assert "fatal error" not in body and "uncaught" not in body, r.text[:400]

    def test_lookup_unknown_action(self):
        c = _client()
        j = c.get(f"{BASE_URL}/ajax/lookup.php?action=bogus").json()
        assert j.get("error") == "unknown action"

    def test_import_malformed_json(self):
        c = _client()
        r = c.post(f"{BASE_URL}/ajax/import_parts.php", data="not-json")
        assert r.status_code == 200
        assert "fatal error" not in r.text.lower(), r.text[:300]
