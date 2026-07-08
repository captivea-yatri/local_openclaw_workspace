#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script to reproduce the mail.activity Missing Record error.
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

    # Step 1: Find or create a test partner
    partner_name = 'Test Partner for Recreation'
    try:
        partner_ids = models.execute_kw(db, uid, password, 'res.partner', 'search', [[['name', '=', partner_name]]], limit=1)
    except Exception as e:
        print(f'Error searching for partner: {e}')
        sys.exit(1)

    if partner_ids:
        partner_id = partner_ids[0]
        print(f'Found existing partner id: {partner_id}')
    else:
        print(f'Creating partner: {partner_name}')
        try:
            partner_id = models.execute_kw(db, uid, password, 'res.partner', 'create', [{'name': partner_name}])
            print(f'Created partner id: {partner_id}')
        except Exception as e:
            print(f'Error creating partner: {e}')
            sys.exit(1)

    # Step 2: Get the activity type for "To Do" (or any generic type)
    # We'll use the mail.activity.data_todo activity type (standard To Do)
    try:
        act_type_ids = models.execute_kw(db, uid, password, 'ir.model.data', 'search_read', [[['model', '=', 'mail.activity.type'], ['name', '=', 'data_todo']]], fields=['res_id'], limit=1)
    except Exception as e:
        print(f'Error searching for activity type: {e}')
        sys.exit(1)

    if not act_type_ids:
        print('Could not find activity type "data_todo". Falling back to any activity type.')
        try:
            act_type_ids = models.execute_kw(db, uid, password, 'mail.activity.type', 'search', [], limit=1)
        except Exception as e:
            print(f'Error searching for any activity type: {e}')
            sys.exit(1)
        if not act_type_ids:
            print('No activity type found.')
            sys.exit(1)
        activity_type_id = act_type_ids[0]
    else:
        activity_type_id = act_type_ids[0]['res_id']
    print(f'Using activity type id: {activity_type_id}')

    # Step 3: Create a mail.activity for the partner
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

    # Step 4: Delete the activity
    try:
        models.execute_kw(db, uid, password, 'mail.activity', 'unlink', [[activity_id]])
        print(f'Deleted activity id: {activity_id}')
    except Exception as e:
        print(f'Error deleting activity: {e}')
        # We still try to read it to see if it exists
        pass

    # Step 5: Try to read the deleted activity -> should raise an exception
    try:
        result = models.execute_kw(db, uid, password, 'mail.activity', 'read', [[activity_id]])
        print('ERROR: Activity still exists! This should not happen.')
        print(f'Result: {result}')
        # Clean up if it still exists (though it shouldn't)
        try:
            models.execute_kw(db, uid, password, 'mail.activity', 'unlink', [[activity_id]])
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
    if not partner_ids:  # we created it
        try:
            models.execute_kw(db, uid, password, 'res.partner', 'unlink', [[partner_id]])
            print(f'Cleaned up temporary partner id: {partner_id}')
        except Exception as e:
            print(f'Error cleaning up partner: {e}')

    print('Done.')

if __name__ == '__main__':
    main()