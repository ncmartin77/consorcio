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
| **Version actual** | `9.5-0811` (en `version.txt`) |
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

1. **Incrementar `version.txt` antes de cada commit** — formato `X.Y-DDMM` donde DDMM es el dia-mes del commit (ej: `5.1-0211` para 2 de noviembre). Menor en cada commit; mayor solo ante cambios de fondo y **consultando al usuario antes** (ver seccion "Versionado" en `CLAUDE.md`). Registrar cada version en `docs/historial_versiones.md`.
2. **Git siempre con ruta completa**: `"/mnt/c/Program Files/Git/bin/git.exe"`
3. **Verificar push**: el hook post-commit intenta push automatico, pero puede fallar. Confirmar con:
   ```bash
   "/mnt/c/Program Files/Git/bin/git.exe" log origin/master -1
   ```
   Si falta el ultimo commit, pushear manualmente:
   ```bash
   "/mnt/c/Program Files/Git/bin/git.exe" push origin master
   ```
4. **MCP Supabase**: si el token expira, actualizar `headers.Authorization` en `~/.mcp.json` con el nuevo `sb_secret_*`. Al 04/11/2026 el token estaba **rechazado (401)**: hay que generar uno nuevo antes de usar el MCP.
6. **Registrar las pruebas** de cada cambio en `docs/pruebas_realizadas.md` (la mas nueva primero, con tablas: caso / esperado / resultado) y, si sirve repetirla, agregar su script en `pruebas/` (usa `pruebas/entorno_prueba.py`, que solo corre contra la base de prueba `consorcio-tst`).
5. **Nunca versionar secretos**: `DATABASE_URL`, tokens y claves van en `.env` (no versionado) o en el dashboard de Render. El script suelto `gen_nov.py` (fuera de git) tiene la contraseña de Supabase escrita: no commitearlo.

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
- **Patron `ensure_*()`**: para migraciones de columnas; se llaman en `before_request` pero ejecutan el `ALTER TABLE` **una sola vez por proceso** (helper `_ensure_columna()` en `pg_db.py`). Para una columna nueva, usar ese helper.
- **Toggle `sin_interes`** (v9.0): `aplicar_sin_interes(periodo, valor, unidad=None)` guarda el flag y recalcula la liquidacion abierta con `generar_liquidacion` (el interes se calcula solo ahi; `_estado_pago` para el estado).
- **`factura_id` en caja**: FK que sincroniza facturas con movimientos de caja (delete en cascada).
- **`sin_interes`**: flag booleano en liquidaciones por unidad; se preserva al recalcular.
- **`get_facturas()`** devuelve tupla `(lista, total)` — no olvidar el unpacking.
- **`get_caja()`** devuelve tupla `(lista, total)`.
- **`tojson` en `onclick`**: NO usar `{{ obj|tojson }}` dentro de atributos HTML con comillas dobles — usar atributos `data-*` en su lugar.
- **Gasto vinculado a su factura** (v9.4, pedido del usuario): `gastos.factura_id`; pagar reutiliza el gasto vinculado (no duplica); borrar la factura deja el gasto sin vinculo y se puede re-emitir desde Gastos Mensuales (boton en todo gasto sin factura). `facturas.observacion` = nota del pago. Fix: factura sin proveedor daba 500.
- **Pagar factura con el fondo** (v9.3, pedido del usuario): switch "Pagar con Fondo de Reserva" en el modal de pago de Facturas; `pagar_factura(..., con_fondo=True)` deja factura y caja con categoria FONDO_RESERVA y el gasto como VARIABLE_FR (no entra en la liquidacion). Recurrente: el gasto FIJO ya cargado pasa a VARIABLE_FR.
- **FONDO_RESERVA**: `save_gasto` fue corregido para permitir actualizar solo el importe (antes bloqueaba edicion).
- **`factura_en_liquidacion`**: usa `liq_esta_cerrada()`, NO `liquidacion_existe()`.
- **Interes al cerrar (v9.2, regla del usuario; reemplaza v9.0 y v9.1)**: abierta = sin interes (generar_liquidacion pone 0). Al cerrar, ventana con switch por unidad (`propuesta_intereses`: unidades con deuda_anterior > 0, interes = tasa × deuda anterior); `cerrar_liquidacion(periodo, con_interes=[ufs])` suma el interes al total de las tildadas (las demas sin_interes=TRUE) y congela. Cobranzas NO cobra interes (las columnas `pagos.interes`/`interes_caja_id` quedan de la v9.1, solo se muestran/anulan).
- **Cobranzas (v9.0, regla del usuario)**: la liquidacion ABIERTA se calcula (gastos del mes anterior); se CIERRA desde el dia 1 de su mes (fecha del sistema) con la anterior cerrada (`error_cierre`, `cerrar_liquidacion`) y queda fija; los pagos se registran en `/cobranzas` SOLO contra la ultima cerrada (`periodo_cobranza()`, `registrar_pago`, `pagar_todo`, `anular_pagos`). Tabla `pagos` (auditada; `_aplicar_pagos` arma monto_pagado/tipo_pago/saldo de cada fila; las columnas de pago de `liquidaciones` quedan sin uso). Deuda anterior de P+1 = total P − pagos de P con fecha <= hoy; interes = tasa × impago de P al vencimiento de P (si hoy > vencimiento). `generar_liquidacion` no escribe si nada cambio. Caja del mes M bloqueada si la liquidacion M+1 esta cerrada (`caja_mes_bloqueado`). Reabrir: admin, sin pagos. Pagos con fecha > fecha del sistema se rechazan. Migracion `migrar_pagos_legacy()` (before_request, una vez por consorcio). Storage pasa a **10.0**.
- **Saldo de caja de la liquidacion** (v8.1): a la fecha de cierre (`liquidaciones_estado.fecha_cierre`, se guarda al cerrar), o a la fecha del sistema si esta abierta (`fecha_corte_liquidacion`).
- **Fondo de Reserva = saldo de caja** (v8.0, regla del usuario): el fondo del mes X es el saldo de caja al cierre de X-1 (`get_resumen_fondo(mes_gastos)` = `get_saldo_caja` al ultimo dia de mes_gastos). Ya no hay saldo inicial del fondo ni suma de aportes. El aporte mensual (FONDO_RESERVA) se sigue cobrando y VARIABLE_FR sigue sin cobrarse. La migracion a Storage pasa a ser **9.0**.
- **Saldo a favor** (v7.0): `saldo_pendiente < 0` en una fila TOTAL = pago de mas; `deuda_anterior < 0` = saldo a favor del mes anterior (`_deuda_desde_mes_anterior`). `_estado_pago`: total <= 0 → TOTAL. Interes solo sobre deuda > 0; mora solo sobre expensas no cubiertas. `unidades.deuda_inicial` positivo = deuda, negativo = a favor. La migracion a Storage paso a 8.0 y luego a **9.0** (v8.0 fue el fondo = caja).
- **Produccion Peru 376 reseteada de nuevo el 08/11/2026** (pedido del usuario, una transaccion auditada como 'claude-code', op_id `0d70e75599f14141a81cf891d75d87fd`, revertible desde el Log): se borraron TODOS los gastos (19), facturas (13), caja (5), liquidaciones oct/nov/dic (72 filas + 3 estados); apertura en cero (saldo inicial de caja 0 sin fecha, deuda inicial 0 en las 24 unidades); fecha del sistema 01/10/2026. Se conservaron unidades/porcentajes, config, proveedores, gastos recurrentes, tareas. El usuario recarga la apertura y los gastos desde septiembre. El Log de Movimientos se conservo (la BD ocupa 19 MB; el borrado no libera espacio apreciable).
- **Produccion Peru 376 reseteada el 06/11/2026** (pedido del usuario, auditado como 'claude-code', revertible desde el Log): se borraron liquidaciones, gastos, facturas, caja, etc.; se conservaron unidades/propietarios/porcentajes, config, apertura (saldo inicial caja $249.736,46 al 30/09 y deudas iniciales UF 06/14/19), proveedores y gastos recurrentes. Fecha del sistema 01/10/2026. Fondo: saldo inicial $0 a 2026-09; el aporte de sep ($80.000) se cobra en oct. El usuario recarga desde septiembre. Claude puede leer/escribir produccion via `ORIGEN_DATABASE_URL` de `.env.local` solo con autorizacion explicita del usuario en el chat.
- **Fondo de reserva y extraordinarios** (v6.0): tipos de gasto: ordinarios (FIJO/VARIABLE/otros), `FONDO_RESERVA` = aporte del periodo, `EXTRAORDINARIO` = extraordinario pendiente que se cobra en las expensas siguientes (no toca el fondo), `VARIABLE_FR` = extraordinario pagado con el fondo (no se cobra, se descuenta). `get_desglose_gastos()`, `get_resumen_fondo(mes_gastos)` (saldo = config `fondo_saldo_inicial` al `fondo_saldo_inicial_periodo` + aportes cuya liquidacion de cobro (periodo+1) existe y es posterior al saldo inicial − VARIABLE_FR posteriores al saldo inicial; v6.6), `set_modo_extraordinario()`, migracion `migrar_gastos_pagados_con_fondo()` (en before_request). La migracion a Storage pasa a ser **8.0** (antes 7.0; la 7.0 fue el saldo a favor).
- **Fecha del sistema** (v5.7/5.8): config `fecha_simulada`, se fija solo por `POST /config/fecha-sistema` (tarjeta arriba en Configuracion). `pg_db.fecha_sistema()` es el "hoy" de la app (`_fecha_hoy()`); checkpoints siguen con fecha real. **v9.0:** la fecha del sistema es el "hoy" tambien para escribir: fecha de pago por defecto y maxima, cierre, deuda e interes de las liquidaciones abiertas. `get_liquidacion(periodo)` (simular=True) no cuenta pagos con fecha posterior (`pago_posterior`); recibos firmados usan `simular=False`. Al fijar/quitar, `recalcular_intereses_abiertas()` regenera las abiertas a esa fecha. El form general de `/config` solo guarda los campos que vienen en el form.
- **Libre deuda** (v5.6): se emite desde Unidades solo si la unidad tiene pagada en TOTAL (o total <= 0) la **ultima liquidacion cerrada** (v9.0; antes la ultima emitida) (`get_estado_libre_deuda()`; se revalida en `emitir_libre_deuda()`). Tabla `libres_deuda` (numero correlativo por consorcio con `pg_advisory_xact_lock`, auditada). Codigo HMAC con `clave_firma` sobre `LIBRE_DEUDA|cid|numero|unidad|periodo_hasta|fecha_emision|validez_dias`; verificacion publica `/libre-deuda/verificar/<cid>/<numero>/<codigo>`. Validez sugerida: config `libre_deuda_validez_dias` (solo la manda el form del resumen; los otros forms no la pisan).

---

## Estado actual del sistema (noviembre 2026)

- Primera liquidacion real: **octubre 2026**.
- Se configuro apertura con saldo inicial de caja.
- Liquidacion octubre fue limpiada (todos sin pagar) para arrancar desde cero.
- Gastos de septiembre (base para octubre) cargados; Fondo de Reserva eliminado.
- Checkbox `sin_interes` disponible por unidad para manejar excepciones de interes.
- v5.2 (03/11): toggle `sin_interes` rapido y con montos actualizados en pantalla. **Pendiente: que el usuario lo confirme en Render** (no se pudo probar contra la BD desde la PC de desarrollo).
- Script `gen_nov.py` (fuera de git) genera la liquidacion 2026-11; no esta confirmado si ya se corrio.
- 06/11: rama `feat/libre-deuda` (desde `master` 5.5-0411) con v5.6-0611 "certificado de libre deuda", probada contra la base de prueba `consorcio-tst` con el test client de Flask (emision, bloqueo por deuda, PDF, QR valido/falso/anulado, auditoria). Mergeada y desplegada el 06/11.
- La rama `supabase-storage` (Storage, v6.0 planeada) sigue aparte y su ultimo commit local `6495413` tiene `.env.local` con claves: **no pushear ni mergear ese commit** (repo publico). Esa rama tiene la version mas completa de esta memoria.

---

## Continuar en otra PC

Todo el codigo y este contexto estan en GitHub; los datos estan en Supabase. Pasos:
Notas de memoria de Claude de la PC original (sin claves): `docs/memoria_claude/` — pueden estar desactualizadas; este archivo manda.

1. Clonar: `git clone https://github.com/ncmartin77/consorcio.git`
2. `python -m venv venv` → activar → `pip install -r requirements.txt`
3. Crear `.env` (no versionado) con `DATABASE_URL`, `SECRET_KEY` y, si se usa login con Google, `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`. Los valores se copian del dashboard de Render (consorcio → Environment) o de Supabase (Connect).
4. **Conexion a Supabase**: el host directo `db.<id>.supabase.co` es **solo IPv6**; en PCs sin IPv6 falla con "could not translate host name". Usar el connection string del **Session pooler** (Supabase → Connect).
5. Ojo: la BD es la de **produccion**. Para probar sin tocar datos reales, usar `APP_ENV=pruebas` o transacciones con rollback.
6. Abrir Claude Code en la carpeta del repo: lee `CLAUDE.md` automaticamente; pedirle que lea tambien este archivo.
7. Opcional: MCP de Supabase → crear `~/.mcp.json` con un token `sb_secret_*` nuevo.

`data/` y `_consorcios.json` no se versionan y no hace falta copiarlos (son datos de prueba de la epoca Excel).

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
