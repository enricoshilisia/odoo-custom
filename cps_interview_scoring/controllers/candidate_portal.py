import base64
from odoo import http, fields, _
from odoo.http import request


class CandidateFormPortal(http.Controller):

    @http.route('/candidate/form/<string:token>', type='http', auth='public', website=True)
    def candidate_form(self, token, **kwargs):
        Token = request.env['cps.candidate.token'].sudo()
        token_rec = Token.search([('token', '=', token)], limit=1)

        if not token_rec:
            return request.render('cps_interview_scoring.candidate_invalid', {})

        if token_rec.state == 'submitted':
            return request.render('cps_interview_scoring.candidate_already_submitted', {
                'candidate': token_rec.applicant_id.partner_name,
            })

        if token_rec.session_id.state not in ('open', 'closed'):
            return request.render('cps_interview_scoring.candidate_session_closed', {})

        return request.render('cps_interview_scoring.candidate_form', {
            'token_rec': token_rec,
            'session': token_rec.session_id,
            'candidate': token_rec.applicant_id,
        })

    @http.route('/candidate/form/<string:token>/submit', type='http', auth='public',
                website=True, methods=['POST'], csrf=True)
    def candidate_form_submit(self, token, **kwargs):
        Token = request.env['cps.candidate.token'].sudo()
        token_rec = Token.search([('token', '=', token)], limit=1)

        if not token_rec or token_rec.state == 'submitted':
            return request.redirect('/candidate/form/%s' % token)

        # Handle photo upload
        photo_data = None
        photo_filename = None
        photo_file = kwargs.get('passport_photo')
        if photo_file and hasattr(photo_file, 'read'):
            photo_data = base64.b64encode(photo_file.read())
            photo_filename = photo_file.filename

        # Save response
        response = request.env['cps.candidate.response'].sudo().create({
            'session_id': token_rec.session_id.id,
            'token_id': token_rec.id,
            'applicant_id': token_rec.applicant_id.id,
            'passport_photo': photo_data,
            'passport_photo_filename': photo_filename,
            'availability': kwargs.get('availability', ''),
            'emoji_rating': kwargs.get('emoji_rating', ''),
            'comment_1': kwargs.get('comment_1', ''),
            'comment_2': kwargs.get('comment_2', ''),
            'comment_3': kwargs.get('comment_3', ''),
            'submitted_date': fields.Datetime.now(),
        })

        # Attach photo to applicant record and set as profile photo
        if photo_data and photo_filename:
            request.env['ir.attachment'].sudo().create({
                'name': photo_filename,
                'datas': photo_data,
                'res_model': 'hr.applicant',
                'res_id': token_rec.applicant_id.id,
                'mimetype': 'image/jpeg',
            })
            # Set as the applicant partner's profile image
            if token_rec.applicant_id.partner_id:
                token_rec.applicant_id.partner_id.sudo().write({'image_1920': photo_data})

        token_rec.write({
            'state': 'submitted',
            'submitted_date': fields.Datetime.now(),
        })

        return request.render('cps_interview_scoring.candidate_thank_you', {
            'candidate': token_rec.applicant_id.partner_name,
            'session': token_rec.session_id,
        })
