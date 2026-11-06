# Pruebas realizadas

Registro de las pruebas hechas antes de subir cada cambio a producción: qué se probó, contra qué datos y qué dio.
Las más recientes van primero. Los scripts para repetirlas están en [`pruebas/`](../pruebas/) (ver [Cómo repetirlas](#cómo-repetirlas)).

---

## Entorno de pruebas

| Item | Valor |
|---|---|
| Base de datos | Supabase **`consorcio-tst`** (proyecto de prueba, copia de producción). **Nunca** producción. |
| Consorcio usado | Edificio Perú 376 (`consorcio_id = 28693516`), 24 unidades |
| Cómo se ejecutan | Cliente de pruebas de Flask (`app.test_client()`) con sesión de admin: recorre las rutas reales sin login de Google ni navegador |
| Python | venv de Windows `C:\Users\Maria\.venvs\consorcio` |
| Fecha real de las pruebas | 06/11/2026 |
| Configuración de la base de prueba | `tasa_mora` = 5 %, `dia_vencimiento` = 0 (último día del mes) |
| Liquidaciones en la base de prueba | 2026-10, 2026-11 y 2026-12, todas ABIERTAS. Octubre pagada completa (pagos registrados el 03/11/2026); noviembre y diciembre pendientes |
| Verificación del deploy | Después de cada push a `master` se consultó la página pública `/libre-deuda/verificar/...` en Render hasta ver la versión nueva |

> Las pruebas que modifican datos (pago simulado, switch) dejan todo como estaba al terminar. Los certificados de libre deuda de prueba se borran.

---

## Corrida completa de los scripts — 06/11/2026 (sobre v5.8)

Se corrieron los cuatro scripts de `pruebas/` seguidos, contra la base de prueba, para dejar constancia de que reproducen todo lo de abajo.

| Script | Resultado | Detalle |
|---|---|---|
| `diagnostico_intereses.py` | ✅ | Interés guardado = fórmula en los 3 períodos. Octubre: todas pagadas el 03/11 con "sin interés". Noviembre: deuda anterior 0, antes del vencimiento (30/11) → interés 0. Diciembre UF 01: $ 630,06 = 5 % de $ 12.601,15 |
| `probar_switch_interes.py` (dic, UF 01) | ✅ | Prendido: $ 0,00 / total $ 24.579,96 · Apagado: $ 630,06 / total $ 25.210,02 · "Todos": total del período $ 2.796.976,73 ↔ $ 2.871.007,90 · switch de cada unidad restaurado |
| `probar_libre_deuda.py --limpiar` | ✅ | Bloqueo por deuda, emisión N° 0001 (hasta 2026-12, vence 06/12/2026), PDF, verificación válido / falso / inexistente / anulado, auditoría; pago restaurado y certificados borrados |
| `probar_fecha_sistema.py` | ✅ | Con 06/10: octubre 24 unidades pendientes con "pagó el 03/11/2026", base sin cambios, recibo real OK, 7 pantallas/PDF OK · Con 05/12: noviembre UF 01 muestra $ 482,50 (guardado $ 0,00), switch OK, PDF "Generado el 05/12/2026", form principal no borra la fecha, fecha inválida rechazada · Al final: fecha real y base igual al inicio |

---

## v6.4-0611 — Anular pagos y fecha de pago con la fecha del sistema

**Pedido:** borrar los pagos de octubre registrados el 03/11/2026 y que, al pagar con la fecha del sistema fijada, el pago quede con esa fecha.

**Hallazgos:** cada pago, además de la fila de la liquidación, crea una entrada en Caja; no había forma de anular pagos; los formularios proponían la fecha real del navegador (no la fijada).

Prueba (`pruebas/probar_anular_pagos.py`, liquidación 2026-10, fecha fijada 06/10/2026; estado inicial: 24 unidades pagadas el 03/11 y 24 entradas en Caja):

| # | Caso | Esperado | Resultado |
|---|---|---|---|
| 1 | Formularios de Liquidación y Caja con fecha fijada | Proponen 2026-10-06 | ✅ |
| 1 | Botones (admin) | "Anular todos los pagos" + uno por unidad | ✅ 1 + 24 |
| 2 | Anular el pago de la UF 01 | Fila TOTAL 13.207,76 (03/11) → PENDIENTE; Caja 24 → 23; resto sin cambios | ✅ |
| 3 | Anular todos los pagos | 0 unidades con pago, 0 entradas en Caja | ✅ |
| 4 | Pagar UF 01 sin indicar fecha | `fecha_pago` = 2026-10-06; Caja con fecha 2026-10-06; en la vista: pagado | ✅ |
| 5 | Revertir las 3 operaciones desde el Log de Movimientos | Liquidación y Caja idénticas al inicio | ✅ |

---

## v6.3-0611 — Causa real del error 500 en Liquidación

**Detalle obtenido en producción** con la página de error de la v6.2 (admin, `GET /liquidacion/2026-10`, fecha 06/10):

```
File "/opt/render/project/src/app.py", line 1071, in liquidacion
    ultimo_dia = _cal.monthrange(yp, mp)[1]
UnboundLocalError: cannot access local variable '_cal' where it is not associated with a value
```

**Causa:** `import calendar as _cal` dentro de un `if` (solo corre con la liquidación abierta) vuelve local a `_cal` en toda la función. Con la liquidación de octubre **cerrada o sin generar** en producción, `_cal` no existe al usarse más abajo. En la base de prueba octubre está abierta, por eso no se reproducía.

Prueba (`pruebas/probar_liquidacion_estados.py`):

| Estado de la liquidación | Fecha real — antes | Fecha real — después | Fecha 06/10 — antes | Fecha 06/10 — después |
|---|---|---|---|---|
| Abierta (2026-12) | ✅ 200 | ✅ 200 | ✅ 200 | ✅ 200 |
| Sin generar (2027-02) | ❌ UnboundLocalError | ✅ 200 | ❌ UnboundLocalError | ✅ 200 |
| Cerrada (2026-12, cerrada para la prueba) | ❌ UnboundLocalError | ✅ 200 | ❌ UnboundLocalError | ✅ 200 |

Se revisaron los demás imports locales de `app.py` (`_re`, `_hmac_mod`, `traceback`, etc.): se usan después de importarse, no tienen el problema.

> Aprendizaje: la v6.1 atacó una causa posible sin confirmarla. Con un error que no se reproduce en prueba, primero obtener el traceback real (página de error de la v6.2 o log de Render).

---

## v6.2-0611 — Página de error con detalle para administradores

Después de la v6.1, `/liquidacion/2026-10` con fecha 06/10 **siguió dando error 500 en producción**, y en la base de prueba no se reproduce: la causa depende de datos de producción, a los que no hay acceso.

| Caso (`pruebas/probar_pagina_error.py`, error forzado en una ruta temporal) | Esperado | Resultado |
|---|---|---|
| Administrador | 500 con traceback, página, versión, consorcio y fecha fijada | ✅ |
| Usuario común | 500 con mensaje simple, sin detalle técnico | ✅ |
| Log | Traceback completo registrado | ✅ |

---

## v6.1-0611 — Error 500 al liquidar octubre con fecha 06/10

**Reporte:** en producción, "Liquidar" octubre con la fecha del sistema en 06/10 devolvió *Internal Server Error*.

### Diagnóstico

| Verificación | Resultado |
|---|---|
| Mismo caso en la base de prueba (`pruebas/reproducir_error_liquidar.py`) | No falla: Liquidar → 302, pantalla → 200 |
| Ruta "Liquidar" | Atrapa sus propios errores y redirige: el 500 tiene que salir al **mostrar** la pantalla de Liquidación |
| Código nuevo de la 6.0 en esa pantalla | El saldo del fondo recorre los aportes y gastos con el fondo de **todos** los meses |
| Gasto de fondo con período mal cargado (`"2026-9"` o vacío) en la base de prueba (`pruebas/probar_periodos_invalidos.py`) | **Reproduce el error** en Gastos, Liquidación, Plano y PDF (`ValueError` al leer el período) |

> No hay acceso a los datos ni al log de producción, así que no está confirmado que producción tenga ese dato: es la causa encontrada que reproduce el síntoma.

### Resultado con la corrección

| Pantalla (con gastos de fondo con período `"2026-9"` y vacío) | Antes | Después |
|---|---|---|
| Gastos 2026-11 | ❌ ValueError | ✅ 200 |
| Liquidación 2026-10 | ❌ ValueError | ✅ 200 |
| Liquidar 2026-10 | ✅ 302 | ✅ 302 |
| Plano | ❌ ValueError | ✅ 200 |
| PDF resumen 2026-12 | ❌ ValueError | ✅ 200 |
| Liquidar octubre con fecha 06/10 (caso reportado) | ✅ | ✅ 302 → 200 |
| Prueba completa del fondo (`probar_fondo_reserva.py`) | — | ✅ mismos saldos que en v6.0 |

---

## v6.0-0611 — Fondo de reserva y gastos extraordinarios

**Pedido:** base de las expensas = gastos ordinarios y recurrentes + aporte del período al fondo (el saldo acumulado no se vuelve a cobrar); cada gasto extraordinario se paga con el fondo o queda pendiente y se cobra en las expensas siguientes; la pantalla de Liquidaciones muestra el saldo acumulado del fondo (saldo anterior + aportes − gastos pagados con el fondo).

### Diagnóstico de lo que había (base de prueba, `pruebas/diagnostico_fondo.py`)

| Tema | Antes de v6.0 |
|---|---|
| Tarjeta "FONDO RESERVA" en Liquidación | Mostraba solo el **aporte del mes** ($ 150.000), no el saldo |
| "Fondo acumulado" del plano | Suma de **todos los aportes cargados** ($ 530.000), sin descontar gastos y con un aporte de agosto que nunca se liquidó; rotulado "pendiente de cobro" |
| Gastos pagados con el fondo (`VARIABLE_FR`) | No se cobraban, pero **nunca se descontaban** del fondo |
| Factura marcada "extraordinario" | Al pagarla se creaba un gasto con tipo = categoría de la factura → se cobraba como ordinario |
| Saldo inicial del fondo | No existía |
| Dato inconsistente | Gasto de octubre "candado" $ 11.000 cargado como VARIABLE (se cobraba) con su factura pagada con el fondo |

### Resultados (`pruebas/probar_fondo_reserva.py`, mes de gastos 2026-11 → liquidación 2026-12)

**1. Migración automática** (gastos cobrados cuya factura se pagó con el fondo):

| Gasto | Antes | Después | Efecto |
|---|---|---|---|
| #20 candado (oct, $ 11.000) | VARIABLE (se cobraba) | VARIABLE_FR (pagado con el fondo) | Liquidación 2026-11: expensas $ 1.060.442,22 → **$ 1.049.442,22** (− $ 11.000) |

**2. Saldo del fondo** (saldo inicial de prueba $ 500.000 al 2026-08; el aporte de agosto no cuenta):

| Mes de gastos | Saldo anterior | + Aporte liquidado | − Pagado con el fondo | = Saldo disponible |
|---|---|---|---|---|
| 2026-10 | $ 580.000,00 (500.000 + 80.000 de sep) | $ 150.000,00 | $ 11.000,00 | **$ 719.000,00** |
| 2026-11 | $ 719.000,00 | $ 150.000,00 | $ 0,00 | **$ 869.000,00** |

**3 y 4. Gasto extraordinario de prueba de $ 100.000 en 2026-11:**

| Modo | Expensas 2026-12 (total repartido) | Saldo del fondo | ¿Correcto? |
|---|---|---|---|
| Sin el gasto | $ 1.316.352,34 (= 1.166.352,34 ordinarios + 150.000 aporte) | $ 869.000,00 | ✅ base = ordinarios + aporte |
| **Pendiente** (se cobra) | $ 1.416.352,34 (+ 100.000, línea aparte) | $ 869.000,00 (sin cambio) | ✅ |
| **Con el fondo** | $ 1.316.352,34 (no se cobra) | $ 769.000,00 (− 100.000) | ✅ |

**5. Pantallas y PDF** (revisados con un extraordinario de cada tipo: $ 100.000 a cobrar y $ 60.000 con el fondo):

| Pantalla | Qué muestra | Resultado |
|---|---|---|
| Gastos | Ordinarios / aporte / tabla "Gastos extraordinarios" con "Pendiente: se cobra" o "Con el fondo" y botón para cambiar; desglose: ordinarios + aporte = base ordinaria + extraordinarios a cobrar = total a repartir; saldo del fondo | ✅ |
| Liquidación | Tarjeta del fondo con el **saldo disponible** ($ 809.000) y el aporte del mes; panel de expensas (ordinarios, aporte, extraordinarios a cobrar, total repartido $ 1.416.352,34) y panel del fondo (anterior 719.000 + aporte 150.000 − bomba 60.000 = 809.000) con aviso de extraordinarios pendientes | ✅ |
| PDF resumen | Gastos rotulados (Fijo / Aporte fondo / Extraord.), "TOTAL A REPARTIR"; estado financiero con el fondo (anterior, aporte, pagado, saldo); tabla aparte de pagados con el fondo | ✅ revisado visualmente |
| Plano, Configuración | Cargan; el plano muestra el saldo disponible | ✅ 200 |

Limpieza: gasto de prueba borrado, liquidación 2026-12 recalculada ($ 1.316.352,34) y configuración del fondo restaurada. La migración del candado queda aplicada (es el cambio buscado).

---

## v5.8-0611 — Fecha del sistema como vista (sin pagos posteriores)

**Problema reportado:** con la fecha del sistema en **06/10/2026**, la liquidación aparecía toda como **pagada**.

### Diagnóstico

| Verificación | Resultado |
|---|---|
| Período que abre la app con fecha 06/10 | **2026-10** (octubre) |
| Estado guardado de octubre | 24 unidades **TOTAL** (pagadas) |
| Filas que cambiaron en la base al fijar 06/10 (v5.7) | **0** — no se rompió ningún dato |
| Pagos de octubre con fecha posterior al 06/10 | **24** (todos registrados el 03/11/2026) |
| Causa | La fecha fijada solo movía intereses y vencimientos; los pagos registrados después se seguían contando |

### Resultado con la corrección

Fecha fijada **06/10/2026** (antes de los pagos):

| Verificación | Esperado | Resultado |
|---|---|---|
| Liquidación de octubre: unidades "Pagado" | 0 | ✅ 0 |
| Liquidación de octubre: unidades "Pendiente" | 24 | ✅ 24 |
| Nota "pagó el 03/11/2026" en cada fila | 24 | ✅ 24 |
| Mensaje "No se modifica ningún dato guardado" | Sí | ✅ |
| Base de datos sin cambios (comparación fila por fila) | Igual | ✅ igual |
| Recibo de pago real de octubre UF 01 (datos reales, firmado) | Se descarga | ✅ 200, PDF |
| Estado de cuenta / plano / unidades | Cargan | ✅ 200 |

Fecha fijada **05/12/2026** (después del vencimiento de noviembre):

| Unidad / período | Vista con la fecha fijada | Guardado en la base |
|---|---|---|
| Octubre UF 01 (pagó el 03/11, anterior a la fecha) | TOTAL, $ 13.207,76 pagado | TOTAL (sin cambios) |
| Noviembre UF 01 (sin pagar) | PENDIENTE, interés **$ 482,50** (mora 5 % de $ 9.650,02), total $ 10.132,52 | interés $ 0,00, total $ 9.650,02 |

Switch "sin interés" con la fecha 05/12 fijada (noviembre, UF 01):

| Acción | Lo que muestra la pantalla | Guardado en la base |
|---|---|---|
| Switch prendido (sin interés) | interés $ 0,00, total $ 9.650,02 | interés $ 0,00 |
| Switch apagado (con interés) | interés $ 482,50, total $ 10.132,52 | interés $ 0,00 (fecha real: noviembre aún no vencido) |

Al quitar la fecha: **base igual al inicio** ✅ y la vista vuelve a coincidir con lo guardado ✅.

> Entre corridas, alguien volvió a generar la liquidación de noviembre en la base de prueba: la deuda anterior de la UF 01 pasó de $ 11.090,55 (valor viejo, con octubre ya pagado) a $ 0,00. Por eso las cifras de noviembre difieren de las de v5.7.

---

## v5.7-0611 — Fecha del sistema

> En v5.8 se cambió el comportamiento: los intereses ya **no se guardan** con la fecha fijada (solo se muestran). Estas pruebas corresponden a la v5.7.

| Verificación | Resultado |
|---|---|
| Tarjeta "Fecha del sistema" arriba en Configuración | ✅ |
| Campo viejo "Fecha Simulada (para pruebas)" en la Zona de Pruebas | ✅ eliminado |
| Período actual con fecha 05/12/2026 | ✅ 2026-12 |
| Franja amarilla y etiqueta con la fecha en la barra superior | ✅ en todas las páginas |
| Guardar el formulario principal de Configuración no borra la fecha | ✅ (antes la borraba: bug corregido) |
| Fecha inválida ("no-es-fecha") | ✅ rechazada |
| Liquidación, PDF resumen, caja, gastos, unidades, plano con fecha fijada | ✅ 200 |
| Marca de los PDF | ✅ "Generado el 05/12/2026 a las …" |

Intereses (datos de la base de prueba en ese momento):

| Caso | Fecha real (06/11) | Fecha fijada 05/12/2026 | Al volver a la fecha real |
|---|---|---|---|
| Noviembre UF 01 (deuda anterior $ 11.090,55, sin pagar) | interés $ 554,53, total $ 21.295,10 | interés **$ 1.037,03** (554,53 + mora 482,50), total $ 21.777,60 | $ 554,53 ✅ |
| Octubre UF 06 (switch "sin interés" activo) | interés $ 0,00 | $ 0,00 ✅ respeta el switch | $ 0,00 |

---

## Switch de interés — diagnóstico (sin cambios de código)

**Problema reportado:** "el switch de intereses no está calculando".

Prueba de las rutas reales del switch (cada cambio se deshizo):

| Caso | Switch prendido (sin interés) | Switch apagado (con interés) |
|---|---|---|
| Noviembre UF 01 | interés $ 0,00 → total $ 20.740,57 | interés $ 554,53 → total $ 21.295,10 |
| Octubre UF 06 (pagada en total) | sin cambio: TOTAL, $ 133.452,31 | sin cambio |
| "Todos", diciembre (UF 01) | interés $ 0,00 → total $ 24.579,96 | interés $ 630,06 → total $ 25.210,02 |
| Pantalla de liquidación | ✅ carga con un switch por unidad (24) y el de "Todos" | |

**Conclusión:** el switch calcula bien. Situaciones en las que parece no hacer nada:

| Situación | Por qué |
|---|---|
| Unidad sin deuda anterior y antes del vencimiento | No hay interés que sacar ni poner ("—" en ambos casos) |
| Primer mes (octubre) | No se cobra interés sobre la deuda inicial |
| Deuda anterior desactualizada | Si se paga el mes anterior después de generar el siguiente, la deuda anterior guardada no se actualiza (registrar un pago no regenera el mes siguiente). Se corrige volviendo a "Generar liquidación". Ej.: noviembre UF 01 tenía $ 11.090,55 de deuda anterior con octubre ya pagado |

---

## v5.6-0611 — Certificado de libre deuda

| # | Caso | Esperado | Resultado |
|---|---|---|---|
| 1 | Estado inicial (último período 2026-12, todas las unidades deben) | Botón deshabilitado con el monto | ✅ ej. "Debe $ 25.210,02 de la liquidación 2026-12." |
| 2 | Emitir a una unidad con deuda (validación del servidor) | Bloqueado | ✅ "No se puede emitir…" |
| 3 | Pago total simulado de UF 01 en 2026-12 y emisión | Certificado emitido | ✅ N° 0001, hasta 2026-12, emitido 06/11/2026, vence 06/12/2026 |
| 4 | Segunda corrida | Número correlativo | ✅ N° 0002 |
| 5 | PDF | Se genera | ✅ 200, `application/pdf`, ~500 KB (incluye logo); revisado visualmente |
| 6 | Texto con caracteres especiales en el solicitante (`Juan <Pérez> & Cía`) | Se muestra literal | ✅ |
| 7 | Verificación pública con el código correcto | "Auténtico y vigente" | ✅ |
| 8 | Verificación con código falso | "Verificación fallida" | ✅ |
| 9 | Verificación de un número inexistente | "No encontrado" | ✅ |
| 10 | Anular y verificar | "ANULADO" | ✅ |
| 11 | Auditoría | Emisión y anulación registradas | ✅ INSERT "Unidades: emitir libre deuda", UPDATE "Unidades: anular libre deuda" |
| 12 | Limpieza | Pago restaurado, certificados borrados | ✅ |

Ajuste hecho a partir de la revisión del PDF: el "N° 0001" quedaba pegado al título.

---

## Cómo repetirlas

Requisitos: `.env.local` en la raíz del repo apuntando a la base de **prueba** (ver `.env.local.ejemplo`). Los scripts abortan si `DATABASE_URL` no es `consorcio-tst`.

Desde la raíz del repo, con el venv de Windows:

```
C:\Users\Maria\.venvs\consorcio\Scripts\python.exe pruebas\diagnostico_intereses.py
C:\Users\Maria\.venvs\consorcio\Scripts\python.exe pruebas\probar_switch_interes.py [periodo] [unidad]
C:\Users\Maria\.venvs\consorcio\Scripts\python.exe pruebas\probar_libre_deuda.py --limpiar
C:\Users\Maria\.venvs\consorcio\Scripts\python.exe pruebas\probar_fecha_sistema.py [fecha_antes] [fecha_despues]
C:\Users\Maria\.venvs\consorcio\Scripts\python.exe pruebas\diagnostico_fondo.py
C:\Users\Maria\.venvs\consorcio\Scripts\python.exe pruebas\probar_fondo_reserva.py [mes_gastos]
```

| Script | Qué prueba | ¿Modifica datos? |
|---|---|---|
| `entorno_prueba.py` | Carga `.env.local`, verifica que sea la base de prueba y arma el cliente con sesión de admin | No |
| `diagnostico_intereses.py` | Compara interés guardado vs. fórmula por período | No (solo lectura) |
| `probar_switch_interes.py` | Switch por unidad y "Todos" | Sí, y restaura el switch de cada unidad |
| `probar_libre_deuda.py` | Libre deuda completo | Sí: pago simulado (se restaura) y certificados (`--limpiar` los borra) |
| `probar_fecha_sistema.py` | Fecha del sistema como vista | Solo la fecha en config; al final vuelve a la anterior y verifica que la base quedó igual |
| `diagnostico_fondo.py` | Gastos por tipo, facturas y caja del fondo, saldo del fondo | No (solo lectura) |
| `reproducir_error_liquidar.py` | "Liquidar" con fecha fijada, mostrando el traceback si falla | Regenera esa liquidación (conserva pagos); restaura la fecha |
| `probar_periodos_invalidos.py` | Pantallas con gastos de fondo con período mal cargado | Inserta y borra gastos de prueba |
| `probar_anular_pagos.py` | Anular pago por unidad y del período, fecha de pago con fecha fijada | Sí, y lo revierte todo desde el Log de Movimientos |
| `probar_liquidacion_estados.py` | Pantalla de Liquidación abierta, cerrada y sin generar, con y sin fecha fijada | Cambia y restaura el estado de una liquidación y la fecha |
| `probar_pagina_error.py` | Página de error 500 para admin y usuario común | No |
| `probar_fondo_reserva.py` | Migración, saldo del fondo, extraordinarios pendiente / con el fondo, pantallas y PDF | Sí: aplica la migración (permanente); el gasto de prueba se borra y la config se restaura |

Cuando se agregue una prueba, sumar su sección arriba (la más nueva primero) y, si sirve repetirla, su script en `pruebas/`.
