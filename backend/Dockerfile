# API FastAPI JobCompass (contexte de build = racine du projet)
FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf_cache \
    MODELS_DIR=/opt/models

WORKDIR /app

# PyTorch CPU (image plus légère que la version CUDA)
RUN pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

# code partagé avec le pipeline (taxonomie des compétences, modèles ML)
COPY pipeline /opt/pipeline
RUN pip install "/opt/pipeline[ml]"

COPY backend/app ./app

# Sécurité : le conteneur ne tourne pas en root
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /opt/hf_cache /opt/models \
 && chown -R appuser /opt/hf_cache /opt/models /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
