# -*- coding: utf-8 -*-
from odoo import fields, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    apollo_person_id = fields.Char(
        string="Apollo Person ID",
        copy=False,
        index=True,
        help="Apollo.io person identifier used to avoid duplicate lead imports.",
    )
