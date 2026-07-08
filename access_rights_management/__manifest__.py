# -*- coding: utf-8 -*-

{
    'name': 'Manage Access Rights',
    'version': '19.0.0.1',
    'summary': 'Access Rights Management',
    'description': """Helps To Manage Access Rights""",
    'category': 'Human Resources/Employees',
    'depends': ['base_user_role', 'sale_crm', 'helpdesk', 'hr_expense', 'event', 'purchase', 'hr_timesheet', 'website',
                'sales_team', 'hr_recruitment', 'sale_subscription', 'account_accountant', 'sale_project', 'approvals',
                'account_followup', 'sale_planning', 'appointment', 'social', 'marketing_automation',
                'cap_gamification', 'survey', 'lunch', 'fleet', 'hr_holidays', 'documents', 'hr_appraisal', 'sign',
                'cap_automatic_deferred_earnings_account', 'cap_hr_employee_extended',
                'sms', 'base_automation', 'marketing_automation', 'utm', 'account_online_synchronization',
                'account_bank_statement_import', 'data_recycle', 'hr_attendance', 'ksc_project_go_live_maintainer',
                'hr_payroll', 'cap_quality_issue_log', 'account_online_synchronization', 'account_edi',
                'account_sepa_direct_debit', 'cap_domain', 'cap_project_test_portal', 'cap_hr_skill',
                'cap_project_feedback_web', 'data_cleaning', 'voip', 'import_journal_entry', 'maintenance',
                'website_sale', 'l10n_in_reports', 'l10n_lu', 'account_budget', 'ksc_hr_payroll',
                'sale_expense', 'account_reports', 'ksc_auto_invoice', 'cap_subsidiary_report', 'cap_actions',
                'spreadsheet_dashboard','sale_timesheet'],

    # TODO : removed in V18 need to check
    # sale_temporal

    'data': [
        #'security/access_rights_security.xml', #Done for start
        # "data/roles_data.xml", #Done for start
        # "data/ir_cron_data.xml", #Done for start
        # "security/ir.model.access.csv", #Done for start
        # 'views/inherited_menus_views.xml', #Done for start
        # 'wizard/change_product_wizard_views.xml', #Done for start
        # 'views/sale_crm_inherit_views.xml', #Done for start
        # 'views/account_asset_inherit_views.xml', #Done for start
        # 'views/sale_order_inherit_views.xml', #Done for start
        # 'views/project_task_inherit_views.xml', #Done for start
        # 'views/res_partner_inherit_views.xml', #Done for start
        # 'views/account_journal_dashboard_inherited_views.xml', #Done for start
        # 'views/hr_job_inherited_views.xml', #Done for start
        # 'views/hr_employee_inherit.xml', #Done for start
        # 'views/purchase_inherit_views.xml', #Done for start
        # 'views/account_journal_inherit_views.xml', #Done for start
        # 'views/product_views_inherit.xml', #Done for start
        # 'views/helpdesk_inherit_views.xml', #Done for start
        # 'views/account_payment_inherit_views.xml', #Done for start
        # 'views/account_move_inherit_views.xml', #Done for start
        # 'views/portal_templates.xml', #Done for start
        # 'views/campaign_inherited_views.xml', #Done for start
        # 'views/gamification_goal_inherit_views.xml', #Done for start
        # 'views/hr_attendance_inherit_views.xml', #Done for start
        # 'views/report_timesheet_templates_inherit.xml', #Done for start
        # 'views/hr_recruitment_inherit_views.xml', #Done for start
        # 'views/go_live_change_req_inherited_views.xml', #Done for start
        # 'views/report_templates_inherit.xml', #Done for start
        # 'views/account_online_sync_inherit_views.xml', #Done for start
        # 'views/hr_timesheet_inherited_views.xml', #Done for start
        # 'views/crm_lead_inherited_views.xml', #Done for start
        # 'views/hr_expense_inherited_views.xml', #Done for start
        # 'views/mailing_mailing_inherit_views.xml', #Done for start
        # 'views/marketing_campaign_inherited_views.xml', #Done for start
        # 'views/data_merge_model_views_inherited.xml', #Done for start
        # 'views/view_res_company.xml',
        # 'views/hr_leave_type.xml',
        # 'views/approval_request.xml',
        # 'views/hr_department_view.xml',
        # 'views/account_report_templates.xml',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}

# TODO : removed in v18 need to check in database
# line 72, 82, 93, 637, 693, 805, 952
# "access_ir_server_object_lines_mm","ir_server_object_lines_marketing_manager","base.model_ir_server_object_lines","role_marketing_manager",1,1,1,1
# "access_ir_server_object_lines_em","ir_server_object_lines_email_manager","base.model_ir_server_object_lines","role_email_manager",1,1,1,1
# "access_ir_server_object_lines_cm","ir_server_object_lines_community_manager","base.model_ir_server_object_lines","role_community_manager",1,1,1,1
# "access_ir_server_object_lines_vpos","ir_server_object_lines_vpos","base.model_ir_server_object_lines","role_vp_of_sales",1,1,1,1
# "access_ir_server_object_lines_ceo","ir_server_object_lines_ceo","base.model_ir_server_object_lines","role_ceo",1,1,1,1
# "access_ir_server_object_lines_vpm","ir_server_object_lines_vpm","base.model_ir_server_object_lines","role_vp_of_marketing",1,1,1,1
# "access_ir_server_object_lines_ms","ir_server_object_lines_marketing_assistant","base.model_ir_server_object_lines","role_marketing_assistant",1,1,1,1

# line 119, 151, 170, 189, 236, 307, 386, 552, 754, 923
# access_sale_order_stage_sales_hot,access_sale_order_stage_view,sale_subscription.model_sale_order_stage,role_sales_hot,1,0,0,0
# access_sale_order_stage_sales_cold_td,access_sale_order_stage_td,sale_subscription.model_sale_order_stage,role_sales_cold_team_director,1,0,0,0
# access_sale_order_stage_sales_cold_tm,access_sale_order_stage_tm,sale_subscription.model_sale_order_stage,role_sales_cold_team_manager,1,0,0,0
# access_sale_order_stage_sales_cold,access_sale_order_stage,sale_subscription.model_sale_order_stage,role_sales_cold,1,0,0,0
# access_sale_order_stage_management,access_sale_order_stage_view,sale_subscription.model_sale_order_stage,role_management_control,1,1,1,1
# access_sale_order_stage_ar,access_sale_order_stage_view,sale_subscription.model_sale_order_stage,role_administrative_responsible,1,1,1,1
# access_sale_order_stage_administrative,access_sale_order_stage_view,sale_subscription.model_sale_order_stage,access_rights_management.role_administrative,1,0,0,0
# access_sale_order_stage_vps,access_sale_order_stage_view_vps,sale_subscription.model_sale_order_stage,role_vps,1,1,1,1
# access_sale_order_stage_cfo,access_sale_order_stage_view_cfo,sale_subscription.model_sale_order_stage,role_cfo,1,1,1,1
# access_sale_order_stage_cfo_com,access_sale_order_stage_view_cfo_com,sale_subscription.model_sale_order_stage,role_cfo_for_his_company,1,1,1,1

# line 125, 153, 172, 191, 238, 362, 555
# access_account_invoice_send_sales_hot,access.account.invoice.send.sales.hot,account.model_account_invoice_send,role_sales_hot,1,1,1,0
# access_account_invoice_send_sales_cold_td,access.account.invoice.send.sales.cold.td,account.model_account_invoice_send,role_sales_cold_team_director,1,1,1,0
# access_account_invoice_send_sales_cold_tm,access.account.invoice.send.sales.cold.tm,account.model_account_invoice_send,role_sales_cold_team_manager,1,1,1,0
# access_account_invoice_send_sales_cold,access.account.invoice.send.sales.cold,account.model_account_invoice_send,role_sales_cold,1,1,1,0
# access_account_invoice_send_management,access.account.invoice.send.management,account.model_account_invoice_send,role_management_control,1,1,1,1
# access_account_invoice_send_administrative,access.account.invoice.send.administrative,account.model_account_invoice_send,role_administrative,1,1,1,1
# access_account_invoice_send_vps,access.account.invoice.send.vps,account.model_account_invoice_send,role_vps,1,1,1,1

# OBJECT CHANGED
# line 204, 223, 300, 342, 418, 467, 490, 512, 584, 842, 869
# hr_recruitment_skills.access_hr_applicant_skill_recruiter,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_recruiter,1,1,1,1
# hr_recruitment_skills.access_hr_applicant_skill_management,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_management_control,1,0,0,0
# hr_recruitment_skills.access_hr_applicant_skill_ar,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_administrative_responsible,1,1,1,1
# hr_recruitment_skills.access_hr_applicant_skill_administrative,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_administrative,1,0,0,0
# hr_recruitment_skills.access_hr_applicant_skill_office_manager,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_office_manager,1,0,0,0
# hr_recruitment_skills.access_hr_applicant_skill_team_manager,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_team_manager,1,0,0,0
# hr_recruitment_skills.access_hr_applicant_skill_team_director,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_team_director,1,0,0,0
# hr_recruitment_skills.access_hr_applicant_skill_vps,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_vps,1,1,1,1
# hr_recruitment_skills.access_hr_applicant_skill_vpos,access_hr_applicant_skill,hr_recruitment_skills.model_hr_applicant_skill,role_vp_of_sales,1,1,1,1
# hr_recruitment_skills.access_hr_applicant_skill_hr,access_hr_applicant_skill_hr,hr_recruitment_skills.model_hr_applicant_skill,access_rights_management.role_hr,1,1,1,1
# hr_recruitment_skills.access_hr_applicant_skill_hr_res,access_hr_applicant_skill_hr_res,hr_recruitment_skills.model_hr_applicant_skill,access_rights_management.role_hr_responsible,1,1,1,1


# line 246, 376, 533, 605, 664, 687
# access_account_report_manager_mc,account.report_mc,account_reports.model_account_report_manager,access_rights_management.role_management_control,1,1,1,0
# access_account_report_manager_administrative,account.report_administrative,account_reports.model_account_report_manager,access_rights_management.role_administrative,1,1,1,0
# access_account_report_manager_vps,account.report_vps,account_reports.model_account_report_manager,access_rights_management.role_vps,1,0,0,0
# access_account_report_manager_vpos,account.report_vpos,account_reports.model_account_report_manager,access_rights_management.role_vp_of_sales,1,0,0,0
# access_account_report_manager_ceo,account.report_ceo,account_reports.model_account_report_manager,access_rights_management.role_ceo,1,0,0,0
# access_account_report_manager_ceo,account.report_ceo,account_reports.model_account_report_manager,access_rights_management.role_ceo,1,1,1,0

# line 247, 364, 534, 606, 665
# access_account_report_footnote_management,account.report_footnote_management,account_reports.model_account_report_footnote,access_rights_management.role_management_control,1,1,1,0
# access_account_report_footnote_administrative,account.report_footnote_administrative,account_reports.model_account_report_footnote,access_rights_management.role_administrative,1,1,1,0
# access_account_report_footnote_vps,account.report_footnote_vps,account_reports.model_account_report_footnote,access_rights_management.role_vps,1,0,0,0
# access_account_report_footnote_vpos,account.report_footnote_vpos,account_reports.model_account_report_footnote,access_rights_management.role_vp_of_sales,1,0,0,0
# access_account_report_footnote_ceo,account.report_footnote_ceo,account_reports.model_account_report_footnote,access_rights_management.role_ceo,1,1,1,0

# line 260, 368, 538, 610, 669
# access_account_budget_post_management,account.budget.post.management,account_budget.model_account_budget_post,access_rights_management.role_management_control,1,0,0,0
# access_account_budget_post_administrative,account.budget.post.administrative,account_budget.model_account_budget_post,access_rights_management.role_administrative,1,0,0,0
# access_account_budget_post_vps,account.budget.post.vps,account_budget.model_account_budget_post,access_rights_management.role_vps,1,0,0,0
# access_account_budget_post_vpos,account.budget.post.vpos,account_budget.model_account_budget_post,access_rights_management.role_vp_of_sales,1,0,0,0
# access_account_budget_post_ceo,account.budget.post.ceo,account_budget.model_account_budget_post,access_rights_management.role_ceo,1,0,0,0

# line 262, 310, 381, 540, 612, 671
# access_product_margin_management,access.product.margin.management,product_margin.model_product_margin,access_rights_management.role_management_control,1,1,1,0
# access_product_margin_ar,access.product.margin.ar,product_margin.model_product_margin,access_rights_management.role_administrative_responsible,1,1,1,0
# access_product_margin_administrative,access.product.margin.administrative,product_margin.model_product_margin,access_rights_management.role_administrative,1,1,1,0
# access_product_margin_vps,access.product.margin.vps,product_margin.model_product_margin,access_rights_management.role_vps,1,1,1,0
# access_product_margin_vpos,access.product.margin.vpos,product_margin.model_product_margin,access_rights_management.role_vp_of_sales,1,1,1,0
# access_product_margin_ceo,access.product.margin.ceo,product_margin.model_product_margin,access_rights_management.role_ceo,1,1,1,0

# line 263, 389
# access_l10n_lu_stored_intra_report_management,l10n_lu_reports.l10n_lu.stored.intra.report.management,l10n_lu_reports.model_l10n_lu_stored_intra_report,access_rights_management.role_management_control,1,0,0,0
# access_l10n_lu_stored_intra_report_administrative,l10n_lu_reports.l10n_lu.stored.intra.report.administrative,l10n_lu_reports.model_l10n_lu_stored_intra_report,access_rights_management.role_administrative,1,0,0,0

# line 264, 356
# access_l10n_lu_yearly_tax_report_manual_management,l10n_lu_reports.l10n_lu.yearly.tax.report.manual.management,l10n_lu_reports.model_l10n_lu_yearly_tax_report_manual,access_rights_management.role_management_control,1,0,0,0
# access_l10n_lu_yearly_tax_report_manual_administrative,l10n_lu_reports.l10n_lu.yearly.tax.report.manual.administrative,l10n_lu_reports.model_l10n_lu_yearly_tax_report_manual,access_rights_management.role_administrative,1,0,0,0

# line 272, 365
# access_account_unreconcile_management,access.account.unreconcile.management,account.model_account_unreconcile,access_rights_management.role_management_control,1,1,1,0
# access_account_unreconcile_administrative,access.account.unreconcile.administrative,account.model_account_unreconcile,access_rights_management.role_administrative,1,1,1,0

# line 895, 901
# access_crossovered_budget_cash,crossovered.budget cashflow_manager,account_budget.model_crossovered_budget,access_rights_management.role_cashflow_manager,1,1,1,0
# access_crossovered_budget_bm,crossovered.budget bm,account_budget.model_crossovered_budget,access_rights_management.role_budget_manager,1,1,1,0




# line 709 - add access right for ceo
# access_res_company_group_ceo,default_domain_company_reports_ceo,cap_subsidiary_report.model_res_company_reports,access_rights_management.role_ceo,1,0,0,0

# line 764
# access_product_pricing_sale_cfo,sale_temporal_cfo,sale_temporal.model_product_pricing,role_cfo,1,1,1,1

# line 933
# access_product_pricing_sale_cfo_com,sale_temporal_cfo_com,sale_temporal.model_product_pricing,role_cfo_for_his_company,1,1,1,1



# TODO : need to check for marketing, email and community manager for sales access
# TODO : smart button go live change request : we can apply groups on it
# TODO : need to check timesheet reporting and all timesheet view in databse
