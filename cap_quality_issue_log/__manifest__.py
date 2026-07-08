# -*- coding: utf-8 -*-
{
    "name": "CAP QUALITY ISSUE LOG",
    "summary": """Employee's Work Quality Measure Tool""",
    "description": """Manages Employee's working quality based on various criteria and log all those quality""",
    "author": "Konsultoo Software Consulting PVT. LTD.",
    "website": "https://www.konsultoo.com/",
    "category": "Extra Tools",
    "summary": "",
    "version": "19.0.0.1",
    "depends": [
        "contacts", "hr", "cap_partner", "hr_gamification", "base_automation",
        "hr_holidays", "cap_project_progress_report", "ksc_project_extended", "analytic",
    ],
    "data": [
        "security/quality_issue_log_security.xml",
        "security/ir.model.access.csv",
        "data/quality_category_data.xml",
        "data/quality_issue_type_data.xml",
        "data/ir_cron_data.xml",
        "data/quality_issue_type_data_new.xml",
        "views/quality_category_view.xml",
        "views/quality_issue_log_view.xml",
        "views/quality_issue_type_view.xml",
        "views/hr_job_views.xml",
        "views/hr_employee_view.xml",
    ],

    "installable": True,
    "application": True,
    "auto_install": False,
    'license': 'LGPL-3',
}
