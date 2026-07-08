#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for cap_account_intern_company_transection
Models covered:
 - account.move (account_move.py)
 - account.move.line (account_move.py)
 - account.account (account_account.py)
 - account.analytic.line (account_analytic_line.py)

Run inside: odoo-bin shell -d DB_NAME --no-http
"""

from odoo import Command, fields, SUPERUSER_ID

def _log(ok, label, detail=''):
    status = 'PASS' if ok else 'FAIL'
    msg = f'[{status}] {label}'
    if detail:
        msg += f' -> {detail}'
    print(msg)
    return ok

def _get_companies(env):
    companies = env['res.company'].search([], order='id')
    if len(companies) < 2:
        company_b = env['res.company'].create({'name': 'CAP Inter-Company Test Co B'})
        env['account.chart.template'].try_loading('generic_coa', company_b, install_demo=False)
        companies = env['res.company'].search([], order='id')
    return companies[0], companies[1]

def _get_product(env):
    product = env['product.product'].search([
        ('sale_ok', '=', True),
        ('type', '=', 'service'),
    ], limit=1)
    if not product:
        product = env['product.product'].create({
            'name': 'CAP Inter-Company Test Product',
            'type': 'service',
            'list_price': 100.0,
        })
    return product

def _create_out_invoice(env, company_a, partner_b, product):
    today = fields.Date.today()
    return env['account.move'].with_company(company_a).create({
        'move_type': 'out_invoice',
        'partner_id': partner_b.id,
        'invoice_date': today,
        'invoice_date_due': today,
        'invoice_payment_term_id': False,
        'invoice_line_ids': [Command.create({
            'product_id': product.id,
            'name': 'CAP inter-company workflow line',
            'quantity': 1.0,
            'price_unit': 450.0,
            'tax_ids': [Command.clear()],
        })],
    })

def test_cap_inter_company_workflow(env):
    env = env(su=True)
    passed = failed = 0
    def check(ok, label, detail=''):
        nonlocal passed, failed
        if _log(ok, label, detail):
            passed += 1
        else:
            failed += 1
        return ok
    print('=' * 80)
    print('CAP Inter-Company Transaction — workflow test')
    print('=' * 80)
    company_a, company_b = _get_companies(env)
    product = _get_product(env)
    print(f'Company A: {company_a.name} | Company B: {company_b.name}')
    # 1) res.company._find_company_from_partner
    found_company = env['res.company']._find_company_from_partner(company_b.partner_id.id)
    check(bool(found_company), 'res.company._find_company_from_partner', found_company.name if found_company else 'False')
    # 2) account.move.create -> auto generate_related_journal_entry
    out_invoice = _create_out_invoice(env, company_a, company_b.partner_id, product)
    check(out_invoice.is_internal_invoice is True, 'account.move.is_internal_invoice')
    check(out_invoice.inverse_move_type == 'in_invoice', 'account.move.inverse_move_type', out_invoice.inverse_move_type)
    check(bool(out_invoice.inter_comp_journal_entry_id), 'account.move.inter_comp_journal_entry_id set on create')
    in_invoice = out_invoice.inter_comp_journal_entry_id
    if in_invoice:
        check(in_invoice.move_type == 'in_invoice', 'related move move_type', in_invoice.move_type)
        check(in_invoice.company_id == company_b, 'related move company_id', in_invoice.company_id.name)
        check(in_invoice.partner_id == company_a.partner_id, 'related move partner_id', in_invoice.partner_id.name)
        check(in_invoice.inter_comp_journal_entry_id == out_invoice, 'bidirectional inter_comp_journal_entry_id')
        check(in_invoice.state == 'draft', 'related move state', in_invoice.state)
    # 3) account.move.line._inter_company_prepare_invoice_data_line
    if out_invoice.invoice_line_ids:
        line_vals = out_invoice.invoice_line_ids[0]._inter_company_prepare_invoice_data_line()
        check(isinstance(line_vals, dict), 'account.move.line._inter_company_prepare_invoice_data_line')
        check('name' in line_vals and 'price_unit' in line_vals, 'line vals keys', str(list(line_vals.keys())[:6]))
    # 4) account.move._inter_company_prepare_invoice
    prepared = out_invoice._inter_company_prepare_invoice('in_invoice')
    check(prepared.get('move_type') == 'in_invoice', 'account.move._inter_company_prepare_invoice move_type')
    check(prepared.get('partner_id') == company_a.partner_id.id, 'account.move._inter_company_prepare_invoice partner_id')
    # 5) account.move.write sync (ref, payment_reference)
    header_invoice = _create_out_invoice(env, company_a, company_b.partner_id, product)
    header_related = header_invoice.inter_comp_journal_entry_id
    new_ref = 'CAP-TEST-REF'
    new_pay_ref = 'CAP-TEST-PAY'
    header_invoice.write({'ref': new_ref, 'payment_reference': new_pay_ref})
    if header_related:
        check(header_related.ref == new_ref, 'write sync ref', header_related.ref)
        check(header_related.payment_reference == new_pay_ref, 'write sync payment_reference', header_related.payment_reference)
    # 6) action_post + due dates
    post_invoice = _create_out_invoice(env, company_a, company_b.partner_id, product)
    post_related = post_invoice.inter_comp_journal_entry_id
    post_invoice.action_post()
    check(post_invoice.state == 'posted', 'account.move.action_post source', post_invoice.state)
    if post_related:
        check(post_related.state == 'posted', 'account.move._post posts inter_comp_journal_entry_id', post_related.state)
        pr_lines = post_related.line_ids.filtered(lambda l: l.account_id.account_type in ('liability_payable', 'asset_receivable'))
        check(not pr_lines or all(l.date_maturity for l in pr_lines), 'account.move._ensure_due_dates_on_moves', f'{len(pr_lines)} payable/receivable lines checked')
    # 7) button_draft
    draft_invoice = _create_out_invoice(env, company_a, company_b.partner_id, product)
    draft_related = draft_invoice.inter_comp_journal_entry_id
    draft_invoice.action_post()
    draft_invoice.button_draft()
    check(draft_invoice.state == 'draft', 'account.move.button_draft source', draft_invoice.state)
    if draft_related:
        check(draft_related.state == 'draft', 'account.move.button_draft related', draft_related.state)
    # 8) button_cancel
    cancel_invoice = _create_out_invoice(env, company_a, company_b.partner_id, product)
    cancel_related = cancel_invoice.inter_comp_journal_entry_id
    cancel_invoice.action_post()
    cancel_invoice.button_cancel()
    check(cancel_invoice.state == 'cancel', 'account.move.button_cancel source', cancel_invoice.state)
    if cancel_related:
        check(cancel_related.state == 'cancel', 'account.move.button_cancel related', cancel_related.state)
    # 9) generate_related_journal_entry
    regen_invoice = _create_out_invoice(env, company_a, company_b.partner_id, product)
    regen_related = regen_invoice.inter_comp_journal_entry_id
    if regen_related:
        regen_related.unlink()
    regen_invoice.write({'inter_comp_journal_entry_id': False})
    regen_invoice.generate_related_journal_entry()
    check(bool(regen_invoice.inter_comp_journal_entry_id), 'account.move.generate_related_journal_entry')
    if regen_invoice.inter_comp_journal_entry_id:
        check(regen_invoice.inter_comp_journal_entry_id.inter_comp_journal_entry_id == regen_invoice, 'generate_related_journal_entry bidirectional link')
    # 10) _inter_company_create_invoices_data
    ic_invoice = _create_out_invoice(env, company_a, company_b.partner_id, product)
    ic_related = ic_invoice.inter_comp_journal_entry_id
    if ic_related:
        ic_related.unlink()
    ic_invoice.write({'inter_comp_journal_entry_id': False})
    created_moves = ic_invoice.with_user(SUPERUSER_ID).with_company(company_b)._inter_company_create_invoices_data()
    check(bool(created_moves), 'account.move._inter_company_create_invoices_data')
    if created_moves:
        check(created_moves.move_type == 'in_invoice', '_inter_company_create_invoices_data move_type')
    # 11) account.account._get_most_frequent_account_for_partner
    account_result = env['account.account'].with_context(from_inter_company_transaction=True)._get_most_frequent_account_for_partner(
        company_id=company_a.id,
        partner_id=company_b.partner_id.id,
        move_type='out_invoice',
    )
    check(account_result is False, 'account.account._get_most_frequent_account_for_partner returns False')
    # 12) account.analytic.line.subsidiary_invoice_id field exists
    check('subsidiary_invoice_id' in env['account.analytic.line']._fields, 'account.analytic.line.subsidiary_invoice_id field exists')
    analytic_line = env['account.analytic.line'].create({
        'name': 'CAP subsidiary test',
        'subsidiary_invoice_id': out_invoice.id,
    })
    check(analytic_line.subsidiary_invoice_id == out_invoice, 'account.analytic.line.subsidiary_invoice_id link')
    # 13) action_switch_invoice_into_refund_credit_note
    switch_invoice = _create_out_invoice(env, company_a, company_b.partner_id, product)
    if hasattr(switch_invoice, 'action_switch_invoice_into_refund_credit_note'):
        switch_invoice.action_switch_invoice_into_refund_credit_note()
        check(switch_invoice.move_type == 'out_refund', 'action_switch_invoice_into_refund_credit_note move_type')
        if switch_invoice.is_internal_invoice:
            check(switch_invoice.inverse_move_type == 'in_refund', 'inverse_move_type after switch', switch_invoice.inverse_move_type)
            check(bool(switch_invoice.inter_comp_journal_entry_id), 'inter_comp_journal_entry_id regenerated after switch')
            if switch_invoice.inter_comp_journal_entry_id:
                check(switch_invoice.inter_comp_journal_entry_id.move_type == 'in_refund', 'related move after switch')
    # 14) Non internal partner -> no related entry
    external_partner = env['res.partner'].create({'name': 'CAP External Partner'})
    external_invoice = env['account.move'].with_company(company_a).create({
        'move_type': 'out_invoice',
        'partner_id': external_partner.id,
        'invoice_line_ids': [Command.create({
            'product_id': product.id,
            'quantity': 1.0,
            'price_unit': 100.0,
            'tax_ids': [Command.clear()],
        })],
    })
    check(external_invoice.is_internal_invoice is False, 'external partner is_internal_invoice is False')
    check(not external_invoice.inter_comp_journal_entry_id, 'external partner has no inter_comp_journal_entry_id')
    print('=' * 80)
    print(f'Result: {passed} passed, {failed} failed')
    print('=' * 80)
    return failed == 0

if 'env' in globals():
    ok = test_cap_inter_company_workflow(env)
    if not ok:
        raise SystemExit(1)
