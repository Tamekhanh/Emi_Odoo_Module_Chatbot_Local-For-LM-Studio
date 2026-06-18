import os
from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from openai import OpenAI

load_dotenv()

class RAGEngine:
    def __init__(self):
        # 1. Load Embedding Model & Vector DB (Từ Tuần 11)
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.persist_directory = "D:/BT/2533_Knowledge_Management_System/Odoo/odoo/chroma_db"
        self.db = Chroma(
            persist_directory=self.persist_directory, 
            embedding_function=self.embeddings,
            collection_name="kms_collection"
        )
        # 2. Kết nối LM Studio/OpenAI
        self.client = OpenAI(base_url=os.getenv("LLM_SERVER_URL", "http://localhost:1234/v1"), 
                             api_key="lm-studio")

    def get_context(self, query, top_k=3):
        # Truy xuất top-k đoạn văn bản liên quan nhất
        docs = self.db.similarity_search(query, k=top_k)
        return "\n\n".join([doc.page_content for doc in docs])

    def generate_answer(self, query, top_k=3, temperature=0.1):
        context = self.get_context(query, top_k)
        
        # Fallback logic: Nếu context trống hoặc quá ngắn
        if not context or len(context) < 10:
            return "⚠️ Tôi không tìm thấy thông tin liên quan trong cơ sở dữ liệu nội bộ để trả lời câu hỏi này."

        # System Prompt (Do BA thiết kế)
        system_prompt = f"""You are a corporate AI assistant. 
        Answer the question based ONLY on the provided context. 
        If the answer is not in the context, say "I don't know".
        Do not hallucinate or use external knowledge.
        If the user greets you, respond with a greeting as well.
        
        CONTEXT:
        {context}
        """

        response = self.client.chat.completions.create(
            model="local-model",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            temperature=temperature
        )
        return response.choices[0].message.content