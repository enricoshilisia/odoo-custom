import uuid
from odoo import models, fields, api, _


class CpsCandidateToken(models.Model):
    _name = 'cps.candidate.token'
    _description = 'Candidate Form Token'

    session_id = fields.Many2one(
        'cps.interview.session',
        string='Session',
        required=True,
        ondelete='cascade',
    )
    applicant_id = fields.Many2one(
        'hr.applicant',
        string='Candidate',
        required=True,
    )
    token = fields.Char(
        string='Token',
        default=lambda self: str(uuid.uuid4()),
        readonly=True,
        copy=False,
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('submitted', 'Submitted'),
    ], string='Status', default='pending')
    submitted_date = fields.Datetime(string='Submitted On', readonly=True)
    form_url = fields.Char(string='Form URL', compute='_compute_form_url')

    @api.depends('token')
    def _compute_form_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            rec.form_url = '%s/candidate/form/%s' % (base_url, rec.token)

    def action_send_email(self):
        self.ensure_one()
        template = self.env.ref(
            'cps_interview_scoring.email_template_candidate_form',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)

    def action_resend_email(self):
        self.action_send_email()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Email Sent'),
                'message': _('Form link resent to %s.') % self.applicant_id.partner_name,
                'type': 'success',
            }
        }
