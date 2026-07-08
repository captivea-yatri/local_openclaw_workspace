from collections import defaultdict

from odoo import models, fields, api, _
from odoo.exceptions import AccessError


class Project(models.Model):
    _inherit = "project.project"

    total_timesheet_time = fields.Float(
        compute='_compute_total_timesheet_time',digits=(16, 2),
        groups='access_rights_management.role_administrative_responsible,access_rights_management.role_management_control,access_rights_management.role_sales_hot,hr_timesheet.group_hr_timesheet_user,access_rights_management.role_administrative,access_rights_management.role_operation_on_boarder,access_rights_management.role_operation,access_rights_management.role_team_manager,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_drh,access_rights_management.role_hr,access_rights_management.role_hr_responsible,access_rights_management.role_cashflow_manager,access_rights_management.role_budget_manager,access_rights_management.role_legal,access_rights_management.role_vp_of_marketing',
        help="Total number of time (in the proper UoM) recorded in the project, rounded to the unit.")

    reinvoiced_sale_order_id = fields.Many2one('sale.order', string='Sales Order',
                                               groups='sales_team.group_sale_salesman,access_rights_management.role_cfo,access_rights_management.role_cfo_for_his_company,access_rights_management.role_vp_of_quality_and_knowledge,access_rights_management.role_ceo,access_rights_management.role_vp_of_sales,access_rights_management.role_team_director,access_rights_management.role_team_manager,access_rights_management.role_operation,access_rights_management.role_operation_on_boarder,access_rights_management.role_operation_on_boarder',
                                               copy=False,domain="[('partner_id', '=', partner_id)]",
                                               help="Products added to stock pickings, whose operation type is configured to generate analytic costs, will be re-invoiced in this sales order if they are set up for it.",
                                               )

    # timesheet_count = fields.Integer(compute="_compute_timesheet_count",
    #                                  groups='hr_timesheet.group_hr_timesheet_user,access_rights_management.role_management_control,access_rights_management.role_administrative_responsible,access_rights_management.role_administrative,access_rights_management.role_vps,access_rights_management.role_vp_of_sales,access_rights_management.role_drh,access_rights_management.role_hr,access_rights_management.role_hr_responsible,access_rights_management.role_legal')

    def action_project_timesheets(self):
        super(Project, self).action_project_timesheets()
        active_id = self.env.context.get('active_id', False)
        action = self.env['ir.actions.act_window']._for_xml_id('hr_timesheet.act_hr_timesheet_line_by_project')
        if self.env.user.has_group('access_rights_management.role_sales_hot') or self.env.user.has_group(
                'hr_timesheet.group_hr_timesheet_approver') or \
                self.env.user.has_group('hr_timesheet.group_timesheet_manager') or self.env.user.has_group(
            'access_rights_management.role_management_control') or self.env.user.has_group(
            'access_rights_management.role_administrative_responsible') or self.env.user.has_group(
            'access_rights_management.role_administrative') or self.env.user.has_group(
            'access_rights_management.role_operation_on_boarder') or self.env.user.has_group(
            'access_rights_management.role_operation') or self.env.user.has_group(
            'access_rights_management.role_team_manager') or self.env.user.has_group(
            'access_rights_management.role_team_director') or self.env.user.has_group(
            'access_rights_management.role_vps') or self.env.user.has_group(
            'access_rights_management.role_vp_of_sales') or self.env.user.has_group(
            'access_rights_management.role_drh') or self.env.user.has_group(
            'access_rights_management.role_hr') or self.env.user.has_group(
            'access_rights_management.role_hr_responsible') or self.env.user.has_group(
            'access_rights_management.role_legal'):
            return action
        action['domain'] = [('project_id', '!=', False), ('employee_id.user_id', '=', self.env.user.id)]
        if active_id:
            action['domain'].append(('project_id', '=', active_id))
        return action

    # TODO : need to check in v18 for field allow_forecast
    # @api.depends('allow_timesheets', 'allow_forecast')
    # @api.depends_context('uid')
    # def _compute_display_planning_timesheet_analysis(self):
    #     authorized_roles = self.env.user.has_group('access_rights_management.role_vps') or self.env.user.has_group(
    #         'access_rights_management.role_vp_of_sales') or self.env.user.has_group(
    #         'access_rights_management.role_vp_of_quality_and_knowledge') or self.env.user.has_group(
    #         'access_rights_management.role_drh')
    #     is_user_authorized = self.env.user.has_group('planning.group_planning_manager') and self.env.user.has_group(
    #         'hr_timesheet.group_hr_timesheet_approver')
    #     if not is_user_authorized:
    #         self.display_planning_timesheet_analysis = False
    #     else:
    #         for project in self:
    #             project.display_planning_timesheet_analysis = project.allow_timesheets and project.allow_forecast
    #     if authorized_roles:
    #         for project in self:
    #             project.display_planning_timesheet_analysis = project.allow_timesheets and project.allow_forecast

    @api.depends('timesheet_ids')
    def _compute_total_timesheet_time(self):
        timesheets_read_group = self.env['account.analytic.line'].read_group(
            [('project_id', 'in', self.ids)],
            ['project_id', 'unit_amount', 'product_uom_id'],
            ['project_id', 'product_uom_id'],
            lazy=False)
        timesheet_time_dict = defaultdict(list)
        uom_ids = set(self.timesheet_encode_uom_id.ids)

        for result in timesheets_read_group:
            uom_id = result['product_uom_id'] and result['product_uom_id'][0]
            if uom_id:
                uom_ids.add(uom_id)
            timesheet_time_dict[result['project_id'][0]].append((uom_id, result['unit_amount']))

        uoms_dict = {uom.id: uom for uom in self.env['uom.uom'].browse(uom_ids)}
        for project in self:
            # Timesheets may be stored in a different unit of measure, so first
            # we convert all of them to the reference unit
            # if the timesheet has no product_uom_id then we take the one of the project
            total_time = 0.0
            for product_uom_id, unit_amount in timesheet_time_dict[project.id]:
                factor = uoms_dict.get(product_uom_id, project.timesheet_encode_uom_id).factor_inv
                total_time += unit_amount * (1.0 if project.encode_uom_in_days else factor)
            # Now convert to the proper unit of measure set in the settings
            total_time *= project.timesheet_encode_uom_id.factor
            project.total_timesheet_time = total_time

    # Used in ksc_project_extended. to compute with superuser.
    @api.depends('sale_order_line_ids.x_studio_remaining_quantity', 'sale_order_line_ids.x_studio_consumed_qty',
                 'sale_order_line_ids', 'sale_order_line_ids.order_id.x_studio_block_timesheet_log',
                 'partner_id.x_studio_authorize_late_amount', 'partner_id.followup_status',
                 'partner_id.x_studio_authorize_to_log_hours_with_late_invoice', 'partner_id.total_overdue',
                 'on_hold_reason', 'partner_id.invoice_ids.payment_state', 'sale_order_line_ids.state')
    def compute_project_color_remaining_hours(self):
        #To update on hold reason with captivea bot.
        captivea_bot = self.env['res.users'].browse(1)
        return super(Project, self.with_user(captivea_bot).sudo()).compute_project_color_remaining_hours()

    @api.onchange('on_hold_reason')
    def onchange_on_hold_reason(self):
        #To update on hold reason with captivea bot.
        captivea_bot = self.env['res.users'].browse(1)
        return super(Project, self.with_user(captivea_bot).sudo()).onchange_on_hold_reason()



class Task(models.Model):
    _inherit = "project.task"

    repeat_interval = fields.Integer(string='Repeat Every', default=1, compute='_compute_repeat', readonly=False,
                                     groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years'),
    ], default='week', compute='_compute_repeat', readonly=False,
        groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_type = fields.Selection(selection_add=[('after', 'Number of Repetitions')],
        default="forever", string="Until", compute='_compute_repeat', readonly=False,
        groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_until = fields.Date(string="End Date", compute='_compute_repeat', readonly=False,
                               groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_number = fields.Integer(string="Repetitions", default=1, compute='_compute_repeat', readonly=False,
                                   groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_on_month = fields.Selection([
        ('date', 'Date of the Month'),
        ('day', 'Day of the Month'),
    ], default='date', compute='_compute_repeat', readonly=False,
        groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_on_year = fields.Selection([
        ('date', 'Date of the Year'),
        ('day', 'Day of the Year'),
    ], default='date', compute='_compute_repeat', readonly=False,
        groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_day = fields.Selection([
        (str(i), str(i)) for i in range(1, 32)
    ], compute='_compute_repeat', readonly=False,
        groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_week = fields.Selection([
        ('first', 'First'),
        ('second', 'Second'),
        ('third', 'Third'),
        ('last', 'Last'),
    ], default='first', compute='_compute_repeat', readonly=False,
        groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_weekday = fields.Selection([
        ('mon', 'Monday'),
        ('tue', 'Tuesday'),
        ('wed', 'Wednesday'),
        ('thu', 'Thursday'),
        ('fri', 'Friday'),
        ('sat', 'Saturday'),
        ('sun', 'Sunday'),
    ], string='Day Of The Week', compute='_compute_repeat', readonly=False,
        groups="project.group_project_user,project.group_project_recurring_tasks")
    repeat_month = fields.Selection([
        ('january', 'January'),
        ('february', 'February'),
        ('march', 'March'),
        ('april', 'April'),
        ('may', 'May'),
        ('june', 'June'),
        ('july', 'July'),
        ('august', 'August'),
        ('september', 'September'),
        ('october', 'October'),
        ('november', 'November'),
        ('december', 'December'),
    ], compute='_compute_repeat', readonly=False,
        groups="project.group_project_user,project.group_project_recurring_tasks")
    mon = fields.Boolean(string="Mon", compute='_compute_repeat', readonly=False,
                         groups="project.group_project_user,project.group_project_recurring_tasks")
    tue = fields.Boolean(string="Tue", compute='_compute_repeat', readonly=False,
                         groups="project.group_project_user,project.group_project_recurring_tasks")
    wed = fields.Boolean(string="Wed", compute='_compute_repeat', readonly=False,
                         groups="project.group_project_user,project.group_project_recurring_tasks")
    thu = fields.Boolean(string="Thu", compute='_compute_repeat', readonly=False,
                         groups="project.group_project_user,project.group_project_recurring_tasks")
    fri = fields.Boolean(string="Fri", compute='_compute_repeat', readonly=False,
                         groups="project.group_project_user,project.group_project_recurring_tasks")
    sat = fields.Boolean(string="Sat", compute='_compute_repeat', readonly=False,
                         groups="project.group_project_user,project.group_project_recurring_tasks")
    sun = fields.Boolean(string="Sun", compute='_compute_repeat', readonly=False,
                         groups="project.group_project_user,project.group_project_recurring_tasks")

    def _notify_get_recipients_groups(self, message, model_description, msg_vals=None):
        """ Handle project users and managers recipients that can assign
        tasks and create new one directly from notification emails. Also give
        access button to portal users and portal customers. If they are notified
        they should probably have access to the document. """

        """ Override the base-default method. because in base default, if user is Project-User
        then only user will be able to see button view task."""

        groups = super(Task, self)._notify_get_recipients_groups(message, model_description, msg_vals=None)
        if not self:
            return groups

        self.ensure_one()

        group_ids = self.env['res.users'].search(
            ['|', '|', '|', '|', '|', '|', '|', ('id', 'in', self.env.ref('project.group_project_user').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_administrative').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_operation').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_vp_of_sales').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_vps').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_operation_on_boarder').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_team_manager').users.ids),
             ('id', 'in', self.env.ref('access_rights_management.role_team_director').users.ids)]).ids

        new_group = ('group_project_user',
                     lambda pdata: pdata['type'] == 'user' and (group_id in pdata['groups'] for group_id in group_ids),
                     {})
        groups = [new_group] + groups

        if self.project_privacy_visibility == 'portal':
            groups.insert(0, (
                'allowed_portal_users',
                lambda pdata: pdata['type'] == 'portal',
                {
                    'active': True,
                    'has_button_access': True,
                }
            ))
        portal_privacy = self.project_id.privacy_visibility == 'portal'
        for group_name, _group_method, group_data in groups:
            if group_name in ('customer', 'user') or group_name == 'portal_customer' and not portal_privacy:
                group_data['has_button_access'] = False
            elif group_name == 'portal_customer' and portal_privacy:
                group_data['has_button_access'] = True
        return groups

    def action_project_sharing_view_so(self):
        """
        checks for portal user
        """
        if self.env.user.has_group('base.group_user') or (
                self.env.user.has_group('base.group_portal') and self.env.user.partner_id.accounting_information):
            return super().action_project_sharing_view_so()
        else:
            raise AccessError(_('You are not authorized to access the sale order.'))
