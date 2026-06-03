from odoo import models, fields, api
from odoo.exceptions import UserError
import openai

class EmiChat(models.Model):
    _name = 'emi.chat'
    _description = 'Lịch sử Chat Emi'
    _order = 'create_date asc'

    user_id = fields.Many2one('res.users', string="Người dùng", default=lambda self: self.env.user)
    message = fields.Text(string="Tin nhắn")
    response = fields.Text(string="Câu trả lời của Emi")
    is_user = fields.Boolean(string="Là người dùng?", default=True)

    def action_ask_emi(self):
        # 1. Lấy cấu hình
        config = self.env['emi.config'].search([], limit=1)
        if not config:
            raise UserError("Vui lòng tạo cấu hình Emi trong menu Cài đặt trước!")

        # 2. Xây dựng ngữ cảnh (Context) từ lịch sử chat
        # Lấy 10 tin nhắn gần nhất của user hiện tại
        history = self.search([('user_id', '=', self.env.user.id)], limit=10)
        messages = [{"role": "system", "content": config.system_prompt}]
        
        for chat in history:
            role = "user" if chat.is_user else "assistant"
            content = chat.message if chat.is_user else chat.response
            messages.append({"role": role, "content": content})

        # Thêm tin nhắn hiện tại vào cuối danh sách
        if not self.message:
            raise UserError("Vui lòng nhập nội dung tin nhắn!")
            
        messages.append({"role": "user", "content": self.message})

        try:
            # 3. Kết nối với LM Studio qua thư viện OpenAI
            client = openai.OpenAI(
                base_url=config.server_url,
                api_key="lm-studio" # LM Studio không check key nhưng thư viện yêu cầu phải có
            )

            response = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                temperature=0.7,
            )

            ai_text = response.choices[0].message.content

            # 4. Lưu câu trả lời của Emi thành một bản ghi mới trong lịch sử
            self.env['emi.chat'].create({
                'user_id': self.env.user.id,
                'message': ai_text,
                'response': ai_text,
                'is_user': False
            })

            # Cập nhật response cho record hiện tại để hiển thị lên màn hình
            self.response = ai_text
            return True

        except Exception as e:
            raise UserError(f"Lỗi kết nối tới LM Studio: {str(e)}")