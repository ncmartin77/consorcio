# Pruebas realizadas

Registro de las pruebas hechas antes de subir cada cambio a producción: qué se probó, contra qué datos y qué dio.
Las más recientes van primero. Los scripts para repetirlas están en [`pruebas/`](../pruebas/) (ver [Cómo repetirlas](#cómo-repetirlas)).

---

## Entorno de pruebas

| Item | Valor |
|---|---|
| Base de datos | Supabase **`consorcio-tst`** (proyecto de prueba, copia de producción), o desde el 11/11 una **base local** (`consorcio_pruebas` en el Postgres de Docker de `plataforma/`, copia de producción del 03/11). **Nunca** producción: `entorno_prueba.py` lo controla. |
| Consorcio usado | Edificio Perú 376 (`consorcio_id = 28693516`), 24 unidades |
| Cómo se ejecutan | Cliente de pruebas de Flask (`app.test_client()`) con sesión de admin: recorre las rutas reales sin login de Google ni navegador |
| Python | venv de Windows `C:\Users\Maria\.venvs\consorcio`, o contenedor Docker con `pruebas/correr_en_docker.sh` (Python 3.12, sin instalar nada) |
| Fecha real de las pruebas | 06/11/2026 |
| Configuración de la base de prueba | `tasa_mora` = 5 %, `dia_vencimiento` = 0 (último día del mes) |
| Liquidaciones en la base de prueba | 2026-10, 2026-11 y 2026-12, todas ABIERTAS. Octubre pagada completa (pagos registrados el 03/11/2026); noviembre y diciembre pendientes |
| Verificación del deploy | Después de cada push a `master` se consultó la página pública `/libre-deuda/verificar/...` en Render hasta ver la versión nueva |

> Las pruebas que modifican datos (pago simulado, switch) dejan todo como estaba al terminar. Los certificados de libre deuda de prueba se borran.

---

## v10.0-0911 — Lineamientos jurídicos (09/11/2026) — EN CURSO

`pruebas/probar_v10.py` contra la base de prueba (consorcio temporal "Prueba v10", 2 UF al 50 %, expensa $100.000,
tasa 3 %, se borra al final). Resultado: **50/50 OK** (antes de agregar los 3 controles de la página Ayuda: falta
repetirla). Regresión, de a una: cobranzas 44/44, factura_con_fondo 14/14, factura_vinculo 16/16, pdf_planilla 15/15,
seguridad 24/24. **Pendiente:** fondo_reserva (actualizada a la regla del libro del fondo), libre_deuda (falló:
`Location` sin `ld=`, sin investigar), saldo_a_favor (rota desde antes: usa `_calcular_interes`, que ya no existe) y
las demás.

| Caso | Esperado | Resultado |
|---|---|---|
| Nov: deuda 100.000, interés 3 % | 3.000, total 203.000 | ✅ |
| Dic: interés sobre el capital 200.000 (no sobre 203.000) | 6.000, total 309.000, intereses impagos 3.000 | ✅ |
| Dic: tasa congelada al cerrar | 3 % | ✅ |
| Tasa con vigencia en un período cerrado | rechazada | ✅ |
| Tasa 4 % desde 01/01/2027 | dic usa 3, ene usa 4 | ✅ |
| Ene UF 1 sin pagos | deuda 309.000 de la cual 9.000 intereses | ✅ |
| Ene UF 2 pagó 150.000 (CCyC 903) | primero cancela los 9.000 de intereses: deuda 159.000, 0 intereses | ✅ |
| Interés propuesto ene (4 % sobre capital) | UF1 12.000, UF2 6.360 | ✅ |
| Capitalización activada / desactivada | 12.360 / vuelve a 9.000 de intereses aparte | ✅ |
| Libro del fondo: aportes cobrados | 14.100 (imputación FIFO, aporte 10 %) | ✅ |
| Libro del fondo: saldo efectivo | 600.000 + 14.100 + 5.000 − 50.000 = 569.100 | ✅ |
| Aportes pendientes / compromisos / disponible | 45.900 / 30.000 / 539.100 | ✅ |
| PDF: cuadro Fondo de Reserva | saldo efectivo y pendiente | ✅ |
| Exportación: ZIP, sin clave de firma, no admin redirige | ✅ / ✅ / 302 | ✅ |
| Gasto ordinario no recurrente / extraordinario con respaldo / ordinario con el fondo | VARIABLE / EXTRAORDINARIO / VARIABLE_FR conservando naturaleza | ✅ |
| "Cobrar" un ordinario pagado con fondo | VARIABLE (no extraordinario) | ✅ |
| Clasificación inválida / gasto viejo sin campos | rechazada / deducida del tipo | ✅ |
| Plazos: 3 hábiles desde vie 08/01, 60 corridos desde 31/12 | 13/01 / 01/03 | ✅ |
| Alertas: mandato, registro en trámite, rendición, ascensor | 4 alertas | ✅ |
| Certificado de ascensor: solo cuenta el último | 1 alerta | ✅ |
| Marcar cumplido | la alerta desaparece | ✅ |
| PDF: registro "en trámite" y CUIT | sin presentarlo como inscripción | ✅ |
| Página Ayuda (navegador) | manual renderizado, 17 enlaces del índice OK, sin diagramas | ✅ (revisado a mano) |
| Diagramas `docs/diagramas.md` | 23 diagramas Mermaid sin errores | ✅ (dibujados en el navegador) |

---

## v11.1-1211 — Borrar comprobantes y archivos (12/11/2026)

`pruebas/probar_storage.py` ahora tiene 37 controles (11 nuevos), corrida contra la base local `consorcio_pruebas`:

| Almacenamiento | Resultado |
|---|---|
| Disco | ✅ 37/37 |
| S3 local (SeaweedFS, bucket `pruebas-flask`) | ✅ 37/37 |
| Supabase Storage de `consorcio-tst` (bucket `comprobantes`, solo consorcios temporales de la prueba) | ✅ 37/37 |

Controles nuevos:
- quitar el comprobante (la factura queda sin comprobante, se borra el archivo y hay aviso);
- quitar cuando no hay comprobante (aviso);
- reemplazar (se borra el archivo anterior);
- eliminar la factura (se borra su comprobante);
- archivo compartido por dos facturas (se borra recién al quitarlo de la última);
- archivo viejo en el disco (se borra);
- eliminar un consorcio con 2 archivos (no queda ninguno y no toca los de otros consorcios).

Corrida completa: las 17 pruebas dan OK.

Navegador (`servidor_local.py` con el S3 local), en la factura 31 de Perú 376:
- el botón "Quitar comprobante" aparece solo si hay comprobante;
- al quitarlo aparece "Comprobante quitado", desaparece el botón y en el S3 local no queda ningún archivo.

---

## v11.0-1211 — Archivos en Supabase Storage (12/11/2026)

`pruebas/probar_storage.py` (consorcio temporal; al terminar borra sus archivos y el consorcio), corrida tres veces contra la base local `consorcio_pruebas`:

| Almacenamiento | Resultado |
|---|---|
| Disco (sin variables `STORAGE_S3_*`) | ✅ 26/26 |
| S3 local (SeaweedFS de `plataforma/`, bucket `pruebas-flask`) | ✅ 26/26 |
| Supabase Storage de `consorcio-tst` (bucket `comprobantes`) | ✅ 26/26 |

Qué controla: subir un PDF y una imagen (se convierte a PDF) como comprobantes, que no quede nada en el disco, verlos por la app, imagen ilegible (aviso, sin error 500), comprobante viejo en disco (se sigue viendo), comprobante registrado que no existe (aviso), Backup y Exportación con los comprobantes y aviso de faltantes, adjunto de notificación (subir, ver, rechazar `.exe`, nombre con trucos → 404), que otro consorcio no vea los archivos y que se rechacen rutas como `../x`.

Además:

| Control | Resultado |
|---|---|
| Bucket `comprobantes` de `consorcio-tst` es privado: el archivo no se puede bajar por la URL pública ni sin clave | ✅ 400 en ambas |
| Navegador (`servidor_local.py` con Storage de `consorcio-tst`): adjuntar un PDF a la factura 31 de Perú 376 y verlo | ✅ "Comprobante adjuntado correctamente"; se sirve `application/pdf` inline con el contenido subido |

> Limpieza: después de la prueba en el navegador se borró la carpeta `28693516/` del bucket y se dejó la factura 31 sin comprobante. En esa carpeta había además un archivo de una prueba anterior (`facturas/cejas_hector/2026-11-04_185932.pdf`, de la v6.0 del 04/11) que también se borró por error. Era del proyecto de prueba, no de producción.

---

## v10.4-1111 — La app corriendo en una PC con base local (11/11/2026)

`pruebas/servidor_local.py` contra `consorcio_pruebas` (copia del 03/11 en el Postgres local):

| Control | Resultado |
|---|---|
| `/__login_local` entra como el usuario 1 (admin) y lleva a Consorcios | ✅ 302 → /consorcios |
| Sin sesión, `/liquidacion` manda al login | ✅ 302 → /login |
| `/__login_local` con `X-Forwarded-For` (pedido que pasa por un proxy) | ✅ 404 |
| Navegador: elegir Peru 376 y abrir Liquidación (noviembre 2026), con la franja "MODO PRUEBAS" | ✅ (revisado en el navegador) |

---

## v10.3-1111 — Las 6 pruebas viejas, actualizadas con escenario propio (11/11/2026)

**Qué cambió:** las 6 pruebas que la v10.2 marcó como viejas se reescribieron con la lógica actual (v9.x/v10) y con un
**escenario propio** (`pruebas/escenario.py`). Cada una crea un consorcio temporal (2 UF al 50 %, expensa de $100.000
por UF, tasa 3 % y vencimiento el día 10), arma lo que necesita y lo borra al terminar. Ya no dependen de los datos de
la base de prueba y terminan con código 1 si algún control falla.

| Prueba | Antes | Ahora | Controles |
|---|---|---|---|
| `probar_pagina_error.py` | Cambiaba `es_admin` en la sesión (sin efecto desde la v9.8) | Usuario **no administrador real** (creado y borrado), con `es_admin=True` en la sesión a propósito | ✅ 5/5 |
| `probar_anular_pagos.py` | Ruta de la v6.4 (`/liquidacion/<p>/anular-pagos`): no anulaba nada | `/cobranzas/<p>/anular`: un pago, una unidad, todos; no admin bloqueado; reabrir solo sin pagos; pago sin fecha = fecha del sistema | ✅ 12/12 |
| `probar_libre_deuda.py` | Dependía de que hubiera una liquidación cerrada | Escenario con octubre cerrado (UF 1 pagó, UF 2 no): bloqueo, emisión, PDF, verificación pública, anulación, auditoría | ✅ 12/12 |
| `probar_fecha_sistema.py` | Usaba el switch quitado en la v9.2 | Vista a una fecha anterior al pago (pendiente) sin cambiar la base, franja de aviso, pantallas y PDF, fecha inválida | ✅ 17/17 |
| `probar_switch_interes.py` | Switch de la pantalla Liquidación (quitado en la v9.2) | Interés al **cerrar** (v9.2) con la regla v10: abierta sin interés, propuesta 3 % sobre el capital, switch por UF, tasa congelada | ✅ 7/7 |
| `probar_saldo_a_favor.py` | Usaba `pg_db._calcular_interes` (no existe desde la v9.2) | Pago de más → saldo −150.000; noviembre pagado sin abonar; sin interés sobre saldo a favor; diciembre arrastra −50.000 | ✅ 12/12 |

**Corrida completa** de las **16** pruebas, de a una, contra la base local limpia (`consorcio_pruebas`, recreada desde
`consorcio_pruebas_inicial`): **las 16 con código 0**. v10 53/53, cobranzas 44/44, seguridad 24/24, factura_con_fondo
14/14, factura_vinculo 16/16, pdf_planilla 15/15, las 6 de arriba (65 controles) y fondo_reserva, liquidacion_estados,
periodos_invalidos y saldo_cierre sin fallas. Al terminar no quedó ningún consorcio ni usuario temporal.

---

## v10.2-1111 — Corrida completa en una base local (10 y 11/11/2026)

**Por qué:** desde la red del Senado no se llega a Supabase, y las pruebas de la v10.0 se habían cortado.

**Cómo:**
- Base `consorcio_pruebas` en el Postgres local de Docker (rama `feat/plataforma`, `scripts/restaurar_legado.sh`), con la copia de producción del 03/11 (v5.x). Al arrancar, las funciones `ensure_*` de la v10.1 pusieron al día la estructura: de 21 a 25 tablas, con `tasas_mora`, `pagos` y las columnas nuevas. Las 11 páginas principales respondieron 200.
- Foto limpia en `consorcio_pruebas_inicial`: después de las pruebas que modifican datos, la base se vuelve a crear desde esa foto.
- Cada prueba corrida de a una con `pruebas/correr_en_docker.sh`. `entorno_prueba.py` ahora acepta una base local además de `consorcio-tst`, y sigue rechazando producción: probado con una URL de producción, que aborta.

| Prueba | Resultado | Nota |
|---|---|---|
| `probar_v10.py` | ✅ **53/53** | Incluye los 3 controles de la página Ayuda que faltaba repetir |
| `probar_cobranzas.py` | ✅ 44/44 | Incluye anular un pago con la ruta de Cobranzas |
| `probar_factura_con_fondo.py` | ✅ 14/14 | |
| `probar_factura_vinculo.py` | ✅ 16/16 | |
| `probar_pdf_planilla.py` | ✅ 15/15 | |
| `probar_seguridad.py` | ✅ 24/24 | |
| `probar_fondo_reserva.py` | ✅ sin fallas | Regla del libro del fondo |
| `probar_liquidacion_estados.py`, `probar_periodos_invalidos.py`, `probar_saldo_cierre.py` | ✅ sin errores | |
| `probar_libre_deuda.py` | ✅ con datos preparados | Necesita una liquidación **cerrada** con la unidad pagada: es el "`Location` sin `ld=`" del 09/11. Se preparó con la app (fecha del sistema 05/11, cierre de 2026-10, pago de la UF 01) y emitió, bloqueó, verificó y anuló bien. **La prueba debería preparar su propio escenario.** |
| `probar_pagina_error.py` | ⚠️ prueba desactualizada; la app está bien | Desde la v9.8 el rol de administrador se lee de la base en cada pedido, y la prueba solo cambia `es_admin` en la sesión: su "usuario común" sigue siendo admin. **Verificado a mano** con un usuario no administrador real: ve el mensaje simple, sin detalle. |
| `probar_anular_pagos.py` | ⚠️ desactualizada | Usa `/liquidacion/<p>/anular-pagos` (v6.4), que la v9.0 movió a `/cobranzas/<p>/anular`: termina sin error pero **no anula nada**. La anulación queda cubierta por `probar_cobranzas.py`. |
| `probar_fecha_sistema.py`, `probar_switch_interes.py` | ❌ desactualizadas | Usan el switch "sin interés" de Liquidación, quitado en la v9.2 |
| `probar_saldo_a_favor.py` | ❌ desactualizada | Usa `pg_db._calcular_interes`, que no existe desde la v9.2 |

**Conclusión:** ninguna falla es del código de la v10.1. Quedan **6 pruebas para actualizar**: libre_deuda (que prepare su escenario), pagina_error, anular_pagos, fecha_sistema, switch_interes y saldo_a_favor.

---

## v9.8-0911 — Arreglos de seguridad (09/11/2026)

`pruebas/probar_seguridad.py` contra la base de prueba. Resultado: **24/24 OK**; la base quedó como al inicio (usuario de prueba borrado; la liquidación 2026-10 se cerró solo durante la prueba y volvió a ABIERTA). Se repitieron `probar_factura_vinculo.py` (16/16), `probar_factura_con_fondo.py` (14/14), `probar_pdf_planilla.py` (15/15) y `probar_cobranzas.py`.

| Caso | Esperado | Resultado |
|---|---|---|
| Cuenta nueva de Google | inactiva, no admin, la manda al login | ✅ |
| Usuario no admin: eliminar consorcio / crear consorcio / resetear datos | rechazado, sin cambios | ✅ |
| Sesión con es_admin=True pero la base dice no admin | el rol se refresca, sin acceso a administración | ✅ |
| POST con Origin o Referer de otro sitio | 403 | ✅ |
| POST del mismo sitio | pasa | ✅ |
| Gasto con importe nan / inf / -50 / texto | rechazado | ✅ |
| Gasto FONDO_RESERVA cargado a mano | rechazado | ✅ |
| Caja con tipo inválido o importe inf | rechazado | ✅ |
| Factura con importe negativo | rechazada | ✅ |
| Factura pagada reenviada a mano con su id | sigue PAGADA, sin cambios | ✅ |
| Pagar dos veces la misma factura | una sola salida en Caja | ✅ |
| Apertura con saldo nan | rechazada, sin cambios | ✅ |
| Pago de expensas con monto nan | rechazado | ✅ |
| Cargar / borrar gasto de un período con liquidación cerrada | rechazado | ✅ |
| Servidor (RENDER=true) sin SECRET_KEY | la app no arranca | ✅ |

---

## v9.6-0811 — Planilla de liquidación horizontal (08/11/2026)

`pruebas/probar_pdf_planilla.py` contra la base de prueba: descarga el PDF de las liquidaciones 2026-10, 2026-11 y 2026-12. Resultado: **15/15 OK**. Además se renderizaron las páginas a imagen y se revisaron a ojo (también una variante con interés ficticio en 2 UF, generada en memoria sin tocar la base).

| Caso | Esperado | Resultado |
|---|---|---|
| PDF de cada liquidación | 200, application/pdf | ✅ |
| Orientación | A4 horizontal | ✅ |
| Columnas nuevas | "Liquidado mes ant." y "Pago anterior" | ✅ |
| Cuadro de totales | debajo de la tabla de UF | ✅ |
| Primera liquidación (2026-10, sin anterior) | columnas nuevas con "—" | ✅ (visual) |
| 24 UF + totales | en la primera hoja | ✅ (visual) |
| Con columna Interés | todo entra en una hoja, sin superposiciones | ✅ (visual) |

---

## v9.4-0811 — Gasto vinculado a su factura y observación del pago (08/11/2026)

`pruebas/probar_factura_vinculo.py` contra la base de prueba, fecha del sistema 08/11/2026 (gastos 2026-11 → liquidación 2026-12, abierta). Resultado: **16/16 OK**; la base quedó como al inicio. `probar_factura_con_fondo.py` repetida: 14/14 OK.

| Caso | Esperado | Resultado |
|---|---|---|
| Guardar factura sin proveedor | se guarda (antes error 500) | ✅ |
| Pagar factura | un gasto vinculado a la factura | ✅ |
| Observación del pago | guardada y visible en Facturas | ✅ |
| Borrar la factura | el gasto queda, sin factura; Gastos Mensuales ofrece "Emitir factura de este gasto" | ✅ |
| Emitir desde el gasto y pagar | factura vinculada, sigue un solo gasto, total +2500 (no +5000) | ✅ |
| Borrar el pago en Caja y repagar | factura PENDIENTE → PAGADA, sigue un solo gasto | ✅ |
| Recurrente: borrar factura y emitirla de nuevo | reutiliza el gasto que quedó; al pagar sigue uno solo | ✅ |
| Limpieza | total de gastos como al inicio | ✅ |

---

## v9.3-0811 — Pagar factura con el Fondo de Reserva (08/11/2026)

`pruebas/probar_factura_con_fondo.py` contra la base de prueba, fecha del sistema 08/11/2026 (gastos 2026-11 → liquidación 2026-12, abierta). Resultado: **14/14 OK**; la base quedó como al inicio.

| Caso | Esperado | Resultado |
|---|---|---|
| Pantalla Facturas | switch "Pagar con Fondo de Reserva" en el modal | ✅ |
| Pagar factura común con el fondo | PAGADA, categoría FONDO_RESERVA | ✅ |
| Caja | salida de $ 12.345,67 con categoría FONDO_RESERVA | ✅ |
| Gasto | uno solo, tipo VARIABLE_FR (en "con fondo" del desglose) | ✅ |
| Total de gastos de la liquidación | sin cambios ($ 1.316.352,34) | ✅ |
| Control: pagar sin el fondo | gasto FIJO, total sube $ 1.000 | ✅ |
| Factura de gasto recurrente pagada con el fondo | el gasto FIJO cargado al guardarla pasa a VARIABLE_FR, sin duplicar | ✅ |
| Limpieza | total de gastos como al inicio | ✅ |

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

## v9.2-0711 — Interés al cerrar la liquidación (07/11/2026)

`pruebas/probar_cobranzas.py` actualizada a la regla v9.2: abierta sin interés; al cerrar, switch por unidad con tasa × deuda anterior (L08: UF 1 deuda 100 → 10; L09: UF 3 deuda 150 → 15); Cobranzas no cobra interés. Mismo consorcio aislado (tasa 10 %). Resultado: **44/44 OK**.

| Caso | Esperado | Resultado |
|---|---|---|
| L08 generada (deuda de apertura, sin interés el 1er mes) | {1: 600, 2: 300, 3: 150} | ✅ |
| Pagar sobre liquidación ABIERTA | rechazado | ✅ |
| Cerrar L08 con fecha 20/07 (no cambió el mes) | sigue ABIERTA | ✅ |
| Pantalla Liquidación sin botones de pago | sin modalPago / Pago Completo | ✅ |
| Ventana de cierre L08: unidades con deuda anterior | solo UF 1 (deuda 100, interés 10) | ✅ |
| Cerrar L08 con fecha 01/08 | CERRADA, fecha de cierre 01/08 | ✅ |
| Periodo en cobro | 2026-08 | ✅ |
| Cerrar con interés para UF 1 | interés 10 % × 100 = 10, total 610 | ✅ |
| Pago con fecha posterior a la fecha del sistema (05/08 con hoy 01/08) | rechazado | ✅ |
| Pagar después del vencimiento (UF 2, 20/08) | Cobranzas no cobra interés | ✅ |
| Estado de L08 tras los pagos | 1 TOTAL 660 / 2 TOTAL 300 / 3 PENDIENTE 0 | ✅ |
| UF 1 pagó de más | saldo a favor 50 | ✅ |
| Pagos y Caja | 4 pagos, 4 entradas Expensas + 1 bonificación, sin Intereses | ✅ |
| Pago con fecha en una Caja cerrada (julio, L08 cerrada) | rechazado | ✅ |
| L09 abierta: deuda / interés / total (abierta: sin interés) | {'1': (-50.0, 0.0, 950.0), '2': (0.0, 0.0, 600.0), '3': (150.0, 0.0, 550.0)} | ✅ |
| Pantalla Liquidación sin columna ni switch de interés | sin chk-sin-interes / toggleTodosInteres | ✅ |
| Pagar sobre L09 abierta | rechazado | ✅ |
| Fecha 15/08: L08 UF 2 no cuenta el pago del 20/08 | PARCIAL 100, pagó el 20/08 | ✅ |
| Fecha 15/08: L09 se recalcula a esa fecha | UF1 deuda 0 / UF2 deuda 200, sin interés | ✅ |
| Cobranzas: fecha por defecto = fecha del sistema | value="2026-08-15" | ✅ |
| Vuelta a 25/08: L09 UF 2 | deuda 0, total 600 | ✅ |
| Cobranzas sin interés (ni switch ni columna) | sin cobrar_interes / si paga hoy | ✅ |
| Anular el pago del 20/08 de UF 2 | se borra pago + entrada + bonificación + interés; L09 UF2 deuda 200 | ✅ |
| Revertir desde el Log el último pago | UF 2 vuelve a deber 200 en L09 | ✅ |
| Cerrar L09 el 25/08 | rechazado (desde el 01/09) | ✅ |
| Propuesta de interés al cerrar L09 | solo UF 3: deuda 150, interés 15 (UF 1 a favor, UF 2 sin deuda) | ✅ |
| L09 cerrada con interés para UF 3 | UF3 15 → total 565; UF1/UF2 sin interés | ✅ |
| Liquidación cerrada muestra la columna Interés | columna con $ 15,00 | ✅ |
| Cerrar L09 el 02/09 | CERRADA, en cobro 2026-09 | ✅ |
| Pagar sobre L08 (ya no es la última cerrada) | rechazado | ✅ |
| Pago a L09 con fecha de agosto (Caja de agosto cerrada) | rechazado | ✅ |
| Pago a L09 el 03/09 | UF 3 TOTAL | ✅ |
| Reabrir L09 con pagos | rechazado | ✅ |
| Reabrir L08 con L09 cerrada | rechazado | ✅ |
| Editar en Caja el cobro de UF 3 (500, 04/09) | el pago acompaña: 500 el 04/09, PARCIAL | ✅ |
| Borrar en Caja el cobro de UF 3 | se borra el pago | ✅ |
| Borrar en Caja un cobro de agosto (Caja cerrada) | bloqueado | ✅ |
| Pago completo de L09 cobra el total (con el interés de UF 3) | 950 / 600 / 565 | ✅ |
| Pago completo de L09 | todas TOTAL | ✅ |
| Libre deuda según la última cerrada (L09) | las 3 libres, período 2026-09 | ✅ |
| Pantallas y PDFs | 200 en todas | ✅ |
| Cobranzas de L08 (no es la última) | solo consulta, sin botón de pago | ✅ |
| Migración de un pago viejo (200 en Caja + 100 sin entrada, bonificación) | 2 pagos: 200 vinculado a Caja + 100; bonificación 10 en el primero | ✅ |
| Migración idempotente | 0 la segunda vez | ✅ |

---

## v9.1-0711 — Interés al cobrar (07/11/2026)

`pruebas/probar_cobranzas.py` actualizada a la regla v9.1 (la liquidación no lleva interés; se cobra al registrar un pago fuera de término con el switch, tasa × saldo, una vez por unidad). Mismo consorcio aislado (tasa 10 %, vencimiento día 10). Resultado: **42/42 OK**.

| Caso | Esperado | Resultado |
|---|---|---|
| L08 generada (deuda de apertura, sin interés el 1er mes) | {1: 600, 2: 300, 3: 150} | ✅ |
| Pagar sobre liquidación ABIERTA | rechazado | ✅ |
| Cerrar L08 con fecha 20/07 (no cambió el mes) | sigue ABIERTA | ✅ |
| Pantalla Liquidación sin botones de pago | sin modalPago / Pago Completo | ✅ |
| Cerrar L08 con fecha 01/08 | CERRADA, fecha de cierre 01/08 | ✅ |
| Periodo en cobro | 2026-08 | ✅ |
| Pago con fecha posterior a la fecha del sistema (05/08 con hoy 01/08) | rechazado | ✅ |
| UF 2 paga 200 el 20/08 (vence 10/08) con el switch activado | interés 10 % × 200 = 20 en ese pago | ✅ |
| UF 1 paga de más el 25/08 (sin saldo) | sin interés | ✅ |
| Estado de L08 tras los pagos | 1 TOTAL 650 / 2 TOTAL 300 / 3 PENDIENTE 0 | ✅ |
| UF 1 pagó de más | saldo a favor 50 | ✅ |
| Pagos y Caja | 4 pagos, 4 entradas Expensas + 1 bonificación + 1 Intereses | ✅ |
| Pago con fecha en una Caja cerrada (julio, L08 cerrada) | rechazado | ✅ |
| L09 abierta: deuda / interés / total (la deuda pasa sin interés) | {'1': (-50.0, 0.0, 950.0), '2': (0.0, 0.0, 600.0), '3': (150.0, 0.0, 550.0)} | ✅ |
| Pantalla Liquidación sin columna ni switch de interés | sin chk-sin-interes / toggleTodosInteres | ✅ |
| Pagar sobre L09 abierta | rechazado | ✅ |
| Fecha 15/08: L08 UF 2 no cuenta el pago del 20/08 | PARCIAL 100, pagó el 20/08 | ✅ |
| Fecha 15/08: L09 se recalcula a esa fecha | UF1 deuda 0 / UF2 deuda 200, sin interés | ✅ |
| Cobranzas: fecha por defecto = fecha del sistema | value="2026-08-15" | ✅ |
| Vuelta a 25/08: L09 UF 2 | deuda 0, total 600 | ✅ |
| Cobranzas a 25/08: UF 3 debe 150 vencido | columna Interés sugiere $ 15,00 si paga hoy | ✅ |
| Anular el pago del 20/08 de UF 2 | se borra pago + entrada + bonificación + interés; L09 UF2 deuda 200 | ✅ |
| Revertir desde el Log el último pago | UF 2 vuelve a deber 200 en L09 | ✅ |
| Cerrar L09 el 25/08 | rechazado (desde el 01/09) | ✅ |
| Cerrar L09 el 02/09 | CERRADA, en cobro 2026-09 | ✅ |
| Pagar sobre L08 (ya no es la última cerrada) | rechazado | ✅ |
| Pago a L09 con fecha de agosto (Caja de agosto cerrada) | rechazado | ✅ |
| Pago a L09 el 03/09 | UF 3 TOTAL | ✅ |
| Reabrir L09 con pagos | rechazado | ✅ |
| Reabrir L08 con L09 cerrada | rechazado | ✅ |
| Editar en Caja el cobro de UF 3 (500, 04/09) | el pago acompaña: 500 el 04/09, PARCIAL | ✅ |
| Borrar en Caja el cobro de UF 3 | se borra el pago | ✅ |
| Borrar en Caja un cobro de agosto (Caja cerrada) | bloqueado | ✅ |
| UF 2 en L09: switch apagado / activado / de nuevo activado | 0 / 50 (10 % de 500) / 0 (una sola vez) | ✅ |
| La liquidación no cambia por el interés | L09 UF 2 total 600, abonado 300 | ✅ |
| Pago completo el 15/09 con interés | UF1 10 % × 950 = 95 / UF2 50 (ya cobrado) / UF3 10 % × 550 = 55 | ✅ |
| Pago completo de L09 | todas TOTAL | ✅ |
| Libre deuda según la última cerrada (L09) | las 3 libres, período 2026-09 | ✅ |
| Pantallas y PDFs | 200 en todas | ✅ |
| Cobranzas de L08 (no es la última) | solo consulta, sin botón de pago | ✅ |
| Migración de un pago viejo (200 en Caja + 100 sin entrada, bonificación) | 2 pagos: 200 vinculado a Caja + 100; bonificación 10 en el primero | ✅ |
| Migración idempotente | 0 la segunda vez | ✅ |

---

## v9.0-0711 — Cobranzas separada de Liquidación (07/11/2026)

Prueba `pruebas/probar_cobranzas.py`: crea un consorcio aislado en la base de prueba (3 UF: deuda de apertura 100 / 0 / −50, porcentajes 50/30/20, tasa 10 %, vencimiento día 10, gastos jul $ 1.000 y ago $ 2.000), recorre el ciclo completo y al final lo borra. Resultado: **35/35 OK** (una corrida anterior dio 33/35 por un corte de conexión de Supabase en medio de la prueba; se agregó el descarte de conexiones cerradas en el pool y se repitió).

| Caso | Esperado | Resultado |
|---|---|---|
| L08 generada (deuda de apertura, sin interés el 1er mes) | {1: 600, 2: 300, 3: 150} | ✅ |
| Pagar sobre liquidación ABIERTA | rechazado | ✅ |
| Cerrar L08 con fecha 20/07 (no cambió el mes) | sigue ABIERTA | ✅ |
| Pantalla Liquidación sin botones de pago | sin modalPago / Pago Completo | ✅ |
| Cerrar L08 con fecha 01/08 | CERRADA, fecha de cierre 01/08 | ✅ |
| Periodo en cobro | 2026-08 | ✅ |
| Pago con fecha posterior a la fecha del sistema (05/08 con hoy 01/08) | rechazado | ✅ |
| Estado de L08 tras los pagos | 1 TOTAL 650 / 2 TOTAL 300 / 3 PENDIENTE 0 | ✅ |
| UF 1 pagó de más | saldo a favor 50 | ✅ |
| Pagos y Caja | 4 pagos, 4 entradas Expensas + 1 bonificación | ✅ |
| Pago con fecha en una Caja cerrada (julio, L08 cerrada) | rechazado | ✅ |
| L09 abierta: deuda / interés / total | {'1': (-50.0, 0.0, 950.0), '2': (0.0, 20.0, 620.0), '3': (150.0, 15.0, 565.0)} | ✅ |
| Pagar sobre L09 abierta | rechazado | ✅ |
| Fecha 15/08: L08 UF 2 no cuenta el pago del 20/08 | PARCIAL 100, pagó el 20/08 | ✅ |
| Fecha 15/08: L09 se recalcula a esa fecha | UF1 deuda 0 / UF2 deuda 200 + interés 20 | ✅ |
| Cobranzas: fecha por defecto = fecha del sistema | value="2026-08-15" | ✅ |
| Vuelta a 25/08: L09 UF 2 | deuda 0, total 620 | ✅ |
| Anular el pago del 20/08 de UF 2 | se borra pago + entrada + bonificación; L09 UF2 deuda 200 | ✅ |
| Revertir desde el Log el último pago | UF 2 vuelve a deber 200 en L09 | ✅ |
| Cerrar L09 el 25/08 | rechazado (desde el 01/09) | ✅ |
| Cerrar L09 el 02/09 | CERRADA, en cobro 2026-09 | ✅ |
| Pagar sobre L08 (ya no es la última cerrada) | rechazado | ✅ |
| Pago a L09 con fecha de agosto (Caja de agosto cerrada) | rechazado | ✅ |
| Pago a L09 el 03/09 | UF 3 TOTAL | ✅ |
| Reabrir L09 con pagos | rechazado | ✅ |
| Reabrir L08 con L09 cerrada | rechazado | ✅ |
| Editar en Caja el cobro de UF 3 (500, 04/09) | el pago acompaña: 500 el 04/09, PARCIAL | ✅ |
| Borrar en Caja el cobro de UF 3 | se borra el pago | ✅ |
| Borrar en Caja un cobro de agosto (Caja cerrada) | bloqueado | ✅ |
| Pago completo de L09 | todas TOTAL | ✅ |
| Libre deuda según la última cerrada (L09) | las 3 libres, período 2026-09 | ✅ |
| Pantallas y PDFs | 200 en todas | ✅ |
| Cobranzas de L08 (no es la última) | solo consulta, sin botón de pago | ✅ |
| Migración de un pago viejo (200 en Caja + 100 sin entrada, bonificación) | 2 pagos: 200 vinculado a Caja + 100; bonificación 10 en el primero | ✅ |
| Migración idempotente | 0 la segunda vez | ✅ |

Ensayo de la migración de pagos (`pruebas/diagnostico_migracion_pagos.py`, Perú 376 en la base de prueba):

| Caso | Esperado | Resultado |
|---|---|---|
| Pagos del sistema viejo (filas de liquidaciones) | 24 filas pasan a la tabla `pagos` | ✅ 24 pagos |
| Vínculo con Caja | cada pago con su entrada "Expensas …" | ✅ 24 vinculados, 0 sueltos |
| Montos por liquidación y unidad | iguales antes y después | ✅ sin diferencias ($ 1.783.511,98) |

---

## v8.1-0611 — Saldo de caja a la fecha de cierre

Reporte: el PDF decía "Saldo de caja al 31/10" pero se generó el 01/10 (fecha del sistema).

Prueba (`pruebas/probar_saldo_cierre.py`, base de prueba, liquidación 2026-12):

| Caso | Esperado | Resultado |
|---|---|---|
| Abierta, fecha del sistema 10/12 | saldo al 10/12 (PDF y tarjeta SALDO EN CAJA) | ✅ |
| Cerrada el 05/01, consultada el 20/01 | saldo al 05/01 | ✅ |
| Cerrada sin fecha de cierre guardada (anterior a v8.1) | saldo a fin de mes (31/12) | ✅ |
| Reabierta | se borra la fecha de cierre | ✅ |
| PDF resumen | 200 | ✅ |

---

## v8.0-0611 — Fondo de Reserva = saldo de caja del mes anterior

| Caso | Esperado | Resultado |
|---|---|---|
| Producción (solo lectura), liquidación oct | fondo = caja al 30/09 = $ 249.736,46 | ✅ |
| Producción (solo lectura), liquidación nov | fondo = caja al 31/10 = $ 249.736,46 (sin movimientos en oct) | ✅ |
| Base de prueba, liquidación nov | fondo = caja al 31/10 = −$ 1.677.797,98 | ✅ |
| Base de prueba, liquidación dic | fondo = caja al 30/11 = −$ 170.630,34 | ✅ |
| Extraordinario pendiente / con el fondo | expensas +100.000 / sin cambio; el fondo (caja) no cambia hasta que se paga | ✅ |
| Pantallas Gastos, Liquidación, plano, Configuración y PDF | cargan y muestran "= saldo de caja al …" | ✅ |

`pruebas/probar_fondo_saldo_inicial.py` se eliminó (la regla de saldo inicial dejó de existir); `probar_fondo_reserva.py` se adaptó.

---

## v7.3-0611 — PDF resumen sin "Fondo de Reserva disponible"

PDF de octubre armado con datos de producción (solo lectura): el cuadro "Base de la expensa" muestra gastos ordinarios $ 1.371.401,82 + aporte $ 80.000 = $ 1.451.401,82, sin la línea del fondo disponible ✅ (revisado a la vista).

---

## v7.2-0611 — PDF resumen (página 2) y GASTOS PAGADOS

**Producción, solo lectura** (Perú 376, liquidación de octubre armada con el código nuevo sin pasar por la app):

| Cuadro | Resultado |
|---|---|
| Gastos Ordinarios — Septiembre 2026 | 8 gastos, total $ 1.371.401,82, sin el Fondo de Reserva ✅ |
| Base de la expensa | $ 1.371.401,82 + aporte $ 80.000 = $ 1.451.401,82 (= expensas de octubre) ✅; fondo disponible $ 80.000 |
| Ingresos y egresos — Octubre 2026 | saldo al 30/09 $ 249.736,46 + 0 − 0 = saldo al 31/10 $ 249.736,46 ✅ |
| GASTOS PAGADOS (septiembre) | antes $ 0 (solo Caja) → $ 1.341.392,22 (7 facturas pagadas) ✅ |

**Base de prueba, por la app:**

| Caso | Resultado |
|---|---|
| PDF 2026-11 y 2026-12 | 200 ✅ |
| Ingresos y egresos nov: −1.677.797,98 + 1.783.511,98 − 276.344,34 | = −170.630,34, igual al saldo real de Caja ✅ |
| GASTOS PAGADOS liq 2026-11 / 2026-12 | = facturas pagadas en oct / nov ($ 2.129.184,44 / $ 321.344,34) ✅ |

> El gasto "Gastos generales de administración (sistema)" ($ 30.009,60, sep) no tiene factura: no entra en GASTOS PAGADOS.

---

## v7.1-0611 — Totales en el PDF resumen y en la pantalla Liquidación

Base de prueba, liquidación 2026-12:

| Verificación | Esperado (suma de filas) | Resultado |
|---|---|---|
| PDF resumen: total columna Deuda | $ 1.049.442,22 | ✅ (revisado a la vista; columnas sin superponerse) |
| Pantalla: total Interés | $ 52.472,11 | ✅ |
| Pantalla: total TOTAL | $ 2.418.266,67 | ✅ bajo su columna |
| Pantalla: total Saldo | $ 2.418.266,67 | ✅ bajo su columna |
| Pie alineado con los encabezados | — | ✅ revisado a la vista |

---

## v7.0-0611 — Saldo a favor

**Pedido:** si una UF paga de más, se salda el total y le queda saldo a favor el mes siguiente.

**Antes:** el formulario no dejaba pagar más que el saldo, y si llegaba un pago mayor el excedente se perdía.

Prueba (`pruebas/probar_saldo_a_favor.py`, base de prueba, meses 2026-11 → 2026-12; todo restaurado al final):

| # | Caso | Esperado | Resultado |
|---|---|---|---|
| 1 | Interés con deuda +10.000 y expensas 20.000 (vencido, 5 %) | 500 + 1.000 = $ 1.500 | ✅ |
| 1 | Con saldo a favor −5.000 y expensas 20.000 | mora solo sobre 15.000 = $ 750 | ✅ |
| 1 | Con saldo a favor −25.000 y expensas 20.000 | $ 0 | ✅ |
| 2 | UF 17 nov: total $ 43.866,68, paga $ 48.866,68 | TOTAL, saldo −5.000; Caja $ 48.866,68; aviso de saldo a favor | ✅ |
| 3 | UF 17 dic | deuda anterior −5.000; total = expensas 55.023,53 − 5.000 = $ 50.023,53 | ✅ |
| 4 | UF 18: a favor $ 44.044,72 vs expensas dic $ 43.044,72 | dic pagada sin abonar (total −1.000) y pasan −1.000 al mes siguiente | ✅ |
| 5 | Pantallas | "a favor" en dic, "a favor próx. mes" en nov, formulario sin máximo, recibo PDF 200 | ✅ |
| — | Restauración | Liquidaciones nov/dic y Caja iguales al inicio | ✅ |

Regresión: `probar_anular_pagos.py` y `probar_liquidacion_estados.py`.

---

## v6.6-0611 — Aporte al fondo cuenta cuando se cobra

**Caso:** Perú 376, saldo inicial del fondo $ 0 a sep-2026; el aporte de septiembre ($ 80.000) se cobra en la liquidación de octubre, pero el fondo seguía en $ 0.

Prueba (`pruebas/probar_fondo_saldo_inicial.py`, base de prueba, mes 2026-10: aporte $ 150.000 cobrado en nov, $ 11.000 pagados con el fondo):

| Saldo inicial | Esperado | Resultado |
|---|---|---|
| $ 0 al 2026-10 | 0 + 150.000 (el uso de oct ya está en el saldo inicial) = $ 150.000 | ✅ (antes: $ 0) |
| $ 80.000 al 2026-10 | 80.000 + 150.000 = $ 230.000 | ✅ (antes: $ 80.000) |
| $ 0 al 2026-09 | aporte sep 80.000 + aporte oct 150.000 − uso oct 11.000 = $ 219.000 | ✅ |

Regresión: `probar_fondo_reserva.py` con los mismos saldos que en v6.0.

---

## v6.5-0611 — Estado de la liquidación debajo del título

Se generó la pantalla de Liquidación en los tres estados (base de prueba; la cerrada se cerró solo para la prueba y se volvió a abrir) y se revisó a la vista:

| Estado | Palabra "Liquidación" | Aviso debajo del título | Resultado |
|---|---|---|---|
| Abierta (2026-12) | verde | "Liquidación ABIERTA" verde | ✅ |
| Cerrada (2026-12) | roja | "Liquidación CERRADA" rojo | ✅ |
| Sin generar (2027-02) | sin color | "Sin generar" gris | ✅ |

El aviso ya no aparece en la barra de botones.

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
| `probar_cobranzas.py` | Ciclo v9.0: cierre, cobro sobre la cerrada, deuda e interés, fecha del sistema, anulaciones, Caja, migración | Crea y borra un consorcio de prueba |
| `diagnostico_migracion_pagos.py` | Migración de pagos viejos a la tabla `pagos` (compara montos) | Migra los pagos del consorcio de prueba (una sola vez) |
| `probar_saldo_cierre.py` | Saldo de caja a la fecha de cierre (abierta / cerrada / reabierta) | Cambia y restaura estado y fecha |
| `probar_saldo_a_favor.py` | Pago de más, saldo a favor al mes siguiente, interés y mora con saldo a favor | Sí, y restaura liquidaciones y Caja |
| `probar_fondo_reserva.py` | Migración, saldo del fondo, extraordinarios pendiente / con el fondo, pantallas y PDF | Sí: aplica la migración (permanente); el gasto de prueba se borra y la config se restaura |

Cuando se agregue una prueba, sumar su sección arriba (la más nueva primero) y, si sirve repetirla, su script en `pruebas/`.
