{
    "name": "Apollo.io Connector",
    "summary": "Apollo.io authentication, people enrichment and contact search for Odoo",
    "version": "19.0.3.2.0",
    "category": "Sales/CRM",
    "author": "Captivea",
    "maintainer": "Captivea",
    "website": "https://www.captivea.com/",
    "description": """
Apollo.io Integration
=====================

* Store Apollo API credentials per company.
* Authenticate requests with the ``x-api-key`` header.
* People Enrichment (POST /people/match) to enrich contacts.
* Contact Search (GET /contacts/search) to find contacts in Apollo.
""",
    "depends": ["base", "contacts"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "views/apollo_instance_views.xml",
        "views/apollo_people_enrichment_views.xml",
        "views/apollo_contact_search_views.xml",
        "views/res_partner_views.xml",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
