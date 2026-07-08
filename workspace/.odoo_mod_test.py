#!/usr/bin/env python3
import sys, xmlrpc.client, urllib.parse
ODOO_URL = "https://staging-odoo19-captivea.odoo.com"
DB = "captivea-staging-odoo19-31833465"
USERNAME = "princy.randimbimanana@captivea.com"
PASSWORD = "a"
common_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/common')
object_url = urllib.parse.urljoin(ODOO_URL.rstrip('/') + '/', 'xmlrpc/2/object')
common = xmlrpc.client.ServerProxy(common_url)
uid = common.authenticate(DB, USERNAME, PASSWORD, {})
if not uid:
    sys.exit('auth fail')
print("Login successful.")
models = xmlrpc.client.ServerProxy(object_url)
module_ids = models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'search', [[('state','!=','uninstalled')]], {'limit':2000})
modules = models.execute_kw(DB, uid, PASSWORD, 'ir.module.module', 'read', [module_ids], {'fields':['name','state','shortdesc']})
for m in modules:
    print(f"{m['name']}: {m['state']} – {m.get('shortdesc','')}")
