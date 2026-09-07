from odoo import models, fields


class HrJob(models.Model):
    _inherit = 'hr.job'

    jd_pdf = fields.Binary(
        string='Job Description PDF',
        attachment=True,
        help='Upload the JD as a PDF. A download button will appear on the public job page.',
    )
    jd_pdf_filename = fields.Char(string='JD Filename')
