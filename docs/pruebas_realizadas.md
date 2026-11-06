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
```

| Script | Qué prueba | ¿Modifica datos? |
|---|---|---|
| `entorno_prueba.py` | Carga `.env.local`, verifica que sea la base de prueba y arma el cliente con sesión de admin | No |
| `diagnostico_intereses.py` | Compara interés guardado vs. fórmula por período | No (solo lectura) |
| `probar_switch_interes.py` | Switch por unidad y "Todos" | Sí, y restaura el switch de cada unidad |
| `probar_libre_deuda.py` | Libre deuda completo | Sí: pago simulado (se restaura) y certificados (`--limpiar` los borra) |
| `probar_fecha_sistema.py` | Fecha del sistema como vista | Solo la fecha en config; al final vuelve a la anterior y verifica que la base quedó igual |

Cuando se agregue una prueba, sumar su sección arriba (la más nueva primero) y, si sirve repetirla, su script en `pruebas/`.
