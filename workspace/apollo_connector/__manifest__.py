{
    "name": "Apollo Connector for Odoo 19",
    "version": "0.1.0",
    "author": "OpenAI Assistant",
    "website": "https://github.com/openclaw",
    "category": "Connector",
    "depends": ["base", "crm"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "wizard/apollo_sync_wizard_view.xml"
    ],
    "installable": true,
    "application": false,
    "license": "LGPL-3",
    "description": "Synchronises contacts from Apollo.io into Odoo CRM leads.\n\n* Pulls contacts via Apollo REST API\n* Creates or updates `crm.lead` records\n* Stores Apollo contact ID on a hidden custom field `x_apollo_id`\n* Runs automatically every 10 minutes via cron\n* Provides a manual wizard to trigger a sync on demand"
}