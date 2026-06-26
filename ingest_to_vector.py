import xmlrpc.client
import os
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document

# --- CONFIGURATION ---
ODOO_URL = 'http://localhost:8069'
DB = 'mydb'
USER = 'admin'
PASS = 'admin'

def get_odoo_data():
    """Fetch raw records from Odoo via XML-RPC"""
    common = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/common')
    uid = common.authenticate(DB, USER, PASS, {})
    models = xmlrpc.client.ServerProxy(f'{ODOO_URL}/xmlrpc/2/object')
    return models.execute_kw(DB, uid, PASS, 'kms.knowledge.article', 'search_read', [[]], 
                             {'fields': ['name', 'body_html', 'workspace_dimension', 'tag_ids']})

def sanitize_html(html_content):
    """Strip HTML tags to prevent pollution of vector math (Task 11.1)"""
    if not html_content: return ""
    soup = BeautifulSoup(html_content, "html.parser")
    return soup.get_text(separator=" ")

def map_access_role(dimension):
    """Programmatically inject access privileges (Task 11.1)"""
    mapping = {
        'hr': 'hr_manager',
        'it': 'it_staff'
    }
    return mapping.get(dimension, 'public')

def main():
    print("🚀 Starting KMS Vector Ingestion Pipeline...")
    try:
        raw_data = get_odoo_data()
    except Exception as e:
        print(f"❌ Error connecting to Odoo: {e}")
        return

    # Sử dụng RecursiveCharacterTextSplitter
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=100)
    
    final_documents = []

    for art in raw_data:
        clean_text = sanitize_html(art['body_html'])
        if not clean_text: continue
        
        role = map_access_role(art['workspace_dimension'])
        chunks = text_splitter.split_text(clean_text)
        
        for chunk in chunks:
            # Sử dụng Document từ langchain_core
            doc = Document(
                page_content=chunk,
                metadata={
                    "title": art['name'],
                    "workspace_dimension": art['workspace_dimension'],
                    "access_role": role,
                    "tags": str(art['tag_ids'])
                }
            )
            final_documents.append(doc)

    if not final_documents:
        print("⚠️ No documents found to vectorize. Please check your Odoo data.")
        return
    
    print("📦 Loading Embedding Model (all-MiniLM-L6-v2)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    print(f"💾 Vectorizing {len(final_documents)} chunks into chroma_db...")
    vector_db = Chroma.from_documents(
        documents=final_documents,
        embedding=embeddings,
        persist_directory="./chroma_db",
        collection_name="kms_collection"
    )
    print("✅ Success! Vector DB is physically stored on disk.")

if __name__ == "__main__":
    main()