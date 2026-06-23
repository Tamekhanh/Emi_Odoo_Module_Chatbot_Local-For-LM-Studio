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
        return ai_response, current_session # Return session_id for JS to save locally
    
    def _get_user_access_role(self):
        user = self.env.user
        
        if user.has_group('base.group_system'):
            return 'admin' 
            
        # Móc thẳng vào mảng groups_id.ids của user
        if 77 in user.groups_id.ids: 
            return 'hr_manager'
            
        if 78 in user.groups_id.ids: 
            return 'it_staff'

        return 'public'
    

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
    def _tool_get_salary_info(self):
        """Tool to get salary information for the current user and subordinates (if authorized)"""
        if 'hr.contract' not in self.env:
            return "The system does not have the HR Contract module (hr_contract) installed."

        employees = self.env['hr.employee'].search([]) 
        
        if not employees:
            return "You do not have permission to view HR/salary information or there is no data."
            
        result = []
        for emp in employees:
            # Find the currently active ('open') contract of the employee
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'open')
            ], limit=1)
            
            wage = contract.wage if contract else "No active contract"
            result.append(f"- Employee {emp.name}: Salary {wage}")
            
        return "Salary data directly from the system:\n" + "\n".join(result)

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
            Classify the following user question into one of 3 categories: 'PRODUCT', 'SALARY', or 'GENERAL'.
            - Choose 'PRODUCT' if asking about product info, price, or inventory.
            - Choose 'SALARY' if asking about salary, bonus, or HR.
            - Choose 'GENERAL' if it's about processes, regulations, general guides, or greetings.
            Return ONLY 1 word.
            Question: "{message}"
            """
            
            # CALL API TO GET INTENT 
            intent = self._call_llm_for_intent(router_prompt, config) 

            # --- STEP 2: RETRIEVE DATA BASED ON INTENT ---
            dynamic_context = ""

            if "PRODUCT" in intent:
                # Extract product name instead of passing the whole message
                product_keyword = self._extract_keyword(message, config)
                print(f"DEBUG: Product name extracted by AI: '{product_keyword}'")
                
                # Call Tool with the cleaned product name
                dynamic_context = self._tool_get_product_info(product_name=product_keyword)
                
            elif "SALARY" in intent:
                dynamic_context = self._tool_get_salary_info()
                
            else:
                # GENERAL - Search static SOPs using Vector DB
                user_role = getattr(self, '_get_user_access_role', lambda: 'public')() # Safeguard if method is missing
                security_filter = None if user_role == 'admin' else {"$or": [{"access_role": user_role}, {"access_role": "public"}]}
                
                docs = VECTOR_DB.similarity_search(message, k=3, filter=security_filter)
                dynamic_context = "Information from Standard Operating Procedures (SOP):\n" + "\n\n".join([d.page_content for d in docs]) if docs else "No relevant documents found."

            # --- STEP 3: BUILD CONTEXT (PROMPT & MEMORY) ---
            rag_system_prompt = f"""
            You are Emi, Odoo's AI Assistant. 
            Answer the user's question based ONLY ON THE INFORMATION PROVIDED BELOW by the system.
            If the provided information contains errors or the system reports a lack of permission, politely explain this to the user.
            
            --- SYSTEM RETURNED DATA ---
            {dynamic_context}
            -------------------------------
            """
            
            # Only get the history of the current session
            history = self.search([
                ('user_id', '=', self.env.user.id),
                ('session_id', '=', session_id) 
            ], order='create_date asc', limit=10)
            
            messages = [{"role": "system", "content": rag_system_prompt}]
            
            for chat in history:
                role = "user" if chat.is_user else "assistant"
                content = chat.message if chat.is_user else chat.response
                messages.append({"role": role, "content": content})

            messages.append({"role": "user", "content": message})

            # --- STEP 4: CALL LM STUDIO FOR ANSWER ---
            payload = {
                "model": config.model_name,
                "messages": messages,
                "temperature": config.temperature
            }
            headers = {"Content-Type": "application/json"}
            
            # Send request to LM Studio URL (e.g., http://localhost:1234/v1/chat/completions)
            api_endpoint = f"{config.server_url.rstrip('/')}/chat/completions"
            response = requests.post(api_endpoint, json=payload, headers=headers)
            
            if response.status_code == 200:
                result_data = response.json()
                return result_data['choices'][0]['message']['content']
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
