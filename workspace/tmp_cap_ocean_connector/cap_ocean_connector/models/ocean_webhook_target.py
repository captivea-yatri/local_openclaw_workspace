# -*- coding: utf-8 -*-
from odoo import fields, models


class OceanWebhookTarget(models.Model):
    _name = "ocean.webhook.target"
    _description = "Ocean.io pending webhook update target"
    _order = "id desc"

    instance_id = fields.Many2one("ocean.instance", required=True, ondelete="cascade")
    ocean_person_id = fields.Char(required=True, index=True)
    partner_id = fields.Many2one("res.partner", ondelete="cascade")
    lead_id = fields.Many2one("crm.lead", ondelete="cascade")
    target_type = fields.Selection(
        [("email", "Email"), ("phone", "Phone")],
        required=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "ocean_target_unique",
            "unique(instance_id, ocean_person_id, target_type)",
            "This Ocean person is already registered for this reveal type.",
        )
    ]
