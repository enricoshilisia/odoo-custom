from markupsafe import Markup
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class CpsInterviewScore(models.Model):
    _name = 'cps.interview.score'
    _description = 'Candidate Interview Score'
    _inherit = ['mail.thread']

    session_id = fields.Many2one(
        'cps.interview.session',
        string='Session',
        required=True,
        ondelete='cascade',
    )
    token_id = fields.Many2one(
        'cps.interview.token',
        string='Panelist Token',
        required=True,
        ondelete='restrict',
    )
    applicant_id = fields.Many2one(
        'hr.applicant',
        string='Candidate',
        required=True,
    )
    question_id = fields.Many2one(
        'cps.interview.question',
        string='Question',
        required=True,
    )
    score = fields.Integer(string='Score', required=True, default=1, tracking=True)

    @api.constrains('score')
    def _check_score(self):
        for rec in self:
            if rec.score < 1 or rec.score > 5:
                raise ValidationError('Score must be between 1 and 5.')


    def unlink(self):
        from collections import defaultdict
        by_session = defaultdict(list)
        for rec in self:
            by_session[rec.session_id].append(rec)
        for session, recs in by_session.items():
            if not session:
                continue
            cands = {}
            for r in recs:
                key = (r.token_id.user_id.name or '?',
                       r.applicant_id.partner_name or '?')
                cands[key] = cands.get(key, 0) + 1
            lines = ''.join(
                '<li>%s — %s (%d score rows)</li>' % (p, c, n)
                for (p, c), n in sorted(cands.items())
            )
            body = Markup(
                '<b style="color:#d9534f;">Interview scores deleted</b> by %s<ul>%s</ul>'
                % (self.env.user.name, lines)
            )
            session.message_post(body=body, subtype_xmlid='mail.mt_note')
        return super().unlink()
