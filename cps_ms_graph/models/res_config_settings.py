# -*- coding: utf-8 -*-
from odoo import fields, models, _


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    cps_graph_tenant_id = fields.Char(
        string='Directory (tenant) ID',
        config_parameter='cps_ms_graph.tenant_id',
        help='Entra ID Directory (tenant) ID from the app registration overview.',
    )
    cps_graph_client_id = fields.Char(
        string='Application (client) ID',
        config_parameter='cps_ms_graph.client_id',
        help='Entra ID Application (client) ID from the app registration overview.',
    )
    cps_graph_client_secret = fields.Char(
        string='Client secret',
        config_parameter='cps_ms_graph.client_secret',
        help='Client secret VALUE (not the Secret ID). Shown only once when created.',
    )
    cps_graph_organizer_upn = fields.Char(
        string='Organizer account',
        config_parameter='cps_ms_graph.organizer_upn',
        help='Mailbox that will organize Teams meetings, e.g. '
             'erp@cloudproductivity-solutions.com. This account must be granted '
             'the Teams application access policy.',
    )

    def action_cps_graph_test_connection(self):
        """Test the values currently on screen, saved or not."""
        self.ensure_one()
        message = self.env['cps.graph.service']._test_connection(
            tenant_id=(self.cps_graph_tenant_id or '').strip(),
            client_id=(self.cps_graph_client_id or '').strip(),
            client_secret=(self.cps_graph_client_secret or '').strip(),
            organizer_upn=(self.cps_graph_organizer_upn or '').strip(),
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Microsoft Graph'),
                'message': message,
                'type': 'success',
                'sticky': True,
            },
        }
