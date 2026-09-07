{
    'name': 'CPS Employee Onboarding',
    'version': '19.0.1.0.0',
    'category': 'Human Resources',
    'summary': 'Structured reusable onboarding plans for any job role',
    'description': """
        Create reusable onboarding templates per job role.
        Generate live onboarding plans for new employees with auto-computed
        deadlines, phase tracking, email reminders, employee self-service
        portal, and a PDF progress report.
    """,
    'author': 'CPS',
    'depends': ['hr', 'hr_recruitment', 'mail', 'portal', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'data/mail_templates.xml',
        'data/default_template_data.xml',
        'views/template_views.xml',
        'views/plan_views.xml',
        'views/menus.xml',
        'templates/onboarding_portal.xml',
        'report/onboarding_report.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
