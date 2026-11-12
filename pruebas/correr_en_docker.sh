#!/usr/bin/env bash
# Corre una prueba (o cualquier script de Python del repo) dentro de un contenedor de
# Python con las dependencias de requirements.txt, sin instalar nada en la PC.
#
#   pruebas/correr_en_docker.sh pruebas/probar_v10.py
#   pruebas/correr_en_docker.sh -c "import app"          # cualquier argumento de python
#
# La base sale de .env.local (no versionado), como siempre: entorno_prueba.py solo acepta
# consorcio-tst o una base local (127.0.0.1 / localhost). Para la base local de Docker de
# plataforma/ (rama feat/plataforma):
#   DATABASE_URL=postgresql://consorcio_pruebas:pruebas-local@127.0.0.1:55433/consorcio_pruebas
#
# Almacenamiento de archivos (v11.0): las variables STORAGE_S3_* de esta terminal pasan al
# contenedor (si .env.local también las tiene, gana .env.local). Por ejemplo, el S3 local de
# plataforma/ (SeaweedFS, acepta cualquier clave):
#   STORAGE_S3_ENDPOINT=http://127.0.0.1:59001 STORAGE_S3_ACCESS_KEY_ID=local \
#   STORAGE_S3_SECRET_ACCESS_KEY=local pruebas/correr_en_docker.sh pruebas/probar_storage.py
#
# Las dependencias se instalan una vez en el volumen "consorcio-flask-venv"; si cambia
# requirements.txt se reinstalan solas. Red del host para llegar al Postgres en 127.0.0.1.
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGEN="python:3.12-slim"
VOLUMEN="consorcio-flask-venv"
HASH=$(sha256sum requirements.txt | cut -c1-16)

docker run --rm -i --network host \
  -u "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -e REQ_HASH="$HASH" \
  -e STORAGE_S3_ENDPOINT -e STORAGE_S3_REGION -e STORAGE_S3_BUCKET \
  -e STORAGE_S3_ACCESS_KEY_ID -e STORAGE_S3_SECRET_ACCESS_KEY \
  -v "$VOLUMEN":/venv -v "$PWD":/app -w /app \
  "$IMAGEN" sh -c '
    set -e
    if [ "$(cat /venv/.req 2>/dev/null)" != "$REQ_HASH" ]; then
      echo "Instalando dependencias en el volumen (una sola vez)..." >&2
      python -m venv --clear /venv >/dev/null
      /venv/bin/pip install -q --disable-pip-version-check -r requirements.txt >&2
      echo "$REQ_HASH" > /venv/.req
    fi
    exec /venv/bin/python "$@"
  ' sh "$@"
