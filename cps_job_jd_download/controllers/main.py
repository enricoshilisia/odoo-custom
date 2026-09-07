from odoo import http
from odoo.http import request, Response
import base64


class JobJdDownload(http.Controller):

    @http.route('/jobs/<int:job_id>/jd', type='http', auth='public', website=True)
    def download_jd(self, job_id, **kwargs):
        job = request.env['hr.job'].sudo().browse(job_id)
        if not job.exists() or not job.jd_pdf:
            return request.not_found()

        filename = job.jd_pdf_filename or f'{job.name} - Job Description.pdf'
        pdf_data = base64.b64decode(job.jd_pdf)

        return Response(
            pdf_data,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'attachment; filename="{filename}"'),
                ('Content-Length', len(pdf_data)),
            ]
        )
