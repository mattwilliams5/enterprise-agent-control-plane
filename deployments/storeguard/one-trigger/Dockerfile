FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt httpx cryptography
COPY applications/ applications/
COPY policy/ policy/
COPY identity/ identity/
COPY registry/ registry/
COPY vault.crt /app/vault.crt
RUN chmod -R a+rX /app/applications /app/policy /app/identity /app/registry /app/vault.crt
USER 65532:65532
CMD ["python", "-m", "applications.storeguard.cloud_dr.run_one_trigger_demo"]
