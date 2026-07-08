# -*- coding: utf-8 -*-
import uuid


def post_init_hook(env):
    """Backfill webhook credentials and rebuild webhookUrl per Ocean.io docs."""
    instances = env["ocean.instance"].search([])
    icp = env["ir.config_parameter"].sudo()
    default_base = icp.get_param("web.base.url", "")
    dbname = env.cr.dbname
    for instance in instances:
        vals = {}
        if not instance.webhook_token:
            vals["webhook_token"] = str(uuid.uuid4())
        if not (instance.webhook_secret or "").strip():
            vals["webhook_secret"] = str(uuid.uuid4())
        if not instance.database and dbname:
            vals["database"] = dbname
        if not instance.public_base_url and default_base.startswith("https://"):
            vals["public_base_url"] = default_base.rstrip("/")
        if vals:
            instance.write(vals)
    for instance in instances.filtered("public_base_url"):
        base = instance.public_base_url.rstrip("/")
        if base != instance.public_base_url:
            instance.write({"public_base_url": base, "database": instance.database or dbname})
