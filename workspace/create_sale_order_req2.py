#!/usr/bin/env python3
import os, sys, json, requests

def rpc(service, method, args):
    url = os.getenv('ODOO_URL').rstrip('/') + '/jsonrpc'
    payload = {
        'jsonrpc': '2.0',
        'method': 'call',
        'params': {
            'service': service,
            'method': method,
            'args': args,
        },
        'id': 1,
    }
    resp = requests.post(url, json=payload, verify=False)
    resp.raise_for_status()
    data = resp.json()
    if 'error' in data:
        raise Exception(data['error'])
    return data.get('result')

def execute_kw(db, uid, pwd, model, method, args=None, kwargs=None):
    if args is None:
        args = []
    if kwargs is None:
        kwargs = {}
    return rpc('object', 'execute_kw', [db, uid, pwd, model, method, args, kwargs])

def main():
    url = os.getenv('ODOO_URL')
    db = os.getenv('ODOO_DB')
    user = os.getenv('ODOO_USER')
    pwd = os.getenv('ODOO_PASSWORD')
    if not all([url, db, user, pwd]):
        sys.stderr.write('Missing ODOO env vars\n')
        sys.exit(1)
    uid = rpc('common', 'login', [db, user, pwd])
    if not uid:
        sys.stderr.write('Login failed\n')
        sys.exit(1)
    # product
    product_name = 'Test Service'
    prod_ids = execute_kw(db, uid, pwd, 'product.product', 'search', [ [('name', '=', product_name)], ], {'limit': 1})
    if prod_ids:
        prod_id = prod_ids[0]
    else:
        prod_id = execute_kw(db, uid, pwd, 'product.product', 'create', [{
            'name': product_name,
            'type': 'service',
            'list_price': 100.0,
            'service_tracking': 'task_global_project',
        }])
        print(f'Created product id {prod_id}')
    # partner
    email = 'demo@example.com'
    partner_ids = execute_kw(db, uid, pwd, 'res.partner', 'search', [ [('email', '=', email)], ], {'limit': 1})
    if partner_ids:
        partner_id = partner_ids[0]
    else:
        partner_id = execute_kw(db, uid, pwd, 'res.partner', 'create', [{
            'name': 'Demo Customer',
            'email': email,
        }])
        print(f'Created partner id {partner_id}')
    # sale order
    order_vals = {
        'partner_id': partner_id,
        'partner_invoice_id': partner_id,
        'partner_shipping_id': partner_id,
        'order_line': [(0, 0, {
            'product_id': prod_id,
            'product_uom_qty': 1,
            'price_unit': 100.0,
        })],
    }
    order_id = execute_kw(db, uid, pwd, 'sale.order', 'create', [order_vals])
    print(f'Sale order created id {order_id}')
    # confirm
    execute_kw(db, uid, pwd, 'sale.order', 'action_confirm', [[order_id]])
    print('Sale order confirmed')

if __name__ == '__main__':
    main()
