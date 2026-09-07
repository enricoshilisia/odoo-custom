from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class CpsInterviewSession(models.Model):
    _name = 'cps.interview.session'
    _description = 'Interview Scoring Session'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Session Name', required=True, tracking=True)
    job_id = fields.Many2one('hr.job', string='Job Position', required=True, tracking=True)
    interview_date = fields.Date(string='Interview Date', tracking=True)
    deadline = fields.Datetime(
        string='Scoring Deadline',
        tracking=True,
        help='Panelists will receive reminder emails 24 hours and 1 hour before this deadline.',
    )
    reminder_24h_sent = fields.Boolean(string='24h Reminder Sent', default=False, copy=False)
    reminder_1h_sent = fields.Boolean(string='1h Reminder Sent', default=False, copy=False)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Open for Scoring'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', tracking=True)

    applicant_ids = fields.Many2many(
        'hr.applicant',
        'cps_session_applicant_rel',
        'session_id', 'applicant_id',
        string='Candidates',
    )
    panelist_ids = fields.Many2many(
        'res.users',
        'cps_session_panelist_rel',
        'session_id', 'user_id',
        string='Panelists',
    )
    question_ids = fields.One2many('cps.interview.question', 'session_id', string='Questions')
    token_ids = fields.One2many('cps.interview.token', 'session_id', string='Panelist Tokens')
    score_ids = fields.One2many('cps.interview.score', 'session_id', string='Scores')
    candidate_token_ids = fields.One2many('cps.candidate.token', 'session_id', string='Candidate Tokens')
    candidate_response_ids = fields.One2many('cps.candidate.response', 'session_id', string='Candidate Responses')

    total_panelists = fields.Integer(string='Total Panelists', compute='_compute_totals')
    submitted_count = fields.Integer(string='Panelists Submitted', compute='_compute_totals')
    results_html = fields.Html(string='Results', compute='_compute_results_html', sanitize=False)
    divergence_threshold = fields.Integer(
        string='Divergence Alert Gap', default=20,
        help='Flag a candidate for review when the gap between the highest and '
             'lowest panelist total exceeds this many points.')

    @api.depends('token_ids.state', 'applicant_ids', 'question_ids', 'divergence_threshold')
    def _compute_results_html(self):
        for rec in self:
            if not rec.applicant_ids or not rec.question_ids:
                rec.results_html = '<p style="color:#999;">No candidates or questions defined yet.</p>'
                continue
            if not rec.score_ids:
                rec.results_html = '<p style="color:#999;">No scores submitted yet.</p>'
                continue

            panelists = rec.token_ids.sorted(lambda t: t.user_id.name or '')
            questions = rec.question_ids.sorted('sequence')
            threshold = rec.divergence_threshold or 20

            # ----- per candidate aggregates -----
            cand_rows = []
            for a in rec.applicant_ids:
                per_panelist = {}
                for t in panelists:
                    rows = rec.score_ids.filtered(
                        lambda s: s.applicant_id.id == a.id and s.token_id.id == t.id)
                    per_panelist[t.id] = sum(rows.mapped('score')) if rows else None
                totals = [v for v in per_panelist.values() if v is not None]
                avg = (sum(totals) / len(totals)) if totals else 0
                spread = (max(totals) - min(totals)) if len(totals) > 1 else 0
                cand_rows.append({
                    'applicant': a,
                    'per_panelist': per_panelist,
                    'avg': avg,
                    'spread': spread,
                    'flag': spread > threshold,
                })

            cand_rows.sort(key=lambda r: r['avg'], reverse=True)

            html = []
            # ---- ranked summary ----
            html.append('<h3 style="margin:0 0 8px;">Ranked Results</h3>')
            html.append('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:18px;">')
            html.append('<tr style="background:#7ebb0e;color:#fff;">'
                        '<th style="padding:6px 8px;text-align:left;">#</th>'
                        '<th style="padding:6px 8px;text-align:left;">Candidate</th>')
            for t in panelists:
                html.append('<th style="padding:6px 8px;">%s</th>' % (t.user_id.name or '?'))
            html.append('<th style="padding:6px 8px;">Average</th>'
                        '<th style="padding:6px 8px;">Spread</th></tr>')
            for i, r in enumerate(cand_rows, 1):
                bg = '#fdecea' if r['flag'] else ('#f7f9fa' if i % 2 else '#fff')
                html.append('<tr style="background:%s;border-bottom:1px solid #e6eaed;">' % bg)
                html.append('<td style="padding:6px 8px;">%d</td>' % i)
                name = r['applicant'].candidate_id.partner_name or '?'
                flag = ' <span style="color:#d9534f;font-weight:bold;">&#9888; review</span>' if r['flag'] else ''
                html.append('<td style="padding:6px 8px;">%s%s</td>' % (name, flag))
                for t in panelists:
                    v = r['per_panelist'].get(t.id)
                    cell = '&ndash;' if v is None else str(v)
                    html.append('<td style="padding:6px 8px;text-align:center;">%s</td>' % cell)
                html.append('<td style="padding:6px 8px;text-align:center;font-weight:bold;">%.1f</td>' % r['avg'])
                sp = r['spread']
                spc = '#d9534f' if r['flag'] else '#6b7280'
                html.append('<td style="padding:6px 8px;text-align:center;color:%s;">%d</td></tr>' % (spc, sp))
            html.append('</table>')

            # ---- full grid per candidate ----
            html.append('<h3 style="margin:14px 0 8px;">Panelist Breakdown by Question</h3>')
            for r in cand_rows:
                a = r['applicant']
                name = a.candidate_id.partner_name or '?'
                border = '2px solid #d9534f' if r['flag'] else '1px solid #e6eaed'
                head_bg = '#fdecea' if r['flag'] else '#f7f9fa'
                banner = ''
                if r['flag']:
                    banner = ('<div style="color:#d9534f;font-weight:bold;font-size:12px;padding:4px 0;">'
                              '&#9888; Panelist divergence (gap %d &gt; threshold %d) &mdash; review before deciding.'
                              '</div>' % (r['spread'], threshold))
                html.append('<div style="border:%s;border-radius:6px;padding:10px 12px;margin-bottom:12px;">' % border)
                html.append('<div style="font-weight:bold;background:%s;padding:4px 6px;margin:-10px -12px 8px;'
                            'border-radius:6px 6px 0 0;">%s</div>' % (head_bg, name))
                html.append(banner)
                html.append('<table style="width:100%;border-collapse:collapse;font-size:12px;">')
                html.append('<tr style="border-bottom:1px solid #ddd;"><th style="text-align:left;padding:3px 6px;">Question</th>')
                for t in panelists:
                    html.append('<th style="padding:3px 6px;">%s</th>' % (t.user_id.name or '?'))
                html.append('</tr>')
                for q in questions:
                    html.append('<tr style="border-bottom:1px solid #f0f2f4;">')
                    html.append('<td style="padding:3px 6px;">%s</td>' % (q.name or ''))
                    for t in panelists:
                        srow = rec.score_ids.filtered(
                            lambda s: s.applicant_id.id == a.id and s.token_id.id == t.id and s.question_id.id == q.id)
                        val = str(srow[0].score) if srow else '&ndash;'
                        html.append('<td style="padding:3px 6px;text-align:center;">%s</td>' % val)
                    html.append('</tr>')
                # totals row
                html.append('<tr style="border-top:2px solid #ccc;font-weight:bold;">')
                html.append('<td style="padding:4px 6px;">Total</td>')
                for t in panelists:
                    v = r['per_panelist'].get(t.id)
                    html.append('<td style="padding:4px 6px;text-align:center;">%s</td>' % ('&ndash;' if v is None else v))
                html.append('</tr>')
                html.append('</table></div>')

            rec.results_html = ''.join(html)

    @api.depends('token_ids', 'token_ids.state')
    def _compute_totals(self):
        for rec in self:
            rec.total_panelists = len(rec.token_ids)
            rec.submitted_count = len(rec.token_ids.filtered(lambda t: t.state == 'submitted'))

    def action_load_candidates(self):
        self.ensure_one()
        if not self.job_id:
            raise UserError(_('Please select a Job Position first.'))
        interview_stages = self.env['hr.recruitment.stage'].search([('name', 'ilike', 'interview')])
        applicants = self.env['hr.applicant'].search([
            ('job_id', '=', self.job_id.id),
            ('stage_id', 'in', interview_stages.ids),
            ('active', '=', True),
        ])
        if not applicants:
            raise UserError(_(
                'No candidates found in an Interview stage for "%s".\n'
                'You can add candidates manually.'
            ) % self.job_id.name)
        self.applicant_ids = [(4, a.id) for a in applicants]
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'cps.interview.session',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_job_id': self.job_id.id,
            }
        }

    def action_open_session(self):
        self.ensure_one()
        if not self.applicant_ids:
            raise UserError(_('Please add at least one candidate.'))
        if not self.panelist_ids:
            raise UserError(_('Please add at least one panelist.'))
        if not self.question_ids:
            raise UserError(_('Please add at least one question.'))
        existing_users = self.token_ids.mapped('user_id')
        for user in self.panelist_ids:
            if user not in existing_users:
                self.env['cps.interview.token'].create({
                    'session_id': self.id,
                    'user_id': user.id,
                })
        self.state = 'open'
        for token in self.token_ids:
            token.action_send_email()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Session Opened'),
                'message': _('Scoring links have been sent to all panelists.'),
                'type': 'success',
            }
        }

    def action_close_session(self):
        self.ensure_one()
        self.state = 'closed'

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_view_results(self):
        self.ensure_one()
        return self.env.ref('cps_interview_scoring.action_interview_results_report').report_action(self)

    def action_send_candidate_forms(self):
        self.ensure_one()
        if not self.applicant_ids:
            raise UserError(_('No candidates in this session.'))

        existing = self.candidate_token_ids.mapped('applicant_id')
        sent = 0
        for applicant in self.applicant_ids:
            if applicant not in existing:
                if not applicant.email_from:
                    continue
                token = self.env['cps.candidate.token'].create({
                    'session_id': self.id,
                    'applicant_id': applicant.id,
                })
                token.action_send_email()
                sent += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Forms Sent'),
                'message': _('Candidate forms sent to %d candidate(s).') % sent,
                'type': 'success',
            }
        }

    def get_results(self):
        self.ensure_one()
        results = []
        for applicant in self.applicant_ids:
            candidate_data = {
                'applicant': applicant,
                'question_scores': [],
                'total': 0,
            }
            for question in self.question_ids:
                scores = self.score_ids.filtered(
                    lambda s, a=applicant, q=question: s.applicant_id == a and s.question_id == q
                ).mapped('score')
                avg = round(sum(scores) / len(scores), 2) if scores else 0
                candidate_data['question_scores'].append(avg)
                candidate_data['total'] += avg
            candidate_data['total'] = round(candidate_data['total'], 2)
            results.append(candidate_data)
        results.sort(key=lambda x: x['total'], reverse=True)
        return results

    @api.model
    def _cron_send_deadline_reminders(self):
        """Cron job — runs every hour. Sends 24h and 1h deadline reminders."""
        from datetime import datetime, timedelta
        now = datetime.utcnow()

        # Window: sessions open, with a deadline, not fully submitted
        open_sessions = self.search([
            ('state', '=', 'open'),
            ('deadline', '!=', False),
        ])

        for session in open_sessions:
            # Skip if all panelists already submitted
            pending_tokens = session.token_ids.filtered(lambda t: t.state == 'pending')
            if not pending_tokens:
                continue

            deadline = fields.Datetime.from_string(session.deadline)
            time_to_deadline = deadline - now
            hours_left = time_to_deadline.total_seconds() / 3600

            # 24h reminder — between 23h and 25h before deadline
            if 23 <= hours_left <= 25 and not session.reminder_24h_sent:
                for token in pending_tokens:
                    token.action_send_reminder_email('24h', deadline)
                session.reminder_24h_sent = True
                _logger.info('24h reminder sent for session: %s', session.name)

            # 1h reminder — between 0.5h and 1.5h before deadline
            elif 0.5 <= hours_left <= 1.5 and not session.reminder_1h_sent:
                for token in pending_tokens:
                    token.action_send_reminder_email('1h', deadline)
                session.reminder_1h_sent = True
                _logger.info('1h reminder sent for session: %s', session.name)


class CpsInterviewSessionMultiDay(models.Model):
    _inherit = 'cps.interview.session'

    interviewed_applicant_ids = fields.Many2many(
        'hr.applicant',
        'cps_session_interviewed_rel',
        'session_id', 'applicant_id',
        string='Interviewed Candidates',
        help='Candidates who have actually been interviewed and are ready to be scored. '
             'Panelists only see these on their scoring page.',
    )

    def get_scorable_candidates(self, token):
        """Interviewed candidates this panelist has NOT yet scored."""
        self.ensure_one()
        already = self.score_ids.filtered(
            lambda s: s.token_id.id == token.id
        ).mapped('applicant_id')
        return self.interviewed_applicant_ids - already


    def get_detailed_report_data(self):
        """Assemble everything the detailed PDF needs into one structure."""
        self.ensure_one()
        panelists = self.token_ids.sorted(lambda t: t.user_id.name or '')
        questions = self.question_ids.sorted('sequence')
        threshold = self.divergence_threshold or 20

        candidates = []
        # Report on candidates who have at least one panel score, pulled from
        # the scores themselves so removed candidates (with scores) still appear.
        scored_applicants = self.score_ids.mapped('applicant_id')
        for a in scored_applicants:
            per = {}
            for t in panelists:
                rows = self.score_ids.filtered(
                    lambda s: s.applicant_id.id == a.id and s.token_id.id == t.id)
                per[t.id] = sum(rows.mapped('score')) if rows else None
            totals = [v for v in per.values() if v is not None]
            if not totals:
                continue
            avg = sum(totals) / len(totals)
            spread = (max(totals) - min(totals)) if len(totals) > 1 else 0
            # per-question grid
            grid = []
            for q in questions:
                cells = []
                for t in panelists:
                    srow = self.score_ids.filtered(
                        lambda s: s.applicant_id.id == a.id and s.token_id.id == t.id
                        and s.question_id.id == q.id)
                    cells.append(srow[0].score if srow else None)
                grid.append({'question': q.name or '', 'cells': cells})
            # comments
            comments = []
            for pc in self.panel_comment_ids.filtered(lambda c: c.applicant_id.id == a.id):
                comments.append({'panelist': pc.user_id.name, 'text': pc.comment or ''})
            # evaluation
            ev = self.evaluation_ids.filtered(lambda e: e.applicant_id.id == a.id)[:1]
            evaluation = None
            if ev:
                evaluation = {
                    'current_salary': ev.current_salary or '',
                    'expected_salary': ev.expected_salary or '',
                    'notice_period': ev.notice_period or '',
                    'recruiter_comments': ev.recruiter_comments or '',
                    'panel_comments': ev.panel_comments or '',
                    'hr_recommendation': dict(ev._fields['hr_recommendation'].selection).get(ev.hr_recommendation, '') if ev.hr_recommendation else '',
                    'final_decision': dict(ev._fields['final_decision'].selection).get(ev.final_decision, '') if ev.final_decision else '',
                }
            candidates.append({
                'name': a.candidate_id.partner_name or '?',
                'auto_score': getattr(a, 'cps_auto_score', 0),
                'per_panelist': per,
                'avg': avg,
                'spread': spread,
                'flag': spread > threshold,
                'grid': grid,
                'comments': comments,
                'evaluation': evaluation,
            })
        candidates.sort(key=lambda c: c['avg'], reverse=True)
        return {
            'panelists': [{'id': t.id, 'name': t.user_id.name or '?'} for t in panelists],
            'questions': [q.name or '' for q in questions],
            'candidates': candidates,
            'threshold': threshold,
        }

    def token_is_complete(self, token):
        """True if this panelist has scored every interviewed candidate."""
        self.ensure_one()
        if not self.interviewed_applicant_ids:
            return False
        return not self.get_scorable_candidates(token)


class CpsInterviewSessionReopen(models.Model):
    _inherit = 'cps.interview.session'

    def _sync_token_states(self):
        """Keep each token's state consistent with what it has scored."""
        for session in self:
            for token in session.token_ids:
                if session.token_is_complete(token):
                    if token.state != 'submitted':
                        token.write({'state': 'submitted',
                                     'submitted_date': fields.Datetime.now()})
                else:
                    # panelist still has interviewed candidates to score
                    if token.state != 'pending':
                        token.write({'state': 'pending'})

    def write(self, vals):
        res = super().write(vals)
        if 'interviewed_applicant_ids' in vals:
            self._sync_token_states()
        return res


class CpsInterviewOverallScore(models.Model):
    _name = 'cps.interview.overall'
    _description = 'Panel Overall Score (manually recorded)'
    _order = 'overall_score desc'

    session_id = fields.Many2one(
        'cps.interview.session', string='Session',
        required=True, ondelete='cascade',
    )
    applicant_id = fields.Many2one(
        'hr.applicant', string='Candidate', required=True,
    )
    overall_score = fields.Float(string='Overall Score', required=True)
    note = fields.Char(
        string='Source / Note',
        help='Where this score came from, e.g. panel record, HR sheet.',
    )


class CpsInterviewSessionOverall(models.Model):
    _inherit = 'cps.interview.session'

    overall_ids = fields.One2many(
        'cps.interview.overall', 'session_id',
        string='Panel Overall Scores',
    )
