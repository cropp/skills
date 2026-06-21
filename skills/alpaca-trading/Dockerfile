FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/
COPY strategies/ ./strategies/

EXPOSE 7432

CMD ["python3", "scripts/dashboard.py", "--host", "0.0.0.0", "--port", "7432"]
