# Flujo de lectura y escritura de la base de datos

## Resumen

La base de datos es un archivo Excel (`edificio_brasil.xlsx`).
El archivo vive en **Google Drive** como fuente de verdad y se mantiene un
**cache local** para que todas las operaciones en disco sean rápidas.

---

## Paths por entorno

| Entorno       | Cache local                          | Google Drive                              |
|---------------|--------------------------------------|-------------------------------------------|
| `produccion`  | `data/edificio_brasil.xlsx`          | `ConsorcioApp/produccion/edificio_brasil.xlsx` |
| `pruebas`     | `data/pruebas/edificio_brasil.xlsx`  | `ConsorcioApp/pruebas/edificio_brasil.xlsx`    |
| `produccion`  | `data/facturas/{prov}/{file}.pdf`    | `ConsorcioApp/produccion/facturas/{prov}/{file}.pdf` |
| `pruebas`     | `data/pruebas/facturas/{prov}/{file}.pdf` | `ConsorcioApp/pruebas/facturas/{prov}/{file}.pdf` |

El entorno se selecciona con la variable de entorno `APP_ENV` (default: `produccion`).

---

## Diagrama general

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CONSORCIO APP                                   │
│                                                                         │
│   Browser ──► Flask (app.py) ──► excel_db.py ──► openpyxl              │
│                                       │                                 │
│                               ┌───────┴────────┐                       │
│                               ▼                ▼                       │
│                         Disco local       drive_sync.py                │
│                     data/edificio_brasil      │                        │
│                         .xlsx (cache)         ▼                        │
│                                        Google Drive API                │
│                                     ConsorcioApp/{env}/                │
│                                     edificio_brasil.xlsx               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Flujo: inicio de la app

```
python app.py
     │
     ▼
db.sync_from_drive()
     │
     ├─ Drive configurado? (token.json existe)
     │       │
     │       ├── SÍ ──► Descarga Excel de Drive → sobreescribe cache local
     │       │                  │
     │       │                  ├── Excel existe en Drive → OK, cache actualizado
     │       │                  └── No existe en Drive   → se usa local (o _init_db)
     │       │
     │       └── NO ──► No hace nada (modo local puro)
     │
     ▼
¿Existe DB_PATH local?
     │
     ├── SÍ ──► app.run()  (usar cache local)
     │
     └── NO ──► _init_db() → crea Excel vacío
                    │
                    └── app.run()
```

---

## Flujo: lectura (`_get_wb`)

Ocurre en **cada operación de base de datos** (get_config, get_facturas, etc.).

```
_get_wb()
     │
     ├─ ¿Existe DB_PATH en disco local?
     │       │
     │       ├── SÍ ──► load_workbook(DB_PATH) → devuelve workbook
     │       │
     │       └── NO ──► ¿Drive configurado?
     │                       │
     │                       ├── SÍ ──► drive.download_excel(DB_PATH)
     │                       │              │
     │                       │              ├── Descarga OK → load_workbook(DB_PATH)
     │                       │              └── Falla / no existe → _init_db()
     │                       │
     │                       └── NO ──► _init_db() → load_workbook(DB_PATH)
```

> **Nota:** En operación normal el archivo local siempre existe (descargado al
> inicio). Este fallback sólo ocurre si el archivo se eliminó manualmente.

---

## Flujo: escritura (`_save_wb`)

Ocurre al final de **cada función que modifica datos** (save_factura, save_gasto, etc.).

```
_save_wb(wb)
     │
     ▼
wb.save(DB_PATH)           ← síncrono, inmediato, en disco local
     │
     ▼
¿Drive configurado?
     │
     ├── SÍ ──► drive.upload_excel_async(DB_PATH)
     │              │
     │              └── Thread daemon ──► Google Drive API (PUT/POST)
     │                   (no bloquea la respuesta HTTP)
     │
     └── NO ──► fin
```

---

## Flujo: upload de comprobante PDF

Cuando el usuario adjunta un PDF/imagen a una factura:

```
POST /facturas/<fid>/upload
     │
     ▼
Guardar archivo en disco:
  data/{env}/facturas/{proveedor}/{timestamp}.pdf
     │
     ▼
db.set_factura_archivo_pdf(fid, ruta_relativa)
     │
     ├── Actualizar columna archivo_pdf en Excel (FACTURAS sheet)
     ├── _save_wb(wb)  →  guarda Excel local + upload Excel a Drive (async)
     │
     └── ¿Drive configurado?
              │
              └── SÍ ──► drive.upload_factura_async(local_path, ruta_relativa)
                              │
                              └── Thread daemon ──► Google Drive API
                                   Crea: ConsorcioApp/{env}/facturas/{prov}/{timestamp}.pdf
```

---

## Flujo: migración de esquema (`migrar.py`)

Ejecutado por `actualizar.bat` al actualizar a una versión nueva:

```
python migrar.py
     │
     ▼
¿Drive configurado?
     │
     ├── SÍ ──► drive.download_excel(DB_PATH)   ← baja la versión más reciente
     │                                              antes de migrar
     └── NO ──► usa el archivo local

     │
     ▼
Aplicar cambios de esquema (hojas nuevas, columnas nuevas)
     │
     ▼
wb.save(DB_PATH)    ← guarda localmente

     │
     ▼
¿Drive configurado? ¿Hubo cambios?
     │
     └── SÍ ──► drive.upload_excel(DB_PATH)   ← síncrono (el script no termina
                                                  hasta confirmar la subida)
```

---

## Flujo: backup manual (botón en la app)

```
GET /backup
     │
     ▼
Crea ZIP en memoria con:
  - data/{env}/edificio_brasil.xlsx
  - data/{env}/facturas/**/*.pdf
     │
     ▼
Descarga al navegador como:
  backup_edificio_brasil_YYYYMMDD_HHMM.zip
```

> El backup es siempre del **cache local**. Para hacer backup desde Drive,
> usar el botón de descarga directamente en Google Drive.

---

## Estados de sincronización

| Estado | Condición | Comportamiento |
|--------|-----------|----------------|
| **Drive activo** | `credentials/token.json` existe | Descarga al inicio, sube en cada escritura |
| **Local puro** | No hay `token.json` | Opera solo con `data/`. No toca Drive |
| **Primer uso con Drive** | `token.json` existe, sin Excel en Drive | `_get_wb` crea la BD localmente; el primer `_save_wb` la crea en Drive |
| **Sin internet** | Drive configurado pero sin red | `_save_wb` falla silenciosamente (log de error); el local queda actualizado |

---

## Inicialización de Drive

El flujo OAuth se hace **una sola vez** con:

```
python configurar_drive.py
```

```
configurar_drive.py
     │
     ├── Verifica credentials.json (descargado de Google Cloud Console)
     ├── Abre navegador para autorizar (OAuth2 interactive flow)
     ├── Guarda token en credentials/token.json
     ├── Crea carpetas en Drive:
     │     ConsorcioApp/produccion/facturas/
     │     ConsorcioApp/pruebas/facturas/
     └── Ofrece subir el Excel local actual a produccion
```

A partir de ese momento la app detecta `token.json` y activa Drive automáticamente.

---

## Modo pruebas

Iniciar con `iniciar_pruebas.bat` (o `APP_ENV=pruebas python app.py`):

- Usa `data/pruebas/edificio_brasil.xlsx` como cache local
- Usa `ConsorcioApp/pruebas/` en Drive
- Muestra un **banner amarillo** en todas las páginas
- **Nunca toca** datos de producción

---

## Módulos involucrados

| Módulo | Responsabilidad |
|--------|-----------------|
| `excel_db.py` | Única capa que lee/escribe el Excel. Llama a `_get_drive()` en `_get_wb` y `_save_wb` |
| `drive_sync.py` | Abstracción de la API de Drive. Upload/download del Excel y PDFs |
| `configurar_drive.py` | Setup interactivo (OAuth, carpetas, subida inicial). Solo se corre una vez |
| `app.py` | Llama a `db.sync_from_drive()` al iniciar. Inyecta `app_env` y `drive_activo` en templates |
| `migrar.py` | Descarga de Drive antes de migrar, sube la versión migrada |
