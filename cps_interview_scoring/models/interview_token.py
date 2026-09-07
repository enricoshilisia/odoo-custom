import uuid
from markupsafe import Markup
from odoo import models, fields, api, _


class CpsInterviewToken(models.Model):
    _name = 'cps.interview.token'
    _description = 'Panelist Scoring Token'

    session_id = fields.Many2one(
        'cps.interview.session',
        string='Session',
        required=True,
        ondelete='cascade',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Panelist',
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
    scoring_url = fields.Char(
        string='Scoring URL',
        compute='_compute_scoring_url',
    )

    @api.depends('token')
    def _compute_scoring_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            rec.scoring_url = '%s/interview/score/%s' % (base_url, rec.token)

    def action_send_email(self):
        self.ensure_one()
        template = self.env.ref(
            'cps_interview_scoring.email_template_panelist_scoring',
            raise_if_not_found=False,
        )
        if template:
            template.send_mail(self.id, force_send=True)
        else:
            self.session_id.message_post(
                body=_(
                    'Scoring link for %s: <a href="%s">%s</a>'
                ) % (self.user_id.name, self.scoring_url, self.scoring_url),
                partner_ids=[self.user_id.partner_id.id],
                message_type='email',
            )

    def action_send_reminder_email(self, reminder_type, deadline):
        """Send a deadline reminder email to a pending panelist."""
        self.ensure_one()

        if reminder_type == '24h':
            urgency_text = 'You have <strong>24 hours</strong> remaining to submit your scores.'
            urgency_color = '#e67e22'
            urgency_label = '⏰ 24-Hour Reminder'
        else:
            urgency_text = 'You have <strong>less than 1 hour</strong> remaining. Please submit now.'
            urgency_color = '#e74c3c'
            urgency_label = '🚨 Final Reminder — 1 Hour Left'

        from datetime import timedelta
        eat_deadline = deadline + timedelta(hours=3)
        deadline_str = eat_deadline.strftime('%d %b %Y %H:%M EAT')

        body = f"""
        <div style="font-family:Arial,sans-serif;font-size:14px;color:#333;max-width:600px;">
            <div style="background:#2c3e50;color:#fff;padding:18px 24px;border-radius:6px 6px 0 0;">
                <h2 style="margin:0;font-size:18px;">{urgency_label}</h2>
                <p style="margin:4px 0 0;opacity:0.8;font-size:13px;">
                    Interview Scoring: {self.session_id.name}
                </p>
            </div>

            <div style="background:#fff;padding:24px;border:1px solid #eee;border-top:none;
                        border-radius:0 0 6px 6px;">
                <p>Dear <strong>{self.user_id.name}</strong>,</p>

                <div style="background:#fff8e1;border-left:4px solid {urgency_color};
                            padding:12px 16px;margin:16px 0;border-radius:4px;">
                    {urgency_text}
                </div>

                <table style="width:100%;border-collapse:collapse;margin:12px 0;">
                    <tr>
                        <td style="padding:6px;color:#666;width:40%;"><strong>Session:</strong></td>
                        <td style="padding:6px;">{self.session_id.name}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px;color:#666;"><strong>Job Position:</strong></td>
                        <td style="padding:6px;">{self.session_id.job_id.name}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px;color:#666;"><strong>Deadline:</strong></td>
                        <td style="padding:6px;color:{urgency_color};font-weight:bold;">
                            {deadline_str}
                        </td>
                    </tr>
                </table>

                <div style="text-align:center;margin:24px 0;">
                    <a href="{self.scoring_url}"
                       style="background-color:{urgency_color};color:#ffffff;padding:14px 36px;
                              border-radius:6px;text-decoration:none;font-size:15px;
                              font-weight:bold;display:inline-block;">
                        Submit My Scores Now
                    </a>
                </div>

                <p style="color:#e74c3c;font-size:12px;">
                    This link is unique to you. Do not share it with anyone.
                </p>
                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;"/>
                <p style="color:#aaa;font-size:12px;">Regards,<br/><strong>HR Team</strong></p>
            </div>
        </div>
        """

        subject = f'{"⏰" if reminder_type == "24h" else "🚨"} Reminder: Score by {deadline_str} — {self.session_id.name}'

        self.env['mail.mail'].sudo().create({
            'subject': subject,
            'email_to': self.user_id.email,
            'body_html': body,
            'auto_delete': True,
        }).send()

    def action_resend_email(self):
        self.action_send_email()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Email Sent'),
                'message': _('Scoring link resent to %s.') % self.user_id.name,
                'type': 'success',
            }
        }


    def unlink(self):
        for rec in self:
            session = rec.session_id
            if not session:
                continue
            score_count = self.env['cps.interview.score'].search_count([
                ('token_id', '=', rec.id)
            ])
            body = Markup(
                '<b style="color:#d9534f;">Panelist scoring link deleted</b> by %s '
                '— panelist: %s (%d score rows attached)'
                % (self.env.user.name, rec.user_id.name or '?', score_count)
            )
            session.message_post(body=body, subtype_xmlid='mail.mt_note')
        return super().unlink()
