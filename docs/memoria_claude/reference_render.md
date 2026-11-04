---
name: Render - Deploy del sistema de consorcio
description: Configuración del servicio web en Render.com para el sistema de consorcio
type: reference
---
**Dashboard:** https://render.com (cuenta ***@***)  
**Nombre del servicio:** consorcio  
**Plan:** free

## Configuración (render.yaml en la raíz del repo)
```yaml
services:
  - type: web
    name: consorcio
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app --workers 2 --timeout 120
    envVars:
      - key: DATABASE_URL
        sync: false          # ← se configura manualmente en el dashboard
      - key: SECRET_KEY
        generateValue: true  # ← Render genera un valor aleatorio
      - key: APP_ENV
        value: produccion
```

## Variables de entorno en el dashboard de Render
Ir a: Dashboard → consorcio → Environment
- `DATABASE_URL` → pegar el connection string de Supabase (ver reference_supabase_consorcio.md)
- `SECRET_KEY` → ya generado por Render
- `APP_ENV` → `produccion`

## Deploy automático
- Cada push a `master` en GitHub dispara un redeploy automático
- El post-commit hook en el repo local ya hace `git push` automáticamente

## URL pública
La URL del servicio se obtiene en el dashboard de Render (algo como `https://consorcio-XXXX.onrender.com`).  
**Importante:** configurar esa URL en la app: Configuración → campo "URL de la app" → guardar.  
Esto afecta los QR de verificación de recibos y los links públicos de recibos.
