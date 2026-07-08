# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    ocean_person_id = fields.Char(
        string="Ocean Person ID",
        copy=False,
        index=True,
        help="Ocean.io person identifier used to avoid duplicate lead imports.",
    )
