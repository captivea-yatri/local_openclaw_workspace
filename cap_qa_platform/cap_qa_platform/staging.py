"""Staging safety guards for cap_qa_platform."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from cap_qa_platform.paths import PACKAGE_ROOT

DEFAULT_PROD_HINTS: tuple[str, ...] = (
    "prod",
    "production",
    "live",
    "www.",
    "odoo.com",
    "captivea.com",
)

STAGING_ENV_FILE = PACKAGE_ROOT.parent / "staging.env"


def load_staging_env(path: Path | None = None) -> None:
    env_path = path or STAGING_ENV_FILE
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def looks_like_production(url: str, db: str, extra_hints: tuple[str, ...] = ()) -> list[str]:
    blob = f"{url.lower()} {db.lower()}"
    hints = tuple(DEFAULT_PROD_HINTS) + extra_hints
    custom = os.environ.get("CAP_QA_PROD_HINTS", "")
    if custom:
        hints = hints + tuple(h.strip().lower() for h in custom.split(",") if h.strip())
    matched = [h for h in hints if h in blob]
    allowed = os.environ.get("CAP_QA_ALLOWED_HOSTS", "")
    if allowed and any(a.strip() in blob for a in allowed.lower().split(",") if a.strip()):
        return []
    return matched


def assert_staging_target(url: str, db: str, *, allow_production: bool = False) -> None:
    if allow_production or os.environ.get("CAP_QA_ALLOW_PRODUCTION") == "1":
        return
    matched = looks_like_production(url, db)
    if matched:
        msg = (
            f"Refusing QA run against suspected production "
            f"(url={url!r}, db={db!r}; matched: {', '.join(matched)}).\n"
            "Use staging or pass --allow-production."
        )
        print(f"ERROR: {msg}", file=sys.stderr)
        raise SystemExit(2)


def apply_staging_defaults(ns, *, load_env: bool = False) -> None:
    if load_env:
        load_staging_env()
    if getattr(ns, "url", None) in (None, "", "http://localhost:8069") and os.environ.get("ODOO_URL"):
        ns.url = os.environ["ODOO_URL"]
    if getattr(ns, "db", None) in (None, "", "odoo") and os.environ.get("ODOO_DB"):
        ns.db = os.environ["ODOO_DB"]
    if getattr(ns, "user", None) in (None, "", "admin") and os.environ.get("ODOO_USER"):
        ns.user = os.environ["ODOO_USER"]
    if getattr(ns, "password", None) in (None, "", "admin") and os.environ.get("ODOO_PASSWORD"):
        ns.password = os.environ["ODOO_PASSWORD"]
