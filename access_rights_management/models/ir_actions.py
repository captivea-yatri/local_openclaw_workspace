from odoo import models, fields, api, _


class IrActionsServer(models.Model):
    _inherit = 'ir.actions.server'

    DEFAULT_PYTHON_CODE = """# Available variables:
#  - env: Odoo Environment on which the action is triggered
#  - model: Odoo Model of the record on which the action is triggered; is a void recordset
#  - record: record on which the action is triggered; may be void
#  - records: recordset of all records on which the action is triggered in multi-mode; may be void
#  - time, datetime, dateutil, timezone: useful Python libraries
#  - float_compare: Odoo function to compare floats based on specific precisions
#  - log: log(message, level='info'): logging function to record debug information in ir.logging table
#  - UserError: Warning Exception to use with raise
#  - Command: x2Many commands namespace
# To return an action, assign: action = {...}\n\n\n\n"""

    code = fields.Text(string='Python Code',
                       groups='base.group_system,access_rights_management.role_marketing_manager,access_rights_management.role_email_manager,access_rights_management.role_community_manager,access_rights_management.role_vp_of_sales,access_rights_management.role_ceo,access_rights_management.role_vp_of_marketing,access_rights_management.role_marketing_assistant',
                       default=DEFAULT_PYTHON_CODE,
                       help="Write Python code that the action will execute. Some variables are "
                            "available for use; help about python expression is given in the help tab.")
