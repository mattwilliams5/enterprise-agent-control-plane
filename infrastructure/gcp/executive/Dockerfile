FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY infrastructure/gcp/executive/requirements-cloud.txt /app/requirements-cloud.txt
RUN pip install --no-cache-dir -r /app/requirements-cloud.txt
COPY ui /app/ui
ENV STOREGUARD_CLOUD_MODE=1 PYTHONPATH=/app
EXPOSE 8080
CMD ["sh", "-c", "exec streamlit run ui/storeguard/app.py --server.address=0.0.0.0 --server.port=${PORT:-8080} --server.headless=true --server.enableCORS=true --server.enableXsrfProtection=true"]
