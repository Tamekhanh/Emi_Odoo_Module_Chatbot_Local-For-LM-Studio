{
    'name': 'Emi AI Chatbot (LM Studio) - Beta',
    'version': '1.0',
    'category': 'AI',
    'summary': 'Trợ lý ảo Emi chạy local qua LM Studio',
    'description': 'Module tích hợp LLM local vào Odoo sử dụng chuẩn OpenAI API của LM Studio',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'views/emi_config_views.xml',
        'views/emi_chat_views.xml',
    ],
    'authors': 'Tamek',
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}