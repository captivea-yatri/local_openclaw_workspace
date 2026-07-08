"""Assign res.users.role to a dedicated test user (base_user_role pattern)."""
from __future__ import annotations

from .client import OdooRPCClient

CMD_CLEAR = 5

TEST_USER_LOGIN = "feature_matrix_tester"
TEST_USER_NAME = "Feature Matrix RPC Tester"
TEST_USER_PASSWORD = "feature_matrix_test"

BASE_GROUP_USER_XMLID = ("base", "group_user")


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

    def _base_group_user_id(self) -> int:
        rows = self.admin.search(
            "ir.model.data",
            [("module", "=", BASE_GROUP_USER_XMLID[0]), ("name", "=", BASE_GROUP_USER_XMLID[1])],
            limit=1,
        )
        if not rows:
            raise RuntimeError("base.group_user not found in ir.model.data")
        return self.admin.read("ir.model.data", rows, ["res_id"])[0]["res_id"]

    def _ensure_internal_user(self, user_id: int) -> None:
        """Force internal (employee) user — never portal/external (share=True)."""
        group_user_id = self._base_group_user_id()
        self.admin.write(
            "res.users",
            [user_id],
            {
                "share": False,
                "group_ids": [(4, group_user_id)],
            },
        )
        user = self.admin.read("res.users", [user_id], ["share", "login"])[0]
        if user.get("share"):
            raise RuntimeError(
                f"Test user {user.get('login')!r} is still portal/external (share=True)"
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
        }
        if existing:
            user_id = existing[0]
            self.admin.write("res.users", [user_id], vals)
        else:
            user_id = self.admin.create(
                "res.users",
                {
                    "name": TEST_USER_NAME,
                    "login": self.test_login,
                    "group_ids": [(6, 0, [group_user_id])],
                    **vals,
                },
            )
        self._ensure_internal_user(user_id)
        self.test_user_id = user_id
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

    def connect_as_tester(self, url: str, db: str, protocol: str) -> OdooRPCClient:
        client = OdooRPCClient(
            url, db, self.test_login, self.test_password, protocol=protocol
        )
        client.authenticate()
        return client
