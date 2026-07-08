from odoo import models, api, fields


class CrmTeam(models.Model):
    _inherit = "crm.team"

    def _add_members_to_favorites(self):
        super(CrmTeam, self)._add_members_to_favorites()
        for team in self:
            for user in team.favorite_user_ids:
                if user not in team.member_ids:
                    team.favorite_user_ids = [(3, user.id)]


class Crmlead(models.Model):
    _inherit = "crm.lead"

    x_studio_second_salesperson = fields.Many2one('res.users')
