from odoo import models, fields


class HelpdeskTeam(models.Model):
    _inherit = "helpdesk.team"

    supervisor_ids = fields.Many2many('res.users', 'rel_supervisor_users', 'user_id', 'supervisor', string='Supervisors')
    creator_ids = fields.Many2many('res.users', 'rel_creator_users', 'user_id', 'creator', string='Creators')
    member_ids = fields.Many2many('res.users', string='Team Members', domain=lambda self: [
        '|', ('groups_id', 'in', self.env.ref('access_rights_management.show_helpdesk').id),
        ('groups_id', 'in', self.env.ref('helpdesk.group_helpdesk_user').id)],
                                  default=lambda self: self.env.user, required=True)
    create_activity = fields.Boolean('Create an activity')
