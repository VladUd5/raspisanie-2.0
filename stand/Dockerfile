FROM python:3.10-slim

WORKDIR /app
COPY stand/requirements.txt stand/requirements.txt
# медленный PyPI не должен ронять сборку: больший таймаут и повторы
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN pip install --no-cache-dir -r stand/requirements.txt
COPY stand stand

ENV DATA_DIR=/app/data \
    PARSER_URL=http://parser:8080 \
    PYTHONUNBUFFERED=1
EXPOSE 8501
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["streamlit", "run", "stand/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
