# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma
Responde siempre en español.

## Git
Después de cada cambio significativo, hacer commit y push a GitHub.
Usar mensajes de commit descriptivos en español.

## Running the app

**Windows (normal use):**
```
instalar.bat                  # first time: fully unattended installer (calls instalar.ps1)
iniciar.bat                   # starts Flask on http://localhost:5000 (solo esta PC)
iniciar_red.bat               # starts Flask on 0.0.0.0 (accesible desde la red local); detecta IP automáticamente
crear_accesos_directos.bat    # crea dos .lnk en el Escritorio: uno para cada modo de inicio
actualizar.bat                # update existing install: backup Excel + run migrar.py + pip install
crear_distribucion.bat        # creates a ZIP for deployment (calls .ps1); excludes data/ and venv/
```

**Data migration (`migrar.py`):** idempotent script that adds missing sheets and columns to an existing `edificio_brasil.xlsx` without touching any data. Run it after copying new code files over an existing install. Called automatically by `instalar.ps1` and `actualizar.ps1` if the Excel already exists. Handles: `GASTOS_RECURRENTES`, `LIQUIDACIONES_ESTADO`, `PEDIDOS_PRESUPUESTO`, `PRESUPUESTOS` sheets; `gasto_recurrente` column in PROVEEDORES; `numero_factura`/`categoria`/`extraordinario`/`archivo_pdf` in FACTURAS; `piso`/`deuda_inicial` in UNIDADES; new CONFIG keys.

**Update process (existing install with data):**
1. User clicks Backup button in app → downloads ZIP of Excel to Downloads
2. Unzip new `consorcio_app_*.zip` over the existing folder (safe: `data/` not in ZIP)
3. Run `actualizar.bat` → auto-backup of Excel + schema migration + pip update

**Installer logic (`instalar.ps1`):**
1. Self-elevates to admin via `Start-Process -Verb RunAs`
2. Looks for Python 3.8+ in common Windows locations
3. If missing: silently downloads `python-3.12.7-amd64.exe` and installs with `/quiet PrependPath=1`
4. If download fails: installs WSL + Debian via `wsl --install -d Debian --no-launch`
5. If WSL needs a reboot: registers `RunOnce` registry key and calls `Restart-Computer -Force`
6. After reboot (with `-PostReboot` param): waits 30s for WSL init, then sets up Debian
7. Writes `.runtime` flag (`windows` or `wsl\n<wslpath>`) read by `iniciar.bat`
8. All output logged to `instalacion.log`

**From WSL/terminal:**
```bash
source venv/Scripts/activate   # or venv/bin/activate on Linux
python app.py                  # runs on port 5000, debug=True, host=127.0.0.1
APP_HOST=0.0.0.0 python app.py # runs accessible from local network
```

**`APP_HOST` env var:** `app.py` reads `APP_HOST` (default `127.0.0.1`) to set the Flask bind address. `iniciar_red.bat` sets `APP_HOST=0.0.0.0` before launching. Do not hardcode the host in `app.run()`.

**Git** is not in WSL PATH — use the full path:
```bash
"/mnt/c/Program Files/Git/bin/git.exe" <command>
```
The post-commit hook auto-pushes to `https://github.com/ncmartin77/consorcio.git`.

## Architecture

Three-layer Flask app with no traditional database:

```
app.py          ← Flask routes (thin controllers, no business logic)
excel_db.py     ← All data access and business logic
pdf_gen.py      ← PDF generation (ReportLab), read-only
data/edificio_brasil.xlsx  ← The database
templates/      ← Jinja2 + Bootstrap 5 + Bootstrap Icons
```

**`excel_db.py`** is the only file that reads/writes the Excel. Every function opens the workbook with `_get_wb()`, operates, and saves with `_save_wb(wb)`. There is no connection pooling or ORM.

## Excel sheet structure

| Sheet | Contents |
|---|---|
| `CONFIG` | key-value pairs (building info, tasa_mora, dia_vencimiento, etc.) |
| `CATEGORIAS_PCT` | expense distribution categories (e.g., EXPENSAS, FONDO_RESERVA) |
| `UNIDADES` | units with dynamic `pct_CATEGORIA` columns per category |
| `GASTOS_MENSUALES` | monthly expenses by period (YYYY-MM) |
| `CAJA_DIARIA` | daily cash movements (ENTRADA/SALIDA) |
| `FACTURAS` | vendor invoices |
| `PROVEEDORES` | vendor directory with optional `gasto_recurrente` field |
| `GASTOS_RECURRENTES` | recurring monthly expense concepts (id, concepto, categoria) |
| `PEDIDOS_PRESUPUESTO` / `PRESUPUESTOS` | purchase orders and quotes |
| `LIQUIDACIONES_YYYY` | one sheet per year, all unit liquidation rows |
| `LIQUIDACIONES_ESTADO` | period → ABIERTA / CERRADA state |

## Key business logic

**Liquidación a mes vencido:** when generating a liquidación for period `P`, the expense base is gastos from period `P-1`. Use `_prev_periodo()` / `_next_periodo()` to navigate periods.

**CERRADA is immutable:** once a liquidación is closed via `set_liq_estado(periodo, "CERRADA")`, `generar_liquidacion()` and `marcar_pagado()` return early without changes. Saving a gasto auto-recalculates the *next* month's liquidación only if it is ABIERTA or doesn't exist yet.

**CERRADA cascade rules:**
- Caja Diaria blocks add/edit/delete of movements when the period's liquidación is CERRADA (checked in `save_movimiento` and `delete_movimiento` routes).
- Generating liquidación for P+1 requires liquidación P to be CERRADA (validated in `generar_liquidacion` route and shown in Gastos Mensuales UI).

**Expense distribution rounding:** each unit's expensa is `round(total_gastos * pct / 100, 2)`. The last unit absorbs the cumulative rounding difference so that `sum(all_expensas) == total_gastos` exactly.

**UNIDADES columns are dynamic:** each category in `CATEGORIAS_PCT` adds a `pct_NOMBRE` column to the UNIDADES sheet. When reading a unit's percentage, `excel_db.py` reads whichever `pct_*` columns exist. If a unit has multiple categories, the average is used.

**`fecha_simulada`** in CONFIG overrides `date.today()` throughout the app (see `_fecha_hoy()` in `app.py`). Useful for testing past/future periods.

**Deuda anterior flow:** if a unit has no previous liquidación row, its `deuda_inicial` field (set in Apertura) seeds the first debt. Subsequent months carry forward `saldo_pendiente` for partial payments or `total_a_pagar` for unpaid units.

**Fondo de reserva** is a special gasto of type `FONDO_RESERVA`, auto-inserted each month by `ensure_fondo_reserva_gasto()`. Its accumulated total is tracked separately via `get_fondo_reserva()` which sums CAJA entries of category `FONDO_RESERVA`.

**Gastos `VARIABLE_FR` (Fondo de Reserva variable):** when adding a VARIABLE gasto, the Agregar Gasto modal shows a checkbox "Usar de Fondo de Reserva". When checked, the gasto is saved to `GASTOS_MENSUALES` with `tipo="VARIABLE_FR"`. Key behaviors:
- Shown in Gastos Mensuales in a separate subsection ("Gastos con Fondo de Reserva"), not in the main table.
- Excluded from `total_gastos` in `get_total_gastos()` and `generar_liquidacion()` → does not affect expensa distribution.
- Has a receipt button: opens `#modalFacturaVariable` with `categoria` pre-filled as `"FONDO_RESERVA"`.
- When the factura is paid, `pagar_factura()` creates a CAJA SALIDA with `categoria=FONDO_RESERVA` (standard factura flow), and skips the duplicate `save_gasto()` call (detected via `factura.categoria == "FONDO_RESERVA"`).
- PDF resumen includes a "GASTOS CON FONDO DE RESERVA" section (amber style) when VARIABLE_FR gastos exist for the period.

**Gastos recurrentes** (`GASTOS_RECURRENTES` sheet): expense concepts that repeat every month (e.g., Luz Común, Gas). Key behaviors:
- When a factura is saved with a `descripcion` matching a recurring concept (case-insensitive), `save_factura()` auto-calls `save_gasto()` for that period immediately — no need to wait for payment.
- When that factura is later paid, `pagar_factura()` skips the duplicate `save_gasto()` call.
- Proveedores can store a `gasto_recurrente` field; selecting that provider in the new-factura modal auto-selects the matching recurring expense.
- Gastos Mensuales shows a "Gastos Recurrentes del Mes" panel with three states per concept: Sin factura / Factura registrada sin pagar / Factura pagada.

**Payment validations:**
- `fecha_pago` must be ≥ `fecha` (emission date) of the factura — enforced in `pagar_factura` route (backend) and via `min=` on the date input (frontend).
- `marcar_todos_pagado(periodo, fecha_pago)` pays all PENDIENTE units at once (used by the "Pago Completo" button in Liquidación).

**Factura desde gasto variable:** VARIABLE-type gastos in Gastos Mensuales show a receipt button that opens `#modalFacturaVariable` pre-filled with the gasto's concept and amount. Submits to the existing `save_factura` route.

**Comprobantes de facturas (upload de archivos):** cada factura puede tener un PDF adjunto (escaneado o foto de la factura física). Key behaviors:
- Columna `archivo_pdf` en la hoja FACTURAS del Excel; almacena la ruta relativa desde `DATA_DIR` (ej. `facturas/proveedor_sa/2026-04-11_143022.pdf`).
- `db.FACTURAS_DIR` = `data/facturas/` — directorio raíz de todos los comprobantes.
- Subdirectorios por proveedor: el nombre se sanitiza con `_sanitize_dirname()` en `app.py` (minúsculas, sin tildes, espacios → guiones bajos, solo `[a-z0-9_-]`).
- Nombre de archivo: `{YYYY-MM-DD_HHMMSS}.pdf` — timestamp del momento de la subida.
- Conversión automática: imágenes (PNG, JPG, GIF, TIFF, BMP) se convierten a PDF con Pillow (`img.save(path, "PDF", resolution=150)`). Imágenes con transparencia (RGBA/P/LA) se convierten a RGB antes de guardar.
- Rutas: `POST /facturas/<fid>/upload` (subida), `GET /facturas/<fid>/comprobante` (visualización inline en el navegador).
- Seguridad: `ver_comprobante` verifica con `os.realpath` que el path resuelto esté dentro de `DATA_DIR` (previene path traversal).
- UI: botón upload (siempre visible por fila) y botón ver-PDF azul (solo si `archivo_pdf` está seteado). Un único `<form id="formUpload">` oculto es reutilizado por JS para todas las filas.
- Dependencia: `Pillow>=10.0.0` en `requirements.txt`.

**Backup:** `GET /backup` streams a ZIP containing `data/edificio_brasil.xlsx` **y toda la carpeta `data/facturas/`** (comprobantes PDF de facturas) como descarga del navegador, con nombre `backup_edificio_brasil_YYYYMMDD_HHMM.zip`. Botón visible en el navbar en todas las páginas.

**Verificación de autenticidad de recibos (HMAC + QR):** cada recibo PDF incluye un código de verificación de 32 chars hex y un QR al pie. El código es un HMAC-SHA256 calculado sobre los campos clave del recibo (`periodo|unidad|descripcion|expensas|deuda_anterior|interes|total_a_pagar|tipo_pago|monto_pagado|fecha_pago|edificio_nombre`) usando una clave secreta almacenada en CONFIG (`clave_firma`). La clave se genera automáticamente con `secrets.token_hex(32)` la primera vez que se necesita (`get_clave_firma()` en `excel_db.py`). El QR codifica la URL `{url_app}/verificar/{periodo}/{unidad}/{codigo}`. La ruta `/verificar/<periodo>/<unidad>/<codigo>` recalcula el HMAC con los datos actuales del Excel y lo compara con `hmac.compare_digest`. La página `verificar.html` muestra 4 estados: `formulario` (entrada manual), `no_encontrado`, `valido`, `invalido`. La URL base se configura en CONFIG como `url_app` (default `http://localhost:5000`); si la app está en red local se configura con la IP real (ej. `http://192.168.1.100:5000`) para que el QR sea escaneable desde celulares. Campo visible en Configuración → sección "Verificación de Recibos". `migrar.py` agrega `clave_firma` y `url_app` a instalaciones existentes. **Bug conocido (corregido):** `config.html` tenía un `<input type="hidden" name="url_app">` duplicado que aparecía antes del campo visible en el mismo form; Flask tomaba el primer valor (el viejo), impidiendo guardar la nueva URL. Eliminado el hidden duplicado.

**Versión del sistema:** stored in `version.txt` (e.g. `0.7-0304`, where the suffix is the release date DDMM). Read at startup via a `@app.context_processor` in `app.py` that injects `app_version` into all templates. Displayed as a badge in the navbar (`base.html`). **Increment the minor number on every push** (e.g. `0.7-0304` → `0.8-0304`). Update `version.txt` before committing.

**Caja Diaria — saldo acumulado:** the caja route computes `saldo_acumulado` via `db.get_saldo_caja()` (all-time total) and `saldo_anterior = saldo_acumulado - saldo_mes`. The template shows 4 summary cards: Saldo Anterior / Entradas Mes / Salidas Mes / Saldo Acumulado.

**Tareas — event handling:** checkboxes use event delegation on `#tareasList` (`.change` listener) instead of inline `onchange` attributes (which broke when task descriptions contained quotes). DOM elements use `data-id` and `data-desc` attributes. Show/hide of the undo bar uses `style.setProperty('display', 'flex'/'none', 'important')` to override Bootstrap utility classes reliably.

**Bonificación en pago de liquidación:** the "Registrar Pago" modal in `liquidacion.html` includes optional fields `bonificacion` (amount) and `bonif_motivo` (reason). If a bonificación > 0 is submitted, the `marcar_pagado` route in `app.py` calls `db.save_movimiento()` with tipo=SALIDA and categoria=BONIFICACION after recording the payment. The bonificación does NOT modify the liquidación row (total_a_pagar, monto_pagado, saldo are unchanged). Only affects Caja Diaria.

**Tareas Pendientes:** a global memo/checklist shown in Gastos Mensuales (always visible, regardless of period). Stored in the `TAREAS` Excel sheet (`id`, `descripcion`). Operations are fully AJAX (no page reload):
- `POST /tareas/add` → returns `{id, descripcion}` JSON
- `POST /tareas/delete/<id>` → returns `{ok: true}` JSON
- Checking off a task deletes it from the sheet and shows a one-item "Deshacer" banner; clicking it re-adds via `/tareas/add`.
- `migrar.py` handles adding the TAREAS sheet to existing installs.

**Caja Diaria — fecha display:** dates are stored internally as `YYYY-MM-DD` but displayed to the user as `DD/MM/YYYY` in `caja.html`.

**Caja Diaria — delete block:** `delete_movimiento()` in `excel_db.py` reads the movement's actual `fecha` from the Excel row, derives its period (`YYYY-MM`), and checks `liq_esta_cerrada()` for that period before deleting. Returns `False` if blocked (CERRADA), `True` on success. The route in `app.py` checks the return value and flashes an error if blocked. This prevents deletion even if the URL period parameter is manipulated.

## Templates and filters

`app.py` registers a Jinja filter `mes_largo` (e.g., `"2026-04" | mes_largo` → `"Abril 2026"`). Use it in any template that displays a period to the user.

## PDF generation

`pdf_gen.py` exposes three functions called directly from `app.py` routes:
- `generar_pdf_resumen_edificio()` — full building summary (all units)
- `generar_recibo_pago()` — individual payment receipt per unit
- `generar_pdf_liquidacion()` — detailed liquidation (currently unused in routes)

All return `bytes` which are streamed via Flask's `send_file`.

**PDF filename format:** `liquidacion_{mes}_{año}_{edificio_nombre}.pdf` (e.g. `liquidacion_abril_2026_edificio_brasil.pdf`). Sanitized to lowercase alphanumeric + underscores.

**Timestamp footer:** both `generar_pdf_resumen_edificio` and `generar_pdf_liquidacion` append a small right-aligned "Generado el DD/MM/YYYY a las HH:MM" line at the bottom.
