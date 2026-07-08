# -*- coding: utf-8 -*-
"""Apollo Connector – background synchronization.

This module pulls contacts from Apollo.io via its REST API and upserts them
into Odoo CRM ``crm.lead`` records.  The sync can be triggered manually
through a wizard or automatically via a cron job (default every 10 minutes).

Configuration (stored in ``ir.config_parameter``):
* ``apollo_connector.api_key`` – Apollo.io API token (required).
* ``apollo_connector.base_url`` – Base URL for the Apollo API; defaults to
  ``https://api.apollo.io/v1``.
"""

import logging
from odoo import api, models
from odoo.exceptions import UserError
import requests

_logger = logging.getLogger(__name__)


class ApolloSync(models.TransientModel):
    """Transient model that runs the synchronization.

    It does not store any persistent data; it only contains the ``action_sync``
    method that the cron and wizard invoke.
    """

    _name = "apollo.sync"
    _description = "Apollo Synchronization"

    @api.model
    def _get_config(self):
        """Retrieve API key and base URL from system parameters."""
        icp = self.env["ir.config_parameter"].sudo()
        api_key = icp.get_param("apollo_connector.api_key")
        base_url = icp.get_param("apollo_connector.base_url") or "https://api.apollo.io/v1"
        if not api_key:
            raise UserError(
                "Apollo API key is not configured. Please set it in the "
                "Apollo Sync settings (System Parameters)."
            )
        return api_key, base_url.rstrip('/')

    def _fetch_contacts(self, api_key, base_url, page=1, per_page=200):
        """Yield contacts from Apollo page‑by‑page.

        Apollo caps a page at 200 items.  We keep requesting until the
        ``contacts`` list is empty or the ``total_pages`` limit is reached.
        """
        headers = {"Authorization": f"Bearer {api_key}"}
        while True:
            resp = requests.get(
                f"{base_url}/contacts",
                headers=headers,
                params={"page": page, "per_page": per_page},
                timeout=30,
            )
            if resp.status_code != 200:
                _logger.error(
                    "Apollo API request failed %s – %s", resp.status_code, resp.text
                )
                raise UserError(
                    f"Apollo API error {resp.status_code}: {resp.text}"
                )
            data = resp.json()
            contacts = data.get("contacts", [])
            if not contacts:
                break
            for contact in contacts:
                yield contact
            page += 1
            if page > data.get("total_pages", page):
                break

    def _upsert_contact(self, contact):
        """Create or update a ``crm.lead`` from an Apollo contact.

        * ``x_apollo_id`` stores the Apollo contact ID for idempotent upserts.
        * Minimal field mapping – extend as needed.
        """
        Lead = self.env["crm.lead"].sudo()
        email = contact.get("email")
        if not email:
            return  # Odoo lead requires an email address
        apollo_id = str(contact.get("id"))
        # Prefer existing lead by Apollo ID, fall back to email match
        domain = []
        if apollo_id:
            domain.append(["x_apollo_id", "=", apollo_id])
        else:
            domain.append(["email_from", "=", email])
        existing = Lead.search(domain, limit=1)

        vals = {
            "name": f"{contact.get('first_name','')} {contact.get('last_name','')}",
            "email_from": email,
            "phone": contact.get("phone"),
            "x_apollo_id": apollo_id,
            "description": contact.get("profile_url", ""),
        }
        if existing:
            existing.write(vals)
            _logger.info(
                "Updated lead %s (id %s) from Apollo contact %s",
                existing.name,
                existing.id,
                apollo_id,
            )
        else:
            new_lead = Lead.create(vals)
            _logger.info(
                "Created lead %s (id %s) from Apollo contact %s",
                new_lead.name,
                new_lead.id,
                apollo_id,
            )

    def action_sync(self):
        """Entry point for cron and wizard – runs the full sync process."""
        api_key, base_url = self._get_config()
        total = 0
        for contact in self._fetch_contacts(api_key, base_url):
            self._upsert_contact(contact)
            total += 1
        _logger.info("Apollo sync finished – processed %d contacts", total)
        return True
