FROM python:3.10-slim

WORKDIR /app

# Cài đặt dependencies hệ thống cho ChromaDB/HuggingFace
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Mở port cho Streamlit (ví dụ 8501) hoặc Flask
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]