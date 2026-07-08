import logging

from odoo import models, _, Command
from odoo.exceptions import AccessError, UserError
from odoo.tools import frozendict

_logger = logging.getLogger('odoo.addons.base.partner.merge')


class PortalWizard(models.TransientModel):
    _inherit = 'portal.wizard'

    def _action_open_modal(self):
        if self.env.user.has_group('access_rights_management.role_operation') or self.env.user.has_group(
                'access_rights_management.role_operation_on_boarder') or self.env.user.has_group(
            'access_rights_management.role_team_manager') or self.env.user.has_group(
            'access_rights_management.role_team_director'):
            parent = self.partner_ids.filtered(lambda x: x.is_company) if any(
                partner.is_company for partner in self.partner_ids) else self.partner_ids
            if self.env.uid not in parent.accessible_user_ids.ids and self.env.uid not in parent.parent_id.accessible_user_ids.ids:
                raise AccessError(
                    _('You are not able to grant portal access for this customer, Please create access request!'))
            else:
                return super(PortalWizard, self)._action_open_modal()
        else:
            return super(PortalWizard, self)._action_open_modal()


class PortalWizardUser(models.TransientModel):
    _inherit = 'portal.wizard.user'

    def action_grant_access(self):
        context = dict(self._context)
        context.update({'from_portal_wizard': True})
        self.env.context = frozendict(context)
        for rec in self:
            if not rec.partner_id.user_allowed_company_ids:
                rec.partner_id.user_allowed_company_ids = [(4, self.env.company.id)]
        res = super(PortalWizardUser, self).action_grant_access()
        for wizard_user in self:
            if wizard_user.partner_id and wizard_user.partner_id.user_ids:
                parent_id = wizard_user.partner_id.parent_id if wizard_user.partner_id.parent_id else wizard_user.partner_id
                company = parent_id.x_studio_customer_of if parent_id.x_studio_customer_of else self.env.company
                if parent_id.x_studio_customer_of and parent_id.x_studio_customer_of not in self.env['res.company'].browse(self.env.context.get('allowed_company_ids', [])):
                    raise AccessError(
                        _("Please make sure the company " + parent_id.x_studio_customer_of.name + " is selected before proceeding!"))
                wizard_user.partner_id.user_ids[0].sudo().write({
                    'company_ids': [(6, 0, company.ids)],
                    'company_id': company.id,
                })
        return res


class MergePartnerAutomatic(models.TransientModel):
    _inherit = 'base.partner.merge.automatic.wizard'

    def _merge(self, partner_ids, dst_partner=None, extra_checks=True):
        """
        Override the method because we need to merge more than 3 partners at a time
        """

        # marketing director can be used to bypass extra checks
        if self.env.is_admin() or self.env.user.has_group('access_rights_management.role_vp_of_marketing'):
            extra_checks = False

        Partner = self.env['res.partner']
        partner_ids = Partner.browse(partner_ids).exists()
        if len(partner_ids) < 2:
            return

        # Remove restriction on the number of partner to merge
        # if len(partner_ids) > 3:
        #     raise UserError(_("For safety reasons, you cannot merge more than 3 contacts together. You can re-open the wizard several times if needed."))

        # check if the list of partners to merge contains child/parent relation
        child_ids = self.env['res.partner']
        for partner_id in partner_ids:
            child_ids |= Partner.search([('id', 'child_of', [partner_id.id])]) - partner_id
        if partner_ids & child_ids:
            raise UserError(_("You cannot merge a contact with one of his parent."))

        if extra_checks and len(set(partner.email for partner in partner_ids)) > 1:
            raise UserError(_("All contacts must have the same email. Only the Administrator can merge contacts with different emails."))

        # remove dst_partner from partners to merge
        if dst_partner and dst_partner in partner_ids:
            src_partners = partner_ids - dst_partner
        else:
            ordered_partners = self._get_ordered_partner(partner_ids.ids)
            dst_partner = ordered_partners[-1]
            src_partners = ordered_partners[:-1]
        _logger.info("dst_partner: %s", dst_partner.id)

        # Make the company of all related users consistent with destination partner company
        if dst_partner.company_id:
            partner_ids.mapped('user_ids').sudo().write({
                'company_ids': [Command.link(dst_partner.company_id.id)],
                'company_id': dst_partner.company_id.id
            })

        # call sub methods to do the merge
        self._update_foreign_keys(src_partners, dst_partner)
        self._update_reference_fields(src_partners, dst_partner)
        self._update_values(src_partners, dst_partner)

        self.env.add_to_compute(dst_partner._fields['partner_share'], dst_partner)

        self._log_merge_operation(src_partners, dst_partner)

        # delete source partner, since they are merged
        src_partners.unlink()