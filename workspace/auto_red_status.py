#!/usr/bin/env python3
"""
Automated red‑status updater
Runs through all projects, checks the most recent posted invoice of the partner,
and sets the project colour:
- red (1) if the invoice is past due
- yellow (5) if due within the next 5 days
- green (2) otherwise.
"""
import os, sys, datetime
from dateutil import parser as dt_parser
import odoorpc

def get_odoo():
    url = os.getenv('ODOO_URL')
    db = os.getenv('ODOO_DB')
    user = os.getenv('ODOO_USER')
    pwd = os.getenv('ODOO_PASSWORD')
    if not all([url, db, user, pwd]):
        sys.stderr.write('[ERROR] ODOO_* env vars missing\n')
        sys.exit(1)
    url = url.rstrip('/')
    host = url.split('://')[1]
    odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
    odoo.login(db, user, pwd)
    return odoo

def set_status(odoo, proj_id, partner_id):
    Invoice = odoo.env['account.move']
    today = datetime.date.today()
    inv_ids = Invoice.search([
        ('partner_id', '=', partner_id),
        ('move_type', '=', 'out_invoice'),
        ('state', '=', 'posted')
    ], order='invoice_date desc', limit=1)
    if not inv_ids:
        return  # nothing to base on
    inv = Invoice.read(inv_ids[0], ['invoice_date_due'])
    due = dt_parser.parse(inv['invoice_date_due']).date()
    days_late = (today - due).days
    colour = 2  # green default
    if days_late > 0:
        colour = 1  # red
    elif -5 <= days_late <= 0:
        colour = 5  # yellow
    odoo.env['project.project'].write(proj_id, {'color': colour})

def main():
    odoo = get_odoo()
    Project = odoo.env['project.project']
    proj_ids = Project.search([])
    for pid in proj_ids:
        proj = Project.read(pid, ['partner_id'])
        partner_id = proj['partner_id'][0] if proj['partner_id'] else None
        if partner_id:
            set_status(odoo, pid, partner_id)
    print(f'Updated {len(proj_ids)} projects')

if __name__ == '__main__':
    main()
