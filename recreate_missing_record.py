import xmlrpc.client
import sys

url = 'https://8f83-2402-a00-152-5177-a71c-8ced-f122-5868.ngrok-free.app'
db = 'odoo19_captivea2'
login = 'admin1'
password = 'a'

print(f'Connecting to {url}...')
try:
    common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
    uid = common.authenticate(db, login, password, {})
    print(f'Authenticated. UID: {uid}')
except Exception as e:
    print(f'Authentication failed: {e}')
    sys.exit(1)

models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

# Find a partner to use (we'll use the first partner, or create a temporary one?)
try:
    partner_ids = models.execute_kw(db, uid, password, 'res.partner', 'search', [[], {'limit': 1}])
except Exception as e:
    print(f'Error searching for partner: {e}')
    sys.exit(1)

if not partner_ids:
    # create a temporary partner
    try:
        partner_id = models.execute_kw(db, uid, password, 'res.partner', 'create', [{'name': 'Test Partner for Activity'}])
        print(f'Created temporary partner id: {partner_id}')
        created_partner = True
    except Exception as e:
        print(f'Error creating partner: {e}')
        sys.exit(1)
else:
    partner_id = partner_ids[0]
    print(f'Using existing partner id: {partner_id}')
    created_partner = False

# Get an activity type id (we can use the todo type)
try:
    activity_type_ids = models.execute_kw(db, uid, password, 'mail.activity.type', 'search', [['name', '=', 'To Do']])
    if not activity_type_ids:
        activity_type_ids = models.execute_kw(db, uid, password, 'mail.activity.type', 'search', [])
except Exception as e:
    print(f'Error searching for activity type: {e}')
    sys.exit(1)

activity_type_id = activity_type_ids[0] if activity_type_ids else False
if not activity_type_id:
    print('No activity type found')
    sys.exit(1)
print(f'Using activity type id: {activity_type_id}')

# Create the activity
try:
    activity_id = models.execute_kw(db, uid, password, 'mail.activity', 'create', [{
        'res_model': 'res.partner',
        'res_id': partner_id,
        'user_id': uid,
        'summary': 'Test Activity for Missing Record Recreation',
        'activity_type_id': activity_type_id,
        'date_deadline': '2026-06-30',  # tomorrow
    }])
    print(f'Created activity id: {activity_id}')
except Exception as e:
    print(f'Error creating activity: {e}')
    sys.exit(1)

# Now delete it
try:
    models.execute_kw(db, uid, password, 'mail.activity', 'unlink', [[activity_id]])
    print(f'Deleted activity id: {activity_id}')
except Exception as e:
    print(f'Error deleting activity: {e}')
    sys.exit(1)

# Now try to read it -> should raise an exception
try:
    result = models.execute_kw(db, uid, password, 'mail.activity', 'read', [[activity_id]])
    print('ERROR: Activity still exists! This should not happen.')
    print(f'Result: {result}')
except Exception as e:
    print(f'Successfully reproduced Missing Record error: {e}')

# Optionally, clean up the temporary partner if we created one
if created_partner:
    try:
        models.execute_kw(db, uid, password, 'res.partner', 'unlink', [[partner_id]])
        print(f'Cleaned up temporary partner id: {partner_id}')
    except Exception as e:
        print(f'Error cleaning up partner: {e}')

print('Done.')
