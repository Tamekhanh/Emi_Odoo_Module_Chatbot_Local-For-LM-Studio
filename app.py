import streamlit as st
from rag_engine import RAGEngine

st.set_page_config(page_title="KMS AI Chatbot", layout="wide")

if "rag_engine" not in st.session_state:
    st.session_state.rag_engine = RAGEngine()
if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.title("⚙️ AI Configuration")
    st.subheader("👤 User Simulation")
    user_role = st.selectbox("Select User Role", options=["public", "it_staff", "hr_manager", "admin"])
    st.info(f"Current Access Level: **{user_role.upper()}**")
    st.divider()
    top_k = st.slider("Context Retrieval (Top-K)", 1, 20, 10)
    temp = st.slider("Creativity (Temperature)", 0.0, 1.0, 0.1)
    if st.button("Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

st.title("🤖 EMI - Corporate RAG Chatbot")
st.caption(f"RBAC Active. User: {user_role}")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask me anything..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner(f"Processing as {user_role}..."):
            answer = st.session_state.rag_engine.generate_answer(prompt, user_role, top_k, temp)
            st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})