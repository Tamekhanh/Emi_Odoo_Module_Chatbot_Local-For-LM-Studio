from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# Dùng đúng đường dẫn tuyệt đối của bạn
PERSIST_DIR = r"D:\BT\2533_Knowledge_Management_System\Odoo\odoo\chroma_db"
embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

try:
    db = Chroma(
        persist_directory=PERSIST_DIR, 
        embedding_function=embeddings,
        collection_name="kms_collection")
    # Đếm tổng số bản ghi trong collection
    count = db._collection.count()
    print(f"\n--- DIAGNOSIS ---")
    print(f"Path: {PERSIST_DIR}")
    print(f"Total documents stored in Vector DB: {count}")
    
    if count == 0:
        print("❌ RESULT: Your Vector DB is EMPTY. You must run ingest_to_vector.py again.")
    else:
        print("✅ RESULT: Data exists. The problem is in the search query or embedding model.")
except Exception as e:
    print(f"❌ Error: {e}")