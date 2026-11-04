---
name: Proyecto Sistema de Expensas (Consorcio)
description: App Flask multi-consorcio para administración de consorcios edilicios argentinos — stack actual, archivos clave, convenciones de trabajo
type: project
---
**Repositorio GitHub:** https://github.com/ncmartin77/consorcio.git  
**Directorio local (WSL):** `/home/norberto/consorcio/`  
**Versión actual:** 2.1-1210

## Stack
- Python + Flask
- **PostgreSQL (Supabase)** como BD — capa de acceso en `pg_db.py` (reemplazó a `excel_db.py`)
- ReportLab para PDFs, qrcode+Pillow para QR en recibos
- Bootstrap 5 + Bootstrap Icons en frontend
- Jinja2 templates con filtros personalizados (`mes_largo`, etc.)
- **Deploy en Render** (free tier, ver `render.yaml` en la raíz)
- Git en Windows: `/mnt/c/Program Files/Git/bin/git.exe` desde WSL

## Archivos clave
- `app.py` — rutas Flask (controladores finos, sin lógica de negocio)
- `pg_db.py` — toda la lógica de datos (reemplaza excel_db.py)
- `pdf_gen.py` — generación de PDFs (ReportLab)
- `render.yaml` — configuración de deploy en Render
- `requirements.txt` — dependencias pip
- `version.txt` — versión (formato X.Y-DDMM, incrementar en cada push)
- `templates/` — Jinja2 + Bootstrap 5

## Multi-consorcio
- `_consorcios.json` en la raíz indexa todos los consorcios
- `session["consorcio_id"]` activa el consorcio en cada request
- `@before_request` llama `db.set_active_consorcio()` que fija `_tls.consorcio_id`
- Toda la BD tiene columna `consorcio_id` (string/UUID) para aislar datos por consorcio

## Convenciones
- CERRADA es inmutable: ningún cambio permitido en períodos cerrados
- `pg_db.py` usa thread-local `_tls.consorcio_id`; NUNCA pasar consorcio_id como parámetro explícito
- Git en Windows: `/mnt/c/Program Files/Git/bin/git.exe`; el post-commit hook auto-pushea a GitHub
- Incrementar `version.txt` en cada push (Y += 1)
- `APP_ENV=produccion` (default); `APP_ENV=pruebas` usa `data/pruebas/` como data dir

## How to apply
Al retomar el proyecto desde otra PC:
1. Clonar: `git clone https://github.com/ncmartin77/consorcio.git`
2. `cd consorcio && python -m venv venv && source venv/bin/activate`
3. `pip install -r requirements.txt`
4. Crear `.env` con `DATABASE_URL=<connection string de Supabase>` y `SECRET_KEY=<cualquier string>`
5. `python app.py` → http://localhost:5000
6. Ver `reference_env_vars.md` para todas las variables de entorno
