# -*- coding: utf-8 -*-
from odoo import fields, models


class OceanWebhookLog(models.Model):
    _name = "ocean.webhook.log"
    _description = "Ocean.io Webhook Log"
    _order = "id desc"

    instance_id = fields.Many2one("ocean.instance", ondelete="cascade")
    webhook_token = fields.Char(string="Token Received", readonly=True)
    payload_type = fields.Selection(
        [
            ("unknown", "Unknown"),
            ("ping", "Ping Test"),
            ("test", "Local Test"),
            ("reveal_emails", "Reveal Emails"),
            ("reveal_phones", "Reveal Phones"),
            ("enrich_companies", "Enrich Companies"),
            ("enrich_people", "Enrich People"),
            ("enrich_person", "Enrich Person"),
        ],
        default="unknown",
        readonly=True,
    )
    state = fields.Selection(
        [
            ("received", "Received"),
            ("processed", "Processed"),
            ("error", "Error"),
        ],
        default="received",
        readonly=True,
    )
    http_status = fields.Integer(string="HTTP Status", readonly=True)
    message = fields.Char(readonly=True)
    payload_json = fields.Text(string="Payload", readonly=True)
    records_updated = fields.Integer(readonly=True)
