"""Assign res.users.role to dedicated QA test user."""
from __future__ import annotations

from cap_qa_platform.rpc.client import OdooRPCClient

TEST_USER_LOGIN = "cap_qa_tester"
TEST_USER_NAME = "CAP QA Platform Tester"
TEST_USER_PASSWORD = "cap_qa_test"

BASE_GROUP_USER_XMLID = ("base", "group_user")
BASE_GROUP_PORTAL_XMLID = ("base", "group_portal")
BASE_GROUP_PUBLIC_XMLID = ("base", "group_public")

# Keep base.group_user on QA users after set_groups_from_roles (see base_user_role).
SKIP_ROLE_GROUPS_CTX = {"skip_set_groups_from_roles": True}


class RoleManager:
    def __init__(
        self,
        admin: OdooRPCClient,
        test_login: str = TEST_USER_LOGIN,
        test_password: str = TEST_USER_PASSWORD,
    ):
        self.admin = admin
        self.test_login = test_login
        self.test_password = test_password
        self.test_user_id: int | None = None
        self._original_role_lines: list[dict] = []

    def _group_id_from_xmlid(self, module: str, name: str) -> int | None:
        rows = self.admin.search(
            "ir.model.data",
            [("module", "=", module), ("name", "=", name)],
            limit=1,
        )
        if not rows:
            return None
        return self.admin.read("ir.model.data", rows, ["res_id"])[0]["res_id"]

    def _base_group_user_id(self) -> int:
        group_id = self._group_id_from_xmlid(*BASE_GROUP_USER_XMLID)
        if not group_id:
            raise RuntimeError("base.group_user not found in ir.model.data")
        return group_id

    def _portal_group_id(self) -> int | None:
        return self._group_id_from_xmlid(*BASE_GROUP_PORTAL_XMLID)

    def _public_group_id(self) -> int | None:
        return self._group_id_from_xmlid(*BASE_GROUP_PUBLIC_XMLID)

    def _ensure_internal_via_groups(self, user_id: int, group_user_id: int) -> bool:
        """Fallback: link internal group via res.groups (avoids some write hooks)."""
        portal_group_id = self._portal_group_id()
        try:
            self.admin.write(
                "res.groups", [group_user_id], {"user_ids": [(4, user_id)]}
            )
            if portal_group_id:
                self.admin.write(
                    "res.groups", [portal_group_id], {"user_ids": [(3, user_id)]}
                )
            self.admin.write(
                "res.users",
                [user_id],
                {"share": False},
                context=SKIP_ROLE_GROUPS_CTX,
            )
            user = self.admin.read(
                "res.users", [user_id], ["share", "group_ids"]
            )[0]
            return not user.get("share") and group_user_id in user.get("group_ids", [])
        except Exception:
            return False

    def _force_internal_via_server(self, user_id: int) -> bool:
        try:
            self.admin.execute_kw(
                "res.users",
                "cap_qa_force_internal",
                [[user_id]],
                {},
            )
            return True
        except Exception:
            return False

    def _ensure_internal_user(self, user_id: int) -> None:
        """Force internal (employee) user — never portal/external (share=True)."""
        group_user_id = self._base_group_user_id()
        if self._force_internal_via_server(user_id):
            user = self.admin.read(
                "res.users", [user_id], ["share", "login", "group_ids"]
            )[0]
            if not user.get("share") and group_user_id in user.get("group_ids", []):
                return

        portal_group_id = self._portal_group_id()
        public_group_id = self._public_group_id()
        login = self.test_login

        for attempt in range(3):
            user = self.admin.read(
                "res.users", [user_id], ["share", "login", "group_ids"]
            )[0]
            login = user.get("login", login)
            group_ids = set(user.get("group_ids") or [])
            group_ids.add(group_user_id)
            if portal_group_id:
                group_ids.discard(portal_group_id)
            if public_group_id:
                group_ids.discard(public_group_id)

            self.admin.write(
                "res.users",
                [user_id],
                {"share": False, "group_ids": [(6, 0, sorted(group_ids))]},
                context=SKIP_ROLE_GROUPS_CTX,
            )
            user = self.admin.read(
                "res.users", [user_id], ["share", "login", "group_ids"]
            )[0]
            if not user.get("share") and group_user_id in user.get("group_ids", []):
                return

        if self._ensure_internal_via_groups(user_id, group_user_id):
            return

        raise RuntimeError(
            f"Test user {login!r} is still portal/external (share=True) "
            f"after {attempt + 1} attempts"
        )

    def ensure_test_user(self, company_id: int) -> int:
        group_user_id = self._base_group_user_id()
        existing = self.admin.search(
            "res.users", [("login", "=", self.test_login)], limit=1
        )
        vals = {
            "password": self.test_password,
            "active": True,
            "share": False,
            "company_id": company_id,
            "company_ids": [(6, 0, [company_id])],
            "group_ids": [(4, group_user_id)],
        }
        if existing:
            user_id = existing[0]
            line_ids = self.admin.search(
                "res.users.role.line", [("user_id", "=", user_id)]
            )
            if line_ids:
                self.admin.unlink("res.users.role.line", line_ids)
            self.admin.write(
                "res.users",
                [user_id],
                vals,
                context=SKIP_ROLE_GROUPS_CTX,
            )
        else:
            user_id = self._create_test_user(company_id, group_user_id, vals)
        self._ensure_internal_user(user_id)
        self.test_user_id = user_id
        return user_id

    def _create_test_user(
        self, company_id: int, group_user_id: int, vals: dict
    ) -> int:
        """Create QA test user as internal; fall back to copy from template if create fails."""
        create_vals = {
            "name": TEST_USER_NAME,
            "login": self.test_login,
            **vals,
        }
        try:
            return self.admin.create(
                "res.users", create_vals, context=SKIP_ROLE_GROUPS_CTX
            )
        except Exception:
            pass
        template_ids = self.admin.search(
            "res.users",
            [("login", "=", "feature_matrix_tester"), ("share", "=", False)],
            limit=1,
        )
        if not template_ids:
            template_ids = self.admin.search(
                "res.users",
                [("share", "=", False), ("id", "!=", 1)],
                limit=1,
            )
        if not template_ids:
            raise RuntimeError(
                f"Cannot create test user {self.test_login!r}: "
                "create/copy failed and no internal user template found"
            )
        user_id = self.admin.copy(
            "res.users",
            template_ids[0],
            {
                "name": TEST_USER_NAME,
                "login": self.test_login,
                "password": self.test_password,
                "active": True,
                "share": False,
                "company_id": company_id,
                "company_ids": [(6, 0, [company_id])],
            },
            context=SKIP_ROLE_GROUPS_CTX,
        )
        return user_id

    def backup_role_lines(self) -> None:
        assert self.test_user_id is not None
        line_ids = self.admin.search(
            "res.users.role.line", [("user_id", "=", self.test_user_id)]
        )
        if line_ids:
            self._original_role_lines = self.admin.read(
                "res.users.role.line",
                line_ids,
                ["role_id", "date_from", "date_to"],
            )

    def restore_role_lines(self) -> None:
        assert self.test_user_id is not None
        line_ids = self.admin.search(
            "res.users.role.line", [("user_id", "=", self.test_user_id)]
        )
        if line_ids:
            self.admin.unlink("res.users.role.line", line_ids)
        for line in self._original_role_lines:
            vals = {
                "user_id": self.test_user_id,
                "role_id": line["role_id"][0],
            }
            if line.get("date_from"):
                vals["date_from"] = line["date_from"]
            if line.get("date_to"):
                vals["date_to"] = line["date_to"]
            self.admin.create("res.users.role.line", vals)
        if self._original_role_lines:
            self.admin.execute_kw(
                "res.users",
                "set_groups_from_roles",
                [[self.test_user_id]],
                {},
            )
            self._ensure_internal_user(self.test_user_id)

    def assign_single_role(self, role_id: int) -> None:
        assert self.test_user_id is not None
        line_ids = self.admin.search(
            "res.users.role.line", [("user_id", "=", self.test_user_id)]
        )
        if line_ids:
            self.admin.unlink("res.users.role.line", line_ids)
        self.admin.create(
            "res.users.role.line",
            {"user_id": self.test_user_id, "role_id": role_id},
        )
        self.admin.execute_kw(
            "res.users",
            "set_groups_from_roles",
            [[self.test_user_id]],
            {},
        )
        self._ensure_internal_user(self.test_user_id)

    def connect_as_tester(self, url: str, db: str, protocol: str) -> OdooRPCClient:
        client = OdooRPCClient(
            url, db, self.test_login, self.test_password, protocol=protocol
        )
        client.authenticate()
        return client
