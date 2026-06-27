from odoo import models, fields, api
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from bs4 import BeautifulSoup


class EmiConfig(models.Model):
    _name = 'emi.config'
    _description = 'Emi Chatbot Configuration'

    name = fields.Char(default="Emi Settings", required=True)
    server_url = fields.Char(
        default="http://localhost:1234/v1", 
        string="LM Studio URL", 
        help="Address of the LM Studio server, e.g. http://localhost:1234/v1"
    )
    model_name = fields.Char(
        default="local-model", 
        string="Model Name", 
        help="Name of the model to use in LM Studio, e.g. 'local-model'"
    )
    system_prompt = fields.Text(
        string="Emi personality (System Prompt)", 
        default="You are Emi, an AI assistant integrated into Odoo. You help users with their questions and tasks related to Odoo. Always be polite and helpful." \
        "You have to answer if it in the context of Odoo, if not, you can answer but should mention that you are not sure because it's outside of your knowledge domain." \
        "If the user greets you, respond with a greeting as well."
    )
    temperature = fields.Float(
        default=0.3, 
        string="Response Creativity (Temperature)", 
        help="Higher values (e.g., 0.8) make the output more creative, while lower values (e.g., 0.2) make it more focused and deterministic."
    )
    def action_sync_vector_db(self):
        """This method is called when the user clicks the "Sync Vector DB" button in the Emi Config form view. It fetches knowledge articles from the KMS module, processes them, and stores them in a vector database for AI retrieval."""
        # 1. Lấy data thẳng từ DB thông qua ORM của Odoo
        articles = self.env['kms.knowledge.article'].search([])
        
        if not articles:
            return { 'warning': 'Không có bài viết nào trong KMS để nạp!' }

        # 2. Xử lý nạp dữ liệu (Logic giống hệt file ingest_to_//vector.py)
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        persist_dir = r"D:\BT\2533_Knowledge_Management_System\Odoo\odoo\chroma_db"
        
        final_docs = []
        for art in articles:
            # Làm sạch HTML
            soup = BeautifulSoup(art.body_html or "", "html.parser")
            clean_text = soup.get_text(separator=" ")
            
            # Gán nhãn bảo mật
            role = 'hr_manager' if art.workspace_dimension == 'hr' else \
                   'it_staff' if art.workspace_dimension == 'it' else 'public'
            
            chunks = text_splitter.split_text(clean_text)
            for chunk in chunks:
                final_docs.append(Document(
                    page_content=chunk,
                    metadata={"title": art.name, "access_role": role}
                ))

        # 3. Lưu vào Vector DB
        Chroma.from_documents(
            documents=final_docs,
            embedding=embeddings,
            persist_directory=persist_dir,
            collection_name="kms_collection"
        )
        return { 'warning': f'Đã đồng bộ thành công {len(final_docs)} đoạn tri thức vào AI!' }