{
    "name": "Ocean.io Connector",
    "summary": "Ocean.io authentication, search, enrichment, and CRM lead generation",
    "version": "19.0.1.10.0",
    "category": "Sales/CRM",
    "author": "Captivea",
    "maintainer": "Captivea",
    "website": "https://www.captivea.com/",
    "description": """
Ocean.io Integration
====================

* Store Ocean.io API tokens per company.
* Authenticate requests with the ``X-Api-Token`` header.
* People Lookup via ``POST /v2/lookup/people`` (LinkedIn / Ocean ID)
  and ``POST /v2/enrich/person`` (email, phone, name, company, reveal options).
* People Search (POST /v3/search/people) for lead prospecting and CRM import.
* Company Enrichment (POST /v2/enrich/companies) for account data.
* Reveal Emails (POST /v2/reveal/emails) for verified email addresses.
* Built-in Odoo webhook receiver at ``/webhooks/ocean?secret=...`` (Ocean.io docs) with logging.
    """,
    "depends": [
        "base",
        "contacts",
        "crm",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "post_init_hook": "post_init_hook",
    "data": [
        "security/ir.model.access.csv",
        "views/ocean_people_enrichment_views.xml",
        "views/ocean_lead_prospect_views.xml",
        "views/ocean_company_enrichment_views.xml",
        "views/ocean_webhook_log_views.xml",
        "views/ocean_instance_views.xml",
        "views/res_partner_views.xml",
        "views/crm_lead_views.xml",
    ],
    "images": [
        "static/description/icon.png",
        "static/description/banner.png",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
