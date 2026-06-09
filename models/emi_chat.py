from odoo import models, fields, api
from odoo.exceptions import UserError
import openai
import os

# Import thư viện Vector DB
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# --- KHỞI TẠO TOÀN CỤC (Global Initialization) ---
# Việc khởi tạo ở đây giúp model được load vào RAM một lần duy nhất khi server start, 
# không load lại mỗi khi nhấn nút chat -> Tránh sập Server (Memory Limit)
try:
    print("🤖 Loading AI Embedding Model into memory...")
    EMBEDDING_MODEL = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    PERSIST_DIRECTORY = "D:/BT/2533_Knowledge_Management_System/Odoo/odoo/chroma_db"
    # Khởi tạo Chroma một lần duy nhất
    VECTOR_DB = Chroma(
        persist_directory=PERSIST_DIRECTORY, 
        embedding_function=EMBEDDING_MODEL,
        collection_name="kms_collection")
    print("✅ AI Model and Vector DB loaded successfully!",
          )
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

    def action_ask_emi(self):
        if VECTOR_DB is None:
            raise UserError("AI Engine is not loaded. Please restart Odoo server.")

        config = self.env['emi.config'].search([], limit=1)
        if not config:
            raise UserError("Please create Emi configuration in the settings menu first!")

        if not self.message:
            raise UserError("Please enter a message!")

        try:
            # --- BƯỚC 1: TRUY XUẤT TRI THỨC (Sử dụng đối tượng GLOBAL) ---
            user_role = self._get_user_access_role()
            security_filter = {"$or": [{"access_role": user_role}, {"access_role": "public"}]}
            
            # Tìm kiếm trực tiếp từ VECTOR_DB đã load sẵn trong RAM
            docs = VECTOR_DB.similarity_search(self.message, k=3, filter=security_filter)
            context_text = "\n\n".join([doc.page_content for doc in docs]) if docs else "No specific SOP found."

            # --- BƯỚC 2: XÂY DỰNG PROMPT ---
            rag_system_prompt = f"""
            You are a simple text-based assistant. 
            IMPORTANT: Do not attempt to use any tools or call any functions. 
            Just provide a direct text answer based ONLY on the provided context.
            
            If the answer is not in the context, say "I don't know".
            
            --- CONTEXT ---
            {context_text}
            ----------------
            """

            history = self.search([('user_id', '=', self.env.user.id)], limit=10)
            messages = [{"role": "system", "content": rag_system_prompt}]
            for chat in history:
                role = "user" if chat.is_user else "assistant"
                content = chat.message if chat.is_user else chat.response
                messages.append({"role": role, "content": content})

            messages.append({"role": "user", "content": self.message})

            # --- BƯỚC 3: GỬI CHO LM STUDIO ---
            client = openai.OpenAI(base_url=config.server_url, api_key="lm-studio")

            response = client.chat.completions.create(
                model=config.model_name,
                messages=messages,
                temperature=0.1, # Giảm cực thấp để AI bám sát văn bản, không "tự chế" kế hoạch
                # Thêm dòng dưới đây nếu model của bạn hỗ trợ (để tắt tool use)
                # tools=[], 
                # tool_choice="none",
            )

            ai_text = response.choices[0].message.content

            # --- BƯỚC 4: LƯU LỊCH SỬ ---
            self.env['emi.chat'].create({
                'user_id': self.env.user.id,
                'message': ai_text,
                'response': ai_text,
                'is_user': False
            })

            self.response = ai_text
            return True

        except Exception as e:
            raise UserError(f"Emi Error: {str(e)}")