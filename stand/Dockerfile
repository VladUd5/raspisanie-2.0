FROM python:3.10-slim

WORKDIR /app
COPY stand/requirements.txt stand/requirements.txt
# медленный PyPI не должен ронять сборку: больший таймаут и повторы
ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10
RUN pip install --no-cache-dir -r stand/requirements.txt
COPY stand stand

ENV DATA_DIR=/app/data \
    PARSER_URL=http://parser:8080 \
    STAFF_BASE_PATH=rukovodstvo \
    PYTHONUNBUFFERED=1
WORKDIR /app/stand
EXPOSE 8000 8501
# Один образ — три роли (команды задаёт docker-compose.yml):
#   collector: python collector.py run
#   public:    uvicorn public.app:app --host 0.0.0.0 --port 8000
#   staff:     streamlit (команда по умолчанию)
CMD ["sh", "-c", "exec streamlit run app.py --server.address=0.0.0.0 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false --server.baseUrlPath=$STAFF_BASE_PATH"]
