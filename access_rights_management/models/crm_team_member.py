# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class CrmTeamMember(models.Model):
    _inherit = 'crm.team.member'

    crm_team_id = fields.Many2one('crm.team', string='Sales Team', group_expand='_read_group_expand_full',
        default=False,
        check_company=False, index=True, ondelete="cascade", required=True)