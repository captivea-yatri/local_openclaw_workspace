{
    "name": "Lusha Connector",
    "summary": "Lusha API v3 authentication, enrichment, prospecting, and webhooks",
    "version": "19.0.1.0.0",
    "category": "Sales/CRM",
    "author": "Captivea",
    "maintainer": "Captivea",
    "website": "https://www.captivea.com/",
    "description": """
Lusha Integration
=================

* Store Lusha API credentials per company (``api_key`` header).
* Contact & company Search, Enrich, and Search-and-Enrich (V3).
* Prospecting, Lookalikes, Signals, and Filter discovery endpoints.
* Account usage, credits, and rate limits (GET /v3/account/usage).
* Webhook subscription management and inbound receiver at ``/webhooks/lusha``.
* CRM lead prospecting and contact enrichment wizards.
    """,
    "depends": [
        "base",
        "contacts",
        "crm",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/lusha_people_enrichment_views.xml",
        "views/lusha_company_enrichment_views.xml",
        "views/lusha_lead_prospect_views.xml",
        "views/lusha_instance_views.xml",
        "views/res_partner_views.xml",
        "views/crm_lead_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": True,
}
