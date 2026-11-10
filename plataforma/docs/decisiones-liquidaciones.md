# Decisiones para la etapa 3 (liquidaciones)

> **Referencia vigente: la v10.1 del sistema actual** (rama `feat/lineamientos-v10`,
> 09/11/2026, todavía sin merge a `master`). Ver "Revisión del 10/11" al final.

Tomadas el 06/11/2026, partiendo de cómo liquida hoy el sistema actual (`pg_db.py`,
`generar_liquidacion`) y de los datos de la copia del 03/11. Cambiarlas cambia los números:
cualquier cambio posterior va con fecha y motivo en este archivo.

## Decididas por el usuario

| # | Tema | Decisión | Sistema actual |
|---|---|---|---|
| 1 | Interés por deuda | **Simple**: la tasa mensual se aplica solo sobre el **capital** adeudado (expensas y cargos impagos), nunca sobre intereses anteriores. | Compuesto: la tasa se aplica sobre toda la deuda anterior, intereses incluidos. |
| 2 | Mora del mes corriente | ~~Como hoy~~ → **Revisada el 10/11: sin mora del mes**, como el sistema actual desde la v9.0. Ver "Revisión del 10/11". | Ya no existe desde la v9.0. |
| 3 | Imputación de pagos | **Primero intereses, después capital más antiguo** (Código Civil y Comercial, art. 903). | El pago se resta del total, sin distinguir conceptos ni períodos. |
| 4 | Pago de más | **Saldo a favor**: queda como crédito de la unidad y se descuenta en la próxima liquidación. | El excedente se pierde: el saldo queda en 0. |

## Propuestas aceptadas (sin objeción)

| # | Tema | Decisión |
|---|---|---|
| 5 | Período | **Mes vencido**: la liquidación del período P reparte los gastos de P−1, como hoy. |
| 6 | Prorrateo | Cada gasto pertenece a un **grupo de prorrateo** (GENERAL por defecto) y se reparte con los coeficientes vigentes de ese grupo al cierre del período de gastos. Se abandona el promedio de porcentajes. |
| 7 | Redondeo | Importes en centavos exactos (`NUMERIC`, `decimal`), redondeo half-up a 2 decimales. La diferencia de centavos se reparte por **mayor resto** (desempate: código de unidad), así la suma por unidad da exactamente el total. Hoy la absorbe siempre la última unidad. |
| 8 | Tasa y vencimiento | Tasa de mora mensual y día de vencimiento **por consorcio y con vigencia**. Hoy: Perú 376 al 5 %, Brasil al 7 %, vencimiento el último día del mes (`dia_vencimiento = 0`). |
| 9 | Deuda inicial | La deuda que se trae al migrar no genera interés el primer mes, como hoy. |
| 10 | Exención de interés | El tilde "sin interés" pasa a ser una **condonación** auditada, con motivo y usuario. |
| 11 | Bonificaciones | Pasan a ser un **ajuste a favor** en la cuenta corriente de la unidad, auditado, y no solo una salida de caja. |
| 12 | Cargos particulares | Se mantienen: cargos a una unidad en un período (hoy `gastos_extra`). |
| 13 | Fondo de reserva | Cargo mensual fijo por consorcio, prorrateado como un gasto (como hoy). Los gastos pagados con el fondo no se prorratean. La cuenta separada del fondo llega con la contabilidad. |
| 14 | Estados | `borrador → calculada → aprobada → emitida`. Emitida es inmutable; las correcciones van por ajuste o rectificación. |
| 15 | Saldos | La cuenta corriente por movimientos es la fuente de verdad; ningún campo de saldo es editable. |
| 16 | Alcance | Argentina. Sin facturación electrónica en el MVP: la liquidación de expensas no es factura. |
| 17 | Pagos | Carga manual con referencia única por consorcio, para no duplicar. La integración bancaria queda para después del MVP. |
| 18 | Para después del MVP | Traspaso de consorcios entre administraciones y portal de propietarios. |

## Consecuencia para la comparación con el sistema actual

La prueba clave de B3 (liquidar los mismos períodos que el sistema actual y comparar)
**no va a dar igual** donde haya deuda que arrastra intereses (decisión 1), pagos de más
(decisión 4) o redondeo (decisión 7). Cada diferencia tiene que poder explicarse con
una de estas decisiones. Si alguna no se explica, es un error.

---

## Revisión del 10/11/2026: alineación con la v10.1

Entre el 06 y el 09/11 el sistema actual pasó de la 5.5 a la 10.1 (v9.7 en `master`; la
v10.1 en la rama `feat/lineamientos-v10`). El usuario indicó **tomar la última versión
disponible como referencia**. Comparación:

| Tema | Plataforma (decisión) | v10.1 | ¿Coinciden? |
|---|---|---|---|
| Interés | Simple, sobre el capital | "Interés sin capitalizar" (CCyC 770): tasa × (deuda anterior − intereses impagos). Tiene un switch "Capitalizar", apagado por defecto. | Sí. La plataforma no tiene ese switch. **Confirmado por el usuario el 10/11.** |
| Base del interés | Capital impago **a la fecha de cierre** | Deuda anterior a la fecha del sistema al cerrar, menos intereses impagos | Sí (se precisó la regla) |
| Mora del mes | **Sin mora del mes** (revisada) | No existe desde la v9.0 | Sí. **Decidido por el usuario el 10/11**: seguir la última versión. |
| Cuándo se decide el interés | Al cerrar/emitir, con condonación auditada por unidad | Al cerrar, con un switch por unidad (activado por defecto) | Sí |
| Imputación | Intereses primero, después lo más viejo | Pagos imputados primero a intereses | Sí |
| Saldo a favor | Sí | Sí (v7.0) | Sí |
| Tasa | Por consorcio, con vigencia | Tabla `tasas_mora` con vigencia y **fundamento**. Se usa la vigente el día 1 del mes de la liquidación, queda congelada al cerrar, y no se cargan ni se borran tasas con vigencia en un período cerrado. | Se adopta igual, con fundamento |
| Reabrir una liquidación cerrada | Antes: emitida = inmutable | Solo administradores, sin pagos y con la siguiente sin cerrar | **Revisada: se permite reabrir** en esas condiciones, auditado y conservando el snapshot anterior. **Decidido por el usuario el 10/11.** |
| Clasificación de gastos | Grupo de prorrateo | Naturaleza (ordinaria o extraordinaria), habitualidad (recurrente o no), financiación (expensas o fondo) y respaldo (acta o autorización); CCyC 2048 | Se adopta. Los extraordinarios a cobrar van en una **línea aparte**; los pagados con el fondo **no se cobran**. |
| Fondo de reserva | Aporte mensual prorrateado | Igual. El saldo sale del "libro del fondo": inicial + aportes cobrados + otros ingresos − pagos con el fondo. | Se adopta para la contabilidad del fondo |
| Prorrateo y redondeo | Por grupo, mayor resto | Promedia porcentajes y la última unidad absorbe la diferencia | **No.** Se mantiene la decisión de la plataforma: las diferencias son esperadas. |
| Mes vencido | Sí | Sí | Sí |

**Cambios en el motor (`internal/expensas`) por esta revisión:**
- Se quitó la mora del mes, con sus campos `Vencimiento` y `PagosPeriodo`.
- Se agregaron los gastos extraordinarios en una línea aparte (`Extraordinaria`).
- El interés se documentó como "capital impago a la fecha de cierre".
