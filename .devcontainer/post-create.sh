#!/usr/bin/env bash
# One-time setup after the Codespace container is created.
set -euo pipefail

cd "$(dirname "$0")/../konformos"

echo "==> Installing KonformOS (db, scan, ai, dev extras)"
pip install --no-cache-dir -e ".[db,scan,ai,dev]"

echo "==> Installing Chromium for axe/crawler tests"
playwright install --with-deps chromium

echo "==> Running database migrations"
alembic upgrade head

echo "==> Validating rules catalog (expect 55 rules)"
python -c "from konformos.registry.loader import load_catalog; c = load_catalog(); assert len(c.rules) == 55, len(c.rules); print('catalog OK —', len(c.rules), 'rules')"

echo ""
echo "KonformOS Codespace is ready."
echo "  Start the API:  cd konformos && uvicorn --factory konformos.api.main:create_app --host 0.0.0.0 --port 8000"
echo "  Then open:      /docs (OpenAPI)  ·  /app (client SPA)  ·  /admin (admin UI)"
echo "  Run tests:      cd konformos && pytest -q"
