#!/usr/bin/env python3
import os, sys
import odoorpc

def main():
    url = os.getenv('ODOO_URL')
    db = os.getenv('ODOO_DB')
    user = os.getenv('ODOO_USER')
    pwd = os.getenv('ODOO_PASSWORD')
    if not all([url, db, user, pwd]):
        sys.stderr.write('Missing ODOO env vars\n')
        sys.exit(1)
    host = url.rstrip('/')
    # split scheme
    host = host.split('://')[1]
    odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
    odoo.login(db, user, pwd)

    # Ensure service product exists
    Product = odoo.env['product.product']
    prod_ids = Product.search([('name', '=', 'Test Service')])
    if prod_ids:
        prod_id = prod_ids[0]
    else:
        prod_id = Product.create({
            'name': 'Test Service',
            'type': 'service',
            'list_price': 100.0,
            # field to auto‑create project when confirming a sale order
            'service_tracking': 'task_global_project',
        })
        print(f'Created product id {prod_id}')

    # Ensure partner exists
    Partner = odoo.env['res.partner']
    email = 'demo@example.com'
    partner_ids = Partner.search([('email', '=', email)])
    if partner_ids:
        partner_id = partner_ids[0]
    else:
        partner_id = Partner.create({'name': 'Demo Customer', 'email': email})
        print(f'Created partner id {partner_id}')

    # Create Sale Order
    SaleOrder = odoo.env['sale.order']
    order_id = SaleOrder.create({
        'partner_id': partner_id,
        'partner_invoice_id': partner_id,
        'partner_shipping_id': partner_id,
        'order_line': [(0, 0, {
            'product_id': prod_id,
            'product_uom_qty': 1,
            'price_unit': 100.0,
        })],
    })
    print(f'Sale order created id {order_id}')

    # Confirm the order (creates project because of service_tracking)
    SaleOrder.action_confirm([order_id])
    print('Sale order confirmed')

if __name__ == '__main__':
    main()
