
from odoo import api, http, models
from odoo.http import request, content_disposition
from odoo.addons.web.models.ir_http import ALLOWED_DEBUG_MODES
from odoo.tools.misc import str2bool


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _handle_debug(cls):
        # Store URL debug mode (might be empty) into session
        # Only 	Administration can move to debug mode
        if 'debug' in request.httprequest.args:
            debug_mode = []
            for debug in request.httprequest.args['debug'].split(','):
                if debug not in ALLOWED_DEBUG_MODES:
                    debug = '1' if str2bool(debug, debug) else ''
                debug_mode.append(debug)
            debug_mode = ','.join(debug_mode)

            user = False
            if request.session.uid:
                user = request.env["res.users"].sudo().browse(request.session.uid)
            # Write on session only when needed
            if debug_mode != request.session.debug and user and user.has_group('access_rights_management.group_can_able_to_debug'):
                request.session.debug = debug_mode
            else:
                request.session.debug = ''
