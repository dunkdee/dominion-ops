FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py intelligence.py model_gateway.py revenue.py runtime_state.py index.html ./
COPY alpaca_bridge.py trading_api.py trading_evidence.py ./
RUN python -c "import app, intelligence, model_gateway, revenue, runtime_state; assert app.app.title == 'Dominion Command Center'"
# alpaca_bridge is stdlib-only and must import standalone inside the image.
RUN python -c "import alpaca_bridge; assert alpaca_bridge.MODE == 'paper'; assert alpaca_bridge.LIVE_TRADING_HOSTS"
# trading_api/trading_evidence resolve control_plane at runtime from the
# read-only mount, so validate syntax here rather than importing.
RUN python -m py_compile trading_api.py trading_evidence.py

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
