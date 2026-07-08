from collections import defaultdict

from odoo import models, fields, api, _


class SaleOrder(models.Model):
    _inherit = "sale.order"

    project_ids = fields.Many2many('project.project', compute="_compute_project_ids", string='Projects', copy=False,
                                   groups="access_rights_management.role_sales_hot,project.group_project_user,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_team_manager,access_rights_management.role_team_director,access_rights_management.role_operation,access_rights_management.role_operation_on_boarder,access_rights_management.role_legal", help="Projects used in this sales order.")
    project_count = fields.Integer(string='Number of Projects', compute='_compute_project_ids',
                                   groups='access_rights_management.role_sales_hot,project.group_project_user,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_team_manager,access_rights_management.role_team_director,access_rights_management.role_operation,access_rights_management.role_operation_on_boarder,access_rights_management.role_legal')
    tasks_count = fields.Integer(string='Tasks', compute='_compute_tasks_ids',
                                 groups="access_rights_management.role_sales_hot,project.group_project_user,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_team_manager,access_rights_management.role_team_director,access_rights_management.role_operation,access_rights_management.role_operation_on_boarder,access_rights_management.role_legal")
    timesheet_count = fields.Float(string='Timesheet activities', compute='_compute_timesheet_count',
                                   groups="access_rights_management.role_sales_hot,hr_timesheet.group_hr_timesheet_user,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_cashflow_manager,access_rights_management.role_budget_manager,access_rights_management.role_legal")
    show_project_button = fields.Boolean(compute='_compute_show_project_and_task_button',
                                         groups='access_rights_management.role_sales_hot,project.group_project_user,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_team_manager,access_rights_management.role_team_director,access_rights_management.role_operation,access_rights_management.role_operation_on_boarder,access_rights_management.role_legal')

    # TODO : need to check in database for all the roles
    # def _compute_timesheet_total_duration(self):
    #     if self.env.user.has_group('access_rights_management.role_sales_hot') or self.env.user.has_group(
    #             'access_rights_management.role_management_control') or self.env.user.has_group(
    #         'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
    #         'access_rights_management.role_administrative') or self.env.user.has_group(
    #         'access_rights_management.role_vps') or self.env.user.has_group(
    #         'access_rights_management.role_vp_of_sales') or self.env.user.has_group(
    #         'access_rights_management.role_cashflow_manager') or self.env.user.has_group(
    #         'access_rights_management.role_budget_manager') or self.env.user.has_group(
    #         'access_rights_management.role_legal'):
    #         group_data = self.env['account.analytic.line'].sudo()._read_group([
    #             ('order_id', 'in', self.ids)
    #         ], ['order_id', 'unit_amount'], ['order_id'])
    #         timesheet_unit_amount_dict = defaultdict(float)
    #         timesheet_unit_amount_dict.update({data['order_id'][0]: data['unit_amount'] for data in group_data})
    #         for sale_order in self:
    #             total_time = sale_order.company_id.project_time_mode_id._compute_quantity(
    #                 timesheet_unit_amount_dict[sale_order.id], sale_order.timesheet_encode_uom_id)
    #             sale_order.timesheet_total_duration = round(total_time)
    #     else:
    #         super(SaleOrder, self)._compute_timesheet_total_duration()

    def _has_to_be_signed_only_by_cust(self):
        """
        Checks access for user: done for portal user
        """
        current_user = self.env.uid_origin
        current_user = self.env['res.users'].browse(current_user)
        if current_user.has_group('base.group_portal') or current_user.has_group('base.group_public') or current_user.has_group('access_rights_management.role_president'):
            return True
        else:
            return False

    def action_view_project_ids(self):
        """Override to prevent opening a new project creation form when the linked project is archived.
        By default, if a sale order has a linked project that is archived, clicking the Project smart button opens
        the project form in create mode. This override ensures that the button does not open a new project form
        when the related project is archived."""

        self.ensure_one()
        if not self.order_line:
            return {'type': 'ir.actions.act_window_close'}

        sorted_line = self.order_line.sorted('sequence')
        default_sale_line = next((
            sol for sol in sorted_line if sol.product_id.type == 'service'
        ), self.env['sale.order.line'])
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Projects'),
            'domain': ['|', ('sale_order_id', '=', self.id), ('id', 'in', self.with_context(active_test=False).project_ids.ids)],
            'res_model': 'project.project',
            'views': [(False, 'kanban'), (False, 'list'), (False, 'form')],
            'view_mode': 'kanban,list,form',
            'context': {
                **self._context,
                'default_partner_id': self.partner_id.id,
                'default_sale_line_id': default_sale_line.id,
                'default_allow_billable': 1,
            }
        }

        all_projects = self.project_ids

        if len(all_projects) == 0:
            return action
        else:
            return super(SaleOrder,self).action_view_project_ids()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def write(self, vals_list):
        """
        When sale order line's hours are converted(local to offshore or offshore to local).
        System will update existing sale order line with same value while creating project progress report.
        To resolve the access error faced by operation team we call write method with sudo only when it is writes from project progress report.
        """
        if self._context.get('from_project_progress', False):
            return super(SaleOrderLine, self.sudo()).write(vals_list)
        else:
            return super(SaleOrderLine, self).write(vals_list)

    @api.depends('product_id', 'product_uom_id', 'product_uom_qty')
    def _compute_price_unit(self):
        """
        Override base default's method so when administrative responsible was changed product then price is not updated!
        """
        for line in self:
            # Don't compute the price for deleted lines.
            if not line.order_id:
                continue
            # check if the price has been manually set or there is already invoiced amount.
            # if so, the price shouldn't change as it might have been manually edited.
            if (
                    (line.technical_price_unit != line.price_unit and not line.env.context.get(
                        'force_price_recomputation'))
                    or line.qty_invoiced > 0
                    or (line.product_id.expense_policy == 'cost' and line.is_expense)
            ):
                continue
            line = line.with_context(sale_write_from_compute=True)
            if not line.product_uom or not line.product_id:
                line.price_unit = 0.0
                line.technical_price_unit = 0.0
            else:
                if not line.state == 'sale':
                    line = line.with_company(line.company_id)
                    price = line._get_display_price()
                    line.price_unit = line.product_id._get_tax_included_unit_price_from_price(
                        price,
                        product_taxes=line.product_id.taxes_id.filtered(
                            lambda tax: tax.company_id == line.env.company
                        ),
                        fiscal_position=line.order_id.fiscal_position_id,
                    )
                    line.technical_price_unit = line.price_unit

    @api.depends('product_id', 'company_id')
    def _compute_tax_id(self):
        """
        Override base default's method so when administrative responsible was changed product then taxes are not updated!
        """
        taxes_by_product_company = defaultdict(lambda: self.env['account.tax'])
        lines_by_company = defaultdict(lambda: self.env['sale.order.line'])
        cached_taxes = {}
        for line in self:
            lines_by_company[line.company_id] += line
        for product in self.product_id:
            for tax in product.taxes_id:
                taxes_by_product_company[(product, tax.company_id)] += tax
        for company, lines in lines_by_company.items():
            for line in lines.with_company(company):
                if not line.state == 'sale':
                    taxes = taxes_by_product_company[(line.product_id, company)]
                    if not line.product_id or not taxes:
                        # Nothing to map
                        line.tax_id = False
                        continue
                    fiscal_position = line.order_id.fiscal_position_id
                    cache_key = (fiscal_position.id, company.id, tuple(taxes.ids))
                    cache_key += line._get_custom_compute_tax_cache_key()
                    if cache_key in cached_taxes:
                        result = cached_taxes[cache_key]
                    else:
                        result = fiscal_position.map_tax(taxes)
                        cached_taxes[cache_key] = result
                    # If company_id is set, always filter taxes by the company
                    line.tax_id = result

    @api.depends('product_id', 'product_uom_id', 'product_uom_qty')
    def _compute_discount(self):
        """
        Override base default's method so when administrative responsible was changed product then discount is not updated!
        """
        discount_enabled = self.env['product.pricelist.item']._is_discount_feature_enabled()
        for line in self.filtered(lambda ol: ol.state != 'sale'):
            if not line.product_id or line.display_type:
                line.discount = 0.0

            if not (line.order_id.pricelist_id and discount_enabled):
                continue

            line.discount = 0.0

            if not line.pricelist_item_id._show_discount():
                # No pricelist rule was found for the product
                # therefore, the pricelist didn't apply any discount/change
                # to the existing sales price.
                continue

            line = line.with_company(line.company_id)
            pricelist_price = line._get_pricelist_price()
            base_price = line._get_pricelist_price_before_discount()

            if base_price != 0:  # Avoid division by zero
                discount = (base_price - pricelist_price) / base_price * 100
                if (discount > 0 and base_price > 0) or (discount < 0 and base_price < 0):
                    # only show negative discounts if price is negative
                    # otherwise it's a surcharge which shouldn't be shown to the customer
                    line.discount = discount

    def action_open_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Change Product',
            'res_model': 'change.product.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_line_id': self.id,
                'default_is_subscription': self.order_id.is_subscription
            },
        }
