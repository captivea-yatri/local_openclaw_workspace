# -*- coding: utf-8 -*-
"""Core sync logic for Ocean.io integration.

Provides:
* Push helpers (lead / contact → Ocean.io)
* Fetch helpers used by the wizard (Ocean.io → Odoo)
"""

from odoo import api, fields, models, _
import logging
import requests

_logger = logging.getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    """Settings screen – stores Ocean.io credentials."""
    _inherit = "res.config.settings"

    ocean_api_key = fields.Char(string="Ocean.io API Key")
    ocean_endpoint = fields.Char(
        string="Ocean.io Endpoint",
        default="https://api.ocean.io/v1/records"
    )

    @api.model
    def get_values(self):
        res = super().get_values()
        IrConfig = self.env["ir.config_parameter"].sudo()
        res.update(
            ocean_api_key=IrConfig.get_param("ocean.integration.api_key"),
            ocean_endpoint=IrConfig.get_param("ocean.integration.endpoint"),
        )
        return res

    @api.model
    def set_values(self):
        super().set_values()
        IrConfig = self.env["ir.config_parameter"].sudo()
        IrConfig.set_param(
            "ocean.integration.api_key", self.ocean_api_key or ""
        )
        IrConfig.set_param(
            "ocean.integration.endpoint",
            self.ocean_endpoint or "https://api.ocean.io/v1/records",
        )

class OceanSync(models.AbstractModel):
    """Utility methods for pushing and pulling data to/from Ocean.io."""
    _name = "ocean.sync"

    # -----------------------------------------------------------------
    # Credentials helpers
    # -----------------------------------------------------------------
    def _get_ocean_credentials(self):
        IrConfig = self.env["ir.config_parameter"].sudo()
        api_key = IrConfig.get_param("ocean.integration.api_key")
        endpoint = (
            IrConfig.get_param("ocean.integration.endpoint")
            or "https://api.ocean.io/v1/records"
        )
        return api_key, endpoint

    # -----------------------------------------------------------------
    # Push helpers (used by model hooks & cron)
    # -----------------------------------------------------------------
    def _push_record(self, payload):
        api_key, endpoint = self._get_ocean_credentials()
        if not api_key:
            _logger.warning("Ocean.io API key not configured – skipping sync")
            return False
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                endpoint, json=payload, headers=headers, timeout=10
            )
            response.raise_for_status()
            _logger.info("Successfully synced record to Ocean.io: %s", payload)
            return True
        except Exception as e:
            _logger.error("Failed to sync to Ocean.io: %s | payload=%s", e, payload)
            return False

    def sync_lead_to_ocean(self, lead):
        payload = {
            "external_id": f"lead_{lead.id}",
            "name": lead.name or "",
            "email": lead.email_from or "",
            "phone": lead.phone or "",
            "type": "lead",
            "source": "odoo",
        }
        return self._push_record(payload)

    def sync_contact_to_ocean(self, partner):
        payload = {
            "external_id": f"partner_{partner.id}",
            "name": partner.name or "",
            "email": partner.email or "",
            "phone": partner.phone or "",
            "type": "contact",
            "source": "odoo",
        }
        return self._push_record(payload)

    # -----------------------------------------------------------------
    # Fetch helpers – used by the wizard to import data from Ocean.io
    # -----------------------------------------------------------------
    def _fetch_and_sync_leads(self):
        api_key, endpoint = self._get_ocean_credentials()
        if not api_key:
            _logger.warning("Ocean.io API key not configured – cannot fetch leads")
            return 0
        url = f"{endpoint}?type=lead"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            _logger.error("Failed to fetch leads from Ocean.io: %s", e)
            return 0
        created = 0
        Lead = self.env["crm.lead"].sudo()
        for rec in data:
            name = rec.get("name")
            if not name:
                continue
            if not Lead.search([("name", "=", name)], limit=1):
                Lead.create(
                    {
                        "name": name,
                        "email_from": rec.get("email", ""),
                        "phone": rec.get("phone", ""),
                    }
                )
                created += 1
        _logger.info("Fetched %s new leads from Ocean.io", created)
        return created

    def _fetch_and_sync_contacts(self):
        api_key, endpoint = self._get_ocean_credentials()
        if not api_key:
            _logger.warning("Ocean.io API key not configured – cannot fetch contacts")
            return 0
        url = f"{endpoint}?type=contact"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            _logger.error("Failed to fetch contacts from Ocean.io: %s", e)
            return 0
        created = 0
        Partner = self.env["res.partner"].sudo()
        for rec in data:
            name = rec.get("name")
            if not name:
                continue
            if not Partner.search([("name", "=", name)], limit=1):
                Partner.create(
                    {
                        "name": name,
                        "email": rec.get("email", ""),
                        "phone": rec.get("phone", ""),
                    }
                )
                created += 1
        _logger.info("Fetched %s new contacts from Ocean.io", created)
        return created

class CrmLead(models.Model):
    """Extend crm.lead – push to Ocean.io on create/write."""
    _inherit = "crm.lead"

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        sync = self.env["ocean.sync"].sudo()
        for rec in records:
            sync.sync_lead_to_ocean(rec)
        return records

    def write(self, vals):
        res = super().write(vals)
        if vals:
            sync = self.env["ocean.sync"].sudo()
            for rec in self:
                sync.sync_lead_to_ocean(rec)
        return res

    def _cron_sync_all_leads(self):
        """Cron that pushes every lead to Ocean.io."""
        sync = self.env["ocean.sync"].sudo()
        for lead in self.search([]):
            sync.sync_lead_to_ocean(lead)

class ResPartner(models.Model):
    """Extend res.partner – push to Ocean.io on create/write."""
    _inherit = "res.partner"

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        sync = self.env["ocean.sync"].sudo()
        for p in partners:
            sync.sync_contact_to_ocean(p)
        return partners

    def write(self, vals):
        res = super().write(vals)
        if vals:
            sync = self.env["ocean.sync"].sudo()
            for p in self:
                sync.sync_contact_to_ocean(p)
        return res

    def _cron_sync_all_contacts(self):
        """Cron that pushes every contact to Ocean.io."""
        sync = self.env["ocean.sync"].sudo()
        for partner in self.search([]):
            sync.sync_contact_to_ocean(partner)
