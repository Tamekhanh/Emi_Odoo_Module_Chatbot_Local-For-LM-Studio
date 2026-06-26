import os
import xmlrpc.client
import logging
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from openai import OpenAI
import re

# Cấu hình logging để theo dõi trong Docker
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("KMS_Engine")

load_dotenv()

class OdooClient:
    """Lớp kết nối trực tiếp với Odoo ERP thông qua XML-RPC"""
    def __init__(self):
        # Sử dụng host.docker.internal để gọi ra máy thật Windows
        self.url = os.getenv("ODOO_URL", "http://host.docker.internal:8069")
        self.db = os.getenv("ODOO_DB", "mydb")
        self.username = os.getenv("ODOO_USER", "admin")
        self.password = os.getenv("ODOO_PASSWORD", "admin")
        
        self.uid = None
        self.models = None
        self.connect()

    def connect(self):
        try:
            self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
            self.uid = self.common.authenticate(self.db, self.username, self.password, {})
            self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
            logger.info("✅ Connected to Odoo ERP successfully!")
        except Exception as e:
            logger.error(f"❌ Odoo Connection Error: {e}")
            self.uid = None

    def search_read(self, model, domain, fields, limit=10):
        if not self.uid or not self.models: return None
        try:
            ids = self.models.execute_kw(self.db, self.uid, self.password, model, 'search', [domain], {'limit': limit})
            if not ids: return []
            return self.models.execute_kw(self.db, self.uid, self.password, model, 'read', [ids], {'fields': fields})
        except Exception as e:
            logger.error(f"❌ Odoo Read Error in model {model}: {e}")
            return None

class RAGEngine:
    def __init__(self):
        # 1. Embeddings
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        # 2. VectorDB - Lấy đường dẫn từ .env
        self.persist_directory = os.getenv("CHROMA_DB_PATH", "/app/chroma_db")
        try:
            self.db = Chroma(
                persist_directory=self.persist_directory, 
                embedding_function=self.embeddings,
                collection_name="kms_collection"
            )
            logger.info(f"✅ VectorDB Loaded from: {self.persist_directory}")
        except Exception as e:
            logger.error(f"❌ ChromaDB Load Error: {e}")
            self.db = None

        # ========================================================================
        # PHẦN BỊ THIẾU: Khởi tạo LLM Client (LM Studio / OpenAI)
        # ========================================================================
        self.client = OpenAI(
            base_url=os.getenv("LLM_SERVER_URL", "http://host.docker.internal:1234/v1"), 
            api_key=os.getenv("LLM_API_KEY", "lm-studio")
        )
        self.model_name = os.getenv("LLM_MODEL_NAME", "local-model")
        # ========================================================================
        
        # 3. Odoo Client
        self.odoo = OdooClient()

    def _extract_entity(self, query, entity_type="person"):
        """
        Tách thực thể và MỞ RỘNG từ khóa. 
        Yêu cầu AI cung cấp cả bản có dấu và không dấu cho tiếng Việt.
        """
        prompt = f"""You are a corporate terminology expert. 
        Extract the {entity_type} name or job title from the user's input.
        If it is a job title or a Vietnamese name, provide a comma-separated list of 
        all possible variations (including accented and non-accented versions, 
        English and Vietnamese equivalents).
        
        Example: 
        - Input: "Salary of CEO" -> Output: "CEO, Chief Executive Officer, Giám đốc điều hành, Giam doc dieu hanh"
        - Input: "Salary of Le Hoang Khanh" -> Output: "Le Hoang Khanh, Lê Hoàng Khánh"
        - Input: "Salary of HR Manager" -> Output: "HR Manager, Human Resources Manager, Trưởng phòng nhân sự, Truong phong nhan su"
        
        If none found, return 'NOT_FOUND'.
        ONLY return the comma-separated list, no explanations.
        
        User input: "{query}"
        Entity:"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": "You are a precise terminology mapper."},
                          {"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=100
            )
            return response.choices[0].message.content.strip().strip("'\"")
        except:
            return "NOT_FOUND"

    def _tool_get_salary(self, query, user_role):
        """Truy vấn lương: Hỗ trợ tìm cá nhân, danh sách tất cả và tìm người lương cao nhất"""
        if user_role != 'admin':
            return "⚠️ ACCESS DENIED: Only administrators can view salary information."
        
        q_lower = query.lower()
        
        # --- CASE 1: TÌM NGƯỜI LƯƠNG CAO NHẤT (Highest Salary) ---
        if any(x in q_lower for x in ["highest", "cao nhất", "max", "maximum", "top"]):
            # Lấy tất cả nhân viên có lương (wage > 0)
            all_emp = self.odoo.search_read('hr.employee', [('wage', '>', 0)], ['name', 'wage', 'job_id'])
            if not all_emp:
                return "No salary data found in the system."
            
            # FIX: Explicitly convert wage to float to avoid string-sorting bugs
            try:
                sorted_emp = sorted(
                    all_emp, 
                    key=lambda x: float(x.get('wage') or 0), 
                    reverse=True
                )
                top_emp = sorted_emp[0]
            except Exception as e:
                logger.error(f"Sorting error: {e}")
                return "Error calculating the highest salary."
            
            job_data = top_emp.get('job_id')
            job_title = job_data[1] if isinstance(job_data, tuple) else job_data
            
            return (f"OFFICIAL HIGHEST SALARY DATA:\n"
                    f"Employee: {top_emp['name']} | Job: {job_title} | Salary: {top_emp['wage']} VND")

        # --- CASE 2: XEM TẤT CẢ LƯƠNG (All Salaries) ---
        if any(x in q_lower for x in ["all", "tất cả", "everyone", "danh sách lương"]):
            all_emp = self.odoo.search_read('hr.employee', [], ['name', 'wage', 'job_id'], limit=50)
            if not all_emp:
                return "No employee data found."
            
            res_list = []
            for e in all_emp:
                job_data = e.get('job_id')
                job_title = job_data[1] if isinstance(job_data, tuple) else job_data
                res_list.append(f"- {e['name']} ({job_title}): {e.get('wage', 'N/A')} VND")
            
            return "OFFICIAL SALARY LIST:\n" + "\n".join(res_list)

        # --- CASE 3: TÌM CÁ NHÂN (Individual - Your original logic) ---
        entity_string = self._extract_entity(query, "person")
        if entity_string == "NOT_FOUND":
            return "I couldn't identify a specific person's name in your question."

        variations = [v.strip() for v in entity_string.split(',')]
        employees = []
        
        for var in variations:
            # Search by Name
            res_name = self.odoo.search_read('hr.employee', [('name', 'ilike', var)], ['name', 'wage', 'job_id'])
            if res_name: employees.extend(res_name)

            # Search by Job Title
            res_job = self.odoo.search_read('hr.employee', [('job_id.name', 'ilike', var)], ['name', 'wage', 'job_id'])
            if res_job: employees.extend(res_job)

        if not employees:
            return f"Could not find any employee matching '{entity_string}'."
        
        unique_employees = {e['id']: e for e in employees}.values()
        res_list = []
        for e in unique_employees:
            job_data = e.get('job_id')
            job_title = job_data[1] if isinstance(job_data, tuple) else job_data
            res_list.append(f"Employee: {e['name']} | Job: {job_title} | Salary: {e.get('wage', 'N/A')} VND")
            
        return "OFFICIAL SALARY DATA:\n" + "\n".join(res_list)
    
    def _tool_get_orders(self, query, user_role):
        """Truy vấn đơn hàng: Cải tiến Regex và xử lý tiền tố Odoo (S vs SO)"""
        if user_role != 'admin':
            return "⚠️ ACCESS DENIED: Only administrators can access financial orders."
        
        q_upper = query.upper()
        q_lower = query.lower()
        
        # 1. CẢI TIẾN REGEX: 
        # (P\s?O?\d+) -> Khớp P1, PO1, P 1, PO 1
        # (S\s?O?\d+) -> Khớp S1, SO1, S 1, SO 1
        match = re.search(r'(P\s?O?\d+|S\s?O?\d+)', q_upper)
        order_id_str = match.group(1).replace(" ", "") if match else None

        # --- XỬ LÝ ĐƠN HÀNG MUA (PURCHASE ORDER) ---
        if any(x in q_lower for x in ["po", "purchase", "mua", "đơn hàng mua"]):
            if order_id_str and order_id_str.startswith('P'):
                # Tìm kiếm linh hoạt: Lấy phần số để search (ví dụ PO001 -> 001)
                numeric_id = re.sub(r'[^0-9]', '', order_id_str)
                pos = self.odoo.search_read('purchase.order', [('name', 'ilike', numeric_id)], ['name', 'amount_total', 'partner_id', 'state'])
                
                if pos:
                    p = pos[0]
                    partner = p.get('partner_id')
                    partner_name = partner[1] if isinstance(partner, tuple) else partner
                    
                    lines = self.odoo.search_read('purchase.order.line', [('order_id', '=', p['id'])], ['product_id', 'product_qty', 'price_unit'])
                    item_list = [f"- {l.get('product_id')[1] if isinstance(l.get('product_id'), tuple) else l.get('product_id')}: {l['product_qty']} units" for l in lines]
                    
                    return (f"OFFICIAL PURCHASE ORDER DATA:\n"
                            f"- Order ID: {p['name']}\n"
                            f"- Vendor: {partner_name}\n"
                            f"- Status: {p['state']}\n"
                            f"- Total: {p['amount_total']} VND\n"
                            f"Items:\n" + "\n".join(item_list))

            # Fallback Purchase
            pos_list = self.odoo.search_read('purchase.order', [], ['name', 'partner_id', 'amount_total'], limit=10)
            if pos_list:
                res = "\nRECENT PURCHASE ORDERS:\n"
                for p in pos_list:
                    partner = p.get('partner_id')
                    p_name = partner[1] if isinstance(partner, tuple) else partner
                    res += f"- {p['name']} | Partner: {p_name} | Total: {p['amount_total']} VND\n"
                return res

        # --- XỬ LÝ ĐƠN HÀNG BÁN (SALE ORDER) ---
        if any(x in q_lower for x in ["so", "sale", "bán", "receipt", "invoice", "hóa đơn", "đơn hàng bán"]):
            if order_id_str and order_id_str.startswith('S'):
                # Xử lý đặc biệt: Odoo thường dùng 'S' thay vì 'SO'
                numeric_id = re.sub(r'[^0-9]', '', order_id_str)
                sos = self.odoo.search_read('sale.order', [('name', 'ilike', numeric_id)], ['name', 'amount_total', 'partner_id', 'state'])
                
                if sos:
                    s = sos[0]
                    partner = s.get('partner_id')
                    partner_name = partner[1] if isinstance(partner, tuple) else partner
                    
                    lines = self.odoo.search_read('sale.order.line', [('order_id', '=', s['id'])], ['product_id', 'product_uom_qty', 'price_unit'])
                    item_list = [f"- {l.get('product_id')[1] if isinstance(l.get('product_id'), tuple) else l.get('product_id')}: {l['product_uom_qty']} units" for l in lines]
                    
                    return (f"OFFICIAL SALES ORDER DATA:\n"
                            f"- Order ID: {s['name']}\n"
                            f"- Customer: {partner_name}\n"
                            f"- Status: {s['state']}\n"
                            f"- Total: {s['amount_total']} VND\n"
                            f"Items:\n" + "\n".join(item_list))

            # Fallback Sales
            sos_list = self.odoo.search_read('sale.order', [], ['name', 'partner_id', 'amount_total'], limit=10)
            if sos_list:
                res = "\nRECENT SALES ORDERS:\n"
                for s in sos_list:
                    partner = s.get('partner_id')
                    p_name = partner[1] if isinstance(partner, tuple) else partner
                    res += f"- {s['name']} | Customer: {p_name} | Total: {s['amount_total']} VND\n"
                return res
        
        return None

    def _tool_get_products(self, query):
        """Truy vấn sản phẩm"""
        product_name = self._extract_entity(query, "product")
        if product_name == "NOT_FOUND": return None

        products = self.odoo.search_read('product.product', [('name', 'ilike', product_name)], ['name', 'list_price', 'qty_available'])
        if not products: return None
            
        res = [f"Product: {p['name']} | Price: {p['list_price']} VND | Stock: {p['qty_available']}" for p in products]
        return "PRODUCT DATA:\n" + "\n".join(res)

    def get_safe_context(self, query, user_role, top_k=10):
        """Router thông minh: Phân biệt giữa truy vấn Dữ liệu và truy vấn Tri thức"""
        q_lower = query.lower()
        
        # 1. Định nghĩa các từ khóa đặc trưng cho "Tri thức/Hướng dẫn/Lỗi"
        knowledge_keywords = ["bug", "error", "lỗi", "procedure", "quy trình", "how to", "cách", "hướng dẫn", "why", "tại sao", "delay", "chậm"]
        
        # 2. Định nghĩa các từ khóa đặc trưng cho "Dữ liệu/Số liệu"
        data_keywords = ["list", "danh sách", "how many", "bao nhiêu", "total", "tổng", "who", "ai", "wage", "lương", "price", "giá"]

        # CHIẾN THUẬT:
        # Nếu câu hỏi chứa từ khóa "Tri thức" (ví dụ: "Bug for Receipts") 
        # -> Ưu tiên tìm trong VectorDB trước, kể cả khi có từ "Receipts".
        if any(k in q_lower for k in knowledge_keywords):
            logger.info("Routing to: Knowledge Base (VectorDB)")
            if self.db is None: return "Knowledge base is unavailable."
            docs = self.db.similarity_search(query, k=top_k)
            allowed_roles = ['admin', 'hr_manager', 'it_staff', 'public'] if user_role == 'admin' else [user_role, 'public']
            safe_docs = [d.page_content for d in docs if d.metadata.get('access_role', 'public') in allowed_roles]
            return "\n\n".join(safe_docs[:5])

        # Nếu câu hỏi chứa từ khóa "Dữ liệu" hoặc không có từ khóa tri thức -> Tìm trong Odoo
        logger.info("Routing to: Odoo ERP (Structured Data)")
        if "salary" in q_lower or "lương" in q_lower:
            return self._tool_get_salary(query, user_role)
            
        if any(x in q_lower for x in ["po", "so", "purchase", "sale", "đơn hàng", "receipt", "invoice", "hóa đơn"]):
            order_data = self._tool_get_orders(query, user_role)
            if order_data: return order_data
            
        if any(x in q_lower for x in ["product", "sản phẩm", "giá", "stock"]):
            prod_data = self._tool_get_products(query)
            if prod_data: return prod_data
        
        # 3. Fallback cuối cùng: Nếu không khớp gì hết, cứ tìm trong VectorDB
        if self.db is not None:
            docs = self.db.similarity_search(query, k=top_k)
            allowed_roles = ['admin', 'hr_manager', 'it_staff', 'public'] if user_role == 'admin' else [user_role, 'public']
            safe_docs = [d.page_content for d in docs if d.metadata.get('access_role', 'public') in allowed_roles]
            return "\n\n".join(safe_docs[:5])
            
        return None

    def generate_answer(self, query, user_role='public', top_k=10, temperature=0.1):
        context = self.get_safe_context(query, user_role, top_k)
        if not context or len(context) < 10:
            return "⚠️ I'm sorry, I couldn't find any relevant information in the Odoo ERP or the Knowledge Base."

        # Cập nhật prompt để ép AI liệt kê chi tiết
        system_prompt = f"""You are Emi, the advanced Corporate Knowledge Management System (KMS) AI.
        Your task is to provide precise and detailed answers based ONLY on the provided context.
        
        GUIDELINES:
        1. If the context contains a Sales Order or Purchase Order, you MUST list:
           - The Customer or Vendor name.
           - The total amount and status.
        2. Do not summarize if detailed lists are available. Use bullet points for clarity.
        3. If the information is not in the context, state that you don't have it.
        
        USER ROLE: {user_role}
        CONTEXT: {context}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": query}],
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI Generation Error: {e}")
            return f"❌ AI Server Error: {str(e)}"