from odoo import models, fields, api
from odoo.tools import float_compare
from odoo.exceptions import ValidationError


class HrExpense(models.Model):
    _inherit = "hr.expense"

    @api.depends('product_id.standard_price')
    def _compute_product_has_cost(self):
        for expense in self:
            expense.sudo().product_has_cost = expense.product_id and (
                    float_compare(expense.product_id.standard_price, 0.0, precision_digits=2) != 0)
            tax_ids = expense.product_id.supplier_taxes_id.filtered(lambda tax: tax.company_id == expense.company_id)
            expense.sudo().product_has_tax = bool(tax_ids)
            if not expense.product_has_cost and expense.state == 'draft':
                expense.sudo().unit_amount = expense.total_amount_company
                expense.sudo().quantity = 1

    expense_type = fields.Selection([('for_sales', 'For Sales'), ('for_customer', 'For a Customer'),
                                     ('other', 'Other')], string='Type of Expense')
    partner_id = fields.Many2one('res.partner', string='Customer')

    @api.onchange('expense_type')
    def _onchange_expense_type(self):
        for record in self:
            if record.expense_type != 'for_customer':
                record.partner_id = False

    @api.depends('expense_type', 'employee_id', 'partner_id')
    def _compute_analytic_distribution(self):
        for expense in self:
            expense.analytic_distribution = {}
            if expense.expense_type == 'for_sales':
                expense.sale_order_id = False
                expense.analytic_distribution = {'2931,2930': 100.0}

            elif expense.expense_type == 'for_customer':
                expense.sale_order_id = False
                latest_sale_order = self.env['sale.order'].search([
                    ('partner_id', 'child_of', expense.partner_id.id),
                    ('state', '=', 'sale')
                ], order='date_order desc', limit=1)

                department_analytic_id = expense.employee_id.department_id.analytic_account_id.id or None
                project_analytic_id = None

                if latest_sale_order:
                    latest_so = latest_sale_order[0]
                    expense.sale_order_id = latest_so

                    if latest_so.company_id != expense.company_id:
                        raise ValidationError(
                            f"The Customer '{expense.partner_id.name}' belongs to company '{latest_so.company_id.name}', "
                            f"but the expense is recorded under company '{expense.company_id.name}'. "
                            "Both must belong to the same company."
                        )

                    if latest_so.project_ids:
                        project_analytic_id = latest_so.project_ids[0].account_id.id

                analytic_dict = {}
                if project_analytic_id:
                    key = str(project_analytic_id)
                    analytic_dict[key] = 100.0
                    if department_analytic_id:
                        value = analytic_dict.pop(key)
                        new_key = f"{key},{department_analytic_id}"
                        analytic_dict[new_key] = value
                elif department_analytic_id:
                    analytic_dict[str(department_analytic_id)] = 100.0
                expense.analytic_distribution = analytic_dict

            elif expense.expense_type == 'other':
                expense.sale_order_id = False
                department_analytic_id = expense.employee_id.department_id.analytic_account_id.id

                if department_analytic_id:
                    expense.analytic_distribution = {'2931': 100.0}
                    analytic_dict = expense.analytic_distribution
                    original_key = list(analytic_dict.keys())[0]
                    value = analytic_dict.pop(original_key)

                    new_key = f"{original_key},{department_analytic_id}"
                    analytic_dict[new_key] = value

                    expense.analytic_distribution = analytic_dict
                else:
                    expense.analytic_distribution = {'2931': 100.0}

            else:
                expense.sale_order_id = False

# todo:check hr.expense.sheet module in odoo 19

# class HrExpenseSheet(models.Model):
#     _inherit = 'hr.expense.sheet'
#
#     # For allowing chatter
#     _mail_post_access = 'read'
