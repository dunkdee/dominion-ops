FROM python:3.11-slim@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd --gid 10001 wixagent \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin wixagent \
    && mkdir -p /app/logs /data \
    && chown -R wixagent:wixagent /app/logs /data

USER 10001:10001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
