FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential tesseract-ocr tesseract-ocr-spa poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Playwright/Chromium (~400 MB) solo hace falta para el scraper visual de DIGEMID, desactivado por defecto.
ARG INSTALL_PLAYWRIGHT=false

COPY requirements-runtime.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu "torch==2.5.1+cpu" \
    && python -m pip install -r requirements-runtime.txt \
    && if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then python -m playwright install --with-deps chromium; fi

COPY . .
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

# Readiness real: BD, migraciones al dia, artefactos de modelo y catalogo cargado.
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/v1/health >/dev/null || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
