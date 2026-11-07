# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma
Responde siempre en español.

## Contexto de sesión
Al empezar una sesión, leer `docs/memoria_sesion_claude.md` (estado actual, pendientes, reglas y cómo continuar en otra PC). Al terminar un trabajo relevante, actualizarlo y commitearlo: es la memoria compartida entre PCs (la memoria local de Claude no viaja con el repo).

## Git
Después de cada cambio significativo, hacer commit y push a GitHub.
Usar mensajes de commit descriptivos en español.

## Pruebas
Probar contra la base de **prueba** (`consorcio-tst`) con los scripts de `pruebas/` (cliente de pruebas de Flask, abortan si `DATABASE_URL` no es la base de prueba). Registrar cada prueba en `docs/pruebas_realizadas.md` con tablas (caso / esperado / resultado), la más nueva primero.

## Versionado (`version.txt`, formato `X.Y-DDMM`)
Actualizar `version.txt` antes de **cada** commit. `DDMM` = día y mes real del commit. Claude decide el incremento según esta regla:

- **Menor (Y += 1)** — caso normal: feature nuevo, fix, cambio visual o de UX. Ej: `5.1-0311` → `5.2-0311`.
- **Mayor (X += 1, Y vuelve a 0)** — solo ante un cambio de fondo:
  - cambio de arquitectura o de base de datos (ej. v1 → v2: Excel → PostgreSQL);
  - cambio en las reglas de cálculo que altera resultados (liquidación, mora, intereses, fondo de reserva) (ej. v4 → v5: mora del primer mes pasa a manual);
  - cambio que requiere migrar datos o rompe compatibilidad con datos/flujo anteriores.
- **Antes de subir la versión mayor, consultar al usuario** explicando por qué se propone (ej. "esto cambia la fórmula de mora, propongo 6.0"). Si no confirma, se sube solo la menor. Si el usuario indica una versión mayor explícitamente, usar esa.
- Registrar cada versión en `docs/historial_versiones.md`.

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
app.py                    ← Flask routes (thin controllers, no business logic)
excel_db.py               ← All data access and business logic
pdf_gen.py                ← PDF generation (ReportLab), read-only
_consorcios.json          ← Multi-consorcio index (app root)
data/edificio_brasil.xlsx ← Legacy default consorcio DB
data/<cid>/base.xlsx      ← New consorcios DB (each in own subfolder)
templates/                ← Jinja2 + Bootstrap 5 + Bootstrap Icons
```

**`excel_db.py`** is the only file that reads/writes the Excel. Every function opens the workbook with `_get_wb()`, operates, and saves with `_save_wb(wb)`. There is no connection pooling or ORM.

**Multi-consorcio:** `_consorcios.json` at the app root lists all consorcios. The active consorcio is stored in Flask `session["consorcio_id"]`. `@app.before_request` sets thread-local paths via `db.set_active_consorcio(data_dir_abs, db_path_abs)` before each request. All `excel_db.py` functions use `get_data_dir()`, `get_db_path()`, `get_facturas_dir()` instead of module constants. Legacy install auto-creates the index on first run pointing to `data/edificio_brasil.xlsx`. Routes: `/consorcios` (selector), `/consorcios/nuevo` (POST), `/consorcios/<id>/abrir` (set session), `/consorcios/<id>/eliminar` (POST removes from index; data on disk is kept).

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
| `NOTAS_PERIODO` | period notices/announcements (id, periodo, tipo, texto). tipo: AVISO/INFO |
| `GASTOS_EXTRA` | per-unit extra charges (id, periodo, unidad, descripcion, monto). Included in total_a_pagar when generating liquidación. Blocked if CERRADA |
| `LIQUIDACIONES_YYYY` | one sheet per year, all unit liquidation rows. Includes `extras` column |
| `LIQUIDACIONES_ESTADO` | period → ABIERTA / CERRADA state |

## Key business logic

**Liquidación a mes vencido:** when generating a liquidación for period `P`, the expense base is gastos from period `P-1`. Use `_prev_periodo()` / `_next_periodo()` to navigate periods.

**Liquidación vs Cobranzas (v9.0, user rule):** a liquidación is ABIERTA while its expenses are loaded (amount recalculated); it is CLOSED once the month changed and there are no more expenses (`pg_db.error_cierre()` / `cerrar_liquidacion()`: from day 1 of its month per the system date, previous one closed; closing recalculates and freezes it). **Payments are made against the CLOSED liquidación**, only the last closed one (`periodo_cobranza()`), in the **Cobranzas** screen (`/cobranzas`, routes `cobranzas_pagar`, `cobranzas_pagar_todo`, `cobranzas_anular`; `pg_db.registrar_pago`, `pagar_todo`, `anular_pagos`). Payments live in table `pagos` (date, amount, bonificación, `caja_id`/`bonif_caja_id`); `get_liquidacion()` derives `monto_pagado`/`tipo_pago`/`saldo_pendiente`/`fecha_pago` from it (`_aplicar_pagos`); the payment columns of `liquidaciones` are legacy. Reopening: admin only, only without payments and if the next one is not closed (`error_reapertura`). `migrar_pagos_legacy()` (before_request, once per consorcio, config `pagos_migrados`) moved old payments to `pagos`.

**CERRADA is immutable:** `generar_liquidacion()` returns early for a CERRADA period. Saving a gasto auto-recalculates the *next* month's liquidación only if it is ABIERTA or doesn't exist yet. `generar_liquidacion()` does not write if nothing changed.

**CERRADA cascade rules:**
- Caja Diaria of month M is blocked (add/edit/delete) when liquidación **M+1** (the one carrying M's expenses) is CERRADA — `caja_mes_bloqueado(mes)`. Editing/deleting in Caja the entry of a payment updates/deletes the payment.
- Generating liquidación for P+1 requires liquidación P to be CERRADA (validated in `generar_liquidacion` route and shown in Gastos Mensuales UI).

**Expense distribution rounding:** each unit's expensa is `round(total_gastos * pct / 100, 2)`. The last unit absorbs the cumulative rounding difference so that `sum(all_expensas) == total_gastos` exactly.

**UNIDADES columns are dynamic:** each category in `CATEGORIAS_PCT` adds a `pct_NOMBRE` column to the UNIDADES sheet. When reading a unit's percentage, `excel_db.py` reads whichever `pct_*` columns exist. If a unit has multiple categories, the average is used.

**`fecha_simulada`** ("Fecha del sistema", tarjeta arriba en Configuración, `POST /config/fecha-sistema`): `pg_db.fecha_sistema()` / `_fecha_hoy()` la usan como "hoy" — also for writes since v9.0: default and maximum payment date, closing date/validation, debt and interest of open liquidaciones (recalculated when the date changes). `get_liquidacion()` (simular=True) ignores payments dated after it (`pago_posterior`); signed receipts use `simular=False`. Ver `docs/memoria_sesion_claude.md`.

**Deuda anterior flow (v9.0):** if a unit has no previous liquidación row, its `deuda_inicial` field (set in Apertura; positive = debt, negative = credit) seeds the first debt, with no interest that month. Afterwards `deuda_anterior(P+1) = total_a_pagar(P) − payments of P dated <= system date` (negative = credit). **Interest (v9.2, user rule):** an open liquidación carries NO interest. When CLOSING it, a modal lists the units with `deuda_anterior > 0` and their interest `tasa_mora × deuda_anterior` (`pg_db.propuesta_intereses`), with one switch per unit (on by default); `cerrar_liquidacion(periodo, con_interes=[...])` adds it to the total of the selected units (others get `sin_interes=TRUE`) and freezes it. The closed liquidación and the PDF show an Interés column. Cobranzas does not charge interest (the v9.1 columns `pagos.interes`/`interes_caja_id` are legacy). Credit never earns interest.

**Fondo de reserva (v6.0):** the monthly contribution is a gasto of type `FONDO_RESERVA` (auto-inserted by `ensure_fondo_reserva_gasto()`), charged in the expensas. Extraordinary expenses are either `VARIABLE_FR` (paid with the fund: not charged, deducted from the fund) or `EXTRAORDINARIO` (pending: charged in the next expensas as a separate line, fund untouched); switch with `POST /gastos/<id>/extraordinario/<FONDO|COBRAR>`. Fund balance (v8.0, user rule): the Fondo de Reserva of month X is the **cash (caja) balance at the end of month X-1** — `pg_db.get_resumen_fondo(mes_gastos)`. The accumulated balance is never charged; only the monthly contribution is. `get_desglose_gastos()` splits ordinarios / aporte / extraordinarios.

**Gastos `VARIABLE_FR` (Fondo de Reserva variable):** when adding a VARIABLE gasto, the Agregar Gasto modal shows a checkbox "Usar de Fondo de Reserva". When checked, the gasto is saved to `GASTOS_MENSUALES` with `tipo="VARIABLE_FR"`. Key behaviors:
- Shown in Gastos Mensuales in a separate subsection ("Gastos con Fondo de Reserva"), not in the main table.
- Excluded from `total_gastos` in `get_total_gastos()` and `generar_liquidacion()` → does not affect expensa distribution.
- Has a receipt button: opens `#modalFacturaVariable` with `categoria` pre-filled as `"FONDO_RESERVA"`.
- When the factura is paid, `pagar_factura()` creates a CAJA SALIDA with `categoria=FONDO_RESERVA` (standard factura flow), and skips the duplicate `save_gasto()` call (detected via `factura.categoria == "FONDO_RESERVA"`).
- PDF resumen includes a "GASTOS CON FONDO DE RESERVA" section (amber style) when VARIABLE_FR gastos exist for the period.

**Notas del período** (`NOTAS_PERIODO` sheet): text notices/announcements for a specific period. `tipo=AVISO` (highlighted) or `tipo=INFO`. Added/deleted via AJAX routes `POST /liquidacion/<periodo>/notas/add` and `POST /liquidacion/<periodo>/notas/<id>/delete`. Blocked if liquidación is CERRADA. Shown in UI and in resumen PDF.

**Gastos extra por unidad** (`GASTOS_EXTRA` sheet): one-time extra charges for a specific unit in a period. Added/deleted via `POST /liquidacion/<periodo>/extras/add|<id>/delete` (AJAX). Blocked if CERRADA. When added/deleted while liq is ABIERTA, `generar_liquidacion` is auto-called to update `total_a_pagar`. In `generar_liquidacion`, extras per unit are summed and added to `total = expensas + deuda_anterior + interes + extras_unidad`. The liq row stores `extras` as column 16 (index 15).

**Gastos recurrentes** (`GASTOS_RECURRENTES` sheet): expense concepts that repeat every month (e.g., Luz Común, Gas). Key behaviors:
- When a factura is saved with a `descripcion` matching a recurring concept (case-insensitive), `save_factura()` auto-calls `save_gasto()` for that period immediately — no need to wait for payment.
- When that factura is later paid, `pagar_factura()` skips the duplicate `save_gasto()` call.
- Proveedores can store a `gasto_recurrente` field; selecting that provider in the new-factura modal auto-selects the matching recurring expense.
- Gastos Mensuales shows a "Gastos Recurrentes del Mes" panel with three states per concept: Sin factura / Factura registrada sin pagar / Factura pagada.

**Payment validations:**
- `fecha_pago` must be ≥ `fecha` (emission date) of the factura — enforced in `pagar_factura` route (backend) and via `min=` on the date input (frontend).
- Expensas payments (`registrar_pago`): only against the last closed liquidación, date not after the system date and not in a closed Caja month. `pagar_todo(periodo, fecha)` pays the balance of every unit with debt ("Pago Completo" in Cobranzas).

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

**Versión del sistema:** stored in `version.txt` (e.g. `0.7-0304`, where the suffix is the release date DDMM). Read at startup via a `@app.context_processor` in `app.py` that injects `app_version` into all templates. Displayed as a badge in the navbar (`base.html`). Update `version.txt` before committing; see section **Versionado** at the top for when to bump minor vs. major.

**Caja Diaria — saldo acumulado:** the caja route computes `saldo_acumulado` via `db.get_saldo_caja()` (all-time total) and `saldo_anterior = saldo_acumulado - saldo_mes`. The template shows 4 summary cards: Saldo Anterior / Entradas Mes / Salidas Mes / Saldo Acumulado.

**Tareas — event handling:** checkboxes use event delegation on `#tareasList` (`.change` listener) instead of inline `onchange` attributes (which broke when task descriptions contained quotes). DOM elements use `data-id` and `data-desc` attributes. Show/hide of the undo bar uses `style.setProperty('display', 'flex'/'none', 'important')` to override Bootstrap utility classes reliably.

**Bonificación en pago:** the "Registrar Pago" modal in `cobranzas.html` includes optional fields `bonificacion` (amount) and `bonif_motivo` (reason). `registrar_pago()` stores it in the `pagos` row and creates a Caja SALIDA with categoria=BONIFICACION (`bonif_caja_id`). It does NOT change what the unit owes. Only affects Caja Diaria.

**Tareas Pendientes:** a global memo/checklist shown in Gastos Mensuales (always visible, regardless of period). Stored in the `TAREAS` Excel sheet (`id`, `descripcion`). Operations are fully AJAX (no page reload):
- `POST /tareas/add` → returns `{id, descripcion}` JSON
- `POST /tareas/delete/<id>` → returns `{ok: true}` JSON
- Checking off a task deletes it from the sheet and shows a one-item "Deshacer" banner; clicking it re-adds via `/tareas/add`.
- `migrar.py` handles adding the TAREAS sheet to existing installs.

**Caja Diaria — fecha display:** dates are stored internally as `YYYY-MM-DD` but displayed to the user as `DD/MM/YYYY` in `caja.html`.

**Caja Diaria — delete block:** `delete_movimiento()` reads the movement's actual `fecha`, derives its month and checks `caja_mes_bloqueado()` (v9.0: liquidación of the next month closed) before deleting; a payment's entry can only be deleted if the payment belongs to the last closed liquidación. Returns `False` if blocked (CERRADA), `True` on success. The route in `app.py` checks the return value and flashes an error if blocked. This prevents deletion even if the URL period parameter is manipulated.

**Checkpoint / Rollback:** file-based snapshot of a consorcio's Excel. No Excel schema changes — purely filesystem. One checkpoint per consorcio, stored in its `data/<cid>/` directory:
- `_checkpoint.xlsx` — copy of `base.xlsx` at the moment of checkpoint creation
- `_checkpoint.json` — metadata: `fecha_creacion` (ISO), `descripcion` (optional text)
- Expiry: 30 days (`_CHECKPOINT_DIAS`). After that, `consolidar_si_expirado()` deletes both files automatically on the next request (`@before_request` calls it after `set_active_consorcio()`).
- `crear_checkpoint(descripcion)` — copies current Excel and writes metadata; replaces any existing checkpoint.
- `rollback_checkpoint()` — copies snapshot back over `base.xlsx`, deletes both checkpoint files; returns `False` if no checkpoint exists.
- `get_checkpoint_info()` — returns metadata dict enriched with `dias_transcurridos`, `dias_restantes`, `expirado`; returns `None` if no checkpoint or if snapshot file is missing.
- Routes: `POST /checkpoint/crear`, `POST /checkpoint/rollback`, `POST /checkpoint/eliminar` (manual consolidation).
- UI: badge in navbar (green, turns amber when ≤ 7 days remain); full management card in `config.html#checkpoint`.
- `checkpoint_info` injected via `@app.context_processor` into all templates (comes from `get_checkpoint_info()`).
- `migrar.py` does NOT need updates — no new Excel sheets or columns are involved.

## Deploy online (Firebase / Cloud Run)

Ver **`FIREBASE.md`** para el plan completo paso a paso.

Resumen: Cloud Run (Flask en Docker) + Cloud Storage (Excel por consorcio) + Firebase Hosting (proxy/dominio).
Variable clave: `USE_GCS=true` activa el backend GCS en `excel_db.py` en lugar del filesystem local.
Archivos a crear: `Dockerfile`, `.dockerignore`, `gcs_sync.py`, `firebase.json`, `public/index.html`.
Costo estimado: $0/mes dentro del free tier de GCP.

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

**Log de movimientos / Auditoría (solo admin):** every INSERT/UPDATE/DELETE on business tables (`pg_db._TABLAS_AUDITADAS`) is recorded in the `audit_log` table by a PostgreSQL trigger (`zz_auditoria` → function `audit_registrar()`), storing the full row before/after as JSONB. Key behaviors:
- Schema, function and triggers are created idempotently by `db.ensure_auditoria()` (once per process, called from `@before_request`). No manual migration needed.
- All DB changes of one HTTP request share an `op_id`: `@before_request _contexto_auditoria` calls `db.set_contexto_auditoria(email, descripcion)`; `_conn()` (write connections only — `_fetchall`/`_fetchone` use `write=False`) passes it to the transaction via `set_config('app.audit_op'|'app.audit_usuario'|'app.audit_desc', ..., true)`. Human-readable labels come from `_DESC_AUDITORIA` in `app.py` (add an entry when creating a new write route).
- UPDATEs that don't change anything (e.g. upserts in `save_config`) are not logged. Retention: 180 days (purged when the log is listed).
- `revertir_operacion(op_id, email)` undoes an operation in reverse order in a single transaction: INSERT→DELETE, DELETE→re-INSERT (`OVERRIDING SYSTEM VALUE`, keeps original id), UPDATE→restore old values. Rows are matched by `to_jsonb(row) = datos_despues`; if a row changed afterwards, the whole revert is aborted (`ConflictoReversion`). FK violations (cascades) are retried after the rest. The revert itself is logged as a new operation ("Reversión: ...") and can also be reverted.
- **Closed periods are immutable for reverts:** an operation can only be reverted if every period it touches is after the last CERRADA liquidación (`get_ultima_liq_cerrada()`). Period per row (`_SQL_PERIODO`, min of before/after): `periodo` for liquidaciones/liquidaciones_estado/gastos_extra/notas_periodo, month of `fecha` + 1 for caja (v9.0), `periodo + 1 month` for gastos (mes vencido) and pagos. Other tables (unidades, config, proveedores, tareas…) have no period and are not blocked. `get_bloqueo_operacion()` returns the reason; the list shows a lock icon and the detail page an alert.
- Routes (admin only via `_require_admin()`): `GET /admin/auditoria` (list, filters `usuario`/`tabla`, pagination), `GET /admin/auditoria/<op_id>` (diff per row), `POST /admin/auditoria/<op_id>/revertir`. Entry point: card "Log de Movimientos" in `config.html#auditoria`, shown only if `es_admin`.
