#!/bin/sh
# Lo corre la imagen de Postgres solo al crear el volumen por primera vez.
# POSTGRES_USER (consorcios_owner) es el dueño del esquema y corre las migraciones;
# consorcios_app es el rol con el que se conectan la API y el worker: sin BYPASSRLS
# ni propiedad de tablas, así las políticas RLS se aplican siempre.
set -eu
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
     -v app_pass="$APP_DB_PASSWORD" <<'SQL'
CREATE ROLE consorcios_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'app_pass';
GRANT CONNECT ON DATABASE consorcios TO consorcios_app;
SQL
