import streamlit as st
from rag_engine import RAGEngine

st.set_page_config(page_title="KMS AI Chatbot", layout="wide")

# Khởi tạo Engine một lần duy nhất
if "rag_engine" not in st.session_state:
    st.session_state.rag_engine = RAGEngine()
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- SIDEBAR: Cấu hình tham số ---
with st.sidebar:
    st.title("⚙️ Cấu hình AI")
    top_k = st.slider("Số lượng đoạn văn bản (Top-K)", 1, 10, 3)
    temp = st.slider("Độ sáng tạo (Temperature)", 0.0, 1.0, 0.1)
    if st.button("Xóa lịch sử chat"):
        st.session_state.messages = []
        st.rerun()

# --- MAIN UI: Chat Interface ---
st.title("🤖 EMI - Corporate RAG Chatbot")
st.caption("Hệ thống trả lời tự động dựa trên tri thức nội bộ doanh nghiệp")

# Hiển thị lịch sử chat
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Xử lý input người dùng
if prompt := st.chat_input("Hãy nhập câu hỏi của bạn..."):
    # Lưu câu hỏi user
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Gọi RAG Engine để lấy câu trả lời
    with st.chat_message("assistant"):
        with st.spinner("Đang tra cứu tri thức..."):
            answer = st.session_state.rag_engine.generate_answer(
                prompt, top_k=top_k, temperature=temp
            )
            st.markdown(answer)
    
    st.session_state.messages.append({"role": "assistant", "content": answer})