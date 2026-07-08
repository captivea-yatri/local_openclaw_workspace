{
    "name": "User Public View",
    "summary": "Exposes a limited view of res.users (login, name) for non‑admin users",
    "version": "14.0.1.0.0",
    "author": "OpenAI",
    "website": "https://openclaw.ai",
    "license": "LGPL-3",
    "depends": ["base"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_users_public_view.xml"
    ],
    "installable": true,
    "application": false,
    "auto_install": false
}