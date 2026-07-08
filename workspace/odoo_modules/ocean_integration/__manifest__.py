{
    "name": "Ocean.io Integration",
    "summary": "Sync Odoo leads and contacts with Ocean.io",
    "version": "19.0.1.0.0",
    "author": "Your Name",
    "website": "https://github.com/your-org/odoo-ocean-integration",
    "category": "Tools",
    "depends": ["base", "crm"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "data/ir_cron.xml",
        "views/ocean_integration_views.xml",
        "views/ocean_fetch_wizard_view.xml"
    ],
    "installable": True,
    "application": False,
    "license": "LGPL-3"
}