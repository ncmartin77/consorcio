# Manual de Usuario — Sistema de Gestión de Consorcio

**Versión del sistema:** 10.0
**Última actualización:** 9 de noviembre de 2026

> Este manual también se ve dentro del sistema: menú **Más → Ayuda y manual**.
> En cualquier pantalla, con **Shift + mouse** sobre el menú o un botón aparece una explicación corta.

---

## Índice

1. [Introducción y conceptos clave](#1-introducción-y-conceptos-clave)
2. [Ingreso al sistema](#2-ingreso-al-sistema)
3. [Configuración inicial (una sola vez)](#3-configuración-inicial-una-sola-vez)
4. [El mes de trabajo, paso a paso](#4-el-mes-de-trabajo-paso-a-paso)
5. [Gastos Mensuales](#5-gastos-mensuales)
6. [Facturas, Proveedores y Presupuestos](#6-facturas-proveedores-y-presupuestos)
7. [Liquidación](#7-liquidación)
8. [Intereses por mora](#8-intereses-por-mora)
9. [Cobranzas](#9-cobranzas)
10. [Caja Diaria](#10-caja-diaria)
11. [Fondo de Reserva](#11-fondo-de-reserva)
12. [Edificio: Unidades, Plano, Estado de cuenta, Apertura](#12-edificio-unidades-plano-estado-de-cuenta-apertura)
13. [Vencimientos y alertas](#13-vencimientos-y-alertas)
14. [Notificaciones, recibos y libre deuda](#14-notificaciones-recibos-y-libre-deuda)
15. [Configuración](#15-configuración)
16. [Herramientas del administrador](#16-herramientas-del-administrador)
17. [Preguntas frecuentes](#17-preguntas-frecuentes)

---

## 1. Introducción y conceptos clave

El sistema administra uno o varios consorcios desde el navegador: gastos, facturas, liquidación de
expensas, cobranzas, caja, fondo de reserva, vencimientos legales y documentos (PDF, recibos con QR,
certificados de libre deuda).

**Liquidación a mes vencido.** Es la regla más importante:

> La liquidación de un mes cobra los **gastos del mes anterior**.

Los gastos de **septiembre** se cobran en la liquidación de **octubre**. Si cargás un gasto de septiembre,
cambia la liquidación de octubre (mientras esté abierta).

**Período de trabajo.** Arriba, en la barra, está el período (mes) con el que estás trabajando. Gastos
muestra el mes anterior a ese período; Liquidación y Caja, el período mismo.

**Fecha del sistema.** En Configuración se puede fijar una fecha para trabajar "como si hoy fuera" ese día
(para preparar o revisar un mes). Si está fijada, aparece un aviso amarillo arriba. Mientras esté fijada,
los pagos posteriores a esa fecha no se cuentan.

**Abierta y cerrada.** Una liquidación **abierta** se recalcula sola cuando cambian los gastos. Una vez
**cerrada** queda fija: es la que se cobra y ya no se modifica.

---

## 2. Ingreso al sistema

1. Entrá a la dirección del sistema y tocá **Ingresar con Google**.
2. La primera vez, tu cuenta queda **pendiente de aprobación**: un administrador la tiene que habilitar en
   **Administración de usuarios** y darte acceso a los consorcios que corresponda.
3. Elegí el consorcio de la lista. Para cambiar de consorcio, tocá su nombre en la barra.

---

## 3. Configuración inicial (una sola vez)

Seguí este orden:

| Paso | Dónde | Qué cargar |
|---|---|---|
| 1 | Configuración → Datos del Edificio | Nombre, dirección, alias/CBU, administrador, contacto, día de vencimiento, aporte mensual al Fondo de Reserva |
| 2 | Configuración → Intereses por mora | La tasa mensual **con su fecha de vigencia y fundamento** (reglamento o acta) |
| 3 | Configuración → Administración | CUIT, mandato (desde/hasta e instrumento), registro de administradores (Ord. 9.131), cierre del ejercicio, si hay ascensor |
| 4 | Configuración → Categorías de porcentaje | Por ejemplo `EXPENSAS` (o `GENERAL`, `ASCENSOR`…) |
| 5 | Edificio → Unidades | Cada unidad: número, propietario, inquilino, contactos y su porcentaje |
| 6 | Edificio → Apertura | Saldo inicial de caja, **saldo inicial del Fondo de Reserva** y deuda inicial de cada unidad |
| 7 | Configuración → Gastos recurrentes | Conceptos de todos los meses: "Luz común", "Limpieza", "Ascensor"… |

**Deuda inicial (Apertura):** número **positivo = deuda**, **negativo = saldo a favor**, cero = al día.
Ejemplo: si la UF 4 debía $15.000 al empezar, cargá `15000`.

Los porcentajes de todas las unidades deben sumar 100 %. Si los centavos no cierran por redondeo, la
última unidad absorbe la diferencia, así la suma de expensas da exactamente el total de gastos.

---

## 4. El mes de trabajo, paso a paso

1. **Gastos:** cargá los gastos del mes que terminó (o dejá que se carguen solos desde las facturas de
   gastos recurrentes).
2. **Liquidación:** tocá **Generar**. Mientras está abierta, cada gasto nuevo la recalcula.
3. **Cerrar:** cuando cambió el mes (desde el día 1 del mes de la liquidación) tocá **Cerrar**. Aparece
   la ventana de intereses (ver sección 8). Desde ese momento la liquidación queda fija.
4. **Cobrar:** en **Cobranzas** registrás los pagos contra la última liquidación cerrada.

> Para generar la liquidación de un mes, la del mes anterior tiene que estar **cerrada**.

---

## 5. Gastos Mensuales

### 5.1 Cómo cargar un gasto

**Gastos → Agregar gasto**:

| Campo | Opciones | Para qué |
|---|---|---|
| Concepto e importe | — | Qué se pagó y cuánto |
| **Naturaleza** | Ordinaria / Extraordinaria | La clasificación jurídica (CCyC art. 2048) |
| **Frecuencia** | Recurrente / No recurrente | Si se repite todos los meses |
| **¿Con qué se paga?** | Se cobra en las expensas / Con el Fondo de Reserva | Cómo se financia |
| **Respaldo** (opcional) | Texto libre | Acta de asamblea, autorización del consejo, etc. |

Estos tres datos son **independientes**:

- Una reparación necesaria de bienes comunes puede ser **ordinaria** aunque sea cara o no se repita.
- Un gasto **extraordinario** que se cobra en las expensas sale en una línea aparte en la liquidación y en el PDF.
- Un gasto **pagado con el Fondo de Reserva** no se cobra en las expensas: sale del fondo. Conserva su
  naturaleza (ordinaria o extraordinaria).

En la tarjeta de gastos extraordinarios y pagados con el fondo, el botón **Usar fondo / Cobrar** cambia cómo
se paga un gasto sin cargarlo de nuevo.

### 5.2 El aporte al Fondo de Reserva

Cada mes el sistema agrega solo el gasto **"Fondo de Reserva"** con el aporte configurado. Se reparte entre
las unidades como cualquier gasto. Solo se puede cambiar su importe.

### 5.3 Gastos recurrentes y tareas

- El panel **Gastos recurrentes del mes** muestra cada concepto como *sin factura*, *factura registrada sin
  pagar* o *factura pagada*: sirve para ver si falta cargar algún servicio.
- Si un gasto no tiene factura, el botón de recibo permite **emitir la factura de ese gasto**.
- **Tareas pendientes:** una lista de recordatorios que se tildan al terminar (tiene "Deshacer").

### 5.4 Gastos de un período cerrado

Si la liquidación que cobra esos gastos ya está **cerrada**, no se pueden cargar, modificar ni borrar.
Un gasto que llega tarde se carga en el mes actual (se cobrará en la liquidación siguiente).

---

## 6. Facturas, Proveedores y Presupuestos

### 6.1 Facturas

Una factura está **Pendiente** o **Pagada**.

- **Cargar:** proveedor, descripción, importe, fecha, número, categoría. Si la descripción coincide con un
  gasto recurrente, el gasto del mes se crea solo (no hace falta cargarlo aparte).
- **Comprobante:** el botón de subir adjunta el PDF o una foto (se convierte a PDF). El botón azul lo abre.
- **Pagar:** fecha de pago (no anterior a la fecha de la factura), **observación** opcional y el switch
  **Pagar con Fondo de Reserva**:
  - **Sin el switch:** se registra la salida en Caja y el gasto se cobra en las expensas.
  - **Con el switch:** la salida va contra el fondo y el gasto **no** se cobra en las expensas. El modal muestra cuánto hay disponible en el fondo.
- Una factura **pagada** no se puede editar. Si la borrás, también se borra su movimiento de Caja; el gasto
  queda sin vínculo y se puede volver a emitir su factura desde Gastos.
- Una factura pendiente marcada para el fondo figura como **compromiso** en el libro del Fondo de Reserva.

### 6.2 Proveedores

Directorio con CUIT, contacto y categoría. Si asociás un proveedor a un gasto recurrente, al elegirlo en una
factura se completa el concepto.

### 6.3 Presupuestos

**Pedidos de presupuesto:** describís el trabajo, cargás las cotizaciones de cada proveedor y marcás la elegida.

---

## 7. Liquidación

### 7.1 Qué tiene cada unidad

```
Total a pagar = Expensas + Deuda anterior + Interés + Extras
```

- **Expensas:** total de gastos del mes anterior (sin los pagados con el fondo) × porcentaje de la unidad.
- **Deuda anterior:** total de la liquidación anterior − lo que pagó hasta hoy. Si es negativa, es **saldo a favor**.
- **Interés:** se decide al cerrar (sección 8). Mientras está abierta es 0.
- **Extras:** cargos de una sola unidad (por ejemplo, una reparación de su uso exclusivo).

### 7.2 Notas y extras

- **Notas del período:** AVISO (destacado) o INFO. Salen en el PDF.
- **Gastos extra por unidad:** descripción y monto. Se suman al total de esa unidad.

Las dos cosas se pueden cargar solo mientras la liquidación está abierta.

### 7.3 Cerrar y reabrir

- **Cerrar:** se puede desde el día 1 del mes de la liquidación y con la anterior ya cerrada. Al cerrar se
  recalcula a la fecha del sistema, se aplican los intereses elegidos y **se guarda la tasa usada**.
- Al cerrarla se bloquea la **Caja del mes anterior** (el de los gastos).
- **Reabrir:** solo un administrador, sin pagos registrados y con la liquidación siguiente abierta.

### 7.4 PDF de la liquidación

**Descargar PDF** genera la planilla horizontal del edificio con:
- **Tabla por unidad:** liquidado y pago del mes anterior, deuda, interés, expensas, total, pagado y MONTO A PAGAR.
- **Totales:** gastos, a cobrar, cobrado y pendiente, debajo de la tabla de unidades.
- **Gastos:** ordinarios (con su frecuencia) y extraordinarios (con su respaldo), y la base de la expensa.
- **Ingresos y egresos de Caja del mes.**
- **Cuadro del Fondo de Reserva:** saldo efectivo, aporte del mes, aportes pendientes de cobro y compromisos.
- **Notas, extras y datos de la administración**, con el CUIT y el registro de administradores si está inscripto.

---

## 8. Intereses por mora

**Regla (v10.0):** el interés se calcula sobre el **capital adeudado**, es decir, las expensas impagas.
Nunca se calcula sobre intereses anteriores (no hay "interés sobre interés"). Cuando una unidad paga, el pago se
aplica **primero a los intereses** y después a lo más antiguo (Código Civil y Comercial, arts. 770 y 903).

**Ejemplo:** expensa de $100.000 por mes, 3 % mensual, la unidad no paga octubre, noviembre ni diciembre.

| Liquidación | Deuda anterior | de la cual intereses | Capital | Interés 3 % | Total |
|---|---:|---:|---:|---:|---:|
| Octubre | 0 | 0 | 0 | 0 | 100.000 |
| Noviembre | 100.000 | 0 | 100.000 | 3.000 | 203.000 |
| Diciembre | 203.000 | 3.000 | 200.000 | 6.000 | 309.000 |
| Enero | 309.000 | 9.000 | 300.000 | 9.000 | 418.000 |

Si en diciembre la unidad paga $150.000, primero se cancelan los $9.000 de intereses y el resto baja la deuda.

**Al cerrar** aparece una ventana con cada unidad que tiene deuda: deuda anterior, cuánto de eso son
intereses, capital e interés propuesto. Cada unidad tiene un switch para cobrarle o no el interés
(encendido por defecto). El saldo a favor nunca genera interés.

**La tasa** se carga en **Configuración → Intereses por mora** con fecha de vigencia y fundamento.
- Cada liquidación usa la tasa vigente el día 1 de su mes.
- Al cerrar, la tasa queda guardada en esa liquidación. No se puede cargar ni borrar una tasa con vigencia en un período ya cerrado.

**Capitalizar intereses:** en la misma tarjeta hay un switch, **apagado por defecto**. Encenderlo solo con
respaldo jurídico: la ley admite la capitalización en casos puntuales.

---

## 9. Cobranzas

- Se cobra **solo la última liquidación cerrada**.
- **Registrar pago:**
  - **Datos:** monto, fecha y, opcionalmente, una **bonificación** con su motivo.
  - **Fecha:** no puede ser posterior a la fecha del sistema ni caer en un mes de Caja cerrado.
  - **Efecto:** el pago crea su entrada en Caja. La bonificación crea una salida en Caja y no cambia lo que la unidad debe.
- **Estados:**
  - **Pendiente:** no pagó nada.
  - **Parcial:** el saldo pasa como deuda anterior al mes siguiente.
  - **Total:** si pagó de más, el sobrante queda como saldo a favor.
- **Pago Completo:** registra el pago total de todas las unidades con deuda, con una misma fecha.
- **Recibo:** PDF con código QR de verificación. Se puede enviar por WhatsApp.
- **Anular pagos:** solo un administrador. Borra también sus movimientos de Caja.

---

## 10. Caja Diaria

- **Movimientos:** Entrada o Salida, con categoría. Los pagos de expensas y de facturas generan sus movimientos solos.
- **Saldos:** cuatro cuadros, saldo anterior, entradas y salidas del mes y saldo acumulado (incluye el saldo
  inicial de Apertura).
- **Fechas:** se muestran como DD/MM/AAAA.
- **Mes bloqueado:** la Caja de un mes se bloquea cuando se cierra la liquidación del mes siguiente. Desde
  ahí no se agregan, editan ni borran movimientos de ese mes.
- **Movimientos del fondo:** un movimiento con categoría **FONDO_RESERVA** cuenta en el libro del fondo. Si es una entrada, es otro ingreso al fondo; si es una salida, es un pago con el fondo.

---

## 11. Fondo de Reserva

**Más → Fondo de Reserva** muestra el libro del fondo:

```
Saldo efectivo = saldo inicial
               + aportes efectivamente COBRADOS
               + otros ingresos al fondo
               − pagos hechos con el fondo
```

| Cuadro | Qué es |
|---|---|
| Saldo efectivo | Dinero realmente integrado al fondo |
| Aportes pendientes de cobro | Aportes liquidados que las unidades todavía no pagaron. **No** son dinero disponible |
| Compromisos sin pagar | Facturas a pagar con el fondo que siguen pendientes |
| Disponible neto | Saldo efectivo − compromisos |

- **Saldo inicial:** se carga en **Apertura** con su fecha (por ejemplo, el de la última rendición o acta).
  Mientras no se cargue, el sistema usa provisoriamente el saldo inicial de caja y lo avisa.
- **Aporte cobrado:** de cada pago se toma primero lo que va a intereses y deuda vieja. De lo que cubre las
  expensas de un mes, la parte del aporte es proporcional. Ejemplo: si el aporte es el 10 % de lo repartido,
  el 10 % de lo cobrado de ese mes va al fondo.
- **Pagos con el fondo:** un gasto pagado con el fondo no se vuelve a cobrar en las expensas. Si después se decide
  reponer el fondo, eso necesita su propio cargo.

---

## 12. Edificio: Unidades, Plano, Estado de cuenta, Apertura

- **Unidades:** datos de cada UF, propietario e inquilino con mail y celular, por dónde se le envían los avisos,
  porcentaje por categoría, si está activa y su deuda inicial. Desde acá se emite el **libre deuda**.
- **Plano:** vista del edificio con el estado de cada unidad (al día, con deuda, sin liquidar).
- **Estado de cuenta:** historial de liquidaciones y pagos de cada unidad.
- **Apertura:** saldo inicial de caja, saldo inicial del Fondo de Reserva y deuda inicial por unidad.

---

## 13. Vencimientos y alertas

**Más → Vencimientos y alertas.** Cuando hay algo vencido o por vencer en 7 días, el menú **Más** muestra un
número en rojo.

**Registrar un vencimiento:** elegís el tipo, la fecha de inicio (por ejemplo, el día que recibiste el pedido)
y el sistema calcula el vencimiento con el plazo legal:

| Tipo | Plazo |
|---|---|
| Rendición de cuentas anual (CCyC 2067 e) | 60 días corridos desde el cierre del ejercicio |
| Entrega de documentación por renuncia o remoción (2067 j) | 15 días hábiles |
| Comunicar un reclamo administrativo o judicial (2067 k) | 48 horas hábiles |
| Certificado de deuda solicitado (2067 l) | 3 días hábiles |
| Pedido de acceso a datos personales (Ley 25.326) | 10 días corridos |
| Rectificación o supresión de datos personales | 5 días hábiles |
| Certificado de seguridad del ascensor (Ord. 8.661) | 1 mes (cuenta solo el último registrado) |
| Póliza de seguro / Otro | La fecha que indiques |

Los días hábiles se cuentan de lunes a viernes **sin descontar feriados**: verificalos. Cuando se cumple,
marcalo como **cumplido** con la fecha.

**Alertas automáticas:**
- Mandato del administrador vencido o por vencer (60 días).
- Registro de administradores (Ord. 9.131) sin inscripción confirmada. "En trámite" no equivale a inscripto.
- Rendición anual pendiente, según el cierre del ejercicio. Se puede registrar con un botón.
- Ascensor sin certificado registrado.

Las alertas ayudan a no olvidar plazos, pero **no reemplazan** las comunicaciones ni los trámites que corresponden.

---

## 14. Notificaciones, recibos y libre deuda

- **Notificaciones:** mensajes y archivos a propietarios e inquilinos por WhatsApp o mail.
- **Verificar recibo:** cada recibo tiene un QR. Al escanearlo, la página dice si el recibo es válido o
  fue alterado. También se puede ingresar el código a mano en **Más → Verificar recibo**.
- **Libre deuda:** se emite desde Unidades cuando la unidad pagó en total la última liquidación cerrada.
  Es un certificado numerado, con validez en días y QR de verificación, y se puede anular.

---

## 15. Configuración

| Tarjeta | Contenido |
|---|---|
| Fecha del sistema | Trabajar como si hoy fuera otro día (o volver a la fecha real) |
| Logo | Aparece en la barra y en los PDF |
| Datos del Edificio | Nombre, dirección, cuenta, administrador, contacto, día de vencimiento, aporte al fondo |
| Intereses por mora | Historial de tasas con vigencia y fundamento, switch de capitalización |
| Administración | CUIT, domicilio, mandato, registro de administradores, cierre del ejercicio, ascensor |
| Resumen de expensas (PDF) | Días, horario y lugar de cobro, texto de anuncio, validez del libre deuda |
| Verificación de recibos | URL de la app para los QR |
| Gastos recurrentes / Categorías | Conceptos de todos los meses y categorías de porcentaje |
| Checkpoint | Punto de restauración por 30 días, con rollback |
| Log de Movimientos | Solo admin (sección 16) |

---

## 16. Herramientas del administrador

- **Usuarios:** habilitar o deshabilitar cuentas, dar o quitar el rol de admin y elegir a qué consorcios
  accede cada uno. Los cambios tienen efecto en el acto.
- **Log de Movimientos:** quién cambió qué y cuándo (180 días). Una operación se puede **revertir** si no
  toca un período con liquidación cerrada y nadie la modificó después. La reversión también queda registrada.
- **Exportación completa** (Más → Exportación completa): un ZIP con todas las tablas del consorcio en CSV
  (se abren con Excel) y JSON, el Log de Movimientos, los comprobantes de facturas y un LEEME.
  - **Para qué:** respaldo y cambio de administración.
  - **Cuidado:** tiene datos personales, así que hay que guardarlo con cuidado.
  - **Qué no es:** no reemplaza los libros rubricados.
- **Crear o eliminar consorcios y resetear datos:** solo admin. Eliminar un consorcio borra **todos** sus
  datos y no se puede revertir.

---

## 17. Preguntas frecuentes

**¿Por qué la liquidación de octubre muestra gastos de septiembre?**
Porque se liquida a mes vencido: se cobra lo ya gastado y conocido.

**Cargué un gasto en el mes equivocado.**
Si la liquidación que lo cobra sigue abierta, editalo o borralo y cargalo en el mes correcto. Si ya
está cerrada, no se puede tocar: cargalo en el mes actual.

**Llegó una factura tarde y la liquidación ya está cerrada.**
Cargala en el mes actual. El gasto se cobra en la liquidación siguiente.

**¿Cómo registro un pago parcial?**
En Cobranzas, cargá el monto real. Lo que falta pasa como deuda anterior al mes siguiente.

**¿Cómo no le cobro interés a una unidad?**
Al cerrar la liquidación, apagá el switch de esa unidad en la ventana de intereses.

**¿Por qué el interés es menor que "tasa × deuda anterior"?**
Porque la deuda anterior puede incluir intereses impagos de meses anteriores, y sobre esos no se cobra
interés. La ventana de cierre muestra cuánto es capital y cuánto intereses.

**Cambió la tasa de mora.**
Registrala en Configuración → Intereses por mora con la fecha desde la que rige y el acta. Las
liquidaciones ya cerradas no cambian.

**¿Cuánto hay en el Fondo de Reserva?**
Más → Fondo de Reserva. El número que importa es el **saldo efectivo**; lo pendiente de cobro todavía no es dinero.

**Cerré una liquidación por error.**
Un administrador puede reabrirla si no tiene pagos y la siguiente sigue abierta.

**¿Cómo hago un respaldo?**
Un administrador lo descarga en Más → Exportación completa.

**¿Cómo sé si un recibo es auténtico?**
Escaneá el QR del recibo o ingresá el código en Más → Verificar recibo.

---

*Este sistema ayuda a cumplir las obligaciones de la administración, pero no reemplaza el asesoramiento
jurídico y contable ni los libros y trámites exigidos por la ley.*
