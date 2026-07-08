{
    "name": "Apollo.io Connector",
    "summary": "Apollo.io authentication, enrichment, and CRM lead generation",
    "version": "19.0.4.0.0",
    "category": "Sales/CRM",
    "author": "Captivea",
    "maintainer": "Captivea",
    "website": "https://www.captivea.com/",
    "description": """
Apollo.io Integration
=====================

* Store Apollo API credentials per company.
* Authenticate requests with the ``x-api-key`` header.
* People Enrichment (POST /people/match) to enrich contacts with Apollo data.
* Lead Prospecting: search Apollo (POST /mixed_people/api_search), bulk enrich
  (POST /people/bulk_match), and create CRM leads in Odoo.
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
        "views/apollo_people_enrichment_views.xml",
        "views/apollo_lead_prospect_views.xml",
        "views/apollo_instance_views.xml",
        "views/res_partner_views.xml",
        "views/crm_lead_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
