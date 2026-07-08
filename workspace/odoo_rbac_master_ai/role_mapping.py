"""Mapping from Odoo group XML IDs to logical business role names.

Populate this dictionary with the actual XML IDs used in the Odoo instance.
The keys are the XML IDs of groups; the values are the role identifiers
expected by the test‑suite scripts.
"""

ROLE_MAP = {
    "team_director_role": "TEAM_DIRECTOR",
    "team_manager_role": "TEAM_MANAGER",
    "operation_role": "OPERATION",
    "office_manager_role": "OFFICE_MANAGER",
    "hr_role": "HR",
    "cfo_role": "CFO",
    "vp_of_marketing_role": "VP_OF_MARKETING",
    "president_role": "PRESIDENT",
    "vp_of_quality_and_knowledge_role": "VP_OF_QUALITY_AND_KNOWLEDGE",
    "ceo_role": "CEO",
    "vp_of_sales_role": "VP_OF_SALES",
    "cash_flow_manager_role": "CASH_FLOW_MANAGER",
    "budget_manager_role": "BUDGET_MANAGER",
    "legal_role": "LEGAL",
    "administrative_role": "ADMINISTRATIVE",
    "recruiter_role": "RECRUITER",
    "sales_cold_role": "SALES_COLD",
    "sales_hot_role": "SALES_HOT",
    "webmaster_role": "WEBMASTER",
    "customer_referencer_role": "CUSTOMER_REFERENCER",
    "community_manager_role": "COMMUNITY_MANAGER",
    "email_manager_role": "EMAIL_MANAGER",
    "marketing_manager_role": "MARKETING_MANAGER",
    "it_person_role": "IT_PERSON",
    # Add additional mappings as required.
}
