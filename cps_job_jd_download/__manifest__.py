{
    'name': 'CPS: Job JD PDF Download',
    'version': '18.0.1.0.0',
    'category': 'Recruitment',
    'summary': 'Attach a JD PDF to any job position; show download button on website and shareable link',
    'depends': ['hr_recruitment', 'website_hr_recruitment'],
    'data': [
        'views/hr_job_views.xml',
        'views/website_job_detail_override.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
