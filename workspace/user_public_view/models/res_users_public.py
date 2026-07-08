from odoo import models, fields

class ResUsersPublic(models.Model):
    """A lightweight proxy for res.users exposing only safe fields.
    This model is a SQL view that selects id, login, name from res_users.
    It is intended for non‑admin users to avoid leaking group memberships
    and other sensitive data.
    """
    _name = "res.users.public"
    _description = "Public view of users"
    _auto = False  # we will define a SQL view

    login = fields.Char(string="Login", readonly=True)
    name = fields.Char(string="Name", readonly=True)

    def init(self):
        # Drop and create the view when the module is (re)installed/updated.
        self.env.cr.execute("""
            DROP VIEW IF EXISTS res_users_public;
            CREATE OR REPLACE VIEW res_users_public AS
            SELECT id, login, name
            FROM res_users;
        """)