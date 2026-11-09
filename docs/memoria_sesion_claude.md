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
| **Version actual** | `10.1-0911` (en `version.txt`) |
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
- **v10.0 — Lineamientos juridicos (09/11/2026, rama `feat/lineamientos-v10`, incluye v9.8)**: el usuario paso un documento de lineamientos legales (Parana, Entre Rios) y pidio los puntos 1 a 5: (1) interes sin capitalizar: `liquidaciones.deuda_interes` (intereses impagos dentro de la deuda anterior, el pago se imputa primero a intereses) y el interes del cierre = tasa × capital; tasa con vigencia en `tasas_mora` (congelada en `liquidaciones.tasa_aplicada` al cerrar); config `capitalizar_intereses` (0 por defecto). (2) Libro del fondo `get_libro_fondo()`: saldo inicial (config `fondo_saldo_inicial`/`_fecha`, en Apertura) + aportes COBRADOS (imputacion FIFO de pagos, `_aportes_cobrados`) + caja ENTRADA FONDO_RESERVA − caja SALIDA FONDO_RESERVA; reemplaza la regla v8.0 (fondo = saldo de caja). (3) `/exportar` (admin): ZIP CSV/JSON de todas las tablas con consorcio_id + comprobantes; reemplaza /backup en el menu. (4) Gastos: `naturaleza`/`habitualidad`/`financiacion`/`respaldo`; el `tipo` se deduce (`tipo_desde_clasificacion`); filas viejas con NULL se clasifican al leer (`get_gastos`, sin reescribirlas). (5) Config administracion (admin_cuit, admin_mandato_*, registro_* Ord. 9.131, ejercicio_cierre, tiene_ascensor) + tabla `vencimientos` + `get_alertas()` (badge en el menu "Mas"). Todo en `ensure_v10()` (before_request, antes de `ensure_auditoria`). Prueba `pruebas/probar_v10.py`. Siguiente del documento (punto 6, no hecho): asambleas, ascensores (ficha), libros/rubrica, locacion art. 1209, bancos y conciliacion, privacidad (links publicos de recibos que no vencen, aviso de privacidad).
- **Patron `ensure_*()`**: para migraciones de columnas; se llaman en `before_request` pero ejecutan el `ALTER TABLE` **una sola vez por proceso** (helper `_ensure_columna()` en `pg_db.py`). Para una columna nueva, usar ese helper.
- **Toggle `sin_interes`** (v9.0): `aplicar_sin_interes(periodo, valor, unidad=None)` guarda el flag y recalcula la liquidacion abierta con `generar_liquidacion` (el interes se calcula solo ahi; `_estado_pago` para el estado).
- **`factura_id` en caja**: FK que sincroniza facturas con movimientos de caja (delete en cascada).
- **`sin_interes`**: flag booleano en liquidaciones por unidad; se preserva al recalcular.
- **`get_facturas()`** devuelve tupla `(lista, total)` — no olvidar el unpacking.
- **`get_caja()`** devuelve tupla `(lista, total)`.
- **`tojson` en `onclick`**: NO usar `{{ obj|tojson }}` dentro de atributos HTML con comillas dobles — usar atributos `data-*` en su lugar.
- **Seguridad** (v9.8, 09/11/2026): cuentas nuevas de Google quedan INACTIVAS hasta que un admin las habilite; crear/eliminar consorcio y resetear datos solo admin; CSRF por Origin/Referer + cookie SameSite=Lax; rol admin refrescado en cada pedido; SECRET_KEY obligatoria en Render; validaciones de importes con `_importe()` en app.py; gastos de periodo cerrado bloqueados en el servidor. Ver seccion Seguridad en CLAUDE.md.
- **Gasto vinculado a su factura** (v9.4, pedido del usuario): `gastos.factura_id`; pagar reutiliza el gasto vinculado (no duplica); borrar la factura deja el gasto sin vinculo y se puede re-emitir desde Gastos Mensuales (boton en todo gasto sin factura). `facturas.observacion` = nota del pago. Fix: factura sin proveedor daba 500.
- **Pagar factura con el fondo** (v9.3, pedido del usuario): switch "Pagar con Fondo de Reserva" en el modal de pago de Facturas; `pagar_factura(..., con_fondo=True)` deja factura y caja con categoria FONDO_RESERVA y el gasto como VARIABLE_FR (no entra en la liquidacion). Recurrente: el gasto FIJO ya cargado pasa a VARIABLE_FR.
- **FONDO_RESERVA**: `save_gasto` fue corregido para permitir actualizar solo el importe (antes bloqueaba edicion).
- **`factura_en_liquidacion`**: usa `liq_esta_cerrada()`, NO `liquidacion_existe()`.
- **Interes al cerrar (v9.2, regla del usuario; reemplaza v9.0 y v9.1)**: abierta = sin interes (generar_liquidacion pone 0). Al cerrar, ventana con switch por unidad (`propuesta_intereses`: unidades con deuda_anterior > 0, interes = tasa × deuda anterior); `cerrar_liquidacion(periodo, con_interes=[ufs])` suma el interes al total de las tildadas (las demas sin_interes=TRUE) y congela. Cobranzas NO cobra interes (las columnas `pagos.interes`/`interes_caja_id` quedan de la v9.1, solo se muestran/anulan).
- **Cobranzas (v9.0, regla del usuario)**: la liquidacion ABIERTA se calcula (gastos del mes anterior); se CIERRA desde el dia 1 de su mes (fecha del sistema) con la anterior cerrada (`error_cierre`, `cerrar_liquidacion`) y queda fija; los pagos se registran en `/cobranzas` SOLO contra la ultima cerrada (`periodo_cobranza()`, `registrar_pago`, `pagar_todo`, `anular_pagos`). Tabla `pagos` (auditada; `_aplicar_pagos` arma monto_pagado/tipo_pago/saldo de cada fila; las columnas de pago de `liquidaciones` quedan sin uso). Deuda anterior de P+1 = total P − pagos de P con fecha <= hoy; interes = tasa × impago de P al vencimiento de P (si hoy > vencimiento). `generar_liquidacion` no escribe si nada cambio. Caja del mes M bloqueada si la liquidacion M+1 esta cerrada (`caja_mes_bloqueado`). Reabrir: admin, sin pagos. Pagos con fecha > fecha del sistema se rechazan. Migracion `migrar_pagos_legacy()` (before_request, una vez por consorcio). Storage pasa a **10.0**.
- **Saldo de caja de la liquidacion** (v8.1): a la fecha de cierre (`liquidaciones_estado.fecha_cierre`, se guarda al cerrar), o a la fecha del sistema si esta abierta (`fecha_corte_liquidacion`).
- **[Reemplazado en v10.0 por el libro del fondo]** **Fondo de Reserva = saldo de caja** (v8.0, regla del usuario): el fondo del mes X es el saldo de caja al cierre de X-1 (`get_resumen_fondo(mes_gastos)` = `get_saldo_caja` al ultimo dia de mes_gastos). Ya no hay saldo inicial del fondo ni suma de aportes. El aporte mensual (FONDO_RESERVA) se sigue cobrando y VARIABLE_FR sigue sin cobrarse. La migracion a Storage pasa a ser **9.0**.
- **Saldo a favor** (v7.0): `saldo_pendiente < 0` en una fila TOTAL = pago de mas; `deuda_anterior < 0` = saldo a favor del mes anterior (`_deuda_desde_mes_anterior`). `_estado_pago`: total <= 0 → TOTAL. Interes solo sobre deuda > 0; mora solo sobre expensas no cubiertas. `unidades.deuda_inicial` positivo = deuda, negativo = a favor. La migracion a Storage paso a 8.0 y luego a **9.0** (v8.0 fue el fondo = caja).
- **Produccion Peru 376 reseteada de nuevo el 08/11/2026** (pedido del usuario, una transaccion auditada como 'claude-code', op_id `0d70e75599f14141a81cf891d75d87fd`, revertible desde el Log): se borraron TODOS los gastos (19), facturas (13), caja (5), liquidaciones oct/nov/dic (72 filas + 3 estados); apertura en cero (saldo inicial de caja 0 sin fecha, deuda inicial 0 en las 24 unidades); fecha del sistema 01/10/2026. Se conservaron unidades/porcentajes, config, proveedores, gastos recurrentes, tareas. El usuario recarga la apertura y los gastos desde septiembre. El Log de Movimientos se conservo (la BD ocupa 19 MB; el borrado no libera espacio apreciable).
- **Produccion Peru 376 reseteada el 06/11/2026** (pedido del usuario, auditado como 'claude-code', revertible desde el Log): se borraron liquidaciones, gastos, facturas, caja, etc.; se conservaron unidades/propietarios/porcentajes, config, apertura (saldo inicial caja $249.736,46 al 30/09 y deudas iniciales UF 06/14/19), proveedores y gastos recurrentes. Fecha del sistema 01/10/2026. Fondo: saldo inicial $0 a 2026-09; el aporte de sep ($80.000) se cobra en oct. El usuario recarga desde septiembre. Claude puede leer/escribir produccion via `ORIGEN_DATABASE_URL` de `.env.local` solo con autorizacion explicita del usuario en el chat.
- **Fondo de reserva y extraordinarios** (v6.0): tipos de gasto: ordinarios (FIJO/VARIABLE/otros), `FONDO_RESERVA` = aporte del periodo, `EXTRAORDINARIO` = extraordinario pendiente que se cobra en las expensas siguientes (no toca el fondo), `VARIABLE_FR` = extraordinario pagado con el fondo (no se cobra, se descuenta). `get_desglose_gastos()`, `get_resumen_fondo(mes_gastos)` (saldo = config `fondo_saldo_inicial` al `fondo_saldo_inicial_periodo` + aportes cuya liquidacion de cobro (periodo+1) existe y es posterior al saldo inicial − VARIABLE_FR posteriores al saldo inicial; v6.6), `set_modo_extraordinario()`, migracion `migrar_gastos_pagados_con_fondo()` (en before_request). La migracion a Storage pasa a ser **8.0** (antes 7.0; la 7.0 fue el saldo a favor).
- **Fecha del sistema** (v5.7/5.8): config `fecha_simulada`, se fija solo por `POST /config/fecha-sistema` (tarjeta arriba en Configuracion). `pg_db.fecha_sistema()` es el "hoy" de la app (`_fecha_hoy()`); checkpoints siguen con fecha real. **v9.0:** la fecha del sistema es el "hoy" tambien para escribir: fecha de pago por defecto y maxima, cierre, deuda e interes de las liquidaciones abiertas. `get_liquidacion(periodo)` (simular=True) no cuenta pagos con fecha posterior (`pago_posterior`); recibos firmados usan `simular=False`. Al fijar/quitar, `recalcular_intereses_abiertas()` regenera las abiertas a esa fecha. El form general de `/config` solo guarda los campos que vienen en el form.
- **Libre deuda** (v5.6): se emite desde Unidades solo si la unidad tiene pagada en TOTAL (o total <= 0) la **ultima liquidacion cerrada** (v9.0; antes la ultima emitida) (`get_estado_libre_deuda()`; se revalida en `emitir_libre_deuda()`). Tabla `libres_deuda` (numero correlativo por consorcio con `pg_advisory_xact_lock`, auditada). Codigo HMAC con `clave_firma` sobre `LIBRE_DEUDA|cid|numero|unidad|periodo_hasta|fecha_emision|validez_dias`; verificacion publica `/libre-deuda/verificar/<cid>/<numero>/<codigo>`. Validez sugerida: config `libre_deuda_validez_dias` (solo la manda el form del resumen; los otros forms no la pisan).

---

## >>> DONDE QUEDAMOS (09/11/2026) — leer primero <<<

**Produccion (Render, rama `master`)**: v9.7 (planilla "MONTO A PAGAR"). Perú 376 reseteada el 08/11; el usuario recarga apertura y gastos desde septiembre.

**Ramas sin mergear (en GitHub):**
1. `fix/seguridad` — v9.8 arreglos de seguridad (24/24). Incluida en la rama 2.
2. `feat/lineamientos-v10` — **v10.0** (incluye la v9.8): puntos 1 a 5 del documento juridico + manual nuevo + diagramas + pagina Ayuda. Ver la entrada v10.0 en `docs/historial_versiones.md` y "Lineamientos juridicos (v10.0)" en `CLAUDE.md`.

**Antes de mergear `feat/lineamientos-v10` a `master` (= deploy):**
- [ ] Confirmar en Render (consorcio → Environment) que existe `SECRET_KEY`: desde la v9.8, sin ella la app NO arranca.
- [ ] Pruebas — resultado al 09/11 (corridas de a una, contra la v10.0):
  - OK: cobranzas 44/44, factura_con_fondo 14/14, factura_vinculo 16/16, pdf_planilla 15/15, seguridad 24/24; saldo_cierre, liquidacion_estados, anular_pagos y periodos_invalidos terminaron sin errores (revisar su salida completa).
  - **Correr de nuevo** (se cortaron por falta de red en la PC, no por el codigo): `probar_v10.py` (dio 50/50 antes de agregarle los 3 controles de Ayuda) y `probar_fondo_reserva.py` (ya actualizada a la regla del libro del fondo).
  - **Pruebas viejas a actualizar** (fallan por cambios ANTERIORES a la v10, no por la v10): `probar_fecha_sistema.py` (usa el switch "sin interes" de Liquidacion, quitado en la v9.2), `probar_libre_deuda.py` (espera emitir con la base de prueba tal cual; desde la v9.0 exige la ultima liquidacion CERRADA y la base de prueba no tiene ninguna), `probar_saldo_a_favor.py` (usa `pg_db._calcular_interes`, que no existe desde la v9.2).
  - **Limpieza**: como `probar_v10.py` se corto a mitad, puede haber quedado en la base de prueba el consorcio temporal "Prueba v10 lineamientos": borrarlo (`db.delete_consorcio(id)` o desde la app, como admin, en la base de PRUEBA).
- [ ] Correr las pruebas de a una (dos a la vez trabaron la base de prueba con un deadlock).
- [ ] Registrar los resultados en `docs/pruebas_realizadas.md` (falta la entrada de la v10.0).
- [ ] Despues del deploy: cargar en Apertura el **saldo inicial del Fondo de Reserva** (si no, el libro usa el saldo inicial de caja y lo avisa), registrar la **tasa de mora con vigencia** en Configuración → Intereses por mora y completar Configuración → Administración.

**Pendiente del documento juridico (punto 6, no empezado):** asambleas (convocatoria, asistencia, poderes, actas, mayorias), ficha de ascensores (Ord. 8.661), libros y rubrica, locacion art. 1209 (propietario/inquilino), bancos y conciliacion, privacidad (links publicos de recibos que no vencen, aviso de privacidad, transferencia internacional Supabase/Render).

**Reglas del usuario de esta sesion:** los diagramas (`docs/diagramas.md`) NO van en la pagina de Ayuda de la app; la Ayuda muestra solo `docs/manual_usuario.md`, que hay que mantener al dia con cada cambio funcional.

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
   Para seguir con la v10: `git fetch` y `git switch feat/lineamientos-v10`, y empezar por la seccion "DONDE QUEDAMOS".
8. **Pruebas** (`pruebas/*.py`): necesitan `.env.local` (no versionado) con `DATABASE_URL` de la base de PRUEBA `consorcio-tst` (Supabase, proyecto `rbwjkgqvfaxxvcwaywtj`; copiar el connection string del Session pooler desde Supabase → Connect). `pruebas/entorno_prueba.py` aborta si no es la base de prueba. Se corren desde la raiz: `python pruebas\probar_v10.py` (en Windows conviene `python -X utf8` por los emojis).
9. **Git en Windows con el repo en WSL**: si dice "dubious ownership", usar `git -c safe.directory='*' ...`.
10. **Documentacion**: manual de usuario `docs/manual_usuario.md` (se ve en la app en Mas → Ayuda y manual), diagramas tecnicos `docs/diagramas.md` (Mermaid; GitHub los dibuja).
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
