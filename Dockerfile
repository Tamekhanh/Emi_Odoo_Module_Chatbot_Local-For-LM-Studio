FROM python:3.10-slim
WORKDIR /app

RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# TẠO THƯ MỤC VÀ CẤP QUYỀN GHI CHO CHROMADB
RUN mkdir -p /app/chroma_db && chmod -R 777 /app/chroma_db

EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]