---
name: Migración Excel → PostgreSQL (consorcio)
description: Plan y estado de la migración de la BD del sistema de consorcio de Excel/openpyxl a PostgreSQL en Supabase
type: project
---
Decisión tomada el 2026-10-10: migrar el sistema de consorcio de Excel como BD a PostgreSQL (Supabase) para poder hacer deploy en la nube (Render + Supabase, gratis sin tarjeta de crédito).

**Why:** Excel como BD en filesystem es incompatible con deploys en contenedores (disco efímero). Firebase/Cloud Run requiere tarjeta. Supabase free tier (PostgreSQL + Storage) + Render free tier = $0 sin tarjeta.

**How to apply:** Al trabajar en el proyecto consorcio, tener en cuenta que la migración está en curso. El objetivo es reemplazar `excel_db.py` por una capa PostgreSQL, manteniendo todas las rutas Flask y templates intactos.

## Estado al 2026-10-10

- [x] Decisión arquitectónica tomada: Supabase (PostgreSQL) + Render
- [x] Cuenta Supabase creada, proyecto "Consorcio" creado (ID: eboskmenitazzwfobwkiq)
- [ ] Verificar connection string correcto desde el dashboard
- [ ] Diseñar schema PostgreSQL
- [ ] Escribir script de migración de datos (Excel → PostgreSQL)
- [ ] Reescribir `excel_db.py` para PostgreSQL
- [ ] Adaptar manejo de archivos PDF a Supabase Storage
- [ ] Deploy en Render

## Decisiones de diseño pendientes

- Multi-consorcio: cada tabla tendrá columna `consorcio_id` (UUID) como FK
- Columnas dinámicas `pct_CATEGORIA` de UNIDADES → tabla separada `unidad_porcentajes (consorcio_id, unidad_id, categoria, porcentaje)`
- Hojas `LIQUIDACIONES_YYYY` → tabla única `liquidaciones` con columna `periodo` (YYYY-MM)
- CONFIG key-value → tabla `config (consorcio_id, clave, valor)`
- Archivos PDF → Supabase Storage bucket por consorcio

## Python venv disponible en Windows

`/mnt/c/Users/Maria/Downloads/consorcio-main/consorcio-main/venv/Scripts/python.exe`
psycopg2-binary ya instalado en ese venv.
