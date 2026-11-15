FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends poppler-utils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 5000
# Threaded workers: a long conversion runs in a thread while the worker
# keeps reporting to gunicorn, so it is not killed at the timeout (sync
# workers were, after 30 s), and a big PDF no longer blocks other imports.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--worker-class", "gthread", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
