from odoo import models, fields, api
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    cps_survey_input_ids = fields.One2many(
        'survey.user_input', 'applicant_id', string='Survey Responses',
    )
    cps_survey_sent  = fields.Boolean(string='Survey Sent', default=False)
    cps_survey_state = fields.Selection([
        ('not_sent',    'Not Sent'),
        ('sent',        'Sent'),
        ('in_progress', 'In Progress / Pending Manual'),
        ('passed',      'Passed'),
        ('failed',      'Failed'),
    ], string='Survey Status', default='not_sent')

    cps_q3_score   = fields.Integer(string='Q3: CIO/CTO Engagement (/10)', default=0, tracking=True)
    cps_q11_score  = fields.Integer(string='Q11: CRM Tools (/5)', default=0, tracking=True)
    cps_q12_score  = fields.Integer(string='Q12: ICT Lifecycle (/10)', default=0, tracking=True)
    cps_auto_score = fields.Integer(string='Auto Score (/75)', default=0, readonly=True)
    cps_total_score = fields.Integer(
        string='Total Score (/100)', default=0, readonly=True,
        compute='_compute_total_score', store=True,
    )
    cps_score_recommendation = fields.Char(string='Recommendation', readonly=True)
    cps_scored_by   = fields.Many2one('res.users', string='Scored By', readonly=True)
    cps_scored_date = fields.Datetime(string='Scored On', readonly=True)

    cps_q3_response  = fields.Text(string='Q3 Response', compute='_compute_manual_responses', store=False)
    cps_q11_response = fields.Text(string='Q11 Response', compute='_compute_manual_responses', store=False)
    cps_q12_response = fields.Text(string='Q12 Response', compute='_compute_manual_responses', store=False)

    @api.depends('cps_auto_score', 'cps_q3_score', 'cps_q11_score', 'cps_q12_score')
    def _compute_total_score(self):
        for rec in self:
            rec.cps_total_score = (rec.cps_auto_score + rec.cps_q3_score +
                                    rec.cps_q11_score + rec.cps_q12_score)

    def _compute_manual_responses(self):
        for rec in self:
            q3 = q11 = q12 = ''
            for sui in rec.cps_survey_input_ids:
                if sui.state == 'done':
                    for line in sui.user_input_line_ids:
                        seq = line.question_id.sequence
                        if seq == 12 and line.value_text_box:
                            q3 = line.value_text_box
                        elif seq == 20 and line.value_text_box:
                            q11 = line.value_text_box
                        elif seq == 21 and line.value_text_box:
                            q12 = line.value_text_box
            rec.cps_q3_response  = q3 or 'No response provided'
            rec.cps_q11_response = q11 or 'No response provided'
            rec.cps_q12_response = q12 or 'No response provided'

    def action_cps_finalize_score(self):
        self.ensure_one()
        if not (0 <= self.cps_q3_score <= 10):
            raise models.ValidationError("Q3 score must be 0–10.")
        if not (0 <= self.cps_q11_score <= 5):
            raise models.ValidationError("Q11 score must be 0–5.")
        if not (0 <= self.cps_q12_score <= 10):
            raise models.ValidationError("Q12 score must be 0–10.")

        total = self.cps_total_score

        if self.cps_q12_score < 5:
            stage = self.env['hr.recruitment.stage'].browse(9)
            self.write({'stage_id': stage.id, 'cps_survey_state': 'failed',
                        'cps_score_recommendation': 'Disqualified – ICT lifecycle below minimum'})
            self.message_post(
                body=(f'<div style="font-family:Arial,sans-serif;font-size:13px;">'
                      f'<h3 style="color:#d9534f;">&#9940; Disqualified after Manual Scoring</h3>'
                      f'<p>Q12 score: <strong>{self.cps_q12_score}/10</strong> — minimum 5 required.</p>'
                      f'<p>Total: <strong>{total}/100</strong></p></div>'),
                subtype_xmlid='mail.mt_note',
            )
            return

        if total >= 90:
            rec, stage_id, state, color, icon = ('Highly Recommended (90–100)', 2, 'passed', '#5cb85c', '&#127942;')
        elif total >= 80:
            rec, stage_id, state, color, icon = ('Recommended (80–89)', 2, 'passed', '#5cb85c', '&#9989;')
        elif total >= 70:
            rec, stage_id, state, color, icon = ('Consider for Interview (70–79)', 2, 'passed', '#f0ad4e', '&#128374;')
        else:
            rec, stage_id, state, color, icon = ('Not Recommended (<70)', 9, 'failed', '#d9534f', '&#10060;')

        self.write({'stage_id': stage_id, 'cps_survey_state': state,
                    'cps_score_recommendation': rec,
                    'cps_scored_by':   self.env.uid,
                    'cps_scored_date': fields.Datetime.now()})

        self.message_post(
            body=(f'<div style="font-family:Arial,sans-serif;font-size:13px;">'
                  f'<h3 style="color:{color};">{icon} Assessment Finalized</h3>'
                  f'<table style="border-collapse:collapse;width:100%;font-size:12px;">'
                  f'<tr><td style="padding:5px 8px;border:1px solid #ddd;">Auto Score</td>'
                  f'<td style="padding:5px 8px;border:1px solid #ddd;">{self.cps_auto_score}/75</td></tr>'
                  f'<tr><td style="padding:5px 8px;border:1px solid #ddd;">Q3 – CIO/CTO</td>'
                  f'<td style="padding:5px 8px;border:1px solid #ddd;">{self.cps_q3_score}/10</td></tr>'
                  f'<tr><td style="padding:5px 8px;border:1px solid #ddd;">Q11 – CRM Tools</td>'
                  f'<td style="padding:5px 8px;border:1px solid #ddd;">{self.cps_q11_score}/5</td></tr>'
                  f'<tr><td style="padding:5px 8px;border:1px solid #ddd;">Q12 – ICT Lifecycle</td>'
                  f'<td style="padding:5px 8px;border:1px solid #ddd;">{self.cps_q12_score}/10</td></tr>'
                  f'<tr style="background:#f0f0f0;font-weight:bold;">'
                  f'<td style="padding:5px 8px;border:1px solid #ddd;">TOTAL</td>'
                  f'<td style="padding:5px 8px;border:1px solid #ddd;color:{color};">{total}/100</td></tr>'
                  f'</table>'
                  f'<p style="font-weight:bold;color:{color};">Recommendation: {rec}</p></div>'),
            subtype_xmlid='mail.mt_note',
        )
        _logger.info('CPS: %s finalized. Total: %s/100. %s', self.partner_name, total, rec)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._cps_handle_stage_change()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'stage_id' in vals:
            for record in self:
                record._cps_handle_stage_change()
        return res

    def _cps_handle_stage_change(self):
        if not self.job_id or not self.email_from:
            return
        config = self.env['cps.recruitment.survey.config'].search([
            ('job_id', '=', self.job_id.id),
            ('stage_id', '=', self.stage_id.id),
        ], limit=1)
        if not config:
            return
        existing = self.env['survey.user_input'].search([
            ('survey_id', '=', config.survey_id.id),
            ('applicant_id', '=', self.id),
        ], limit=1)
        if existing:
            return
        self._cps_send_survey(config)

    def _cps_send_survey(self, config):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        company  = self.env['res.company'].browse(1)
        btn_color = company.secondary_color or '#7EBB0E'

        user_input = self.env['survey.user_input'].create({
            'survey_id':    config.survey_id.id,
            'partner_id':   self.partner_id.id if self.partner_id else False,
            'email':        self.email_from,
            'applicant_id': self.id,
        })
        survey_url = base_url + user_input.get_start_url()

        self.env['mail.mail'].create({
            'subject':    f"{self.job_id.name} – {config.survey_id.title} | Cloud Productivity Solutions",
            'email_to':   self.email_from,
            'email_from': 'notifications@cloudproductivity-solutions.com',
            'body_html':  (f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">'
                           f'<p>Dear {self.partner_name or "Applicant"},</p>'
                           f'<p>Thank you for applying for <strong>{self.job_id.name}</strong> '
                           f'at Cloud Productivity Solutions Limited.</p>'
                           f'<p>Please complete the screening assessment:</p>'
                           f'<div style="margin:24px 0;">'
                           f'<a href="{survey_url}" style="background:{btn_color};color:white;'
                           f'padding:12px 24px;text-decoration:none;border-radius:5px;font-weight:bold;">'
                           f'Start Assessment</a></div>'
                           f'<p>If the button does not work: <a href="{survey_url}">{survey_url}</a></p>'
                           f'<ul><li>Answer all questions honestly</li>'
                           f'<li>You can only submit once</li></ul>'
                           f'<p>Best regards,<br/><strong>HR Team</strong><br/>'
                           f'Cloud Productivity Solutions Limited</p></div>'),
        }).send()

        self.write({'cps_survey_sent': True, 'cps_survey_state': 'sent'})
        _logger.info('CPS: Survey sent to %s for %s', self.email_from, self.job_id.name)
