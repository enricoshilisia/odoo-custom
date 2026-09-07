from odoo import models, fields


class CpsInterviewPanelComment(models.Model):
    _name = 'cps.interview.panel.comment'
    _description = 'Per-Panelist Interview Comment'
    _order = 'applicant_id, user_id'

    session_id = fields.Many2one(
        'cps.interview.session', string='Session',
        required=True, ondelete='cascade', index=True,
    )
    applicant_id = fields.Many2one(
        'hr.applicant', string='Candidate', required=True, index=True,
    )
    user_id = fields.Many2one(
        'res.users', string='Panelist', required=True, index=True,
    )
    token_id = fields.Many2one(
        'cps.interview.token', string='Panelist Token', ondelete='set null',
    )
    comment = fields.Text(string='Comment')

    _uniq_comment = models.Constraint(
        'unique(session_id, applicant_id, user_id)',
        'This panelist already has a comment for this candidate.',
    )


class CpsInterviewSessionPanelComment(models.Model):
    _inherit = 'cps.interview.session'

    panel_comment_ids = fields.One2many(
        'cps.interview.panel.comment', 'session_id',
        string='Panelist Comments',
    )


class CpsInterviewSessionScoredBy(models.Model):
    _inherit = 'cps.interview.session'

    def get_scored_candidates(self, token):
        """Candidates this panelist has already scored (has Score rows for)."""
        self.ensure_one()
        return self.score_ids.filtered(
            lambda s: s.token_id.id == token.id
        ).mapped('applicant_id')

    def get_panelist_comment(self, token, applicant):
        """Existing comment text for this panelist+candidate, or ''."""
        self.ensure_one()
        pc = self.env['cps.interview.panel.comment'].sudo().search([
            ('session_id', '=', self.id),
            ('applicant_id', '=', applicant.id),
            ('user_id', '=', token.user_id.id),
        ], limit=1)
        return pc.comment if pc else ''
