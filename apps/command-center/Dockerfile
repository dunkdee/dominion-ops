FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py intelligence.py revenue.py runtime_state.py index.html ./

# Packaging gate: the built image must be able to import every module used by app.py.
RUN python -c "import app, intelligence, revenue, runtime_state; assert app.app.title == 'Dominion Command Center'"

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
