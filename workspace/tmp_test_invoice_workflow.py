#!/usr/bin/env python3
import os, sys, datetime
from dateutil import parser as dt_parser
import odoorpc

def get_odoo():
    url = os.getenv('ODOO_URL')
    db = os.getenv('ODOO_DB')
    user = os.getenv('ODOO_USER')
    pwd = os.getenv('ODOO_PASSWORD')
    if not all([url, db, user, pwd]):
        sys.stderr.write('[ERROR] Missing ODOO_* env vars\n')
        sys.exit(1)
    url = url.rstrip('/')
    proto, host = url.split('://')
    odoo = odoorpc.ODOO(host, protocol='jsonrpc+ssl', port=443, version='19.0')
    odoo.login(db, user, pwd)
    return odoo

def main():
    if len(sys.argv) != 2:
        print('Usage: script.py <INVOICE_ID>')
        sys.exit(1)
    inv_id = int(sys.argv[1])
    odoo = get_odoo()
    Invoice = odoo.env['account.move']
    inv_data = Invoice.read(inv_id, ['partner_id', 'invoice_date', 'invoice_date_due', 'amount_total', 'amount_residual'])
    # odoorpc returns a list of dicts for many2one reads
    inv = inv_data[0] if isinstance(inv_data, list) else inv_data
    partner_id = inv['partner_id'][0]
    Partner = odoo.env['res.partner']
    partner_data = Partner.read(partner_id, ['email'])
    partner = partner_data[0] if isinstance(partner_data, list) else partner_data
    partner_email = partner['email']
    print(f'Invoice {inv_id} belongs to partner {partner_email} (id {partner_id})')
    # Project name - use invoice id
    project_name = f'Project_{inv_id}'
    Project = odoo.env['project.project']
    proj_ids = Project.search([('name', '=', project_name), ('partner_id', '=', partner_id)])
    if proj_ids:
        project_id = proj_ids[0]
        print(f'Found existing project {project_name} (id {project_id})')
    else:
        # Include the signatory dropdown field (assumed technical name)
        project_vals = {
            'name': project_name,
            'partner_id': partner_id,
            'signatory_progress_report_partner_id': partner_id,
        }
        project_id = Project.create(project_vals)
        print(f'Created project {project_name} (id {project_id}) with signatory field set')
    # Set status/colour based on due date
    today = datetime.date.today()
    due_date = dt_parser.parse(inv['invoice_date_due']).date()
    days_late = (today - due_date).days
    if days_late < -5:
        colour = 'green'
        stage_name = 'Live (On‑going customization)'
    elif -5 <= days_late <= 0:
        colour = 'yellow'
        stage_name = 'Live (Support)'
    else:
        colour = 'red'
        stage_name = 'On Hold (Live)'
    Stage = odoo.env['project.task.type']
    stage_ids = Stage.search([('name', '=', stage_name)], limit=1)
    stage_id = stage_ids[0] if stage_ids else False
    colour_map = {'green': 2, 'yellow': 5, 'red': 1}
    # NOTE: Project status is handled independently of colour logic.
    # The status can be set elsewhere; we do not set it here.
    status_id = False  # placeholder – no automatic status assignment
    # Try to set stage, colour, and status; fall back gracefully
    try:
        write_vals = {'color': colour_map[colour]}
        if stage_id:
            write_vals['stage_id'] = stage_id
        # status_id is intentionally not written; status is managed separately.
        Project.write(project_id, write_vals)
        print(f'Set project colour {colour}, stage "{stage_name}" (days late {days_late})')
    except Exception as e:
        # Fallback to colour only
        try:
            Project.write(project_id, {'color': colour_map[colour]})
            print(f'Set project colour {colour} (stage unchanged) – error: {e}')
        except Exception as e2:
            print(f'Failed to set colour/state: {e2}')
    # Grant portal access
    try:
        Partner.action_grant_portal_access([partner_id])
        print('Portal access granted.')
    except Exception as e:
        print(f'Portal access error (method may differ): {e}')
    # Refresh domain calculation
    try:
        # Use the correct button name as requested (plural)
        Project.refresh_project_domain_calculations(project_id)
        print('Domain calculation refreshed via refresh_project_domain_calculations.')
    except Exception as e:
        print(f'Domain refresh error: {e}')
    # Generate a simple progress report (optional)
    try:
        Phase = odoo.env['project.project.phase']
        phase_ids = Phase.search([], limit=1)
        phase_id = phase_ids[0] if phase_ids else None
        if phase_id:
            wiz = odoo.env['project.project.progress.report']
            wiz_id = wiz.create({'project_id': project_id, 'phase_id': phase_id})
            report = wiz.print_report(wiz_id)
            att = odoo.env['ir.attachment'].read(report, ['datas', 'name'])[0]
            data = att['datas']
            fname = att['name']
            out_path = f'/home/captivea/.openclaw/workspace/{fname}'
            with open(out_path, 'wb') as f:
                f.write(data.decode('base64'))
            print(f'Progress report saved to {out_path}')
    except Exception as e:
        print(f'Progress report error: {e}')
    # Run optional steps (review, test, feedback, plan)
    # Production Review
    try:
        ProdReview = odoo.env['production.review']
        rev_id = ProdReview.create({'project_id': project_id, 'date': datetime.date.today().isoformat()})
        print(f'Production Review created id {rev_id}')
    except Exception as e:
        print(f'Production Review error: {e}')
    # Test Session (assign to partner email user)
    try:
        User = odoo.env['res.users']
        user_ids = User.search([('login', '=', partner_email)], limit=1)
        if user_ids:
            Test = odoo.env['project.test.session']
            sess_id = Test.create({'project_id': project_id, 'assigned_user_id': user_ids[0], 'signatory_id': user_ids[0]})
            Test.button_initialize(sess_id)
            print(f'Test Session initialised id {sess_id}')
        else:
            print('No Odoo user matches partner email, skipping test session')
    except Exception as e:
        print(f'Test Session error: {e}')
    # Feedback wizard
    try:
        Feedback = odoo.env['project.feedback']
        fb_id = Feedback.create({'project_id': project_id})
        print(f'Feedback wizard opened id {fb_id}')
    except Exception as e:
        print(f'Feedback error: {e}')
    # Update planning
    # Attempt to run the server action with the known numeric ID 3980
    try:
        ServerAction = odoo.env['ir.actions.server']
        # Directly call run; if the action does not exist Odoo will raise an error
        ServerAction.run(3980, {'project_id': project_id})
        print('Project planning updated via server action 3980.')
    except Exception as e:
        print(f'Planning update error (server action 3980 failed): {e}')
if __name__ == '__main__':
    main()
