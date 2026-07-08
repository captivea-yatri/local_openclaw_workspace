from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    manager_approval_required = fields.Boolean(string="Manager Approval Required")  # new field

    def action_confirm(self):
        self.ensure_one()

        # Check purchase type has lines
        if self.approval_type == 'purchase' and not self.product_line_ids:
            raise UserError(_("You cannot create an empty purchase request."))

        # Check manager approval
        if self.manager_approval_required:
            employee = self.env['hr.employee'].search(
                [('user_id', '=', self.request_owner_id.id),
                 ('company_id', '=', self.env.company.id)], limit=1
            )
            if not employee.parent_id:
                raise UserError(
                    _('This request needs to be approved by your manager. '
                      'There is no manager linked to your employee profile.')
                )
            if not employee.parent_id.user_id:
                raise UserError(
                    _('This request needs to be approved by your manager. '
                      'Your manager has no linked user.')
                )
            if not self.approver_ids.filtered(lambda a: a.user_id.id == employee.parent_id.user_id.id):
                raise UserError(
                    _('This request needs to be approved by your manager. '
                      'Your manager is not in the approvers list.')
                )

        # Minimum approvers check
        if len(self.approver_ids) < self.approval_minimum:
            raise UserError(
                _("You have to add at least %s approvers to confirm your request.") % self.approval_minimum
            )

        # Document check
        if self.requirer_document == 'required' and not self.attachment_number:
            raise UserError(_("You have to attach at least one document."))

        # Determine approvers
        approvers = self.approver_ids
        if self.approver_sequence:
            approvers = approvers.filtered(lambda a: a.status in ['new', 'pending', 'waiting'])
            if len(approvers) > 1:
                approvers[1:].sudo().write({'status': 'waiting'})
            approvers = approvers[:1] if approvers and approvers[0].status != 'pending' else self.env['approval.approver']
        else:
            approvers = approvers.filtered(lambda a: a.status == 'new')

        # Create activity & update status
        approvers._create_activity()
        approvers.sudo().write({'status': 'pending'})
        self.sudo().write({'date_confirmed': fields.Datetime.now()})
