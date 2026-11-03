# Memoria de Sesion — Sistema de Gestión de Consorcio

> Leer al inicio de cada sesion de Claude Code para tener contexto inmediato sin explorar el codigo.

---

## Datos del proyecto

| Campo | Valor |
|---|---|
| **Proyecto** | Sistema de gestión de consorcios de edificio |
| **Stack** | Flask + PostgreSQL (Supabase) + Jinja2 + Bootstrap 5 |
| **Repo** | https://github.com/ncmartin77/consorcio (rama: `master`) |
| **Deploy** | https://consorcio-soo4.onrender.com (Render.com free tier, auto-deploy desde master) |
| **Directorio local** | `/home/norberto/consorcio` |
| **Git en WSL** | `"/mnt/c/Program Files/Git/bin/git.exe"` (siempre con ruta completa) |
| **Version actual** | `5.3-0311` (en `version.txt`) |
| **Supabase Project ID** | `eboskmenitazzwfobwkiq` (region: ca-central-1) |
| **MCP Supabase config** | `~/.mcp.json` (token `sb_secret_*` en `headers.Authorization`) |
| **Consorcio activo en DB** | `consorcio_id = '28693516'` |
| **Idioma de trabajo** | Espanol (responder siempre en espanol) |

---

## Archivos criticos

| Archivo | Rol |
|---|---|
| `app.py` | Rutas Flask |
| `pg_db.py` | Toda la logica y acceso a datos (PostgreSQL/Supabase) |
| `pdf_gen.py` | Generacion de PDFs |
| `version.txt` | Version actual — **incrementar en cada commit** |
| `templates/` | Plantillas Jinja2 + Bootstrap 5 |
| `~/.mcp.json` | Config del MCP de Supabase (token personal) |

---

## Reglas de trabajo

1. **Incrementar `version.txt` antes de cada commit** — formato `X.Y-DDMM` donde DDMM es el dia-mes del commit (ej: `5.1-0211` para 2 de noviembre).
2. **Git siempre con ruta completa**: `"/mnt/c/Program Files/Git/bin/git.exe"`
3. **Verificar push**: el hook post-commit intenta push automatico, pero puede fallar. Confirmar con:
   ```bash
   "/mnt/c/Program Files/Git/bin/git.exe" log origin/master -1
   ```
   Si falta el ultimo commit, pushear manualmente:
   ```bash
   "/mnt/c/Program Files/Git/bin/git.exe" push origin master
   ```
4. **MCP Supabase**: si el token expira, actualizar `headers.Authorization` en `~/.mcp.json` con el nuevo `sb_secret_*`.

### Flujo tipico de un cambio

```bash
# 1. Editar codigo
# 2. Actualizar version.txt
"/mnt/c/Program Files/Git/bin/git.exe" add <archivos> version.txt
"/mnt/c/Program Files/Git/bin/git.exe" commit -m "descripcion del cambio"
"/mnt/c/Program Files/Git/bin/git.exe" push origin master   # si el hook fallo
```

---

## Logica de negocio no obvia

- **Mes vencido**: la liquidacion del periodo P usa los gastos del periodo P-1. Si se editan gastos de septiembre, afecta la liquidacion de octubre.
- **Periodo de trabajo**: `session["periodo_trabajo"]` persiste en sesion. La ruta de gastos usa `_prev_periodo(periodo_trabajo)` automaticamente.
- **Patron `ensure_*()`**: para migraciones de columnas; se llaman en `before_request`. No requieren migraciones manuales.
- **`factura_id` en caja**: FK que sincroniza facturas con movimientos de caja (delete en cascada).
- **`sin_interes`**: flag booleano en liquidaciones por unidad; se preserva al recalcular.
- **`get_facturas()`** devuelve tupla `(lista, total)` — no olvidar el unpacking.
- **`get_caja()`** devuelve tupla `(lista, total)`.
- **`tojson` en `onclick`**: NO usar `{{ obj|tojson }}` dentro de atributos HTML con comillas dobles — usar atributos `data-*` en su lugar.
- **FONDO_RESERVA**: `save_gasto` fue corregido para permitir actualizar solo el importe (antes bloqueaba edicion).
- **`factura_en_liquidacion`**: usa `liq_esta_cerrada()`, NO `liquidacion_existe()`.

---

## Estado actual del sistema (noviembre 2026)

- Primera liquidacion real: **octubre 2026**.
- Se configuro apertura con saldo inicial de caja.
- Liquidacion octubre fue limpiada (todos sin pagar) para arrancar desde cero.
- Gastos de septiembre (base para octubre) cargados; Fondo de Reserva eliminado.
- Checkbox `sin_interes` disponible por unidad para manejar excepciones de interes.

---

## Pendientes / mejoras conocidas

- Diseno del PDF de resumen puede mejorar.
- No hay envio automatico de emails (solo generacion de PDF/WhatsApp manual).
- Render free tier: cold start de ~30 seg despues de inactividad.

---

## Consultas SQL utiles (Supabase MCP)

```sql
-- Liquidaciones de un periodo
SELECT unidad, total_a_pagar, pagado, sin_interes
FROM liquidaciones
WHERE periodo='2026-10' AND consorcio_id='28693516';

-- Gastos de un mes
SELECT * FROM gastos
WHERE periodo='2026-09' AND consorcio_id='28693516';

-- Movimientos de caja de un mes
SELECT * FROM caja
WHERE consorcio_id='28693516'
  AND TO_CHAR(fecha, 'YYYY-MM') = '2026-10';
```

---

*Este archivo es la fuente de verdad del contexto de sesion. Actualizarlo si cambian reglas, estado o version del proyecto.*
