FROM python:3.11-slim

WORKDIR /app

# System deps for lxml, psycopg2
RUN apt-get update && apt-get install -y \
    gcc g++ curl libpq-dev libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
