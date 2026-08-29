"""Smoke test: login + semua halaman merespons 200 tanpa PHP error (iterasi 7, UI-only fix)."""
import os
import re

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

PAGES = [
    "dashboard", "pos", "transactions", "reports", "charts", "customers",
    "parts", "categories", "stock", "suppliers", "warranty", "notes",
    "users", "settings",
]

PHP_ERROR_RE = re.compile(r"(Fatal error|Parse error|Warning:|Notice:|Uncaught)", re.I)


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/index.php?page=login",
               data={"username": "admin", "password": "admin123"},
               timeout=30, allow_redirects=True)
    assert r.status_code == 200, r.status_code
    assert "Dashboard" in r.text or "sidebar" in r.text, "Login gagal"
    return s


@pytest.mark.parametrize("page", PAGES)
def test_page_loads(session, page):
    url = f"{BASE_URL}/index.php" if page == "dashboard" else f"{BASE_URL}/index.php?page={page}"
    r = session.get(url, timeout=30)
    assert r.status_code == 200, f"{page} -> {r.status_code}"
    found = PHP_ERROR_RE.findall(r.text)
    assert not found, f"{page} PHP error: {found[:3]}"
    assert 'data-testid="sidebar"' in r.text, f"{page} sidebar missing"
    assert 'data-testid="hamburger-btn"' in r.text, f"{page} hamburger missing"
    assert 'data-testid="sidebar-overlay"' in r.text, f"{page} overlay missing"
