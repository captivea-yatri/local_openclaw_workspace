from odoo import http
from odoo.http import request
from odoo.addons.account.controllers.portal import PortalAccount
from odoo.addons.sale.controllers.portal import CustomerPortal as SaleCustomerPortal
from odoo.addons.sale_subscription.controllers.portal import CustomerPortal as SubscriptionCustomerPortal
from odoo.addons.project.controllers.portal import ProjectCustomerPortal
from odoo.addons.hr_timesheet.controllers.portal import TimesheetCustomerPortal
from odoo.addons.cap_project_test_portal.controller.session_test_portal import SessionTestPortal
from odoo.addons.cap_project_feedback_web.controller.feedback_website import FeedbackSharingChatter



# Accounting Section
class PortalAccountInheritCustom(PortalAccount):

    @http.route(['/my/invoices', '/my/invoices/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_invoices(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        """
        checks if user has accounting rights or not and redirects accordingly
        """
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.accounting_information):
            return super(PortalAccountInheritCustom, self).portal_my_invoices(page, date_begin, date_end, sortby,
                                                                              filterby, **kw)
        else:
            return request.redirect('/my')


class CustomerPortalInheritCustom(SaleCustomerPortal):

    @http.route(['/my/quotes', '/my/quotes/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_quotes(self, **kwargs):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.accounting_information):
            return super(CustomerPortalInheritCustom, self).portal_my_quotes(**kwargs)
        else:
            return request.redirect('/my')

    @http.route(['/my/orders', '/my/orders/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_orders(self, **kwargs):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.accounting_information):
            return super(CustomerPortalInheritCustom, self).portal_my_orders(**kwargs)
        else:
            return request.redirect('/my')

    # @http.route(['/my/orders/<int:order_id>'], type='http', auth="public", website=True)
    # def portal_order_page(self, order_id, report_type=None, access_token=None, message=False, download=False, **kw):
    #     if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.accounting_information):
    #         return super(CustomerPortalInheritCustom, self).portal_order_page(order_id, report_type, access_token,
    #                                                                          message, download, **kw)
    #     else:
    #         return request.redirect('/my')


class SubscriptionCustomerPortalInherit(SubscriptionCustomerPortal):

    @http.route(['/my/subscription', '/my/subscription/page/<int:page>'], type='http', auth="user", website=True)
    def my_subscription(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.accounting_information):
            return super(SubscriptionCustomerPortalInherit, self).my_subscription(page, date_begin, date_end, sortby,
                                                                                 filterby, **kw)
        else:
            return request.redirect('/my')

    @http.route(['/my/subscription/<int:order_id>', '/my/subscription/<int:order_id>/<access_token>'],
                type='http', auth='public', website=True)
    def subscription(self, order_id, access_token=None, message='', message_class='', report_type=None, download=False,
                     **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.accounting_information):
            return super(SubscriptionCustomerPortalInherit, self).subscription(order_id, access_token, message,
                                                                                message_class, report_type, download,
                                                                                **kw)
        else:
            return request.redirect('/my')


# Project Section
class ProjectCustomerPortalInheritCustom(ProjectCustomerPortal):

    @http.route(['/my/projects', '/my/projects/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_projects(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.project_information):
            return super(ProjectCustomerPortalInheritCustom, self).portal_my_projects(page, date_begin, date_end,
                                                                                      sortby, **kw)
        else:
            return request.redirect('/my')

    @http.route(['/my/projects/<int:project_id>', '/my/projects/<int:project_id>/page/<int:page>'], type='http',
                auth="public", website=True)
    def portal_my_project(self, project_id=None, access_token=None, page=1, date_begin=None, date_end=None, sortby=None,
                          search=None, search_in='content', groupby=None, task_id=None, **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.project_information):
            return super(ProjectCustomerPortalInheritCustom, self).portal_my_project(project_id, access_token, page,
                                                                                    date_begin, date_end, sortby, search,
                                                                                    search_in, groupby, task_id, **kw)
        else:
            return request.redirect('/my')

    @http.route(['/my/tasks', '/my/tasks/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_tasks(self, page=1, date_begin=None, date_end=None, sortby=None, filterby=None, search=None,
                        search_in='content', groupby=None, **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.project_information):
            return super(ProjectCustomerPortalInheritCustom, self).portal_my_projects(page, date_begin, date_end,
                                                                                      sortby, **kw)
        else:
            return request.redirect('/my')

    @http.route(['/my/tasks/<int:task_id>'], type='http', auth="public", website=True)
    def portal_my_task(self, task_id, report_type=None, access_token=None, project_sharing=False, **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.project_information):
            return super(ProjectCustomerPortalInheritCustom, self).portal_my_task(task_id, report_type, access_token,
                                                                                 project_sharing, **kw)
        else:
            return request.redirect('/my')


class TimesheetCustomerPortalInheritCustom(TimesheetCustomerPortal):

    @http.route(['/my/timesheets', '/my/timesheets/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_timesheets(self, page=1, sortby=None, filterby=None, search=None, search_in='all', groupby='none',
                             **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.project_information):
            return super(TimesheetCustomerPortalInheritCustom, self).portal_my_timesheets(page, sortby, filterby,
                                                                                          search, search_in,
                                                                                          **kw)
        else:
            return request.redirect('/my')

class SessionTestPortalInheritCustom(SessionTestPortal):

    @http.route(['/my/project_tests', '/my/project_tests/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_project_tests(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.project_information):
            return super(SessionTestPortalInheritCustom, self).portal_my_project_tests(page, date_begin, date_end,
                                                                                      sortby, **kw)
        else:
            return request.redirect('/my')

class FeedbackWebsiteInheritCustom(FeedbackSharingChatter):

    @http.route(['/my/feedback/', '/my/feedback/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_feedback(self, page=1, date_begin=None, date_end=None, sortby=None, **kw):
        if request.env.user.has_group('base.group_user') or (request.env.user.has_group('base.group_portal') and request.env.user.partner_id.project_information):
            return super(FeedbackWebsiteInheritCustom, self).portal_my_feedback(page, date_begin, date_end, sortby, **kw)
        else:
            return request.redirect('/my')


class RedirectController(http.Controller):

    @http.route('/odoo/odoo-<string:page>', type='http', auth='public', website=True)
    def dynamic_redirect(self, page, **kw):
        """
        Manage Web-pages Here:
        All the webpages with /odoo will be redirected to /odoo-erp
        """
        new_url = f'/odoo-erp/odoo-{page}'
        return request.redirect(new_url, code=301)

    @http.route('/odoo', type='http', auth='public', website=True)
    def dynamic_redirect_odoo(self, **kw):
        """
        Checks that if not internal user then redirect to odoo-erp
        """
        user = request.env.user
        if 'debug' in kw and kw['debug'] == '1':
            request.session.debug = True
            return request.redirect('/web?debug=1')
        elif user.has_group('base.group_user'):
            return request.redirect('/web')
        else:
            return request.redirect('/odoo-erp', code=301)