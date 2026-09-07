from odoo import models, fields, api
from markupsafe import Markup
import logging

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LEGACY HARDCODED ENGINE — Survey ID 14 (Multi-Cloud & AI Sales Executive)
# Kept as fallback when no brackets are configured on a survey
# ---------------------------------------------------------------------------

QUESTION_MAX = {
    10: 10, 11: 10, 12: 10, 13: 7, 14: 15,
    15: 10, 16: 10, 17: 5,  18: 10, 19: 10,
    20: 5,  21: 10,
}

ANSWER_SCORES = {
    380: 0, 381: 7, 382: 9, 383: 10,
    384: 5, 385: 3, 386: 2, 387: 2, 424: 0,
    388: 7, 389: 5, 422: 0,
    390: 2, 391: 4, 392: 8, 393: 12, 394: 15,
    395: 2, 396: 5, 397: 8, 398: 10,
    399: 10, 400: 8, 401: 8, 402: 7, 403: 6,
    404: 5, 405: 5, 406: 3, 425: 0,
    407: 5, 408: 0,
    409: 4, 410: 2, 411: 3, 412: 4, 413: 2,
    414: 2, 415: 1, 416: 0,
    417: 10, 418: 8, 419: 6, 420: 5, 421: 0,
}

KNOCKOUT_ANSWERS = {
    380: "Less than 5 years of technology/cloud sales experience (minimum 5 years required).",
    424: "No cloud platform sales experience (must have sold at least one recognised cloud platform).",
    422: "No enterprise RFP/RFQ/Tender experience (required for this role).",
    421: "Unable to provide evidence of cloud sales activity in the last 6 months.",
}

Q5_KNOCKOUT_THRESHOLD = 8

Q_LABELS = {
    10: 'Q1: Years of Experience',
    11: 'Q2: Cloud Platforms Sold',
    12: 'Q3: CIO/CTO Engagement (Manual)',
    13: 'Q4: RFP/RFQ Experience',
    14: 'Q5: Tender Role',
    15: 'Q6: Largest Deal Value',
    16: 'Q7: Cloud Solution on Largest Deal',
    17: 'Q8: Executive Stakeholder Engagement',
    18: 'Q9: Cloud Certifications',
    19: 'Q10: Proof of Recent Sales',
    20: 'Q11: CRM Tools (Manual)',
    21: 'Q12: ICT Sales Lifecycle (Manual)',
    22: 'Q13: Current Pay (Info Only)',
    23: 'Q14: Expected Pay (Info Only)',
}

MANUAL_SEQS = {12, 20, 21}


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    applicant_id = fields.Many2one(
        'hr.applicant', string='Applicant', ondelete='cascade',
    )

    def write(self, vals):
        res = super().write(vals)
        if 'state' in vals and vals['state'] == 'done':
            for record in self:
                if record.applicant_id:
                    record._cps_handle_survey_completion()
        return res

    # ------------------------------------------------------------------
    # MAIN COMPLETION HANDLER — routes to reusable or legacy engine
    # ------------------------------------------------------------------
    def _cps_handle_survey_completion(self):
        applicant = self.applicant_id
        job = applicant.job_id
        if not job:
            return

        config = self.env['cps.recruitment.survey.config'].search([
            ('job_id', '=', job.id),
            ('survey_id', '=', self.survey_id.id),
        ], limit=1)

        if not config:
            return

        if config.is_manual:
            self._cps_notify_hr_manual_review(applicant, config)
            return

        # Route: reusable engine if brackets configured, else legacy
        if self.survey_id.cps_score_bracket_ids:
            _logger.info(
                'CPS: Using reusable scoring engine for survey "%s"',
                self.survey_id.title
            )
            self._cps_reusable_engine(applicant, config)
        else:
            _logger.info(
                'CPS: Using legacy hardcoded engine for survey "%s"',
                self.survey_id.title
            )
            self._cps_legacy_engine(applicant, config)

    # ==================================================================
    # REUSABLE SCORING ENGINE
    # ==================================================================
    def _cps_reusable_engine(self, applicant, config):
        survey   = self.survey_id
        lines    = self.user_input_line_ids
        breakdown = {}
        knockouts = []

        for line in lines:
            q    = line.question_id
            qid  = q.id
            if qid not in breakdown:
                breakdown[qid] = {
                    'label':       q.title,
                    'score':       0,
                    'max':         q.cps_max_score or 0,
                    'is_manual':   q.cps_is_manual,
                    'manual_max':  q.cps_manual_max or 0,
                    'guide':       q.cps_scoring_guide or '',
                    'text_answer': '',
                    'answer_ids':  [],
                }

            if line.suggested_answer_id:
                ans = line.suggested_answer_id
                breakdown[qid]['answer_ids'].append(ans.id)
                breakdown[qid]['score'] += ans.answer_score or 0

                # Check knockout
                if ans.cps_is_knockout:
                    reason = (ans.cps_knockout_reason
                              or f'Answer "{ans.value}" triggers disqualification.')
                    if reason not in knockouts:
                        knockouts.append(reason)

            elif line.value_text_box:
                breakdown[qid]['text_answer'] = line.value_text_box

        # Count-based scoring: recompute flagged multi-select questions
        for qid, data in breakdown.items():
            q = self.env['survey.question'].browse(qid)
            if q.cps_count_scoring:
                excluded = q.suggested_answer_ids.filtered(
                    'cps_exclude_from_count').ids
                count = len([a for a in data['answer_ids']
                             if a not in excluded])
                data['score'] = q.get_cps_count_marks(count)

        # Apply max score caps
        for qid, data in breakdown.items():
            if data['max'] and data['score'] > data['max']:
                data['score'] = data['max']

        # Compute auto total (exclude manual questions)
        total_auto = sum(
            d['score'] for d in breakdown.values()
            if not d['is_manual']
        )

        # Compute manual total max
        manual_max = sum(
            d['manual_max'] for d in breakdown.values()
            if d['is_manual']
        )

        # Store auto score on applicant
        applicant.write({'cps_auto_score': total_auto})

        _logger.info(
            'CPS Reusable: %s | Auto: %s | Manual max pending: %s | Knockouts: %s',
            applicant.partner_name, total_auto, manual_max, knockouts
        )

        # Handle knockouts
        if knockouts:
            self._cps_reusable_disqualify(applicant, knockouts, total_auto, breakdown)
            return

        # Check if total can ever reach lowest passing bracket
        brackets   = survey.cps_score_bracket_ids.sorted('min_score')
        pass_brackets = brackets.filtered(
            lambda b: b.survey_state == 'passed'
        )
        min_pass = min(
            (b.min_score for b in pass_brackets), default=70
        )
        max_possible = total_auto + manual_max

        if max_possible < min_pass:
            # Cannot pass even with perfect manual score
            fail_bracket = brackets.filtered(
                lambda b: b.survey_state == 'failed'
            )
            stage_id = fail_bracket[0].stage_id.id if fail_bracket else 9
            applicant.write({
                'stage_id':         stage_id,
                'cps_survey_state': 'failed',
            })
            note = (f"Auto score: {total_auto}. Max possible total "
                    f"{max_possible} cannot reach passing threshold {min_pass}. "
                    f"Auto-rejected.")
            applicant.message_post(
                body=self._cps_reusable_breakdown_html(
                    breakdown, total_auto, note, '#d9534f', 'Failed'),
                subtype_xmlid='mail.mt_note',
                message_type='comment',
            )
            self._cps_reusable_notify_hr(
                applicant, total_auto, knockouts, breakdown, note)
            return

        # Move to Pre-Screened and flag for manual review if manual questions exist
        if manual_max > 0:
            applicant.write({
                'stage_id':         10,
                'cps_survey_state': 'in_progress',
            })
            note = (f"Auto score: {total_auto}. "
                    f"Manual questions worth {manual_max} marks pending HR review.")
            applicant.message_post(
                body=self._cps_reusable_breakdown_html(
                    breakdown, total_auto, note, '#f0ad4e', 'Pending Manual Review'),
                subtype_xmlid='mail.mt_note',
                message_type='comment',
            )
            self._cps_reusable_notify_hr(
                applicant, total_auto, [], breakdown, note)
        else:
            # No manual questions — finalize immediately using brackets
            self._cps_reusable_apply_bracket(
                applicant, survey, total_auto, breakdown)

    def _cps_reusable_apply_bracket(self, applicant, survey, total_score, breakdown):
        """Move applicant to stage based on score bracket."""
        bracket = survey.get_cps_bracket(total_score)
        if not bracket:
            _logger.warning(
                'CPS: No bracket found for score %s on survey "%s"',
                total_score, survey.title
            )
            applicant.write({'cps_survey_state': 'in_progress'})
            return

        applicant.write({
            'stage_id':                  bracket.stage_id.id,
            'cps_survey_state':          bracket.survey_state,
            'cps_score_recommendation':  bracket.label,
        })

        color = '#5cb85c' if bracket.survey_state == 'passed' else '#d9534f'
        note  = (f"Total score: {total_score}. "
                 f"Bracket: {bracket.label} → {bracket.stage_id.name}")
        applicant.message_post(
            body=self._cps_reusable_breakdown_html(
                breakdown, total_score, note, color, bracket.label),
            subtype_xmlid='mail.mt_note',
            message_type='comment',
        )

        if bracket.notify_hr:
            self._cps_reusable_notify_hr(
                applicant, total_score, [], breakdown, note)

        _logger.info(
            'CPS Reusable: %s → bracket "%s" stage "%s"',
            applicant.partner_name,
            bracket.label, bracket.stage_id.name
        )

    def _cps_reusable_disqualify(self, applicant, knockouts, total_auto, breakdown):
        refused_stage = self.env['hr.recruitment.stage'].browse(9)
        applicant.write({
            'stage_id':         refused_stage.id,
            'cps_survey_state': 'failed',
        })
        try:
            applicant.action_refuse()
        except Exception:
            pass

        ko_html = ''.join(f'<li style="color:#d9534f;">{r}</li>' for r in knockouts)
        note    = f'<h4>Knockout Reasons:</h4><ul>{ko_html}</ul>'
        applicant.message_post(
            body=self._cps_reusable_breakdown_html(
                breakdown, total_auto, note, '#d9534f', 'Disqualified'),
            subtype_xmlid='mail.mt_note',
            message_type='comment',
        )
        self._cps_reusable_notify_hr(
            applicant, total_auto, knockouts, breakdown, '')
        _logger.info(
            'CPS Reusable: %s DISQUALIFIED. %s',
            applicant.partner_name, ' | '.join(knockouts)
        )

    def _cps_reusable_breakdown_html(self, breakdown, total_auto, note, color, status):
        rows = ''
        for qid, d in sorted(breakdown.items(), key=lambda x: x[0]):
            is_manual = d['is_manual']
            score_display = 'Pending (Manual)' if is_manual else f"{d['score']}/{d['max'] or '?'}"
            row_color = '#888' if is_manual else (
                '#5cb85c' if d['score'] >= (d['max'] or 1) * 0.7 else '#d9534f'
            )
            text = d.get('text_answer', '')
            text_cell = (f'<br/><em style="color:#555;font-size:11px;">'
                         f'{text[:300]}</em>') if text else ''
            rows += (
                f'<tr>'
                f'<td style="padding:5px 8px;border:1px solid #ddd;">{d["label"]}</td>'
                f'<td style="padding:5px 8px;border:1px solid #ddd;'
                f'color:{row_color};font-weight:bold;">'
                f'{score_display}{text_cell}</td>'
                f'</tr>'
            )

        return (
            f'<div style="font-family:Arial,sans-serif;font-size:13px;">'
            f'<h3 style="color:{color};">{status}</h3>'
            f'{note}'
            f'<h4>Score Breakdown:</h4>'
            f'<table style="border-collapse:collapse;width:100%;font-size:12px;">'
            f'<tr style="background:#f5f5f5;">'
            f'<th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">Question</th>'
            f'<th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">Score</th>'
            f'</tr>{rows}'
            f'<tr style="background:#f0f0f0;font-weight:bold;">'
            f'<td style="padding:5px 8px;border:1px solid #ddd;">Auto Total</td>'
            f'<td style="padding:5px 8px;border:1px solid #ddd;">{total_auto}</td>'
            f'</tr></table></div>'
        )

    def _cps_reusable_notify_hr(self, applicant, total_auto, knockouts,
                                 breakdown, note):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        applicant_url = (f"{base_url}/web#id={applicant.id}"
                         f"&model=hr.applicant&view_type=form")
        responses_url = (f"{base_url}/web#id={self.id}"
                         f"&model=survey.user_input&view_type=form")

        disqualified = bool(knockouts)
        status  = "DISQUALIFIED" if disqualified else "Assessment Completed"
        color   = "#d9534f" if disqualified else "#2680af"
        ko_html = (''.join(f'<li>{r}</li>' for r in knockouts)
                   if knockouts else '')
        ko_sec  = (f'<h4 style="color:#d9534f;">Knockout Reasons:</h4>'
                   f'<ul>{ko_html}</ul>') if ko_html else ''
        bd_html = self._cps_reusable_breakdown_html(
            breakdown, total_auto, '', color, status)

        candidates_name = applicant.partner_name or 'N/A'
        subject = f"{status} — {candidates_name} | {applicant.job_id.name}"

        body = (
            f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">'
            f'<h2 style="color:{color};">{status}</h2>'
            f'<p><strong>Candidate:</strong> {candidates_name}<br/>'
            f'<strong>Job:</strong> {applicant.job_id.name}<br/>'
            f'<strong>Auto Score:</strong> {total_auto}</p>'
            f'{ko_sec}<p>{note}</p>{bd_html}'
            f'<div style="margin:20px 0;">'
            f'<a href="{applicant_url}" style="background:#7EBB0E;color:white;'
            f'padding:12px 24px;text-decoration:none;border-radius:5px;'
            f'font-weight:bold;margin-right:12px;">View Applicant</a>'
            f'<a href="{responses_url}" style="background:#2680af;color:white;'
            f'padding:12px 24px;text-decoration:none;border-radius:5px;'
            f'font-weight:bold;">View Responses</a></div>'
            f'<p>Best regards,<br/><strong>CPS Recruitment System</strong></p>'
            f'</div>'
        )

        recipients = ['hr@cloudproductivity-solutions.com']
        if applicant.user_id and applicant.user_id.email:
            if applicant.user_id.email not in recipients:
                recipients.append(applicant.user_id.email)

        self.env['mail.mail'].create({
            'subject':    subject,
            'email_to':   ','.join(recipients),
            'email_from': 'notifications@cloudproductivity-solutions.com',
            'body_html':  body,
        }).send()

    # ==================================================================
    # LEGACY HARDCODED ENGINE (Survey 14 — Multi-Cloud & AI Sales Exec)
    # ==================================================================
    def _cps_legacy_engine(self, applicant, config):
        score_result = self._cps_compute_score()
        total_auto   = score_result['total_auto']
        breakdown    = score_result['breakdown']
        knockouts    = score_result['knockouts']

        applicant.write({'cps_auto_score': total_auto})

        _logger.info(
            'CPS Legacy: %s | Auto: %s/75 | Knockouts: %s',
            applicant.partner_name, total_auto, knockouts
        )

        if knockouts:
            self._cps_disqualify(applicant, knockouts, total_auto, breakdown)
        else:
            self._cps_move_by_score(applicant, config, total_auto, breakdown)

    def _cps_compute_score(self):
        lines     = self.user_input_line_ids
        breakdown = {}
        knockouts = []

        for line in lines:
            q_seq = line.question_id.sequence
            if q_seq not in breakdown:
                breakdown[q_seq] = {
                    'question':    line.question_id.title,
                    'score':       0,
                    'max':         QUESTION_MAX.get(q_seq, 0),
                    'answer_ids':  [],
                    'text_answer': '',
                }
            if line.suggested_answer_id:
                aid = line.suggested_answer_id.id
                breakdown[q_seq]['answer_ids'].append(aid)
                breakdown[q_seq]['score'] += ANSWER_SCORES.get(aid, 0)
                if aid in KNOCKOUT_ANSWERS and KNOCKOUT_ANSWERS[aid] not in knockouts:
                    knockouts.append(KNOCKOUT_ANSWERS[aid])
            elif line.value_text_box:
                breakdown[q_seq]['text_answer'] = line.value_text_box

        for q_seq, data in breakdown.items():
            cap = QUESTION_MAX.get(q_seq, 999)
            if data['score'] > cap:
                data['score'] = cap

        q5 = breakdown.get(14, {})
        if q5 and q5.get('score', 0) < Q5_KNOCKOUT_THRESHOLD:
            knockouts.append(
                f"Tender/proposal role score {q5.get('score',0)}/15 "
                f"— minimum 8/15 required."
            )

        total_auto = sum(
            d['score'] for seq, d in breakdown.items()
            if seq not in MANUAL_SEQS
        )
        return {'total_auto': total_auto, 'breakdown': breakdown,
                'knockouts': knockouts}

    def _cps_disqualify(self, applicant, knockouts, total_auto, breakdown):
        refused_stage = self.env['hr.recruitment.stage'].browse(9)
        applicant.write({'stage_id': refused_stage.id, 'cps_survey_state': 'failed'})
        try:
            applicant.action_refuse()
        except Exception:
            pass

        knockout_html = ''.join(f'<li>{r}</li>' for r in knockouts)
        breakdown_html = self._cps_build_breakdown_html(breakdown, total_auto)
        applicant.message_post(
            body=(f'<div style="font-family:Arial,sans-serif;font-size:13px;">'
                  f'<h3 style="color:#d9534f;">&#9940; Automatic Disqualification</h3>'
                  f'<p><strong>Auto Score:</strong> {total_auto}/75</p>'
                  f'<h4>Knockout Reason(s):</h4>'
                  f'<ul style="color:#d9534f;">{knockout_html}</ul>'
                  f'{breakdown_html}</div>'),
            subtype_xmlid='mail.mt_note',
            message_type='comment',
        )
        self._cps_notify_hr_result(
            applicant, total_auto, knockouts, breakdown, disqualified=True)

    def _cps_move_by_score(self, applicant, config, total_auto, breakdown):
        max_possible   = total_auto + 25
        breakdown_html = self._cps_build_breakdown_html(breakdown, total_auto)

        if max_possible < 70:
            refused_stage = self.env['hr.recruitment.stage'].browse(9)
            applicant.write({'stage_id': refused_stage.id,
                             'cps_survey_state': 'failed'})
            note = (f"Auto score: {total_auto}/75. Even with full manual marks "
                    f"(25pts), total cannot reach 70. Auto-rejected.")
            applicant.message_post(
                body=(f'<div style="font-family:Arial,sans-serif;font-size:13px;">'
                      f'<h3 style="color:#d9534f;">&#10060; Assessment Failed</h3>'
                      f'<p>{note}</p>{breakdown_html}</div>'),
                subtype_xmlid='mail.mt_note',
                message_type='comment',
            )
            self._cps_notify_hr_result(applicant, total_auto, [], breakdown,
                                        disqualified=False, note=note)
        else:
            applicant.write({
                'stage_id':         10,
                'cps_survey_state': 'in_progress',
            })
            note = (f"Auto score: {total_auto}/75. Manual questions Q3/Q11/Q12 "
                    f"(25 marks) pending HR review.")
            applicant.message_post(
                body=(f'<div style="font-family:Arial,sans-serif;font-size:13px;">'
                      f'<h3 style="color:#f0ad4e;">&#9203; Pending Manual Review</h3>'
                      f'<p>{note}</p>{breakdown_html}'
                      f'<p><strong>Action:</strong> Score Q3, Q11, Q12 on the '
                      f'applicant record then click Finalize Assessment Score.</p>'
                      f'</div>'),
                subtype_xmlid='mail.mt_note',
                message_type='comment',
            )
            self._cps_notify_hr_manual_review(applicant, None, extra_note=note)

    def _cps_build_breakdown_html(self, breakdown, total_auto):
        rows = ''
        for seq in sorted(breakdown.keys()):
            d     = breakdown[seq]
            label = Q_LABELS.get(seq, f'Q (seq {seq})')
            is_manual = seq in MANUAL_SEQS
            is_info   = seq in {22, 23}
            if is_info:
                score_display = 'Info Only'
                color = '#888'
            elif is_manual:
                score_display = 'Pending (Manual)'
                color = '#888'
            else:
                score = d['score']
                max_s = d['max']
                score_display = f"{score}/{max_s}"
                color = '#5cb85c' if score >= max_s * 0.7 else '#d9534f'
            text = d.get('text_answer', '')
            text_cell = (f'<br/><em style="color:#666;font-size:11px;">'
                         f'{text[:300]}</em>') if text else ''
            rows += (f'<tr>'
                     f'<td style="padding:5px 8px;border:1px solid #ddd;">{label}</td>'
                     f'<td style="padding:5px 8px;border:1px solid #ddd;'
                     f'color:{color};font-weight:bold;">{score_display}{text_cell}</td>'
                     f'</tr>')

        return (f'<h4>Score Breakdown:</h4>'
                f'<table style="border-collapse:collapse;width:100%;font-size:12px;">'
                f'<tr style="background:#f5f5f5;">'
                f'<th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">'
                f'Question</th>'
                f'<th style="padding:5px 8px;border:1px solid #ddd;text-align:left;">'
                f'Score</th></tr>{rows}'
                f'<tr style="background:#f0f0f0;font-weight:bold;">'
                f'<td style="padding:5px 8px;border:1px solid #ddd;">Auto Total</td>'
                f'<td style="padding:5px 8px;border:1px solid #ddd;">'
                f'{total_auto}/75</td></tr>'
                f'<tr><td style="padding:5px 8px;border:1px solid #ddd;">'
                f'Manual Pending</td>'
                f'<td style="padding:5px 8px;border:1px solid #ddd;">— /25</td>'
                f'</tr></table>')

    def _cps_notify_hr_result(self, applicant, total_auto, knockouts, breakdown,
                               disqualified=False, note=''):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        applicant_url = (f"{base_url}/web#id={applicant.id}"
                         f"&model=hr.applicant&view_type=form")
        responses_url = (f"{base_url}/web#id={self.id}"
                         f"&model=survey.user_input&view_type=form")
        status = "DISQUALIFIED" if disqualified else "Assessment Completed"
        color  = "#d9534f" if disqualified else "#2680af"
        ko_html = (''.join(f'<li>{r}</li>' for r in knockouts)
                   if knockouts else '')
        ko_section = (f'<h4 style="color:#d9534f;">Knockout Reasons:</h4>'
                      f'<ul>{ko_html}</ul>') if ko_html else ''
        bd_html = self._cps_build_breakdown_html(breakdown, total_auto)
        candidate_name = applicant.partner_name or 'N/A'
        subject = f"{status} — {candidate_name} | {applicant.job_id.name}"
        body = (f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">'
                f'<h2 style="color:{color};">{status}</h2>'
                f'<p><strong>Candidate:</strong> {candidate_name}<br/>'
                f'<strong>Email:</strong> {applicant.email_from}<br/>'
                f'<strong>Job:</strong> {applicant.job_id.name}<br/>'
                f'<strong>Auto Score:</strong> {total_auto}/75</p>'
                f'{ko_section}<p>{note}</p>{bd_html}'
                f'<div style="margin:20px 0;">'
                f'<a href="{applicant_url}" style="background:#7EBB0E;color:white;'
                f'padding:12px 24px;text-decoration:none;border-radius:5px;'
                f'font-weight:bold;margin-right:12px;">View Applicant</a>'
                f'<a href="{responses_url}" style="background:#2680af;color:white;'
                f'padding:12px 24px;text-decoration:none;border-radius:5px;'
                f'font-weight:bold;">View Responses</a></div>'
                f'<p>Best regards,<br/><strong>CPS Recruitment System</strong></p>'
                f'</div>')

        recipients = ['hr@cloudproductivity-solutions.com']
        if applicant.user_id and applicant.user_id.email:
            if applicant.user_id.email not in recipients:
                recipients.append(applicant.user_id.email)

        self.env['mail.mail'].create({
            'subject':    subject,
            'email_to':   ','.join(recipients),
            'email_from': 'notifications@cloudproductivity-solutions.com',
            'body_html':  body,
        }).send()

    def _cps_notify_hr_manual_review(self, applicant, config, extra_note=''):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        applicant_url = (f"{base_url}/web#id={applicant.id}"
                         f"&model=hr.applicant&view_type=form")
        responses_url = (f"{base_url}/web#id={self.id}"
                         f"&model=survey.user_input&view_type=form")
        survey_title  = config.survey_id.title if config else self.survey_id.title

        # Get manual questions dynamically if using reusable engine
        manual_items = ''
        if self.survey_id.cps_score_bracket_ids:
            manual_qs = self.survey_id.get_cps_manual_questions()
            if manual_qs:
                manual_items = ''.join(
                    f'<li>{q.title} — Max: {q.cps_manual_max} marks'
                    f'{f"<br/><em>{q.cps_scoring_guide}</em>" if q.cps_scoring_guide else ""}'
                    f'</li>'
                    for q in manual_qs
                )
        else:
            manual_items = (
                '<li>Q3: CIO/CTO Engagement — 10 marks</li>'
                '<li>Q11: CRM Tools Experience — 5 marks</li>'
                '<li>Q12: ICT Sales Lifecycle — 10 marks</li>'
            )

        candidate_name = applicant.partner_name or 'N/A'
        subject = (f"Manual Review Required — {candidate_name} "
                   f"| {applicant.job_id.name}")
        body = (f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#333;">'
                f'<h2 style="color:#f0ad4e;">&#9203; Manual Review Required</h2>'
                f'<p><strong>Candidate:</strong> {candidate_name}<br/>'
                f'<strong>Email:</strong> {applicant.email_from}<br/>'
                f'<strong>Job:</strong> {applicant.job_id.name}</p>'
                f'<p><strong>Questions to score:</strong></p>'
                f'<ul>{manual_items}</ul>'
                f'{f"<p>{extra_note}</p>" if extra_note else ""}'
                f'<div style="margin:20px 0;">'
                f'<a href="{applicant_url}" style="background:#7EBB0E;color:white;'
                f'padding:12px 24px;text-decoration:none;border-radius:5px;'
                f'font-weight:bold;margin-right:12px;">View Applicant</a>'
                f'<a href="{responses_url}" style="background:#2680af;color:white;'
                f'padding:12px 24px;text-decoration:none;border-radius:5px;'
                f'font-weight:bold;">View Responses</a></div>'
                f'<p>Best regards,<br/><strong>CPS Recruitment System</strong></p>'
                f'</div>')

        recipients = ['hr@cloudproductivity-solutions.com']
        if applicant.user_id and applicant.user_id.email:
            if applicant.user_id.email not in recipients:
                recipients.append(applicant.user_id.email)

        self.env['mail.mail'].create({
            'subject':    subject,
            'email_to':   ','.join(recipients),
            'email_from': 'notifications@cloudproductivity-solutions.com',
            'body_html':  body,
        }).send()

        applicant.write({'cps_survey_state': 'in_progress'})
        _logger.info(
            'CPS: Manual review notification sent for %s',
            candidate_name
        )
