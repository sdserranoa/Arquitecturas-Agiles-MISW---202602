# Contexto de build: la raíz del experimento (el dashboard reutiliza experimento/).
FROM python:3.11-slim
WORKDIR /app
COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY experimento/ ./experimento/
COPY dashboard/ .
EXPOSE 5000
CMD ["python", "app.py"]
