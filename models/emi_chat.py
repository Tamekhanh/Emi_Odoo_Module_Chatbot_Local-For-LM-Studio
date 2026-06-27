from odoo import models, fields, api
from odoo.exceptions import UserError
import uuid 
import requests
import re
import logging
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Cấu hình logging
logger = logging.getLogger("Odoo_KMS_AI")

# --- GLOBAL INITIALIZATION ---
try:
    print("🤖 Loading AI Embedding Model into memory...")
    EMBEDDING_MODEL = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    # LƯU Ý: Hãy đảm bảo đường dẫn này chính xác trên server Odoo của bạn
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
    session_id = fields.Char(string="Session ID", index=True) 
    message = fields.Text(string="Message")
    response = fields.Text(string="Emi's Response")
    is_user = fields.Boolean(string="Is User?", default=True)

    # ========================================================================
    # 1. PHÂN QUYỀN (GIỮ NGUYÊN THEO YÊU CẦU CỦA BẠN)
    # ========================================================================
    def _get_user_access_role(self):
        user = self.env.user
        roles = [] 
        try:
            # 1. Kiểm tra Admin
            if user.has_group('base.group_system'):
                return 'admin' 
            
            # 2. Kiểm tra HR (Group ID 77)
            if user.has_group(77):
                roles.append('hr_manager')
                
            # 3. Kiểm tra IT (Group ID 78)
            if user.has_group(78): 
                roles.append('it_staff')
        except Exception as e:
            print(f"❌ Error in role detection: {str(e)}")

        if not roles:
            return ['public']
        return roles

    # ========================================================================
    # 2. AI HELPER FUNCTIONS (TÍCH HỢP TỪ STANDALONE)
    # ========================================================================
    def _call_llm_api(self, messages, temperature=0.1, max_tokens=500):
        """Hàm dùng chung để gọi LM Studio/OpenAI API"""
        config = self.env['emi.config'].search([], limit=1)
        if not config:
            return "Error: Emi configuration not found."
        
        try:
            payload = {
                "model": config.model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            api_endpoint = f"{config.server_url.rstrip('/')}/chat/completions"
            response = requests.post(api_endpoint, json=payload, timeout=10)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
            return f"API Error: {response.status_code}"
        except Exception as e:
            return f"Connection Error: {str(e)}"

    def _extract_entity(self, query, entity_type="person"):
        """Sử dụng AI để chuẩn hóa thực thể (Có dấu/Không dấu)"""
        prompt = f"""You are a corporate terminology expert. 
        Extract the {entity_type} name or job title from the user's input.
        Provide a comma-separated list of all possible variations (accented, non-accented, English, Vietnamese).
        Example: "Salary of CEO" -> "CEO, Chief Executive Officer, Giám đốc điều hành, Giam doc dieu hanh"
        If none found, return 'NOT_FOUND'. ONLY return the list.
        User input: "{query}"
        Entity:"""
        
        messages = [
            {"role": "system", "content": "You are a precise terminology mapper."},
            {"role": "user", "content": prompt}
        ]
        return self._call_llm_api(messages, temperature=0, max_tokens=100)

    # ========================================================================
    # 3. DATA TOOLS (SỬ DỤNG ODOO ORM thay cho XML-RPC)
    # ========================================================================
    def _tool_get_salary(self, query, user_role):
        """Lấy lương từ hr.employee - Cho phép xem lương chính mình, Admin/HR xem tất cả"""
        q_lower = query.lower()
        
        # ========================================================================
        # BƯỚC 1: ƯU TIÊN KIỂM TRA LƯƠNG CỦA CHÍNH MÌNH (Self-Service)
        # ========================================================================
        if any(x in q_lower for x in ["my", "tôi", "mình", "của tôi"]):
            current_user = self.env.user
            # Tìm nhân viên liên kết với User đang đăng nhập
            my_employee = self.env['hr.employee'].search([('user_id', '=', current_user.id)], limit=1)
            
            if my_employee:
                # Lấy lương từ trường 'wage'
                wage = my_employee.wage if my_employee.wage else "Not specified"
                return f"Your current salary is: {wage} VND."
            else:
                return "I found your user account, but you are not linked to any Employee record. Please contact HR."

        # ========================================================================
        # BƯỚC 2: KIỂM TRA QUYỀN (Đối với yêu cầu xem lương người khác)
        # ========================================================================
        if user_role != 'admin' and 'hr_manager' not in (user_role if isinstance(user_role, list) else [user_role]):
            return "⚠️ ACCESS DENIED: You can only view your own salary. To view others, you need Admin or HR Manager permissions."
        
        # CASE 1: Lương cao nhất
        if any(x in q_lower for x in ["highest", "cao nhất", "max", "top"]):
            employees = self.env['hr.employee'].search([('wage', '>', 0)])
            if not employees: return "No salary data found."
            top_emp = max(employees, key=lambda e: float(e.wage or 0))
            return f"OFFICIAL HIGHEST SALARY: {top_emp.name} | Job: {top_emp.job_id.name} | Salary: {top_emp.wage} VND"

        # CASE 2: Tất cả lương
        if any(x in q_lower for x in ["all", "tất cả", "danh sách"]):
            employees = self.env['hr.employee'].search([], limit=50)
            res = [f"- {e.name} ({e.job_id.name}): {e.wage} VND" for e in employees]
            return "OFFICIAL SALARY LIST:\n" + "\n".join(res)

        # CASE 3: Cá nhân (Sử dụng biến thể)
        entity_string = self._extract_entity(query, "person")
        if entity_string == "NOT_FOUND": return "Could not identify a specific person."
        
        variations = [v.strip() for v in entity_string.split(',')]
        # Tìm kiếm linh hoạt cho nhiều biến thể
        employees = self.env['hr.employee'].search([], limit=100)
        found = []
        for emp in employees:
            if any(var.lower() in (emp.name or "").lower() for var in variations):
                found.append(emp)
        
        if not found: return f"Could not find employee matching '{entity_string}'."
        res = [f"Employee: {e.name} | Job: {e.job_id.name} | Salary: {e.wage} VND" for e in found[:3]]
        return "OFFICIAL SALARY DATA:\n" + "\n".join(res)

    def _tool_get_orders(self, query, user_role):
        """Lấy đơn hàng PO/SO dùng Regex"""
        if user_role != 'admin':
            return "⚠️ ACCESS DENIED: Only administrators can access financial orders."
        
        q_upper = query.upper()
        match = re.search(r'(P\s?O?\d+|S\s?O?\d+)', q_upper)
        order_id_str = match.group(1).replace(" ", "") if match else None

        if any(x in query.lower() for x in ["po", "purchase", "mua"]):
            if order_id_str and order_id_str.startswith('P'):
                numeric_id = re.sub(r'[^0-9]', '', order_id_str)
                po = self.env['purchase.order'].search([('name', 'ilike', numeric_id)], limit=1)
                if po:
                    lines = po.order_line
                    item_list = [f"- {l.product_id.name}: {l.product_qty} units" for l in lines]
                    return (f"OFFICIAL PO: {po.name}\nVendor: {po.partner_id.name}\nStatus: {po.state}\nTotal: {po.amount_total} VND\nItems:\n" + "\n".join(item_list))
            
            pos_list = self.env['purchase.order'].search([], limit=10)
            return "RECENT POs:\n" + "\n".join([f"- {p.name} | {p.partner_id.name} | {p.amount_total} VND" for p in pos_list])

        if any(x in query.lower() for x in ["so", "sale", "bán", "invoice"]):
            if order_id_str and order_id_str.startswith('S'):
                numeric_id = re.sub(r'[^0-9]', '', order_id_str)
                so = self.env['sale.order'].search([('name', 'ilike', numeric_id)], limit=1)
                if so:
                    lines = so.order_line
                    item_list = [f"- {l.product_id.name}: {l.product_uom_qty} units" for l in lines]
                    return (f"OFFICIAL SO: {so.name}\nCustomer: {so.partner_id.name}\nStatus: {so.state}\nTotal: {so.amount_total} VND\nItems:\n" + "\n".join(item_list))
            
            sos_list = self.env['sale.order'].search([], limit=10)
            return "RECENT SOs:\n" + "\n".join([f"- {s.name} | {s.partner_id.name} | {s.amount_total} VND" for s in sos_list])
        
        return None

    def _tool_get_products(self, query):
        """Truy vấn sản phẩm - Nâng cấp tìm kiếm đa biến thể"""
        entity_string = self._extract_entity(query, "product")
        if entity_string == "NOT_FOUND": return None

        # TÁCH BIẾN THỂ (ví dụ: "Talos-X, Talos X, Robot Talos")
        variations = [v.strip() for v in entity_string.split(',')]
        
        products = self.env['product.product'].search([], limit=100)
        found_products = []
        
        for p in products:
            # Kiểm tra nếu tên sản phẩm chứa bất kỳ biến thể nào AI gợi ý
            if any(var.lower() in p.name.lower() for var in variations):
                found_products.append(p)
        
        if not found_products: return None
        res = [f"Product: {p.name} | Price: {p.list_price} VND | Stock: {p.qty_available}" for p in found_products[:3]]
        return "PRODUCT DATA:\n" + "\n".join(res)

    # ========================================================================
    # 4. CORE RAG LOGIC (SMART ROUTING)
    # ========================================================================
    def get_safe_context(self, query, user_role, top_k=10):
        q_lower = query.lower()
        
        # 1. Routing tới Tri thức (SOPs)
        knowledge_keywords = ["bug", "error", "lỗi", "procedure", "quy trình", "how to", "cách", "hướng dẫn", "delay", "chậm"]
        if any(k in q_lower for k in knowledge_keywords):
            if VECTOR_DB is None: return "Knowledge base unavailable."
            docs = VECTOR_DB.similarity_search(query, k=top_k)
            allowed = ['admin', 'hr_manager', 'it_staff', 'public'] if user_role == 'admin' else [user_role, 'public'] if isinstance(user_role, list) else [user_role, 'public']
            safe_docs = [d.page_content for d in docs if d.metadata.get('access_role', 'public') in allowed]
            return "\n\n".join(safe_docs[:5])

        # 2. Routing tới Lương (Salary)
        if "salary" in q_lower or "lương" in q_lower:
            return self._tool_get_salary(query, user_role)

        # 3. Routing tới Nhân sự (Employee Info)
        if any(x in q_lower for x in ["who", "ai là", "employee", "nhân viên", "position", "chức vụ"]):
            entity_string = self._extract_entity(query, "person")
            if entity_string != "NOT_FOUND":
                # TÁCH BIẾN THỂ (Giống logic hàm lương)
                variations = [v.strip() for v in entity_string.split(',')]
                employees = self.env['hr.employee'].search([], limit=100) # Lấy danh sách để lọc
                
                found_employees = []
                for emp in employees:
                    # Kiểm tra nếu tên hoặc chức vụ khớp với BẤT KỲ biến thể nào
                    if any(var.lower() in emp.name.lower() or var.lower() in (emp.job_id.name or "").lower() for var in variations):
                        found_employees.append(emp)
                
                if found_employees:
                    return "\n".join([f"Employee: {e.name} | Position: {e.job_id.name} | Dept: {e.department_id.name}" for e in found_employees[:3]])

        # 4. Routing tới Đơn hàng (PO/SO)
        if any(x in q_lower for x in ["po", "so", "purchase", "sale", "đơn hàng", "hóa đơn"]):
            order_data = self._tool_get_orders(query, user_role)
            if order_data: return order_data

        # 5. Routing tới Sản phẩm (Products)
        if any(x in q_lower for x in ["product", "sản phẩm", "giá", "stock"]):
            prod_data = self._tool_get_products(query)
            if prod_data: return prod_data

        # Fallback: VectorDB
        if VECTOR_DB is not None:
            docs = VECTOR_DB.similarity_search(query, k=top_k)
            allowed = ['admin', 'hr_manager', 'it_staff', 'public'] if user_role == 'admin' else [user_role, 'public'] if isinstance(user_role, list) else [user_role, 'public']
            safe_docs = [d.page_content for d in docs if d.metadata.get('access_role', 'public') in allowed]
            return "\n\n".join(safe_docs[:5])
            
        return None

    def _get_ai_response(self, message, session_id):
        if VECTOR_DB is None: return "AI Engine not loaded."
        config = self.env['emi.config'].search([], limit=1)
        if not config: return "Please configure Emi settings first!"

        try:
            # 1. Lấy Context an toàn
            user_role = self._get_user_access_role()
            context = self.get_safe_context(message, user_role)

            if not context or len(context) < 10:
                return "⚠️ I'm sorry, I couldn't find any relevant information in Odoo or the Knowledge Base."

            # 2. Xây dựng Prompt
            system_prompt = f"""You are Emi, the advanced Corporate KMS AI.
            Answer based ONLY on the context. If PO/SO is present, list Vendor/Customer, Total, and Status.
            USER ROLE: {user_role}
            CONTEXT: {context}"""

            # 3. Lấy lịch sử chat để AI nhớ ngữ cảnh
            history = self.search([('user_id', '=', self.env.user.id), ('session_id', '=', session_id)], order='create_date asc', limit=10)
            messages = [{"role": "system", "content": system_prompt}]
            for chat in history:
                messages.append({"role": "user" if chat.is_user else "assistant", "content": chat.message if chat.is_user else chat.response})
            messages.append({"role": "user", "content": message})

            return self._call_llm_api(messages, temperature=config.temperature)

        except Exception as e:
            return f"Emi system error: {str(e)}"

    # ========================================================================
    # 5. ODOO API ENDPOINTS (Cho Giao diện JS)
    # ========================================================================
    @api.model
    def chat_with_emi(self, message=None, user_id=None, session_id=None):
        if not message: return "Error: No message content received."
        current_user_id = user_id or self.env.user.id
        current_session = session_id or str(uuid.uuid4())

        self.create({'user_id': current_user_id, 'session_id': current_session, 'message': message, 'is_user': True})
        ai_response = self._get_ai_response(message, current_session) 
        self.create({'user_id': current_user_id, 'session_id': current_session, 'message': ai_response, 'response': ai_response, 'is_user': False})
        
        return {'response': ai_response, 'session_id': current_session}

    @api.model
    def get_chat_history(self, session_id=None, user_id=None):
        current_user_id = user_id or self.env.user.id
        domain = [('user_id', '=', current_user_id)]
        if session_id: domain.append(('session_id', '=', session_id))
        chats = self.search(domain, order='create_date asc')
        return [{'id': c.id, 'message': c.message if c.is_user else c.response, 'is_user': c.is_user} for c in chats]

    @api.model
    def get_chat_sessions(self, user_id=None):
        current_user_id = user_id or self.env.user.id
        sessions = self.read(['session_id', 'create_date'], [('user_id', '=', current_user_id)])
        unique_sessions = {s['session_id']: s['create_date'] for s in sessions}
        return [{'session_id': sid, 'date': date} for sid, date in unique_sessions.items()]

    @api.model
    def clear_chat_history(self, user_id=None):
        current_user_id = user_id or self.env.user.id
        self.search([('user_id', '=', current_user_id)]).unlink()
        return True