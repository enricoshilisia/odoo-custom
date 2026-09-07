{
    'name': 'CPS: Hide Survey Score from Candidates',
    'version': '18.0.1.1.0',
    'category': 'Survey',
    'summary': 'Hides score from candidates; customises recruitment application form',
    'depends': ['survey', 'website_hr_recruitment'],
    'data': [
        'views/survey_templates_override.xml',
        'views/recruitment_form_override.xml',
    ],
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
