import os
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings

# Connect to physical storage
PERSIST_DIR = r"D:\BT\2533_Knowledge_Management_System\Odoo\odoo\chroma_db"
embedding_model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
db = Chroma(persist_directory=PERSIST_DIR, embedding_function=embedding_model)

print("\n=================== RUNNING KMS WEEK 11 AUDIT ===================")

# --- TEST SCENARIO A: SEMANTIC ACCURACY ---
query_synonym = "How do we welcome a new developer into the team?"
results_semantic = db.similarity_search(query_synonym, k=2)

print(f"\n🔍 [TEST A] Semantic Search Results for Query: '{query_synonym}'")
print("-" * 65)
for i, doc in enumerate(results_semantic):
    print(f"[{i+1}] MATCH FOUND:\n    -> Source Title : {doc.metadata.get('title')}\n    -> Access Role  : {doc.metadata.get('access_role')}\n    -> Snippet      : {doc.page_content[:130]}...\n")

# --- TEST SCENARIO B: SECURITY ISOLATION ---
query_shared = "System safety and disciplinary actions protocol"
it_user_filter = {"$or": [{"access_role": "it_staff"}, {"access_role": "public"}]}

results_filtered = db.similarity_search(query_shared, k=2, filter=it_user_filter)

print(f"\n🔒 [TEST B] Simulating User with 'it_staff' Role (FILTER: access_role == it_staff OR public)")
print("-" * 65)
for i, doc in enumerate(results_filtered):
    print(f"[{i+1}] SECURE MATCH FOUND:\n    -> Source Title : {doc.metadata.get('title')}\n    -> Access Role  : {doc.metadata.get('access_role')}\n    -> Snippet      : {doc.page_content[:130]}...\n")