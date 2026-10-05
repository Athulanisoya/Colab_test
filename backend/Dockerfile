FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY data/severity_dataset ./data/severity_dataset
COPY data/raw ./data/raw
COPY models/severity_classifier ./models/severity_classifier
RUN mkdir -p data/uploads
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

