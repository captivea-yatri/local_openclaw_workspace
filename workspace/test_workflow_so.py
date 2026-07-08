#!/usr/bin/env python3
import os, json, sys, datetime
import odoorpc, ssl

# Load credentials from file
with open('odoo_credentials.json') as f:
    cred = json.load(f)
url = cred['url'].rstrip('/')
host = url.split('://')[1]
db = cred['db']
user = cred['username']
pwd = cred['password']

# Connect
common = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
uid = common.login(db, user, pwd)
if not uid:
    print(json.dumps({'error':'auth failed'}))
    sys.exit(1)
models = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
models.login(db, user, pwd)

so_id = 6286
log = []

def add(step, status, detail=''):
    log.append({'step':step,'status':status,'detail':detail})

# Check sales order exists
so = models.env['sale.order'].search_read([('id','=',so_id)])
if not so:
    add('load_so','FAIL',f'SO {so_id} not found')
    print(json.dumps({'log':log},indent=2))
    sys.exit(0)
add('load_so','PASS',f'Found SO {so_id}')
so = so[0]
partner_id = so['partner_id'][0]
# Ensure project exists (auto project should be linked via field project_id maybe)
project_ids = models.env['project.project'].search([('partner_id','=',partner_id)])
if not project_ids:
    add('find_project','FAIL','No project linked to partner')
else:
    project_id = project_ids[0]
    add('find_project','PASS',f'project_id={project_id}')
    # Simple status change example
    try:
        models.env['project.project'].write(project_id, {'color':5})
        add('set_colour','PASS','Set colour to yellow')
    except Exception as e:
        add('set_colour','FAIL',str(e))

print(json.dumps({'log':log},indent=2))
