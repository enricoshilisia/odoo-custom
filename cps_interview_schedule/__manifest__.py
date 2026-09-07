{
    'name': 'CPS Interview Schedule',
    'version': '19.0.1.0.0',
    'category': 'Recruitment',
    'summary': 'Automated interview slot scheduling and invitations',
    'author': 'CPS',
    'depends': ['cps_interview_scoring', 'hr_recruitment', 'mail', 'cps_ms_graph'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'views/interview_schedule_views.xml',
        # If install FAILS on the next line, the external IDs it references
        # (session form view / recruitment menu) differ in your setup.
        # Remove this one line, then reinstall — the core module still works.
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
