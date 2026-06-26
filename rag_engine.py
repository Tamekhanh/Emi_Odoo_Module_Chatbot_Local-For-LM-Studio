import os
import xmlrpc.client
import logging
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from openai import OpenAI

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
        """Tách tên người hoặc sản phẩm bằng LLM"""
        prompt = f"""You are an information extraction tool. 
        Extract the {entity_type} name or job title from the user's input. 
        ONLY return the exact name/title, no explanations.
        If none, return 'NOT_FOUND'.
        
        User input: "{query}"
        Entity:"""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": "Extract entity strictly."},
                          {"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=20
            )
            return response.choices[0].message.content.strip().strip("'\"")
        except Exception as e:
            logger.error(f"Extraction Error: {e}")
            return "NOT_FOUND"

    def _tool_get_salary(self, query, user_role):
        """Truy vấn lương - CHỈ ADMIN"""
        if user_role != 'admin':
            return "⚠️ ACCESS DENIED: Only administrators can view salary information."
        
        entity = self._extract_entity(query, "person")
        if entity == "NOT_FOUND":
            return "I couldn't identify the person's name or title in your question."

        employees = self.odoo.search_read('hr.employee', [('name', 'ilike', entity)], ['name', 'wage'])
        if not employees:
            employees = self.odoo.search_read('hr.employee', [('job_id.name', 'ilike', entity)], ['name', 'wage'])
        if not employees:
            name_parts = entity.split()
            if name_parts:
                last_name = name_parts[-1]
                employees = self.odoo.search_read('hr.employee', [('name', 'ilike', last_name)], ['name', 'wage'])

        if not employees:
            return f"Could not find any employee matching '{entity}' in the system."
        
        res = [f"Employee: {e['name']} | Salary: {e.get('wage', 'N/A')} VND" for e in employees]
        return "OFFICIAL SALARY DATA:\n" + "\n".join(res)

    def _tool_get_orders(self, query, user_role):
        """Truy vấn PO, SO, Invoices - CHỈ ADMIN"""
        if user_role != 'admin':
            return "⚠️ ACCESS DENIED: Only administrators can access financial orders."
        
        res_text = ""
        q_lower = query.lower()
        if any(x in q_lower for x in ["po", "purchase", "mua"]):
            pos = self.odoo.search_read('purchase.order', [], ['name', 'amount_total'])
            if pos: res_text += "\nPURCHASE ORDERS:\n" + "\n".join([f"{p['name']} - {p['amount_total']} VND" for p in pos])
        
        if any(x in q_lower for x in ["so", "sale", "bán", "receipt", "invoice", "hóa đơn"]):
            sos = self.odoo.search_read('sale.order', [], ['name', 'amount_total'])
            if sos: res_text += "\nSALES/INVOICE ORDERS:\n" + "\n".join([f"{s['name']} - {s['amount_total']} VND" for s in sos])
        
        return res_text if res_text else None

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
            return "⚠️ I'm sorry, I couldn't find any relevant information in the Odoo ERP or the Knowledge Base that you have permission to access."

        system_prompt = f"""You are Emi, the advanced Corporate Knowledge Management System (KMS) AI.
        Answer the question based ONLY on the provided context. 
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