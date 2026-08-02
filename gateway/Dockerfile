FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir -p /app/data

ENV GATEWAY_HOST=0.0.0.0
ENV GATEWAY_PORT=8020
ENV GATEWAY_DB_PATH=/app/data/gateway.db

EXPOSE 8020
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020"]
