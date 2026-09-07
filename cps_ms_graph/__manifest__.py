# -*- coding: utf-8 -*-
{
    'name': 'CPS Microsoft Graph Connector',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Reusable Microsoft Graph API connector (app-only auth)',
    'description': """
CPS Microsoft Graph Connector
=============================
Provides a reusable service model for calling the Microsoft Graph API
using client-credentials (app-only) authentication.

Consumed by other CPS modules:
  - cps_learning : Teams meeting creation + attendance retrieval

Configuration lives in Settings > CPS Graph.
    """,
    'author': 'Cloud Productivity Solutions',
    'website': 'https://cloudproductivity-solutions.com',
    'depends': ['base', 'base_setup'],
    'data': [
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
