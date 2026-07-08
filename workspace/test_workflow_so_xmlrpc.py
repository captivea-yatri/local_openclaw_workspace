#!/usr/bin/env python3
import json, sys, datetime, ssl, xmlrpc.client

# Load credentials
with open('odoo_credentials.json') as f:
    cred = json.load(f)
url = cred['url'].rstrip('/')
DB = cred['db']
USER = cred['username']
PASS = cred['password']

common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common", context=ssl._create_unverified_context())
uid = common.authenticate(DB, USER, PASS, {})
if not uid:
    print(json.dumps({'error':'auth failed'}))
    sys.exit(1)

models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object", context=ssl._create_unverified_context())

so_id = 6286
log = []

def add(step,status,detail=''):
    log.append({'step':step,'status':status,'detail':detail})

# Check sales order
so = models.execute_kw(DB, uid, PASS, 'sale.order', 'read', [[so_id]], {'fields':['partner_id']})
if not so:
    add('load_so','FAIL',f'SO {so_id} not found')
    print(json.dumps({'log':log},indent=2))
    sys.exit(0)
add('load_so','PASS',f'Found SO {so_id}')
partner_id = so[0].get('partner_id')[0]
# Find project linked via partner
proj_ids = models.execute_kw(DB, uid, PASS, 'project.project', 'search', [[('partner_id','=',partner_id)]], {'limit':1})
if not proj_ids:
    add('find_project','FAIL','No project for partner')
else:
    project_id = proj_ids[0]
    add('find_project','PASS',f'project_id={project_id}')
    # Set colour to yellow (5)
    try:
        models.execute_kw(DB, uid, PASS, 'project.project', 'write', [[project_id], {'color':5}])
        add('set_colour','PASS','Set colour to 5')
    except Exception as e:
        add('set_colour','FAIL',str(e))

print(json.dumps({'log':log},indent=2))
