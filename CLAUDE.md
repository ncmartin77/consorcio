# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

**Windows (normal use):**
```
instalar.bat   # first time: creates venv and installs dependencies
iniciar.bat    # starts Flask on http://localhost:5000
```

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

**Gastos recurrentes** (`GASTOS_RECURRENTES` sheet): expense concepts that repeat every month (e.g., Luz Común, Gas). Key behaviors:
- When a factura is saved with a `descripcion` matching a recurring concept (case-insensitive), `save_factura()` auto-calls `save_gasto()` for that period immediately — no need to wait for payment.
- When that factura is later paid, `pagar_factura()` skips the duplicate `save_gasto()` call.
- Proveedores can store a `gasto_recurrente` field; selecting that provider in the new-factura modal auto-selects the matching recurring expense.
- Gastos Mensuales shows a "Gastos Recurrentes del Mes" panel with three states per concept: Sin factura / Factura registrada sin pagar / Factura pagada.

**Payment validations:**
- `fecha_pago` must be ≥ `fecha` (emission date) of the factura — enforced in `pagar_factura` route (backend) and via `min=` on the date input (frontend).
- `marcar_todos_pagado(periodo, fecha_pago)` pays all PENDIENTE units at once (used by the "Pago Completo" button in Liquidación).

## Templates and filters

`app.py` registers a Jinja filter `mes_largo` (e.g., `"2026-04" | mes_largo` → `"Abril 2026"`). Use it in any template that displays a period to the user.

## PDF generation

`pdf_gen.py` exposes three functions called directly from `app.py` routes:
- `generar_pdf_resumen_edificio()` — full building summary (all units)
- `generar_recibo_pago()` — individual payment receipt per unit
- `generar_pdf_liquidacion()` — detailed liquidation (currently unused in routes)

All return `bytes` which are streamed via Flask's `send_file`.
