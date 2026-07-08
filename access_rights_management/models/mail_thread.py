from odoo import models


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    def _notify_get_recipients_classify(self, message, recipients_data,
                                        model_description, msg_vals=None):
        """
        If the object is a Signature Request, return an empty list.
        This ensures that two emails are not sent (the system email is not sent here, only our customized email is sent)
        """
        res = super(MailThread, self)._notify_get_recipients_classify(message, recipients_data,
                                        model_description, msg_vals=None)
        if model_description == 'Signature Request':
            return []
        return res