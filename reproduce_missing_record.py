#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to reproduce the mail.activity Missing Record error by creating and deleting an activity.
"""

import sys
import xmlrpc.client

def main():
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

    # Helper function to call execute_kw
    def ek(model, method, args=None, kwargs=None):
        print(f"  Calling {model}.{method} with args={args}, kwargs={kwargs}")
        return models.execute_kw(db, uid, password, model, method, args or [], kwargs or {})

    # Step 1: Find or create a test partner
    partner_name = 'Test Partner for Recreation'
    try:
        # Search for partner by name
        domain = [['name', '=', partner_name]]
        partner_ids = ek('res.partner', 'search', [domain], {'limit': 1})
    except Exception as e:
        print(f'Error searching for partner: {e}')
        sys.exit(1)

    if partner_ids:
        partner_id = partner_ids[0]
        print(f'Found existing partner id: {partner_id}')
    else:
        print(f'Creating partner: {partner_name}')
        try:
            partner_id = ek('res.partner', 'create', [{'name': partner_name}])
            print(f'Created partner id: {partner_id}')
        except Exception as e:
            print(f'Error creating partner: {e}')
            sys.exit(1)

    # Step 2: Get an activity type (we'll use the first one we find)
    try:
        act_type_ids = ek('mail.activity.type', 'search', [], {'limit': 1})
    except Exception as e:
        print(f'Error searching for any activity type: {e}')
        sys.exit(1)
    if not act_type_ids:
        print('No activity type found.')
        sys.exit(1)
    activity_type_id = act_type_ids[0]
    print(f'Using activity type id: {activity_type_id}')

    # Step 3: Create a mail.activity for the partner
    try:
        activity_id = ek('mail.activity', 'create', [{
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

    # Step 4: Delete the activity
    try:
        ek('mail.activity', 'unlink', [[activity_id]])
        print(f'Deleted activity id: {activity_id}')
    except Exception as e:
        print(f'Error deleting activity: {e}')
        # We still try to read it to see if it exists
        pass

    # Step 5: Try to read the deleted activity -> should raise an exception
    try:
        result = ek('mail.activity', 'read', [[activity_id]])
        print('ERROR: Activity still exists! This should not happen.')
        print(f'Result: {result}')
        # Clean up if it still exists (though it shouldn't)
        try:
            ek('mail.activity', 'unlink', [[activity_id]])
        except:
            pass
    except Exception as e:
        print(f'Successfully reproduced Missing Record error: {e}')
        # Check if it's the expected Missing Record error
        if 'Missing Record' in str(e) or 'Record does not exist' in str(e):
            print('Confirmed: Missing Record error reproduced.')
        else:
            print('Note: The error is not exactly the Missing Record error, but the activity is gone.')

    # Step 6: Clean up the temporary partner if we created it
    # We don't know if we created it or found it, so we'll skip cleanup for now.
    print('Done.')

if __name__ == '__main__':
    main()