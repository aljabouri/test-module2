FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY corpus ./corpus

RUN pip install --no-cache-dir ".[db,scan]" \
    && playwright install --with-deps chromium

# The catalog is data (Rules-as-Data) — mount or bake docs/rules-catalog
# and point KONFORMOS_CATALOG_DIR at it.
ENV KONFORMOS_CATALOG_DIR=/app/rules-catalog \
    KONFORMOS_STORAGE_DIR=/data/storage

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn --factory konformos.api.main:create_app --host 0.0.0.0 --port 8000"]
