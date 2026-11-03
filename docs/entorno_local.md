# Entorno local y backups

Para probar cambios sin tocar producción (Render + Supabase).

## Backup diario (`.github/workflows/backup-db.yml`)

Todos los días a las 03:17 (hora argentina) GitHub Actions hace un `pg_dump` del esquema `public` de Supabase, lo **cifra con age** y lo guarda como artifact por 30 días. También se puede correr a mano desde la pestaña Actions → "Backup base de datos" → Run workflow.

El repo es público: el dump nunca se sube sin cifrar.

Secretos del repo (Settings → Secrets and variables → Actions):

| Secreto | Valor |
|---|---|
| `SUPABASE_DB_URL` | Supabase → Connect → **Session pooler** (IPv4, puerto 5432): `postgresql://postgres.eboskmenitazzwfobwkiq:<clave>@aws-X-ca-central-1.pooler.supabase.com:5432/postgres` |
| `AGE_RECIPIENTS` | Una o más claves públicas age (`age1...`) separadas por espacios. Cualquiera de esas claves privadas puede descifrar el backup. |

Bajar el último backup:

```bash
gh run download --repo ncmartin77/consorcio -n <nombre_del_artifact> -D backups/
```

## Entorno local

Requisitos: Docker con Compose, `age` y Python 3.

```bash
docker compose -f docker-compose.local.yml up -d --wait   # Postgres :55432 + S3 :59000
scripts/restaurar_local.sh backups/                        # restaura el .dump.age más nuevo
cp .env.local.example .env.local                           # y completarlo
scripts/correr_local.sh                                    # http://127.0.0.1:5000
```

- **Postgres** local: `postgresql://consorcio:consorcio@127.0.0.1:55432/consorcio`.
- **S3** local: SeaweedFS en `http://127.0.0.1:59000`, bucket `comprobantes`, claves `consorcio` / `consorcio-local`. Hace de Supabase Storage: misma API S3.
- `restaurar_local.sh` borra y recrea el esquema `public` **de la base local** y se puede repetir. Usa la clave privada de `$AGE_IDENTITY` (por defecto `~/.claude/age/key.txt`).
- `correr_local.sh` no arranca si `DATABASE_URL` de `.env.local` no apunta a `127.0.0.1`/`localhost`.
- `.env`, `.env.local`, `backups/` y los `*.dump*` están en `.gitignore`.

Borrar todo el entorno local (datos incluidos):

```bash
docker compose -f docker-compose.local.yml down -v
```
