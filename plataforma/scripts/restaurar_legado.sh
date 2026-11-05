#!/usr/bin/env bash
# Restaura un backup cifrado del sistema actual (workflow backup-db.yml: pg_dump del
# esquema public de Supabase, cifrado con age) en la base LOCAL "legado" del Postgres
# de la plataforma. Sirve para comparar resultados y para la migración de datos (B5).
#
#   scripts/restaurar_legado.sh <archivo.dump.age | carpeta>
#
# Clave privada: $AGE_IDENTITY, o ~/.claude/age/key.txt por defecto.
# Borra y recrea solo la base local "legado". Nunca toca Supabase.
# El dump se descifra en un pipe hacia el contenedor: no queda en claro en el disco.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f deploy/compose.yaml"
IDENTITY="${AGE_IDENTITY:-$HOME/.claude/age/key.txt}"
OWNER=consorcios_owner

src="${1:-}"
[ -n "$src" ] || { echo "Uso: $0 <archivo.dump.age | carpeta>"; exit 1; }
if [ -d "$src" ]; then
  src=$(ls -t "$src"/*.dump.age 2>/dev/null | head -1)
  [ -n "$src" ] || { echo "No hay ningún .dump.age en la carpeta"; exit 1; }
fi
[ -f "$src" ] || { echo "No existe: $src"; exit 1; }
[ -r "$IDENTITY" ] || { echo "No se puede leer la clave age: $IDENTITY (usar AGE_IDENTITY=...)"; exit 1; }

echo "Backup:  $src"
echo "Destino: base local \"legado\" (contenedor consorcios-plataforma-db-1, 127.0.0.1:55433)"

$COMPOSE up -d --wait db >/dev/null 2>&1

$COMPOSE exec -T db psql -q -v ON_ERROR_STOP=1 -U "$OWNER" -d postgres \
  -c "DROP DATABASE IF EXISTS legado WITH (FORCE)" \
  -c "CREATE DATABASE legado OWNER $OWNER"

# Restaurar sin la entrada "SCHEMA public", que ya existe en la base nueva.
age -d -i "$IDENTITY" "$src" | $COMPOSE exec -T db sh -c '
  set -e
  f=$(mktemp); l=$(mktemp); trap "rm -f $f $l" EXIT
  cat > "$f"
  pg_restore -l "$f" | grep -v " SCHEMA - public " > "$l"
  pg_restore --no-owner --no-privileges --exit-on-error -L "$l" -U '"$OWNER"' -d legado "$f"
'

$COMPOSE exec -T db psql -q -U "$OWNER" -d legado -c "ANALYZE" >/dev/null
echo
echo "Listo. Filas por tabla:"
$COMPOSE exec -T db psql -U "$OWNER" -d legado -Atc "
  SELECT format('%-28s %s', table_name,
         (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) c FROM public.%I', table_name), false, true, '')))[1]::text)
    FROM information_schema.tables
   WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
   ORDER BY table_name"
