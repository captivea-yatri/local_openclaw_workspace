"""Playwright UI configuration from environment."""
from __future__ import annotations

import os


def odoo_url() -> str:
    return os.environ.get("ODOO_URL", "http://localhost:8069").rstrip("/")


def odoo_db() -> str:
    return os.environ.get("ODOO_DB", "odoo")


def ui_user() -> str:
    return os.environ.get("CAP_QA_UI_USER", os.environ.get("ODOO_USER", "admin"))


def ui_password() -> str:
    return os.environ.get("CAP_QA_UI_PASSWORD", os.environ.get("ODOO_PASSWORD", "admin"))


def headless() -> bool:
    return os.environ.get("CAP_QA_UI_HEADLESS", "1") != "0"
