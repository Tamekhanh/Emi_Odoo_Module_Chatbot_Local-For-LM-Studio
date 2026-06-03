from odoo import models, fields

class EmiConfig(models.Model):
    _name = 'emi.config'
    _description = 'Cấu hình Chatbot Emi'

    name = fields.Char(default="Emi Settings", required=True)
    server_url = fields.Char(
        default="http://localhost:1234/v1", 
        string="LM Studio URL", 
        help="Địa chỉ server của LM Studio, ví dụ: http://localhost:1234/v1"
    )
    model_name = fields.Char(
        default="local-model", 
        string="Model Name", 
        help="Tên model trong LM Studio (thường để local-model)"
    )
    system_prompt = fields.Text(
        string="Tính cách của Emi", 
        default="Bạn là Emi, một trợ lý ảo thông minh, dễ thương chạy local. Hãy hỗ trợ người dùng Odoo một cách nhiệt tình."
    )