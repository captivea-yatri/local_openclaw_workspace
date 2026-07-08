import xmlrpc.client, json, sys, traceback

# Credentials (user supplied)
url = 'https://staging-odoo19-captivea.odoo.com'
db = 'captivea-staging-odoo19-31833465'
username = 'baholimalala.razakamanarivo@captivea.com'
password = 'a'

common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})
if not uid:
    print(json.dumps({'error':'Authentication failed'}))
    sys.exit(1)

obj = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')

def safe_rpc(method, *args, **kwargs):
    try:
        return obj.execute_kw(db, uid, password, *args, **kwargs)
    except xmlrpc.client.Fault as f:
        return {'__fault__': str(f)}
    except Exception as e:
        return {'__error__': str(e)}

# Define test matrix: for each model specify expected allowed ops (set)
# Ops: create, read, write, unlink, export
# For simplicity, we treat 'read' as search (allow empty list) and 'read_one' as read specific id.

test_plan = {
    # Contacts – read all, edit allowed only for some (we just test edit on a record we can read)
    'res.partner': {'allow': {'read','create','write','unlink'}},
    # Sales – read only via smart button (we test read on sale.order with partner filter)
    'sale.order': {'allow': {'read'}},
    # Project – read limited
    'project.project': {'allow': {'read'}},
    # Timesheet – full create/read/write for own and team (we test create/read/write)
    'hr.timesheet': {'allow': {'create','read','write','unlink'}},
    # Helpdesk – create/read own, edit if in team (we test create/read)
    'helpdesk.ticket': {'allow': {'create','read'}},
    # Attendance – check-in/out via UI only, no RPC CRUD (should be blocked)
    'hr.attendance': {'allow': set()},
    # Goals – read only own
    'hr.goal': {'allow': {'read'}},
    # Challenges – read only
    'hr.challenge': {'allow': {'read'}},
    # Employee public – read only via hr.employee.public model (if exists)
    'hr.employee.public': {'allow': {'read'}},
    # Restricted modules – all ops blocked
    'crm.lead': {'allow': set()},
    'account.move': {'allow': set()},
    'purchase.order': {'allow': set()},
    'account.asset': {'allow': set()},
    'website.page': {'allow': set()},
    'marketing.campaign': {'allow': set()},
    'mail.mass_mailing': {'allow': set()},
    'social.post': {'allow': set()},
    'hr.recruitment.stage': {'allow': set()},
}

report = {
    'executive_summary': {},
    'module_results': {},
    'final_verdict': 'UNKNOWN'
}

counters = {'total':0,'passed':0,'failed':0,'unexpected_allowed':0,'blocked':0}

for model, spec in test_plan.items():
    res = {'model': model, 'operations': {}}
    # READ test – search (limit 1)
    counters['total']+=1
    read = safe_rpc('search', model, [[]], {'limit':1})
    if isinstance(read, dict) and ('__fault__' in read or '__error__' in read):
        res['operations']['read'] = {'status':'blocked','detail':read}
        counters['blocked']+=1
    else:
        res['operations']['read'] = {'status':'allowed','ids':read}
        counters['passed']+=1
    # CREATE test – minimal vals
    counters['total']+=1
    # get fields to choose a required char or fallback name
    fields = safe_rpc('fields_get', model, [], {'attributes':['type','required']})
    if isinstance(fields, dict) and ('__fault__' in fields or '__error__' in fields):
        create_vals = {'name':'test'}
    else:
        req_char = None
        for f,m in fields.items():
            if m.get('required') and m.get('type')=='char':
                req_char = f
                break
        if not req_char and 'name' in fields:
            req_char = 'name'
        create_vals = {req_char:'test'} if req_char else {'name':'test'}
    create = safe_rpc('create', model, [create_vals])
    if isinstance(create, dict) and ('__fault__' in create or '__error__' in create):
        res['operations']['create'] = {'status':'blocked','detail':create}
        counters['blocked']+=1
        new_id = None
    else:
        res['operations']['create'] = {'status':'allowed','id':create}
        counters['passed']+=1
        new_id = create
    # WRITE test – attempt on created record if any, else on first read id or dummy
    counters['total']+=1
    if new_id:
        write = safe_rpc('write', model, [[new_id],{'name':'updated'}])
    else:
        target = read[0] if isinstance(read, list) and read else 0
        write = safe_rpc('write', model, [[target],{'name':'shouldfail'}])
    if isinstance(write, dict) and ('__fault__' in write or '__error__' in write):
        res['operations']['write'] = {'status':'blocked','detail':write}
        counters['blocked']+=1
    else:
        # if operation succeeded unexpectedly for a model expected blocked
        if 'write' not in spec['allow']:
            res['operations']['write'] = {'status':'unexpectedly_allowed'}
            counters['unexpected_allowed']+=1
        else:
            res['operations']['write'] = {'status':'allowed'}
            counters['passed']+=1
    # UNLINK test – delete created record if any, else attempt delete on read id
    counters['total']+=1
    if new_id:
        unlink = safe_rpc('unlink', model, [[new_id]])
    else:
        target = read[0] if isinstance(read, list) and read else 0
        unlink = safe_rpc('unlink', model, [[target]])
    if isinstance(unlink, dict) and ('__fault__' in unlink or '__error__' in unlink):
        res['operations']['unlink'] = {'status':'blocked','detail':unlink}
        counters['blocked']+=1
    else:
        if 'unlink' not in spec['allow']:
            res['operations']['unlink'] = {'status':'unexpectedly_allowed'}
            counters['unexpected_allowed']+=1
        else:
            res['operations']['unlink'] = {'status':'allowed'}
            counters['passed']+=1
    # EXPORT test if any read ids
    counters['total']+=1
    if isinstance(read, list) and read:
        try:
            export = obj.execute_kw(db, uid, password, model, 'export_data', [read, ['name']])
            res['operations']['export'] = {'status':'allowed'}
            counters['passed']+=1
        except Exception as e:
            res['operations']['export'] = {'status':'blocked','detail':str(e)}
            counters['blocked']+=1
    else:
        res['operations']['export'] = {'status':'no_records'}
    report['module_results'][model] = res

# Executive summary
report['executive_summary'] = {
    'total_test_cases': counters['total'],
    'passed': counters['passed'],
    'blocked': counters['blocked'],
    'unexpected_allowed': counters['unexpected_allowed'],
    'final_posture': 'PARTIALLY SECURE' if counters['unexpected_allowed']>0 else 'SECURE'
}

# Final verdict based on any unexpected allowed or critical failures (none coded)
report['final_verdict'] = 'PARTIALLY SECURE' if counters['unexpected_allowed']>0 else 'SECURE'

print(json.dumps(report, indent=2, default=str))
