FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY applications/ /app/applications/
ENV PORT=8080
CMD ["sh", "-c", "exec uvicorn applications.storeguard.cloud_control.api:app --host 0.0.0.0 --port ${PORT}"]
