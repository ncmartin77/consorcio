# Manual de Usuario — Sistema de Gestión de Consorcio

**Versión del sistema:** 5.0  
**Última actualización:** Noviembre 2026

---

## Índice

1. [Introducción](#1-introducción)
2. [Primeros pasos — Configuración inicial](#2-primeros-pasos--configuración-inicial)
3. [Flujo mensual — Qué hacer cada mes](#3-flujo-mensual--qué-hacer-cada-mes)
4. [Unidades Funcionales](#4-unidades-funcionales)
5. [Gastos Mensuales](#5-gastos-mensuales)
6. [Liquidaciones de Expensas](#6-liquidaciones-de-expensas)
7. [Caja Diaria](#7-caja-diaria)
8. [Facturas de Proveedores](#8-facturas-de-proveedores)
9. [Configuración del Sistema](#9-configuración-del-sistema)
10. [Preguntas Frecuentes](#10-preguntas-frecuentes)

---

## 1. Introducción

El **Sistema de Gestión de Consorcio** es una aplicación web diseñada para administradores de edificios. Centraliza todo lo que necesitás para gestionar un consorcio:

- **Liquidaciones mensuales de expensas** por unidad
- **Registro de gastos** fijos, variables y del fondo de reserva
- **Caja diaria** con saldo acumulado
- **Facturas de proveedores** con comprobantes adjuntos
- **Múltiples consorcios** desde una sola instalación

Accedés al sistema desde cualquier navegador (Chrome, Firefox, Edge) ingresando la dirección IP que te dio el administrador técnico. No requiere instalación en tu computadora.

### Conceptos clave antes de empezar

**Período de trabajo:** todo en el sistema gira alrededor de un "período" (mes y año). En la barra superior hay un selector de período. Cuando cambiás el período, cambia lo que se muestra en Gastos, Liquidación y Caja.

**Liquidación a mes vencido:** este es el concepto más importante del sistema.

> La liquidación de un mes usa los **gastos del mes anterior**.

Ejemplo concreto:
- Cargás los gastos de **septiembre** (sueldo del encargado, luz, limpieza)
- Esos gastos aparecen en la **liquidación de octubre**
- Las boletas de octubre reflejan lo que gastaron en septiembre

Esto significa que si cargás un gasto tarde, afecta la boleta del mes siguiente.

---

## 2. Primeros pasos — Configuración inicial

Antes de usar el sistema por primera vez, hay que configurarlo. Seguí este orden:

### 2.1 Configurar los datos del edificio

Ir a **Configuración** y completar:

| Campo | Descripción | Ejemplo |
|-------|-------------|---------|
| Nombre del edificio | Nombre que aparece en los recibos | "Edificio Brasil" |
| Dirección | Dirección del inmueble | "Brasil 1234, Santa Fe" |
| Tasa de mora | Porcentaje mensual de interés por mora | 7 |
| Día de vencimiento | Día del mes en que vencen las expensas | 15 |
| Monto Fondo de Reserva | Aporte mensual fijo al fondo | 5000.00 |
| URL de la aplicación | Dirección para verificar recibos vía QR | http://192.168.1.100:5000 |

Hacer clic en **Guardar configuración**.

### 2.2 Cargar las Unidades Funcionales

Ir a **Unidades** y agregar cada departamento/local del edificio. Para cada unidad necesitás:

- **Número / Identificador**: puede ser "1A", "PB", "Cochera 2", etc.
- **Propietario / Inquilino**: nombre del responsable
- **Porcentaje de expensas**: el porcentaje que le corresponde a esa unidad (todos deben sumar 100%)

### 2.3 Configurar los Saldos Iniciales (Apertura)

Ir a **Apertura / Saldos Iniciales**. Esta pantalla permite definir:

**Saldos por unidad:** lo que cada unidad debía (o tenía a favor) antes de empezar a usar el sistema.

- Número **negativo** = la unidad tenía **deuda** con el consorcio
- Número **positivo** = la unidad tenía un **saldo a favor**
- Cero = la unidad estaba al día

Ejemplo: si el depto 3B debía $12.000 antes de empezar, ingresá `-12000` en su saldo inicial.

**Saldo inicial de caja:** el dinero disponible en caja al momento de empezar, con su fecha de corte.

### 2.4 Configurar Gastos Recurrentes (opcional pero recomendado)

Ir a **Configuración → Gastos Recurrentes** y agregar los conceptos que se repiten todos los meses: "Sueldo Encargado", "Luz Común", "Gas", "Limpieza", etc.

Cuando después cargues una factura cuya descripción coincida con alguno de estos conceptos, el sistema va a registrar el gasto del mes automáticamente.

---

## 3. Flujo mensual — Qué hacer cada mes

Cada mes el proceso es el mismo. Acá lo tenés paso a paso:

```
INICIO DE MES
     │
     ▼
1. Seleccioná el período actual en el selector del navbar
     │
     ▼
2. Cargá los gastos del mes anterior
   (recordá: los gastos que cargás afectan la liquidación del mes siguiente)
     │
     ▼
3. Registrá las facturas de proveedores del mes
     │
     ▼
4. Generá la liquidación del mes actual
     │
     ▼
5. Registrá los pagos a medida que llegan
     │
     ▼
6. Al finalizar el mes: cerrá la liquidación
     │
     ▼
FIN DE MES → El mes siguiente empieza en el paso 1
```

### Paso 1: Seleccioná el período

En el selector del navbar (parte superior), elegí el **mes y año de la liquidación que querés generar**. Por ejemplo: si es noviembre y estás preparando las boletas de noviembre, seleccioná "Noviembre 2026".

### Paso 2: Cargá los gastos

Ir a **Gastos Mensuales**. Vas a ver que el sistema te muestra los gastos del **mes anterior** al período seleccionado (porque la liquidación de noviembre usa los gastos de octubre).

Cargá todos los gastos del mes anterior: servicios, sueldos, reparaciones, limpieza, etc.

### Paso 3: Registrá las facturas

Ir a **Facturas** y cargá las facturas de los proveedores. Si configuraste gastos recurrentes, muchos gastos se van a registrar automáticamente.

### Paso 4: Generá la liquidación

Ir a **Liquidación** y hacer clic en **Generar Liquidación**. El sistema calcula automáticamente lo que debe pagar cada unidad.

### Paso 5: Registrá los pagos

A medida que los propietarios o inquilinos van pagando, ingresá los pagos en la liquidación correspondiente a cada unidad.

### Paso 6: Cerrá la liquidación

Al final del mes, cuando ya registraste todos los pagos, hacé clic en **Cerrar Liquidación**. Una vez cerrada, no se puede modificar (a menos que la reabras manualmente).

> **Importante:** Para poder generar la liquidación de un mes, la liquidación del mes anterior debe estar **cerrada**. Esto garantiza que los datos históricos no cambien.

---

## 4. Unidades Funcionales

### 4.1 ¿Qué es una unidad funcional?

Es cada departamento, local, cochera o espacio del edificio que paga expensas. Cada unidad tiene:

- Un **identificador** único (ej: "1A", "PH", "Local 1", "Coch-3")
- El **nombre del propietario o inquilino**
- Su **porcentaje** de participación en los gastos del edificio

### 4.2 Cómo agregar una unidad

1. Ir a **Unidades**
2. Clic en **Nueva Unidad**
3. Completar los datos
4. Clic en **Guardar**

### 4.3 El porcentaje de expensas

Todos los porcentajes de las unidades deben sumar exactamente **100%**. El sistema te avisa si no cierran.

Ejemplo para un edificio de 4 departamentos:

| Unidad | Porcentaje |
|--------|-----------|
| 1A | 25% |
| 1B | 25% |
| 2A | 25% |
| 2B | 25% |
| **Total** | **100%** |

Los porcentajes no tienen por qué ser iguales. Un PH más grande puede tener 35% mientras un monoambiente tiene 15%.

### 4.4 Cómo afecta el porcentaje al cálculo

El sistema calcula la expensa de cada unidad así:

```
Expensa unidad = Total gastos del mes anterior × Porcentaje de la unidad / 100
```

Ejemplo concreto:
- Total gastos de septiembre: $80.000
- Unidad 2A tiene 25% de participación
- Expensa octubre de 2A = $80.000 × 25 / 100 = **$20.000**

> **Nota sobre el redondeo:** cuando los centavos no cierran exactamente por el redondeo, la última unidad de la lista absorbe la diferencia, garantizando que la suma de todas las expensas sea exactamente igual al total de gastos.

---

## 5. Gastos Mensuales

### 5.1 Tipos de gastos

El sistema maneja cuatro tipos:

| Tipo | Para qué se usa | ¿Afecta expensas? |
|------|-----------------|-------------------|
| **FIJO** | Gastos que se repiten cada mes (sueldo, seguro) | Sí |
| **VARIABLE** | Gastos esporádicos (reparación, compra) | Sí |
| **VARIABLE_FR** | Gastos pagados con el Fondo de Reserva | **No** |
| **FONDO_RESERVA** | El aporte mensual al fondo | Sí |

### 5.2 Cómo cargar un gasto

1. Ir a **Gastos Mensuales** con el período correcto seleccionado
2. Clic en **Agregar Gasto**
3. Elegir el tipo (FIJO o VARIABLE)
4. Ingresar concepto, monto y fecha
5. Guardar

> **Recordá siempre:** el período que ves en "Gastos Mensuales" es el mes **anterior** al período de liquidación. Si seleccionaste octubre en el navbar, los gastos que cargás son los que van a aparecer en la liquidación de **noviembre**.

### 5.3 El Fondo de Reserva

El sistema crea automáticamente, cada mes, un gasto de tipo FONDO_RESERVA con el monto configurado en Configuración.

Este gasto:
- Aparece en la pantalla de Gastos Mensuales
- **Sí** afecta el cálculo de las expensas (las unidades contribuyen a formarlo)
- El saldo acumulado del fondo se ve en la pantalla de Liquidación

No necesitás crearlo manualmente — el sistema lo inserta solo.

### 5.4 Gastos con Fondo de Reserva (VARIABLE_FR)

Cuando el edificio hace una reparación importante (ej: cambio de la bomba de agua por $30.000) y se decide pagarlo con el Fondo de Reserva:

1. Al agregar el gasto, marcá el checkbox **"Usar de Fondo de Reserva"**
2. El gasto se registra como VARIABLE_FR
3. Se muestra en una sección separada en la pantalla de Gastos
4. **No se suma** al total de gastos que pagan las unidades (porque ya se pagó con el fondo)
5. Podés adjuntarle la factura correspondiente

### 5.5 Gastos Recurrentes

Si configuraste gastos recurrentes (ej: "Luz Común"), el sistema los muestra en un panel especial con tres estados posibles:

- **Sin factura**: todavía no cargaste la factura de ese servicio
- **Factura registrada sin pagar**: ya cargaste la factura pero no la marcaste como pagada
- **Factura pagada**: todo en orden

Esto te ayuda a ver de un vistazo si te olvidaste de cargar algún servicio del mes.

---

## 6. Liquidaciones de Expensas

### 6.1 Cómo se calcula la expensa de cada unidad

La liquidación de cada unidad tiene estos componentes:

```
Total a pagar = Expensas + Deuda anterior + Interés + Extras
```

**Expensas:** parte proporcional del total de gastos del mes anterior, según el porcentaje de la unidad.

**Deuda anterior:** lo que la unidad adeudaba del mes anterior. Puede ser:
- Cero, si pagó completo el mes anterior
- El saldo pendiente, si pagó parcialmente
- El total anterior completo, si no pagó nada

**Interés por mora:** se calcula según el caso:
- *Interés sobre deuda antigua:* `Deuda anterior × Tasa de mora`
- *Mora corriente:* `Expensas × Tasa de mora` (solo si hoy pasó la fecha de vencimiento y la unidad no pagó)

**Extras:** cargos extraordinarios asignados específicamente a esa unidad para ese período.

### 6.2 Ejemplo completo de cálculo

Configuración del edificio:
- Tasa de mora: 7% mensual
- Día de vencimiento: 15

Situación de la unidad 1B en la liquidación de octubre:
- Total gastos septiembre: $80.000
- Porcentaje 1B: 25%
- La unidad 1B no pagó septiembre (debía $20.000)

Cálculo:
```
Expensas octubre = $80.000 × 25% = $20.000
Deuda anterior   = $20.000 (no pagó septiembre)
Interés sobre deuda anterior = $20.000 × 7% = $1.400
Mora corriente   = $20.000 × 7% = $1.400 (si hoy > día 15)

Total a pagar = $20.000 + $20.000 + $1.400 + $1.400 = $42.800
```

### 6.3 Eximir el interés a una unidad

Si por algún motivo acordás no cobrar intereses a una unidad específica:

1. En la liquidación, buscá la fila de esa unidad
2. Marcá el checkbox **"Sin interés"**
3. El sistema recalcula automáticamente sin aplicar mora a esa unidad
4. Este flag se preserva si volvés a generar la liquidación

### 6.4 Cómo generar la liquidación

1. Seleccioná el período en el navbar (ej: "Octubre 2026")
2. Ir a **Liquidación**
3. Clic en **Generar Liquidación**
4. El sistema procesa todos los datos y muestra la tabla con cada unidad

> **Requisito:** la liquidación del mes anterior debe estar CERRADA para poder generar la del mes actual.

### 6.5 Estados de una liquidación

**ABIERTA:**
- Podés editar, agregar pagos, recalcular
- Los movimientos de caja del período pueden modificarse
- Es el estado inicial al generar una liquidación

**CERRADA:**
- No se puede modificar nada
- No se pueden agregar movimientos de caja ni facturas del período
- Garantiza que los datos históricos queden intactos

Para cerrar: clic en **Cerrar Liquidación**.
Para reabrir (si necesitás corregir algo): clic en **Reabrir**.

### 6.6 Registrar el pago de una unidad

1. En la tabla de liquidación, hacer clic en el ícono de pago de la unidad correspondiente
2. Ingresar:
   - **Monto pagado**
   - **Fecha de pago**
   - **Tipo de pago** (efectivo, transferencia, etc.)
   - **Bonificación** (opcional, si decidís hacer un descuento)
3. Hacer clic en **Registrar Pago**

El pago se registra y también genera automáticamente un movimiento de **Entrada** en Caja Diaria.

### 6.7 Pago masivo — marcar todos como pagados

Si todos pagaron en el mismo día (ej: una reunión de consorcio donde cobraste todo junto):

1. Usar el botón **Pago Completo**
2. Ingresar la fecha de pago
3. El sistema marca como pagadas todas las unidades pendientes de ese período

### 6.8 Notas del período

Podés agregar notas o avisos que aparecen en el resumen PDF de la liquidación:

- **AVISO**: se muestra destacado (para informaciones importantes)
- **INFO**: información general del período

Útil para comunicar a los propietarios novedades del edificio (obras, reuniones, cortes de servicio, etc.).

### 6.9 Cargos extra por unidad

Si una unidad tiene un cargo extraordinario específico (ej: reparación de algo de uso exclusivo de ese departamento):

1. En la liquidación, usar el botón **Agregar Extra** en la fila de esa unidad
2. Ingresar descripción y monto
3. El sistema recalcula el total a pagar de esa unidad incluyendo el extra

### 6.10 Recibos y PDF

Para cada unidad que pagó, podés generar un **recibo PDF** individual. Los recibos incluyen:
- Datos del edificio y del período
- Detalle del cálculo (expensas, deuda anterior, interés, total)
- Datos del pago (monto, fecha, tipo)
- **Código QR** para verificar la autenticidad del recibo

El resumen completo de la liquidación (todas las unidades) también se puede exportar como PDF.

---

## 7. Caja Diaria

### 7.1 ¿Para qué sirve la Caja Diaria?

Registra todos los movimientos de dinero del consorcio:
- **ENTRADA**: dinero que entra (pagos de expensas, otros ingresos)
- **SALIDA**: dinero que sale (pago de facturas, gastos varios)

### 7.2 Cómo ver el saldo

La pantalla de Caja muestra cuatro indicadores:

| Indicador | Qué muestra |
|-----------|-------------|
| Saldo Anterior | El saldo al inicio del período actual |
| Entradas del Mes | Total de entradas del mes seleccionado |
| Salidas del Mes | Total de salidas del mes seleccionado |
| Saldo Acumulado | El saldo total desde el inicio (incluyendo el saldo inicial de apertura) |

El **Saldo Acumulado** es el saldo real de caja: suma todo desde el primer día, incluyendo el saldo inicial que configuraste en Apertura.

### 7.3 Cómo agregar un movimiento manual

1. Ir a **Caja**
2. Clic en **Nuevo Movimiento**
3. Elegir tipo (Entrada o Salida)
4. Ingresar descripción, monto y fecha
5. Guardar

### 7.4 Movimientos automáticos

Algunos movimientos se crean solos, sin que tengas que ingresarlos:

- **Al registrar el pago de una unidad:** se crea automáticamente una Entrada
- **Al marcar una factura como pagada:** se crea automáticamente una Salida
- **Si borrás una factura pagada:** también se borra su movimiento de caja automáticamente

### 7.5 Restricciones por período cerrado

Si la liquidación de un período está **CERRADA**, no podés:
- Agregar movimientos de caja de ese período
- Editar movimientos existentes de ese período
- Borrar movimientos de ese período

Esto protege la integridad del historial contable.

### 7.6 Saldo de caja en la liquidación

En la pantalla de Liquidación se muestra el saldo de caja al último día del período. Esto te permite ver cuánto dinero quedaba en caja al cierre del mes.

---

## 8. Facturas de Proveedores

### 8.1 Ciclo de vida de una factura

```
PENDIENTE → (marcás como pagada) → PAGADA
```

Una factura pasa por dos estados:
- **PENDIENTE**: ya la cargaste pero todavía no la pagaste
- **PAGADA**: ya fue abonada

### 8.2 Cómo cargar una factura

1. Ir a **Facturas**
2. Clic en **Nueva Factura**
3. Completar:
   - **Proveedor**: elegí de la lista o escribí uno nuevo
   - **Descripción**: qué servicio o producto es
   - **Importe**: monto de la factura
   - **Categoría**: para clasificar el gasto
   - **Fecha de emisión**
4. Clic en **Guardar**

### 8.3 Gastos automáticos al cargar facturas

Si la descripción de la factura coincide con algún **Gasto Recurrente** configurado, el sistema registra automáticamente el gasto del mes. No necesitás cargarlo por separado.

Ejemplo: si tenés configurado "Luz Común" como gasto recurrente y cargás una factura con descripción "Luz Común" (o "EDESF Luz Común", etc.), el gasto del mes se registra solo.

### 8.4 Cómo adjuntar el comprobante

Podés adjuntar la factura física digitalizada (PDF, foto):

1. En la lista de facturas, clic en el ícono de subir archivo de la factura
2. Seleccioná el archivo (PDF, JPG, PNG, etc.)
3. Si es una imagen, el sistema la convierte automáticamente a PDF
4. Para verla después, clic en el ícono azul de PDF

### 8.5 Cómo marcar una factura como pagada

1. En la lista, hacer clic en el ícono de "Pagar" de la factura
2. Ingresar la fecha de pago
3. Confirmar

Al pagar una factura, el sistema **automáticamente** crea un movimiento de **Salida** en Caja Diaria por el mismo importe.

### 8.6 Relación con Caja Diaria

| Acción | Efecto en Caja |
|--------|---------------|
| Marcar factura como PAGADA | Crea Salida automática |
| Borrar factura PAGADA | Borra también su movimiento de Caja |
| Borrar movimiento de Caja que viene de factura | Borra también la factura pagada |

Esta sincronización garantiza que Caja y Facturas siempre estén alineadas.

### 8.7 Filtros y búsqueda

En la lista de facturas podés:
- Filtrar por **mes de pago**
- Filtrar por **estado** (PENDIENTE / PAGADA)
- Navegar por páginas si hay muchas facturas

---

## 9. Configuración del Sistema

### 9.1 Datos del edificio

- **Nombre del edificio:** aparece en todos los PDF y recibos
- **Dirección:** se incluye en los documentos
- **URL de la aplicación:** se usa para generar los códigos QR de verificación. Debe ser la dirección IP real del servidor en tu red (ej: `http://192.168.1.100:5000`)

### 9.2 Parámetros financieros

**Tasa de mora:** porcentaje mensual que se aplica como interés por pago tardío. Se ingresa como número entero o decimal (ej: `7` para 7% mensual, `3.5` para 3,5%).

**Día de vencimiento:** día del mes en que vencen las expensas. Por ejemplo, `15` significa que el día 15 de cada mes vencen las boletas. Si un propietario paga el día 16 o después sin haber pagado antes, se aplica la mora corriente.

**Monto Fondo de Reserva:** cuánto aporta cada mes el edificio al fondo de reserva. Se distribuye entre todas las unidades según su porcentaje. El sistema crea automáticamente este gasto cada mes.

### 9.3 Gastos Recurrentes

Conceptos que se repiten cada mes. Configurarlos tiene dos ventajas:
1. El sistema te muestra un panel de estado para saber si los cargaste o no
2. Al cargar una factura con descripción coincidente, el gasto se registra automáticamente

Para agregar uno: Configuración → sección Gastos Recurrentes → ingresar nombre y categoría.

### 9.4 Proveedores

El directorio de proveedores te permite:
- Tener una lista de tus proveedores habituales
- Asociar cada proveedor a un gasto recurrente (para que al seleccionar el proveedor en una factura, se complete automáticamente la categoría)

### 9.5 Checkpoint (respaldo temporal)

El sistema permite crear un "punto de restauración" antes de hacer cambios importantes:

1. Ir a Configuración → sección Checkpoint
2. Clic en **Crear Checkpoint**
3. Optionalmente agregar una descripción
4. El sistema guarda una copia del estado actual

Si algo sale mal, podés hacer **Rollback** para volver al estado del checkpoint.

Los checkpoints expiran automáticamente a los **30 días**.

### 9.6 Múltiples consorcios

Si administrás más de un edificio, el sistema permite tener varios consorcios:

1. En el menú ir a **Consorcios**
2. Clic en **Nuevo Consorcio**
3. Cada consorcio tiene sus propios datos, unidades, gastos y caja completamente separados
4. Para cambiar de consorcio, clic en su nombre en la lista

El período seleccionado en el navbar aplica al consorcio activo.

### 9.7 Log de movimientos (auditoría)

El sistema registra automáticamente todos los cambios realizados (quién hizo qué y cuándo). Los administradores pueden:
- Ver el historial completo de cambios
- Revertir operaciones individuales si se cometió un error

Disponible en Configuración → sección Log de Movimientos.

---

## 10. Preguntas Frecuentes

### ¿Por qué la liquidación de octubre muestra gastos de septiembre?

Porque el sistema usa **liquidación a mes vencido**: la boleta de octubre refleja lo que se gastó en septiembre. Es la forma estándar de administración de consorcios en Argentina, donde las expensas se calculan sobre gastos ya conocidos y verificados.

---

### Cargué un gasto en el mes equivocado. ¿Qué hago?

1. Ir a **Gastos Mensuales** y seleccioná el período donde lo cargaste
2. Eliminá el gasto incorrecto
3. Cambiá al período correcto
4. Cargalo nuevamente

Si la liquidación del mes siguiente ya está cerrada, necesitás reabrirla para que el cambio tenga efecto.

---

### Una unidad quiere pagar en cuotas o hizo un pago parcial. ¿Cómo lo registro?

Al registrar el pago, ingresá el **monto real que pagó**. El sistema calcula automáticamente el saldo pendiente:

```
Saldo pendiente = Total a pagar - Monto pagado
```

El mes siguiente, ese saldo pendiente aparece como "Deuda anterior" en la liquidación de esa unidad.

---

### ¿Cómo eximo a una unidad de pagar intereses?

En la pantalla de Liquidación, buscá la fila de esa unidad y marcá el checkbox **"Sin interés"**. El sistema recalcula el total sin aplicar mora, y guarda ese flag para que no se pierda al recalcular.

---

### La suma de los porcentajes no da 100%. ¿Qué pasa?

El sistema te va a avisar con un error o advertencia. Revisá los porcentajes de todas las unidades y ajustalos para que sumen exactamente 100%. Podés usar decimales (ej: 33.33%) si el edificio tiene unidades de igual tamaño.

---

### Cerré una liquidación por error. ¿Puedo reabrirla?

Sí. En la pantalla de Liquidación, con el período correspondiente seleccionado, hacé clic en el botón **"Reabrir"**. Esto cambia el estado a ABIERTA y podés volver a editarla.

---

### ¿Cómo sé si una unidad tiene mora corriente?

La mora corriente se aplica automáticamente cuando:
1. Hoy es mayor que el día de vencimiento configurado (ej: día 15)
2. La unidad no tiene pago registrado para ese período

Si hoy es 20 de octubre y el vencimiento es el 15, todas las unidades sin pago van a tener mora corriente en la liquidación.

---

### ¿Qué pasa si el primer mes la unidad ya tenía deuda?

Eso se configura en **Apertura / Saldos Iniciales**. Ingresás el saldo de cada unidad con signo negativo para las deudas. El sistema lo toma como "deuda anterior" en la primera liquidación.

Ejemplo: la unidad 4A tenía $15.000 de deuda antes de empezar a usar el sistema. Ingresás `-15000` como saldo inicial. En la primera liquidación, ese monto aparece como "Deuda anterior".

---

### ¿Cómo verifico si un recibo es auténtico?

Cada recibo PDF tiene un código QR al pie. Escaneándolo con el celular, vas a una página que confirma si el recibo es genuino (emitido por el sistema) o si fue alterado.

También podés ir manualmente a la dirección del sistema y agregar `/verificar` al final para ingresar el código manualmente.

---

### El proveedor me mandó la factura tarde y ya cerré la liquidación. ¿Qué hago?

Tenés dos opciones:

**Opción A:** Registrá la factura en el mes actual (no en el cerrado) y cargá el gasto manualmente en el mes correcto:
1. Reabrir la liquidación del mes cerrado
2. Agregar el gasto
3. Recalcular la liquidación
4. Cerrarla nuevamente

**Opción B:** Si el impacto es menor, podés simplemente registrar la factura en el mes actual sin modificar el pasado. El gasto afectará la liquidación del mes siguiente.

---

### ¿Puedo hacer un backup de los datos?

Sí. En la barra de navegación hay un botón de **Backup** (ícono de descarga). Descarga un archivo ZIP con todos los datos del consorcio activo, incluyendo los comprobantes adjuntos de facturas. Guardá este archivo en un lugar seguro periódicamente.

---

### ¿Cómo funciona el Fondo de Reserva?

El Fondo de Reserva es dinero que el consorcio ahorra mensualmente para gastos extraordinarios (ej: refacción del ascensor, impermeabilización de la terraza).

- Cada mes el sistema agrega automáticamente un gasto de tipo FONDO_RESERVA con el monto configurado
- Ese monto se distribuye entre todas las unidades según su porcentaje (igual que cualquier gasto)
- Cuando usás el fondo para pagar algo, registrás ese gasto como VARIABLE_FR
- Los gastos VARIABLE_FR no se suman al cálculo de expensas (ya los pagó el fondo)

El saldo del fondo se muestra en la pantalla de Liquidación.

---

### ¿Puedo agregar una nota o comunicado en la liquidación?

Sí. En la pantalla de Liquidación hay una sección para agregar **Notas del Período**. Estas notas aparecen en el PDF resumen que se puede entregar a los propietarios. Usá tipo AVISO para información urgente e INFO para comunicaciones generales.

---

*Para soporte técnico o consultas sobre el sistema, contactar al administrador técnico.*
