FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .

RUN python -c "import sys; assert sys.version_info >= (3, 11), sys.version" \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip check \
    && python -c "from browser_use import Agent; from langchain_anthropic import ChatAnthropic; from playwright.async_api import async_playwright; print('browser-agents dependency smoke test passed')"

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "120"]
