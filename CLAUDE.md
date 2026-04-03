# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

**Windows (normal use):**
```
instalar.bat            # first time: fully unattended installer (calls instalar.ps1)
iniciar.bat             # starts Flask on http://localhost:5000
actualizar.bat          # update existing install: backup Excel + run migrar.py + pip install
crear_distribucion.bat  # creates a ZIP for deployment (calls .ps1); excludes data/ and venv/
```

**Data migration (`migrar.py`):** idempotent script that adds missing sheets and columns to an existing `edificio_brasil.xlsx` without touching any data. Run it after copying new code files over an existing install. Called automatically by `instalar.ps1` and `actualizar.ps1` if the Excel already exists. Handles: `GASTOS_RECURRENTES`, `LIQUIDACIONES_ESTADO`, `PEDIDOS_PRESUPUESTO`, `PRESUPUESTOS` sheets; `gasto_recurrente` column in PROVEEDORES; `numero_factura`/`categoria`/`extraordinario` in FACTURAS; `piso`/`deuda_inicial` in UNIDADES; new CONFIG keys.

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
python app.py                  # runs on port 5000, debug=True
```

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

**"Usar de Fondo de Reserva" on variable gastos:** the Agregar Gasto modal in Gastos Mensuales shows a checkbox (only when tipo = VARIABLE). When checked, `save_gasto` route in `app.py` calls `db.save_movimiento()` with tipo=SALIDA and categoria=FONDO_RESERVA (today's date), then returns — no entry is written to GASTOS_MENSUALES and no liquidación recalculation is triggered. The movement appears in Caja Diaria and counts toward `get_fondo_reserva()` totals, but does not affect the monthly expense distribution.

**Gastos recurrentes** (`GASTOS_RECURRENTES` sheet): expense concepts that repeat every month (e.g., Luz Común, Gas). Key behaviors:
- When a factura is saved with a `descripcion` matching a recurring concept (case-insensitive), `save_factura()` auto-calls `save_gasto()` for that period immediately — no need to wait for payment.
- When that factura is later paid, `pagar_factura()` skips the duplicate `save_gasto()` call.
- Proveedores can store a `gasto_recurrente` field; selecting that provider in the new-factura modal auto-selects the matching recurring expense.
- Gastos Mensuales shows a "Gastos Recurrentes del Mes" panel with three states per concept: Sin factura / Factura registrada sin pagar / Factura pagada.

**Payment validations:**
- `fecha_pago` must be ≥ `fecha` (emission date) of the factura — enforced in `pagar_factura` route (backend) and via `min=` on the date input (frontend).
- `marcar_todos_pagado(periodo, fecha_pago)` pays all PENDIENTE units at once (used by the "Pago Completo" button in Liquidación).

**Factura desde gasto variable:** VARIABLE-type gastos in Gastos Mensuales show a receipt button that opens `#modalFacturaVariable` pre-filled with the gasto's concept and amount. Submits to the existing `save_factura` route.

**Backup:** `GET /backup` streams a ZIP of `data/edificio_brasil.xlsx` as a browser download named `backup_edificio_brasil_YYYYMMDD_HHMM.zip`. Button visible in the navbar on every page.

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
