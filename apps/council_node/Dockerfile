# Council Node image. Build context is the repository root so the app can
# read the shared governance/ tree at build time for validation.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends git curl \
 && rm -rf /var/lib/apt/lists/*

COPY apps/council_node/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/council_node /app/apps/council_node
COPY governance /app/governance

# Runs unprivileged. The receipt volume is mounted with matching ownership.
RUN useradd --system --uid 10001 council \
 && mkdir -p /var/lib/dominion/receipts \
 && chown -R council:council /var/lib/dominion /app
USER council

EXPOSE 8200

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8200/health',timeout=3).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "apps.council_node.app.main:app", \
     "--host", "0.0.0.0", "--port", "8200", "--log-config", "/dev/null"]
