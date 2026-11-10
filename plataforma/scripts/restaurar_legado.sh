#!/usr/bin/env bash
# Restaura un backup cifrado del sistema actual (workflow backup-db.yml: pg_dump del
# esquema public de Supabase, cifrado con age) en la base LOCAL "legado" del Postgres
# de la plataforma. Sirve para comparar resultados y para la migración de datos (B5).
#
#   scripts/restaurar_legado.sh <archivo.dump.age | carpeta>
#
# Variables opcionales:
#   BASE=consorcio_pruebas   base destino (por defecto "legado")
#   DUENO=consorcio_pruebas  rol dueño de la base y de las tablas; si no existe se crea
#                            (LOGIN, sin superusuario) con la clave $CLAVE_DUENO
#                            (por defecto "pruebas-local": solo desarrollo, 127.0.0.1)
#
# Clave privada: $AGE_IDENTITY, o ~/.claude/age/key.txt por defecto.
# Borra y recrea solo la base local indicada. Nunca toca Supabase.
# El dump se descifra en un pipe hacia el contenedor: no queda en claro en el disco.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f deploy/compose.yaml"
IDENTITY="${AGE_IDENTITY:-$HOME/.claude/age/key.txt}"
ADMIN=consorcios_owner          # superusuario del contenedor: crea roles y bases
BASE="${BASE:-legado}"
DUENO="${DUENO:-$ADMIN}"
CLAVE_DUENO="${CLAVE_DUENO:-pruebas-local}"
case "$BASE" in consorcios|postgres|template0|template1)
  echo "No se restaura sobre la base \"$BASE\""; exit 1;; esac
[[ "$BASE" =~ ^[a-z_][a-z0-9_]*$ && "$DUENO" =~ ^[a-z_][a-z0-9_]*$ ]] || { echo "Nombre de base o rol inválido"; exit 1; }

src="${1:-}"
[ -n "$src" ] || { echo "Uso: $0 <archivo.dump.age | carpeta>"; exit 1; }
if [ -d "$src" ]; then
  src=$(ls -t "$src"/*.dump.age 2>/dev/null | head -1)
  [ -n "$src" ] || { echo "No hay ningún .dump.age en la carpeta"; exit 1; }
fi
[ -f "$src" ] || { echo "No existe: $src"; exit 1; }
[ -r "$IDENTITY" ] || { echo "No se puede leer la clave age: $IDENTITY (usar AGE_IDENTITY=...)"; exit 1; }

echo "Backup:  $src"
echo "Destino: base local \"$BASE\", dueño $DUENO (contenedor consorcios-plataforma-db-1, 127.0.0.1:55433)"

$COMPOSE up -d --wait db >/dev/null 2>&1

if [ "$DUENO" != "$ADMIN" ]; then
  $COMPOSE exec -T db psql -q -v ON_ERROR_STOP=1 -U "$ADMIN" -d postgres -v clave="$CLAVE_DUENO" <<SQL
SELECT format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', '$DUENO')
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$DUENO') \\gexec
ALTER ROLE $DUENO PASSWORD :'clave';
SQL
fi
$COMPOSE exec -T db psql -q -v ON_ERROR_STOP=1 -U "$ADMIN" -d postgres \
  -c "DROP DATABASE IF EXISTS $BASE WITH (FORCE)" \
  -c "CREATE DATABASE $BASE OWNER $DUENO"

# Restaurar sin la entrada "SCHEMA public", que ya existe en la base nueva.
age -d -i "$IDENTITY" "$src" | $COMPOSE exec -T db sh -c '
  set -e
  f=$(mktemp); l=$(mktemp); trap "rm -f $f $l" EXIT
  cat > "$f"
  pg_restore -l "$f" | grep -v " SCHEMA - public " > "$l"
  pg_restore --no-owner --no-privileges --exit-on-error -L "$l" -U '"$DUENO"' -d '"$BASE"' "$f"
'

$COMPOSE exec -T db psql -q -U "$DUENO" -d "$BASE" -c "ANALYZE" >/dev/null 2>&1
echo
echo "Listo. Filas por tabla:"
$COMPOSE exec -T db psql -U "$DUENO" -d "$BASE" -Atc "
  SELECT format('%-28s %s', table_name,
         (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) c FROM public.%I', table_name), false, true, '')))[1]::text)
    FROM information_schema.tables
   WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
   ORDER BY table_name"
