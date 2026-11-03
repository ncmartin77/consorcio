#!/usr/bin/env bash
# Levanta la app contra el entorno local (docker-compose.local.yml), con las variables de .env.local.
#
#   scripts/correr_local.sh            # http://127.0.0.1:5000
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env.local ] || { echo "Falta .env.local: copiar .env.local.example y completarlo"; exit 1; }

docker compose -f docker-compose.local.yml up -d --wait db s3 >/dev/null 2>&1

set -a; . ./.env.local; set +a
case "${DATABASE_URL:-}" in
  *localhost*|*127.0.0.1*) ;;
  *) echo "DATABASE_URL de .env.local no apunta a la base local. No se arranca."; exit 1 ;;
esac

[ -x venv/bin/python ] || { python3 -m venv venv && venv/bin/pip install -q -r requirements.txt; }
exec venv/bin/python app.py
