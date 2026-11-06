# Decisiones para la etapa 3 (liquidaciones)

Tomadas el 06/11/2026, partiendo de cómo liquida hoy el sistema actual (`pg_db.py`,
`generar_liquidacion`) y de los datos de la copia del 03/11. Cambiarlas cambia los números:
cualquier cambio posterior va con fecha y motivo en este archivo.

## Decididas por el usuario

| # | Tema | Decisión | Sistema actual |
|---|---|---|---|
| 1 | Interés por deuda | **Simple**: la tasa mensual se aplica solo sobre el **capital** adeudado (expensas y cargos impagos), nunca sobre intereses anteriores. | Compuesto: la tasa se aplica sobre toda la deuda anterior, intereses incluidos. |
| 2 | Mora del mes corriente | **Como hoy**: si a la fecha de cálculo ya pasó el vencimiento y la unidad no pagó nada del período, se suma tasa × expensas del mes en la misma liquidación. **La fecha de cálculo queda guardada en la liquidación**: recalcular da los mismos números. | Igual, pero usa "hoy": regenerar otro día cambia el resultado. |
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
