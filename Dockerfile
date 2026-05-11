FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY annotator_backend/ ./annotator_backend/
COPY db/ ./db/

EXPOSE 8000

CMD ["python", "-c", "print('API not wired yet; use docker compose for db only')"]
