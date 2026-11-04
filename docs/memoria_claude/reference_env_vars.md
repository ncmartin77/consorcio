---
name: Variables de entorno - Sistema Consorcio
description: Todas las variables de entorno que necesita la app Flask del sistema de consorcio
type: reference
---
## Obligatorias
| Variable | Descripción | Ejemplo |
|---|---|---|
| `DATABASE_URL` | Connection string PostgreSQL (Supabase) | `postgresql://postgres:***@db.eboskxnitazzwfobwkiq.supabase.co:5432/postgres` |
| `SECRET_KEY` | Clave Flask para firmar sesiones | cualquier string aleatorio largo |

## Opcionales
| Variable | Descripción | Default |
|---|---|---|
| `APP_ENV` | Entorno (`produccion` / `pruebas`) | `produccion` |
| `APP_HOST` | IP de bind del servidor Flask | `127.0.0.1` (usar `0.0.0.0` para red local) |
| `GOOGLE_CLIENT_ID` | OAuth Google (login con Google) | — |
| `GOOGLE_CLIENT_SECRET` | OAuth Google | — |

## Configuración en-app (guardada en la BD, no en env vars)
Estas se configuran desde la UI en Configuración → no son env vars:
- `url_app` — URL pública de la app (ej. `https://consorcio-xxxx.onrender.com`). Afecta QR de recibos y links públicos.
- `clave_firma` — HMAC secret para firmar recibos (auto-generada si no existe).
- `dia_vencimiento` — día del mes en que vencen las expensas.
- `tasa_mora` — tasa de interés por mora (decimal, ej. `0.05` = 5%).

## Para desarrollo local
Crear `/home/norberto/consorcio/.env` (no versionado):
```
DATABASE_URL=postgresql://postgres:***@db.eboskxnitazzwfobwkiq.supabase.co:5432/postgres
SECRET_KEY=dev-secret-local
APP_ENV=produccion
```
Flask no carga `.env` automáticamente — usar `python-dotenv` o exportar manualmente:
```bash
export $(cat .env | xargs) && python app.py
```
