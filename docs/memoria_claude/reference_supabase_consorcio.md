---
name: Supabase - Proyecto Consorcio
description: Credenciales y connection string de Supabase (PostgreSQL) para el sistema de consorcio
type: reference
---
**Dashboard:** https://supabase.com (cuenta ***@***)  
**Nombre del proyecto:** Consorcio  
**Project ID:** `eboskxnitazzwfobwkiq`  
**Region:** ca-central-1 (Canada Central)  
**DB Password:** `***` (ver dashboard de Supabase → Project Settings → Database)

## Connection string (DATABASE_URL)
```
postgresql://postgres:***@db.eboskxnitazzwfobwkiq.supabase.co:5432/postgres
```

## Cómo obtener el string actualizado
Dashboard → Settings → Database → Connection string → URI (usar el Transaction Pooler si hay muchas conexiones concurrentes).

## Acceso MCP desde Claude Code
El servidor MCP de Supabase está configurado — usar herramientas `mcp__supabase__*` directamente.  
Project ID para las llamadas MCP: `eboskxnitazzwfobwkiq`

## Estado
- Proyecto creado 2026-10-10
- `pg_db.py` ya implementado y en producción (reemplazó `excel_db.py`)
- Deploy en Render consume esta BD
