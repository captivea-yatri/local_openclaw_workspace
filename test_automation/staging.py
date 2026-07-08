"""Staging QA guards — never hit production by accident."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from test_automation.paths import PACKAGE_ROOT

# Host/db substrings that suggest production (override with --allow-production).
DEFAULT_PROD_HINTS: tuple[str, ...] = (
    "prod",
    "production",
    "live",
    "www.",
    "odoo.com",
    "captivea.com",
)

STAGING_ENV_FILE = PACKAGE_ROOT / "staging.env"


def load_staging_env(path: Path | None = None) -> None:
    """Load KEY=VALUE lines into os.environ (does not override existing vars)."""
    env_path = path or STAGING_ENV_FILE
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        os.environ.setdefault(key, value)


def _target_blob(url: str, db: str) -> str:
    return f"{url.lower()} {db.lower()}"


def looks_like_production(url: str, db: str, extra_hints: tuple[str, ...] = ()) -> list[str]:
    """Return matched hint strings if target looks like production."""
    blob = _target_blob(url, db)
    hints = tuple(DEFAULT_PROD_HINTS) + extra_hints
    custom = os.environ.get("STAGING_QA_PROD_HINTS", "")
    if custom:
        hints = hints + tuple(h.strip().lower() for h in custom.split(",") if h.strip())
    matched = [h for h in hints if h in blob]
    # Explicit staging allowlist in env: STAGING_QA_ALLOWED_HOSTS=localhost,staging
    allowed = os.environ.get("STAGING_QA_ALLOWED_HOSTS", "")
    if allowed:
        allow_blob = allowed.lower()
        if any(a.strip() in blob for a in allow_blob.split(",") if a.strip()):
            return []
    return matched


def assert_staging_target(
    url: str,
    db: str,
    *,
    allow_production: bool = False,
) -> None:
    """Abort if URL/DB looks like production unless explicitly allowed."""
    if allow_production or os.environ.get("STAGING_QA_ALLOW_PRODUCTION") == "1":
        return
    matched = looks_like_production(url, db)
    if matched:
        msg = (
            f"Refusing to run QA against suspected production target "
            f"(url={url!r}, db={db!r}; matched: {', '.join(matched)}).\n"
            "Use a staging URL/DB, or pass --allow-production / set STAGING_QA_ALLOW_PRODUCTION=1."
        )
        print(f"ERROR: {msg}", file=sys.stderr)
        raise SystemExit(2)


def apply_staging_defaults(args_namespace, *, load_env: bool = False) -> None:
    """Optional: load staging.env then fill empty url/db/user/password from os.environ."""
    if load_env:
        load_staging_env()
    ns = args_namespace
    if getattr(ns, "url", None) in (None, "", "http://localhost:8069") and os.environ.get("ODOO_URL"):
        ns.url = os.environ["ODOO_URL"]
    if getattr(ns, "db", None) in (None, "", "odoo") and os.environ.get("ODOO_DB"):
        ns.db = os.environ["ODOO_DB"]
    if getattr(ns, "user", None) in (None, "", "admin") and os.environ.get("ODOO_USER"):
        ns.user = os.environ["ODOO_USER"]
    if getattr(ns, "password", None) in (None, "", "admin") and os.environ.get("ODOO_PASSWORD"):
        ns.password = os.environ["ODOO_PASSWORD"]
