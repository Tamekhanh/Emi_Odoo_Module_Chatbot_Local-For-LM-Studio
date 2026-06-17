{
    'name': 'Emi AI Chatbot (LM Studio) - Beta',
    'version': '1.0',
    'category': 'AI',
    'summary': 'AI assistant chatbot using local LLM with OpenAI API standard for Odoo',
    'description': 'Module Odoo AI assistant chatbot using local LLM with OpenAI API standard for Odoo',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/emi_config_views.xml',
        'views/emi_chat_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'emi_chatbot/static/src/emi_chat.scss',
            'emi_chatbot/static/src/emi_chat.xml',
            'emi_chatbot/static/src/emi_chat.js',
        ],
    },
    'author': 'Tamek',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}