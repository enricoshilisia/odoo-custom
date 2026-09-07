from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class CpsRecruitmentSurveyConfig(models.Model):
    _name = 'cps.recruitment.survey.config'
    _description = 'Recruitment Survey Configuration'
    _order = 'sequence asc'

    sequence = fields.Integer(string='Sequence', default=10)
    job_id = fields.Many2one(
        'hr.job',
        string='Job Position',
        required=True,
        ondelete='cascade',
    )
    stage_id = fields.Many2one(
        'hr.recruitment.stage',
        string='Trigger Stage',
        required=True,
    )
    survey_id = fields.Many2one(
        'survey.survey',
        string='Survey',
        required=True,
    )
    passing_score = fields.Float(
        string='Pass Mark (%) — Legacy',
        default=70.0,
        help='Used only if no Score Brackets are configured on the survey.',
    )
    on_pass_stage_id = fields.Many2one(
        'hr.recruitment.stage',
        string='Move to Stage on Pass — Legacy',
        help='Used only if no Score Brackets are configured on the survey.',
    )
    is_manual = fields.Boolean(
        string='Manual Review',
        default=False,
        help='If enabled, no auto-move on completion. HR reviews manually.',
    )

    def _get_gm_email(self):
        """Dynamically find General Manager email from hr.employee job position."""
        # First try: active employee with job position General Manager
        gm_employee = self.env['hr.employee'].sudo().search([
            ('job_id.name', 'ilike', 'General Manager'),
            ('active', '=', True),
        ], limit=1)
        if gm_employee and gm_employee.work_email:
            _logger.info('CPS: GM email found via employee: %s', gm_employee.work_email)
            return gm_employee.work_email

        # Second try: user linked to employee with GM job position
        gm_user = self.env['res.users'].sudo().search([
            ('employee_ids.job_id.name', 'ilike', 'General Manager'),
            ('active', '=', True),
        ], limit=1)
        if gm_user and gm_user.email:
            _logger.info('CPS: GM email found via user: %s', gm_user.email)
            return gm_user.email

        # Fallback: system parameter
        fallback = self.env['ir.config_parameter'].sudo().get_param(
            'cps_recruitment.gm_email', default=False
        )
        if fallback:
            _logger.info('CPS: GM email from system parameter: %s', fallback)
            return fallback

        _logger.warning(
            'CPS: GM email not found. Ensure an employee with job position '
            '"General Manager" exists and has a work email set.'
        )
        return False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._cps_notify_gm_survey_assigned()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'survey_id' in vals or 'job_id' in vals:
            for record in self:
                record._cps_notify_gm_survey_assigned()
        return res

    def _cps_notify_gm_survey_assigned(self):
        if not self.survey_id or not self.job_id:
            return

        gm_email = self._get_gm_email()
        if not gm_email:
            return

        survey   = self.survey_id
        job      = self.job_id
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        job_url  = f"{base_url}/web#id={job.id}&model=hr.job&view_type=form"

        # Bracket summary
        brackets = survey.cps_score_bracket_ids
        if brackets:
            rows = ''.join(
                f'<tr>'
                f'<td style="padding:5px 8px;border:1px solid #ddd;">{b.label}</td>'
                f'<td style="padding:5px 8px;border:1px solid #ddd;">{b.min_score}–{b.max_score}</td>'
                f'<td style="padding:5px 8px;border:1px solid #ddd;">{b.stage_id.name}</td>'
                f'</tr>'
                for b in brackets
            )
            bracket_html = f'''
                <h4>Score Brackets:</h4>
                <table style="border-collapse:collapse;width:100%;font-size:12px;">
                    <tr style="background:#f5f5f5;">
                        <th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">Label</th>
                        <th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">Range</th>
                        <th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">Stage</th>
                    </tr>
                    {rows}
                </table>
            '''
        else:
            bracket_html = '<p style="color:#f0ad4e;">&#9888; No score brackets configured yet.</p>'

        # Manual questions
        manual_qs = survey.get_cps_manual_questions()
        if manual_qs:
            items = ''.join(
                f'<li>{q.title} — Max: {q.cps_manual_max} marks</li>'
                for q in manual_qs
            )
            manual_html = f'<h4>Manual Scoring Questions:</h4><ul>{items}</ul>'
        else:
            manual_html = ''

        subject = f"New Prescreening Survey Assigned — {job.name}"
        body = f'''
            <div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">
                <h2 style="color:#2680af;">&#128203; Prescreening Survey Assigned</h2>
                <p>The HR team has configured a prescreening survey for a job position.</p>
                <table style="border-collapse:collapse;width:100%;margin:16px 0;">
                    <tr>
                        <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Job Position</td>
                        <td style="padding:8px;border:1px solid #ddd;">{job.name}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Survey</td>
                        <td style="padding:8px;border:1px solid #ddd;">{survey.title}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Trigger Stage</td>
                        <td style="padding:8px;border:1px solid #ddd;">{self.stage_id.name}</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">Manual Review</td>
                        <td style="padding:8px;border:1px solid #ddd;">
                            {'Yes — HR will score manually' if self.is_manual else 'No — Fully automated'}
                        </td>
                    </tr>
                </table>
                {bracket_html}
                {manual_html}
                <div style="margin:20px 0;">
                    <a href="{job_url}"
                       style="background:#7EBB0E;color:white;padding:12px 24px;
                              text-decoration:none;border-radius:5px;font-weight:bold;">
                        View Job Position
                    </a>
                </div>
                <p>Best regards,<br/><strong>CPS Recruitment System</strong></p>
            </div>
        '''

        self.env['mail.mail'].create({
            'subject':    subject,
            'email_to':   gm_email,
            'email_from': 'notifications@cloudproductivity-solutions.com',
            'body_html':  body,
        }).send()

        _logger.info(
            'CPS: Survey "%s" assigned to job "%s" — GM notified at %s',
            survey.title, job.name, gm_email
        )
