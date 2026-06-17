from odoo import models, fields, api
from odoo.exceptions import UserError
import openai
import os
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# --- KHỞI TẠO TOÀN CỤC ---
try:
    print("🤖 Loading AI Embedding Model into memory...")
    EMBEDDING_MODEL = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    PERSIST_DIRECTORY = "D:/BT/2533_Knowledge_Management_System/Odoo/odoo/chroma_db"
    VECTOR_DB = Chroma(
        persist_directory=PERSIST_DIRECTORY, 
        embedding_function=EMBEDDING_MODEL,
        collection_name="kms_collection")
    print("✅ AI Model and Vector DB loaded successfully!")
except Exception as e:
    print(f"❌ Critical Error loading AI Model: {e}")
    EMBEDDING_MODEL = None
    VECTOR_DB = None

class EmiChat(models.Model):
    _name = 'emi.chat'
    _description = 'Emi Chat History'
    _order = 'create_date asc'

    user_id = fields.Many2one('res.users', string="User", default=lambda self: self.env.user)
    message = fields.Text(string="Message")
    response = fields.Text(string="Emi's Response")
    is_user = fields.Boolean(string="Is User?", default=True)

    def _get_user_access_role(self):
        user = self.env.user
        if user.has_group('base.group_system'):
            return 'hr_manager'
        elif 'it' in user.name.lower():
            return 'it_staff'
        return 'public'

    # --- API CHO JS CALL ---
    @api.model
    def get_chat_history(self, user_id=None): # Thêm =None để không bị lỗi missing argument
        # Nếu JS không gửi user_id, tự lấy từ session
        current_user_id = user_id or self.env.user.id
        chats = self.search([('user_id', '=', current_user_id)], order='create_date asc')
        return [{
            'id': c.id,
            'message': c.message if c.is_user else c.response,
            'is_user': c.is_user,
        } for c in chats]

    @api.model
    def chat_with_emi(self, message=None, user_id=None): # Thêm =None cho cả hai
        # Kiểm tra nếu không có message thì báo lỗi
        if not message:
            return "Lỗi: Không nhận được nội dung tin nhắn."

        current_user_id = user_id or self.env.user.id

        # 1. Lưu tin nhắn người dùng
        self.create({
            'user_id': current_user_id,
            'message': message,
            'is_user': True,
        })
        
        # 2. Gọi logic AI xử lý
        ai_response = self._get_ai_response(message) 

        # 3. Lưu câu trả lời của AI
        self.create({
            'user_id': current_user_id,
            'message': ai_response,
            'response': ai_response,
            'is_user': False,
        })
        return ai_response

    def _get_ai_response(self, message):
        """ Logic cốt lõi xử lý RAG và LLM """
        if VECTOR_DB is None:
            return "AI Engine is not loaded. Please restart Odoo server."

        config = self.env['emi.config'].search([], limit=1)
        if not config:
            return "Please create Emi configuration in the settings menu first!"

        try:
            # BƯỚC 1: TRUY XUẤT TRI THỨC
            user_role = self._get_user_access_role()
            security_filter = {"$or": [{"access_role": user_role}, {"access_role": "public"}]}
            docs = VECTOR_DB.similarity_search(message, k=3, filter=security_filter)
            context_text = "\n\n".join([doc.page_content for doc in docs]) if docs else "No specific SOP found."

            # BƯỚC 2: XÂY DỰNG PROMPT
            rag_system_prompt = f"""
            You are a strict factual assistant. 
            Your ONLY job is to rewrite the provided context into a natural answer.
            If the answer is not in the context, simply say "I don't know", If it Greetings, respond appropriately.
            --- CONTEXT ---
            {context_text}
            ----------------
            """
            # Lấy 10 tin nhắn gần nhất của user này để làm memory
            history = self.search([('user_id', '=', self.env.user.id)], limit=10)
            messages = [{"role": "system", "content": rag_system_prompt}]
            for chat in history:
                role = "user" if chat.is_user else "assistant"
                content = chat.message if chat.is_user else chat.response
                messages.append({"role": role, "content": content})

            messages.append({"role": "user", "content": message})

            # BƯỚC 3: GỬI CHO LM STUDIO
            client = openai.OpenAI(base_url=config.server_url, api_key="lm-studio")
            response = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                temperature=config.temperature,
            )
            return response.choices[0].message.content

        except Exception as e:
            return f"Emi Error: {str(e)}"

    # Giữ lại hàm cũ nếu bạn vẫn dùng Form View
    def action_ask_emi(self):
        res = self._get_ai_response(self.message)
        self.response = res
        # Tạo bản ghi AI để lưu lịch sử
        self.create({'user_id': self.env.user.id, 'message': res, 'response': res, 'is_user': False})
        return True