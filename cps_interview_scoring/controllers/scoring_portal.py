from odoo import http, fields, _
from odoo.http import request

HR_NOTIFICATION_EMAIL = 'hr@cloudproductivity-solutions.com'


class InterviewScoringPortal(http.Controller):

    @http.route('/interview/score/<string:token>', type='http', auth='public', website=True)
    def scoring_page(self, token, **kwargs):
        Token = request.env['cps.interview.token'].sudo()
        token_rec = Token.search([('token', '=', token)], limit=1)

        if not token_rec:
            return request.render('cps_interview_scoring.scoring_invalid', {})

        if token_rec.session_id.state != 'open':
            return request.render('cps_interview_scoring.scoring_session_closed', {})

        session = token_rec.session_id
        scorable = session.get_scorable_candidates(token_rec)

        if not scorable:
            scored = session.get_scored_candidates(token_rec)
            if scored:
                comments = {a.id: session.get_panelist_comment(token_rec, a) for a in scored}
                return request.render('cps_interview_scoring.comment_form', {
                    'token_rec': token_rec,
                    'session': session,
                    'candidates': scored,
                    'comments': comments,
                })
            return request.render('cps_interview_scoring.scoring_already_submitted', {
                'panelist': token_rec.user_id.name,
            })

        return request.render('cps_interview_scoring.scoring_form', {
            'token_rec': token_rec,
            'session': session,
            'candidates': scorable,
            'questions': session.question_ids,
        })

    @http.route('/interview/score/<string:token>/submit', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def scoring_submit(self, token, **kwargs):
        Token = request.env['cps.interview.token'].sudo()
        token_rec = Token.search([('token', '=', token)], limit=1)

        if not token_rec or token_rec.session_id.state != 'open':
            return request.redirect('/interview/score/%s' % token)

        session = token_rec.session_id
        Score = request.env['cps.interview.score'].sudo()

        scorable = session.get_scorable_candidates(token_rec)

        # Reject the submission if any question was left unscored, rather than
        # silently defaulting to 1 (which produced bogus all-1s submissions).
        missing = []
        for applicant in scorable:
            for question in session.question_ids:
                raw = kwargs.get('score_%d_%d' % (applicant.id, question.id))
                try:
                    v = int(raw)
                except (TypeError, ValueError):
                    missing.append((applicant, question))
                    continue
                if v < 1 or v > 5:
                    missing.append((applicant, question))

        if missing:
            return request.render('cps_interview_scoring.scoring_form', {
                'token_rec': token_rec,
                'session': session,
                'candidates': scorable,
                'questions': session.question_ids,
                'error_missing': len(missing),
            })

        for applicant in scorable:
            for question in session.question_ids:
                field_name = 'score_%d_%d' % (applicant.id, question.id)
                score_val = kwargs.get(field_name)
                score_int = int(score_val)

                Score.create({
                    'session_id': session.id,
                    'token_id': token_rec.id,
                    'applicant_id': applicant.id,
                    'question_id': question.id,
                    'score': score_int,
                })

        # Lock the token only if this panelist has now scored everyone interviewed
        if session.token_is_complete(token_rec):
            token_rec.write({
                'state': 'submitted',
                'submitted_date': fields.Datetime.now(),
            })

        # Check if all panelists have now submitted
        all_tokens = session.token_ids
        all_submitted = all(t.state == 'submitted' for t in all_tokens)

        if all_submitted:
            self._notify_hr_all_submitted(session)

        return request.render('cps_interview_scoring.scoring_thank_you', {
            'panelist': token_rec.user_id.name,
            'session': session,
        })

    def _notify_hr_all_submitted(self, session):
        """Send notification email to HR when all panelists have submitted."""
        try:
            # Build results summary
            results = session.get_results()
            top = results[0] if results else None

            rows = ''
            for idx, row in enumerate(results):
                medal = ['&#127947;', '&#129352;', '&#129353;'][idx] if idx < 3 else ''
                rows += f'''<tr>
                    <td style="padding:8px;border:1px solid #ddd;">{idx + 1}</td>
                    <td style="padding:8px;border:1px solid #ddd;">{medal} {row['applicant'].partner_name}</td>
                    <td style="padding:8px;border:1px solid #ddd;text-align:center;font-weight:bold;">{row['total']}</td>
                </tr>'''

            panelists = ', '.join(t.user_id.name for t in session.token_ids)

            top_banner = ''
            if top:
                top_banner = f'''
                <div style="background:#eafaf1;border-left:4px solid #27ae60;padding:12px 16px;
                            margin:16px 0;border-radius:4px;font-size:15px;">
                    &#9733; <strong>Top Candidate: {top['applicant'].partner_name}</strong>
                    &mdash; Total Score: <strong>{top['total']}</strong>
                </div>'''

            body = f"""
            <html>
            <body style="font-family:Arial,sans-serif;font-size:14px;color:#333;">
                <div style="background:#2c3e50;color:#fff;padding:18px 24px;border-radius:6px;">
                    <h2 style="margin:0;">&#10003; All Panelists Have Submitted</h2>
                    <p style="margin:6px 0 0;opacity:0.8;">{session.name}</p>
                </div>

                <p style="margin-top:20px;">
                    All <strong>{len(session.token_ids)}</strong> panelist(s) have completed
                    scoring for the following interview session:
                </p>

                <table style="width:100%;border-collapse:collapse;margin:8px 0;">
                    <tr>
                        <td style="padding:6px;color:#666;width:30%;"><strong>Session:</strong></td>
                        <td style="padding:6px;">{session.name}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px;color:#666;"><strong>Job Position:</strong></td>
                        <td style="padding:6px;">{session.job_id.name}</td>
                    </tr>
                    <tr>
                        <td style="padding:6px;color:#666;"><strong>Panelists:</strong></td>
                        <td style="padding:6px;">{panelists}</td>
                    </tr>
                </table>

                {top_banner}

                <h3 style="color:#2c3e50;border-bottom:2px solid #2c3e50;padding-bottom:6px;">
                    Candidate Rankings
                </h3>
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="background:#2c3e50;color:#fff;">
                            <th style="padding:8px;border:1px solid #ddd;text-align:left;">#</th>
                            <th style="padding:8px;border:1px solid #ddd;text-align:left;">Candidate</th>
                            <th style="padding:8px;border:1px solid #ddd;text-align:center;">Total Score</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>

                <p style="margin-top:24px;">
                    Please log in to Odoo to view the full breakdown and download the results report.
                </p>

                <hr style="border:none;border-top:1px solid #eee;margin:20px 0;"/>
                <p style="color:#aaa;font-size:12px;">
                    CPS Interview Scoring &middot; {session.company_id.name if session.company_id else ''}
                </p>
            </body>
            </html>
            """

            request.env['mail.mail'].sudo().create({
                'subject': f'All Scores In: {session.name}',
                'email_to': HR_NOTIFICATION_EMAIL,
                'body_html': body,
                'auto_delete': True,
            }).send()

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                'Failed to send HR completion notification for session %s: %s',
                session.name, e
            )

    @http.route('/interview/comment/<string:token>', type='http', auth='public',
                methods=['POST'], website=True, csrf=False)
    def comment_submit(self, token, **kwargs):
        Token = request.env['cps.interview.token'].sudo()
        token_rec = Token.search([('token', '=', token)], limit=1)
        if not token_rec or token_rec.session_id.state != 'open':
            return request.redirect('/interview/score/%s' % token)
        session = token_rec.session_id
        PC = request.env['cps.interview.panel.comment'].sudo()
        scored = session.get_scored_candidates(token_rec)
        for applicant in scored:
            txt = (kwargs.get('comment_%d' % applicant.id) or '').strip()
            existing = PC.search([
                ('session_id', '=', session.id),
                ('applicant_id', '=', applicant.id),
                ('user_id', '=', token_rec.user_id.id),
            ], limit=1)
            if txt:
                if existing:
                    existing.comment = txt
                else:
                    PC.create({
                        'session_id': session.id,
                        'applicant_id': applicant.id,
                        'user_id': token_rec.user_id.id,
                        'token_id': token_rec.id,
                        'comment': txt,
                    })
            elif existing:
                existing.comment = ''
        return request.render('cps_interview_scoring.comment_thank_you', {
            'panelist': token_rec.user_id.name,
        })

    @http.route('/interview/comment/<string:token>', type='http', auth='public', website=True)
    def comment_page(self, token, **kwargs):
        Token = request.env['cps.interview.token'].sudo()
        token_rec = Token.search([('token', '=', token)], limit=1)
        if not token_rec:
            return request.render('cps_interview_scoring.scoring_invalid', {})
        session = token_rec.session_id
        scored = session.get_scored_candidates(token_rec)
        comments = {a.id: session.get_panelist_comment(token_rec, a) for a in scored}
        return request.render('cps_interview_scoring.comment_form', {
            'token_rec': token_rec, 'session': session,
            'candidates': scored, 'comments': comments,
        })

