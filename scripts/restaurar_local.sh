#!/usr/bin/env bash
# Restaura un backup cifrado (de .github/workflows/backup-db.yml) en el Postgres local.
#
#   scripts/restaurar_local.sh <archivo.dump.age | archivo.zip de gh run download | carpeta>
#
# Clave privada: $AGE_IDENTITY, o ~/.claude/age/key.txt por defecto.
# Borra y recrea el esquema public de la base LOCAL. Nunca toca Supabase.
set -euo pipefail

cd "$(dirname "$0")/.."
COMPOSE="docker compose -f docker-compose.local.yml"
IDENTITY="${AGE_IDENTITY:-$HOME/.claude/age/key.txt}"

src="${1:-}"
[ -n "$src" ] || { echo "Uso: $0 <archivo.dump.age | carpeta>"; exit 1; }
if [ -d "$src" ]; then
  src=$(ls -t "$src"/*.dump.age 2>/dev/null | head -1)
  [ -n "$src" ] || { echo "No hay ningun .dump.age en la carpeta"; exit 1; }
fi
[ -f "$src" ] || { echo "No existe: $src"; exit 1; }
[ -r "$IDENTITY" ] || { echo "No se puede leer la clave age: $IDENTITY (usar AGE_IDENTITY=...)"; exit 1; }

echo "Backup:  $src"
echo "Destino: Postgres local (contenedor consorcio-local-db, puerto 55432)"

$COMPOSE up -d --wait db >/dev/null 2>&1

# Vaciar solo el esquema public de la base local
$COMPOSE exec -T db psql -q -v ON_ERROR_STOP=1 -U consorcio -d consorcio \
  -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public AUTHORIZATION consorcio;"

# Descifrar dentro del contenedor (el dump en claro no queda en el disco de la maquina)
# y restaurar sin la entrada "SCHEMA public", que ya existe.
age -d -i "$IDENTITY" "$src" | $COMPOSE exec -T db sh -c '
  set -e
  f=$(mktemp); l=$(mktemp); trap "rm -f $f $l" EXIT
  cat > "$f"
  pg_restore -l "$f" | grep -v " SCHEMA - public " > "$l"
  pg_restore --no-owner --no-privileges --exit-on-error -L "$l" -U consorcio -d consorcio "$f"
'

$COMPOSE exec -T db psql -q -U consorcio -d consorcio -c "ANALYZE" >/dev/null
echo
echo "Listo. Filas por tabla:"
$COMPOSE exec -T db psql -U consorcio -d consorcio -Atc "
  SELECT format('%-28s %s', table_name,
         (xpath('/row/c/text()', query_to_xml(format('SELECT count(*) c FROM public.%I', table_name), false, true, '')))[1]::text)
    FROM information_schema.tables
   WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
   ORDER BY table_name"
