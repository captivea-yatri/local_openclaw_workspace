from odoo import models, fields, api

class RoleAudit(models.Model):
    """Utility model to discover Odoo groups (roles) assigned to a user and
    trigger the appropriate QA/security test suite.
    
    The model does NOT perform the tests itself – it merely returns the list
    of groups for the supplied user ID. External automation (e.g., a Python
    script or a sub‑agent) can consume this information and invoke the matching
    test suite (e.g., `team_director_test_suite.py`, `hybrid_user_test_suite.py`).
    """
    _name = "role.audit"
    _description = "Role audit helper"

    user_id = fields.Many2one('res.users', string='User', required=True)
    group_ids = fields.Many2many('res.groups', string='Groups', compute='_compute_groups')
    group_names = fields.Char(compute='_compute_group_names')

    @api.depends('user_id')
    def _compute_groups(self):
        for rec in self:
            rec.group_ids = rec.user_id.groups_id

    @api.depends('group_ids')
    def _compute_group_names(self):
        for rec in self:
            rec.group_names = ', '.join(rec.group_ids.mapped('name'))

    def get_roles(self):
        """Return a simple list of group XML IDs for the user.
        This method can be called via RPC:
            call('role.audit', 'get_roles', args=[[audit_id]])
        """
        self.ensure_one()
        return self.group_ids.mapped('xml_id')
