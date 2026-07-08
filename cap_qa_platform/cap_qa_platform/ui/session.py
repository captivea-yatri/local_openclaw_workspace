"""Prepare test user + role for UI flows (no backend scenario run)."""
from __future__ import annotations

from cap_qa_platform.backend.runner import RunConfig
from cap_qa_platform.rpc.client import OdooRPCClient, m2o_id
from cap_qa_platform.rpc.role_manager import RoleManager


def prepare_ui_session(cfg: RunConfig, role_name: str) -> tuple[OdooRPCClient, RoleManager]:
    """Ensure internal test user and assign one role; keep until caller restores."""
    admin = OdooRPCClient(cfg.url, cfg.db, cfg.user, cfg.password, protocol=cfg.protocol)
    admin.authenticate()
    company_id = m2o_id(admin.read("res.users", [admin.uid], ["company_id"])[0]["company_id"])
    if not company_id:
        raise RuntimeError("Admin has no company_id")

    role_manager = RoleManager(admin, cfg.test_login, cfg.test_password)
    role_manager.ensure_test_user(company_id)
    role_manager.backup_role_lines()

    roles = admin.search_read(
        "res.users.role",
        [("name", "=", role_name)],
        ["id", "name"],
        limit=1,
    )
    if not roles:
        raise RuntimeError(f"Role {role_name!r} not found")
    role_manager.assign_single_role(roles[0]["id"])
    return admin, role_manager
