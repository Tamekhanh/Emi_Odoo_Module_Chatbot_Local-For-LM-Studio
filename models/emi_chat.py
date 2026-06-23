from odoo import models, fields, api
from odoo.exceptions import UserError
import uuid 
import requests
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# --- GLOBAL INITIALIZATION ---
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
    # ADDED THIS FIELD: To group messages into the same chat session
    session_id = fields.Char(string="Session ID", index=True) 
    message = fields.Text(string="Message")
    response = fields.Text(string="Emi's Response")
    is_user = fields.Boolean(string="Is User?", default=True)

    # --- NEW API: Get the list of old chat sessions (For Sidebar display) ---
    @api.model
    def get_chat_sessions(self, user_id=None):
        current_user_id = user_id or self.env.user.id
        # Find all unique session_ids for this user
        sessions = self.read(['session_id', 'create_date'], [('user_id', '=', current_user_id)])
        
        # Group to get the first message's date as the chat session title
        unique_sessions = {}
        for s in sessions:
            sid = s['session_id']
            if sid not in unique_sessions:
                unique_sessions[sid] = s['create_date']
        
        return [{'session_id': sid, 'date': date} for sid, date in unique_sessions.items()]
    
    @api.model
    def clear_chat_history(self, user_id=None):
        current_user_id = user_id or self.env.user.id
        # Tìm tất cả tin nhắn của user hiện tại
        chats = self.search([('user_id', '=', current_user_id)])
        # Xóa toàn bộ
        chats.unlink()
        return True

    # --- UPDATED API: Get history for a specific Session ---
    @api.model
    def get_chat_history(self, session_id=None, user_id=None):
        current_user_id = user_id or self.env.user.id
        domain = [('user_id', '=', current_user_id)]
        
        if session_id:
            domain.append(('session_id', '=', session_id))
            
        chats = self.search(domain, order='create_date asc')
        return [{
            'id': c.id,
            'message': c.message if c.is_user else c.response,
            'is_user': c.is_user,
        } for c in chats]

    @api.model
    def chat_with_emi(self, message=None, user_id=None, session_id=None):
        if not message:
            return "Error: No message content received."

        current_user_id = user_id or self.env.user.id
        # If JS doesn't send session_id, generate a new one (new chat session)
        current_session = session_id or str(uuid.uuid4())

        # 1. Save user message (attached with session_id)
        self.create({
            'user_id': current_user_id,
            'session_id': current_session,
            'message': message,
            'is_user': True,
        })
        
        # 2. Call AI (Pass session_id so AI retrieves the correct session memory)
        ai_response = self._get_ai_response(message, current_session) 

        # 3. Save AI response (attached with session_id)
        self.create({
            'user_id': current_user_id,
            'session_id': current_session,
            'message': ai_response,
            'response': ai_response,
            'is_user': False,
        })
        return {
        'response': ai_response, 
        'session_id': current_session
        }
    
    def _get_user_access_role(self):
        user = self.env.user
        user_id = user.id
        roles = [] # Thay vì return ngay, ta bỏ tất cả quyền vào một list

        try:
            # 1. Kiểm tra Admin
            if user.has_group('base.group_system'):
                return 'admin' # Admin vẫn trả về string 'admin' để ưu tiên cao nhất
            
            # 2. Kiểm tra HR (Không dùng elif, dùng if để check tất cả)
            if user.has_group(77):
                roles.append('hr_manager')
                
            # 3. Kiểm tra IT
            if user.has_group(78): # Thay bằng XML ID nhóm IT của bạn
                roles.append('it_staff')

        except Exception as e:
            print(f"❌ Error in role detection: {str(e)}")

        # Nếu không có quyền đặc biệt nào, mặc định là public
        if not roles:
            return ['public']
            
        return roles # Trả về danh sách: ví dụ ['hr_manager', 'it_staff']
    

    # TOOL FUNCTION: Get product info directly from DB (Bypass RAG)
    def _tool_get_product_info(self, product_name):
        """Tool to get product information directly from the DB"""
        # Only fetch active products (active = True)
        products = self.env['product.product'].search([
            ('name', 'ilike', product_name),
            ('active', '=', True)
        ], limit=3)
        
        if not products:
            return f"Could not find any active product named '{product_name}' in the system."
        
        result = []
        for p in products:
            result.append(f"- {p.name}: Price {p.list_price} VND, Stock: {p.qty_available}")
        
        return "Product data directly from DB:\n" + "\n".join(result)
    
    # TOOL FUNCTION: Get employee salary info directly from DB (Bypass RAG)
    def _tool_get_salary_info(self, message=""):
        """Lấy thông tin lương: Ưu tiên lương của chính người dùng hiện tại"""
        try:
            # 1. Xác định nhân viên liên kết với User hiện tại
            current_user = self.env.user
            # Tìm nhân viên có user_id khớp với user đang đăng nhập
            my_employee = self.env['hr.employee'].search([('user_id', '=', current_user.id)], limit=1)

            # 2. Kiểm tra nếu người dùng hỏi về "lương của tôi" (my salary / lương của tôi)
            if "my" in message.lower() or "tôi" in message.lower() or "mình" in message.lower():
                if my_employee:
                    # Lấy lương linh hoạt (như đã hướng dẫn ở bước trước)
                    wage = "Không có dữ liệu lương"
                    if hasattr(my_employee, 'wage') and my_employee.wage:
                        wage = my_employee.wage
                    elif hasattr(my_employee, 'contract_id') and my_employee.contract_id and hasattr(my_employee.contract_id, 'wage'):
                        wage = my_employee.contract_id.wage
                    
                    return f"Your current salary is: {wage} VND."
                else:
                    return "I found your user account, but you are not linked to any Employee record in the system. Please contact HR."

            # 3. Nếu không phải hỏi về bản thân, mà là hỏi chung (chỉ dành cho Manager/Admin)
            # Kiểm tra quyền trước khi cho xem lương người khác
            user_role = self._get_user_access_role()
            if user_role not in ['admin', 'hr_manager']:
                return "You do not have permission to view other employees' salaries."

            # Lấy danh sách lương cho Manager
            employees = self.env['hr.employee'].search([])
            result = []
            for emp in employees:
                wage = "No data"
                if hasattr(emp, 'wage') and emp.wage: wage = emp.wage
                elif hasattr(emp, 'contract_id') and emp.contract_id and hasattr(emp.contract_id, 'wage'): wage = emp.contract_id.wage
                result.append(f"- {emp.name}: {wage}")
                
            return "Salary list for all employees:\n" + "\n".join(result)

        except Exception as e:
            return f"Error retrieving salary info: {str(e)}"

    def _call_llm_for_intent(self, prompt, config):
        """
        Helper function to call LM Studio for intent classification.
        Always returns one of 3 strings: 'PRODUCT', 'SALARY', or 'GENERAL'.
        """
        try:
            # Setup payload for the small model (Router)
            # Use low temperature (0.1) for accurate keyword extraction without creativity
            payload = {
                "model": config.model_name,
                "messages": [
                    {
                        "role": "system", 
                        "content": "You are a strict routing assistant. You must ONLY reply with exactly one of these words: PRODUCT, SALARY, or GENERAL."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3, 
                "max_tokens": 10 # Only need to generate 1 word
            }
            
            headers = {"Content-Type": "application/json"}
            api_endpoint = f"{config.server_url.rstrip('/')}/chat/completions"
            
            # Send request to LM Studio (timeout 5s to prevent freezing if LM Studio lags)
            response = requests.post(api_endpoint, json=payload, headers=headers, timeout=5)
            
            if response.status_code == 200:
                result_data = response.json()
                # Get AI text response, uppercase and strip whitespace
                intent_text = result_data['choices'][0]['message']['content'].strip().upper()
                
                # Safely catch keywords
                if "PRODUCT" in intent_text: 
                    return "PRODUCT"
                elif "SALARY" in intent_text: 
                    return "SALARY"
                else:
                    return "GENERAL"
            else:
                # Log error if AI server fails and fallback to GENERAL
                print(f"❌ Emi Routing Error: API returned {response.status_code} - {response.text}")
                return "GENERAL"
                
        except Exception as e:
            # Fallback: If LM Studio crashes or network fails, 
            # default to GENERAL to still search ChromaDB for SOPs.
            print(f"❌ Emi Routing Exception: {str(e)}")
            return "GENERAL"
    
    def _extract_keyword(self, message, config):
        """Helper function using LLM to extract the exact product name from a natural language query"""
        try:
            payload = {
                "model": config.model_name,
                "messages": [
                    {
                        "role": "system", 
                        "content": "You are an information extraction tool. Extract the PRODUCT NAME (or service) from the user's input. ONLY return the exact product name, no explanations, no punctuation, do not repeat the user's words."
                    },
                    {"role": "user", "content": message}
                ],
                "temperature": 0.3, # Low temperature for precise, deterministic output
                "max_tokens": 20
            }
            
            headers = {"Content-Type": "application/json"}
            api_endpoint = f"{config.server_url.rstrip('/')}/chat/completions"
            
            response = requests.post(api_endpoint, json=payload, headers=headers, timeout=5)
            
            if response.status_code == 200:
                result_data = response.json()
                # Get the extracted product name
                keyword = result_data['choices'][0]['message']['content'].strip()
                # Remove quotes if AI accidentally adds them
                return keyword.strip("'\"")
            else:
                return message # Fallback: return the original message
                
        except Exception as e:
            print(f"❌ Emi Extraction Error: {str(e)}")
            return message # If AI fails, use the raw user input as the keyword

    def _get_ai_response(self, message, session_id):
        if VECTOR_DB is None:
            return "AI Engine is not loaded. Please restart the Odoo server."

        config = self.env['emi.config'].search([], limit=1)
        if not config:
            return "Please create the Emi configuration in the settings menu first!"

        try:
            # --- STEP 1: INTENT ROUTING ---
            router_prompt = f"""
                Classify the user question into: 'PRODUCT', 'SALARY', or 'GENERAL'.
                - 'PRODUCT': ONLY if the user is asking for a specific item's price, stock, or specs (e.g., "What is the price of LiDAR?").
                - 'SALARY': ONLY if asking about wages, bonuses, or HR contracts.
                - 'GENERAL': If the question is about a PROCESS, a GUIDE, a PROCEDURE, a SOP, or a general knowledge article (e.g., "How to...", "Procedures for...", "Ensuring...").
                Return ONLY 1 word.
                Question: "{message}"
                """
            intent = self._call_llm_for_intent(router_prompt, config) 

            # --- STEP 2: RETRIEVE DATA ---
            dynamic_context = ""

            if "PRODUCT" in intent:
                product_keyword = self._extract_keyword(message, config)
                dynamic_context = self._tool_get_product_info(product_name=product_keyword)
                
            elif "SALARY" in intent:
                dynamic_context = self._tool_get_salary_info(message=message)
                
            else:
                # 1. Xác định quyền của User
                user_role = getattr(self, '_get_user_access_role', lambda: ['public'])()
                print(f"\n--- SECURITY CHECK ---")
                print(f"👤 User Role: {user_role}")

                # Chuẩn hóa allowed_roles thành một list
                if user_role == 'admin':
                    allowed_roles = 'admin' 
                else:
                    allowed_roles = user_role if isinstance(user_role, list) else [user_role]
                    if 'public' not in allowed_roles:
                        allowed_roles.append('public')
                
                # 2. Lấy dữ liệu từ Vector DB (Bỏ qua filter của Chroma vì nó bị lỗi trên máy bạn)
                # Lấy nhiều kết quả (k=10) để lọc thủ công
                docs = VECTOR_DB.similarity_search(message, k=10) 
                
                # 3. BỨC TƯỜNG LỬA PYTHON (Lọc thủ công từng tài liệu)
                final_safe_docs = []
                for i, d in enumerate(docs):
                    doc_role = d.metadata.get('access_role', 'private')
                    
                    # Kiểm tra quyền
                    if user_role == 'admin' or doc_role in allowed_roles:
                        print(f"✅ Doc {i}: Role {doc_role} -> ALLOWED")
                        final_safe_docs.append(d)
                    else:
                        print(f"❌ Doc {i}: Role {doc_role} -> BLOCKED (User {allowed_roles} cannot see this)")
                
                if final_safe_docs:
                    dynamic_context = "Information from SOP:\n" + "\n\n".join([d.page_content for d in final_safe_docs])
                else:
                    dynamic_context = "No relevant documents found or you do not have permission to access this information."
                print(f"----------------------\n")

            # --- STEP 3: BUILD PROMPT & CALL LLM ---
            rag_system_prompt = f"""
            You are Emi, Odoo's AI Assistant. 
            Answer the user's question based ONLY ON THE INFORMATION PROVIDED BELOW.
            If the information is missing or permission is denied, politely say you don't have the info.
            
            --- SYSTEM DATA ---
            {dynamic_context}
            -------------------
            """
            
            history = self.search([('user_id', '=', self.env.user.id), ('session_id', '=', session_id)], order='create_date asc', limit=10)
            messages = [{"role": "system", "content": rag_system_prompt}]
            for chat in history:
                messages.append({"role": "user" if chat.is_user else "assistant", "content": chat.message if chat.is_user else chat.response})
            messages.append({"role": "user", "content": message})

            payload = {"model": config.model_name, "messages": messages, "temperature": config.temperature}
            api_endpoint = f"{config.server_url.rstrip('/')}/chat/completions"
            response = requests.post(api_endpoint, json=payload, timeout=10)
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"Error from AI server: {response.text}"

        except Exception as e:
            return f"Emi system error: {str(e)}"

    # Keep the old function if you still use the Form View
    def action_ask_emi(self):
        # Create a temporary session_id for the form view to prevent missing parameter errors
        temp_session = str(uuid.uuid4())
        
        res = self._get_ai_response(self.message, temp_session)
        self.response = res
        
        # Create an AI record to save history
        user_role = getattr(self, '_get_user_access_role', lambda: 'public')()
        print(f"DEBUG: User {self.env.user.name} is identified as role: {user_role}") 
        
        self.create({
            'user_id': self.env.user.id, 
            'session_id': temp_session,
            'message': self.message, 
            'response': res, 
            'is_user': False
        })
        return True 
