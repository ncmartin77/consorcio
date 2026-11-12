# Historial de Versiones — Sistema de Gestión de Consorcio

**Proyecto:** App Flask + PostgreSQL (Supabase) para administración de consorcios  
**Repositorio:** github.com/ncmartin77/consorcio  
**Deploy:** Render.com  
**Versión actual:** 11.1-1211

---

## Cómo leer el número de versión

El archivo `version.txt` usa el formato:

```
X.Y-DDMM
```

| Componente | Significado | Ejemplo |
|---|---|---|
| `X` | Versión mayor. Cambio de arquitectura, migración de base de datos, rediseño de funcionalidades centrales. | `4` |
| `Y` | Versión menor. Feature nuevo, fix significativo, cambio de comportamiento visible. | `2` |
| `DDMM` | Día y mes de lanzamiento (sin año). | `2210` = 22 de octubre |

**Ejemplo completo:** `4.2-2210` = versión 4.2, lanzada el 22 de octubre.

### Convención de incremento

- **Versión mayor (X):** Se incrementa cuando hay un cambio que rompe compatibilidad o implica una migración de datos/arquitectura significativa (ejemplo: pasar de Excel a PostgreSQL, rediseño del modelo de liquidaciones).
- **Versión menor (Y):** Se incrementa en cada commit que agrega funcionalidad, corrige un comportamiento o modifica la interfaz de forma visible. Se reinicia a `0` al incrementar la versión mayor.
- **DDMM:** Se actualiza con la fecha real de cada lanzamiento.

---

## Recomendaciones de versionado

### Comparación con SemVer

[SemVer](https://semver.org/) (Semantic Versioning) usa el formato `MAJOR.MINOR.PATCH`:

| Criterio | Formato actual (`X.Y-DDMM`) | SemVer (`MAJOR.MINOR.PATCH`) |
|---|---|---|
| Legibilidad de fecha | Alta: la fecha está embebida | Sin información de fecha |
| Granularidad | Dos niveles (mayor/menor) | Tres niveles (mayor/menor/parche) |
| Ordenamiento por string | Incorrecto (lexicográfico falla) | Correcto con comparadores estándar |
| Uso en changelogs | Intuitivo para el administrador | Estándar para desarrolladores |
| Compatibilidad con herramientas | Limitada (pip, npm no lo entienden) | Amplia |

### Pros del formato actual

- La fecha embebida (`DDMM`) permite saber de un vistazo cuándo se lanzó cada versión sin consultar el historial de git.
- Sencillo de mantener en un archivo de texto plano.
- Adecuado para un sistema administrado por una sola persona o equipo pequeño.

### Contras del formato actual

- La fecha no incluye el año, lo que puede generar ambigüedad si el proyecto supera los doce meses activos.
- No distingue entre fixes de bugs menores (parches) y features nuevos (minor).
- El componente `DDMM` no es un número de versión estricto, por lo que herramientas de comparación de versiones no lo interpretan correctamente.

### Recomendación para el futuro

Para este tipo de proyecto (app de producción, equipo pequeño, sin dependencias de paquete), se recomienda:

1. **Mantener el formato actual** mientras el equipo sea unipersonal y el administrador valore la fecha embebida.
2. **Agregar tags de git** en cada release para tener trazabilidad completa:
   ```bash
   git tag -a v4.2 -m "v4.2: período persistente, reapertura de liquidaciones"
   git push origin v4.2
   ```
3. **Considerar migrar a `X.Y.Z-DDMM`** cuando se quiera distinguir parches de features sin perder la fecha:
   - `Z` = parche/fix sin cambio de comportamiento
   - Ejemplo: `4.2.1-2410` = fix de la 4.2, lanzado el 24 de octubre
4. Si en algún momento se publica como paquete o se abre a colaboradores externos, migrar a SemVer puro con fecha en el changelog.

---

## Historial completo de versiones

Las pruebas hechas en cada versión (desde la 5.6) están en [`pruebas_realizadas.md`](pruebas_realizadas.md).

---

### v1.x — Sistema base con Excel

**Período:** Etapa inicial del proyecto  
**Base de datos:** Excel (módulo `excel_db.py`)

Esta fue la primera versión funcional del sistema. La persistencia de datos se basaba en archivos Excel manipulados desde Python, lo que simplificaba el desarrollo inicial pero limitaba la escalabilidad y el acceso concurrente.

**Funcionalidades incluidas:**

- Gestión de unidades del consorcio
- Carga de gastos mensuales
- Generación de liquidaciones de expensas
- Caja diaria
- Registro de facturas
- Administración de proveedores

**Limitaciones que motivaron la migración:**

- Sin soporte multi-consorcio (un Excel = un consorcio)
- Sin autenticación de usuarios
- Sin acceso remoto ni deploy en la nube
- Riesgo de corrupción de datos con uso concurrente
- Sin auditoría de cambios

---

### v2.x — Migración a PostgreSQL / Supabase

**Período:** Segunda etapa, migración completa de base de datos  
**Base de datos:** PostgreSQL hosteado en Supabase

**Por qué se migró a PostgreSQL:**  
El sistema creció para gestionar múltiples consorcios con distintos administradores. Excel no permite multiusuario real, no ofrece transacciones y es frágil frente a archivos grandes. PostgreSQL sobre Supabase resolvió todos estos puntos y habilitó el deploy en la nube.

**Cambios principales:**

- Reemplazo completo de `excel_db.py` por `pg_db.py`
- Soporte multi-consorcio: cada consorcio tiene su propio espacio de datos
- Sistema de autenticación de usuarios
- Deploy en Render.com con acceso remoto
- Supabase como capa de base de datos gestionada (backups, SSL, acceso por URL)

---

### v3.x — Auditoría, seguridad y funcionalidades avanzadas

**Período:** Tercera etapa de maduración del sistema

**Cambios principales:**

- **Log de auditoría:** Registro de movimientos con usuario y timestamp para trazabilidad completa
- **Checkpoint y rollback:** Posibilidad de crear puntos de restauración y revertir cambios
- **Verificación de recibos:** Firma HMAC + código QR para validar autenticidad de recibos emitidos
- **Envío por WhatsApp:** Integración para enviar liquidaciones o avisos a propietarios
- **Gastos extra por unidad:** Cargos adicionales asignables a unidades específicas (no proporcionales)
- **Notas del período:** Campo de texto libre por período para el administrador
- **Presupuestos:** Módulo para registrar y comparar presupuestos de proveedores
- **Gastos recurrentes con auto-matching:** Los gastos que se repiten mensualmente se vinculan automáticamente con la factura correspondiente al registrarla

---

### v4.x — Correcciones de cálculo y mejoras de UX

---

#### v4.0 y v4.1 — Corrección del Fondo de Reserva

**Cambio clave:** Corrección en el cálculo de expensas.

Hasta la v3.x, el Fondo de Reserva se sumaba junto con los gastos ordinarios en un único pool, lo que distorsionaba el cálculo de la liquidación. A partir de v4.0:

- El Fondo de Reserva se separa como ítem independiente
- La separación se refleja visualmente en la pantalla de Gastos
- El cálculo de la cuota por unidad es ahora correcto tanto para gastos ordinarios como para el fondo

**Por qué este cambio:** El Fondo de Reserva tiene naturaleza diferente a los gastos ordinarios (no se "gasta", se acumula). Mezclarlo generaba confusión contable y errores en la cuota informada a los propietarios.

---

#### v4.2-2210 — Período persistente y reapertura de liquidaciones

**Lanzamiento:** 22 de octubre

**Cambios:**

- **Período persistente en sesión:** El período de trabajo seleccionado (mes/año) se mantiene durante toda la sesión del usuario, sin necesidad de reseleccionarlo en cada pantalla
- **Reapertura de liquidaciones cerradas:** Las liquidaciones ya cerradas pueden reabrirse para corregir errores, siempre que el administrador tenga los permisos correspondientes
- **Fix:** Al reabrir una liquidación, las facturas asociadas al período ahora pueden borrarse correctamente (antes quedaban bloqueadas)
- **Fix:** Edición y borrado de gastos recurrentes funcionaba incorrectamente en ciertos estados

---

#### v4.3-0211 — Saldo Inicial y valores negativos

**Lanzamiento:** 2 de noviembre

**Cambios:**

- **Renombrado:** "Deuda Inicial" pasa a llamarse "Saldo Inicial" en las pantallas de Apertura y Unidades, para reflejar que el valor puede ser positivo o negativo
- **Semántica de signo:** Valores negativos = deuda (se muestra en rojo), valores positivos = saldo a favor (se muestra en verde)
- **Fix de UI:** Se elimina el atributo `min=0` en los campos de ingreso numérico, permitiendo ingresar valores negativos directamente

**Motivación:** La convención anterior impedía registrar unidades con saldo a favor al inicio, forzando workarounds. El cambio alinea el sistema con la realidad contable.

---

#### v4.4-0211 — Paginación y filtros en Facturas

**Lanzamiento:** 2 de noviembre

**Cambios:**

- **Filtro por mes de pago:** Las facturas pueden filtrarse por el mes en que fueron efectivamente pagadas (no solo por mes de carga)
- **Paginación:** La vista de facturas muestra 25 registros por página
- **Agrupación por mes:** En la vista de facturas pagadas, los registros se agrupan por mes para facilitar la lectura
- **Total pendiente global:** El total de facturas pendientes se calcula sobre todos los registros, independientemente de la página visible

---

#### v4.5-0211 — Caja Diaria: paginación, saldo corriente y sincronización

**Lanzamiento:** 2 de noviembre

**Cambios:**

- **Paginación en Caja Diaria:** Muestra 50 movimientos por página
- **Saldo acumulado por fila (running balance):** Cada fila de la caja muestra el saldo acumulado hasta ese movimiento, facilitando la revisión del flujo de caja
- **Badge "Fac.":** Los movimientos vinculados a una factura muestran una etiqueta visual para identificarlos rápidamente
- **Sincronización factura ↔ caja (borrado):**
  - Al borrar una factura, el movimiento de caja asociado también se elimina automáticamente
  - Al borrar un movimiento de caja vinculado a una factura, la factura vuelve al estado `PENDIENTE`
- **Aviso al eliminar:** Si el movimiento a borrar está vinculado a una factura, el sistema muestra una advertencia antes de confirmar

---

#### v4.6-0211 — Fix: saldo al corte en paginación

**Lanzamiento:** 2 de noviembre

**Cambios:**

- **Fix de running balance:** El saldo acumulado en Caja Diaria ahora parte correctamente del saldo histórico acumulado, incluso al navegar entre páginas. Antes, cada página comenzaba desde cero, mostrando saldos incorrectos en páginas distintas a la primera.

---

#### v4.7-0211 — Fix: mora en primer mes de apertura

**Lanzamiento:** 2 de noviembre

**Cambios:**

- **Fix de mora corriente:** En el primer mes de apertura del consorcio (cuando no existe liquidación previa), el sistema ya no cobra mora por vencimiento. La mora solo aplica a partir del segundo período, cuando hay una liquidación anterior como referencia.

**Motivación:** Sin liquidación anterior no hay deuda anterior que genere mora. Cobrar mora en el primer mes era un error lógico.

---

#### v4.8-0211 — Saldo en liquidación y Fondo de Reserva por período

**Lanzamiento:** 2 de noviembre

**Cambios:**

- **Saldo en pantalla Liquidación:** Se muestra el saldo de Caja al último día del período por defecto, con un selector de fecha editable para consultar el saldo a cualquier corte
- **Fondo de Reserva por período:** El valor de Fondo de Reserva mostrado en la liquidación corresponde al configurado específicamente para ese período, no a una suma histórica acumulada

---

#### v4.9-0311 — Checkbox "sin interés" por unidad

**Lanzamiento:** 3 de noviembre

**Cambios:**

- **Checkbox por unidad:** En la pantalla de liquidación, cada unidad tiene un checkbox "sin interés" que exime a esa unidad del cobro de mora para el período actual
- **Toggle general:** Botón para activar o desactivar el interés en todas las unidades a la vez
- **Persistencia del flag:** El estado del checkbox se preserva al recalcular la liquidación, sin perderse
- **Actualización AJAX en tiempo real:** Al togglear el checkbox, el interés y el total de esa unidad se actualizan sin recargar la página completa

---

### v5.x — Simplificación de lógica de mora

---

#### v5.0-0311 — Mora sin restricción de apertura

**Lanzamiento:** 3 de noviembre

**Cambios:**

- **Mora corriente sin restricción de apertura:** La exención del primer mes de apertura (introducida en v4.7) se eliminó como regla automática. Ahora la exención se maneja explícitamente mediante el checkbox "sin interés" (introducido en v4.9), dando control total al administrador
- **Deudas siempre en rojo:** El color del interés cambia de `text-warning` (amarillo) a `text-danger` (rojo), unificando la presentación visual de deudas
- **Filas PENDIENTE en fondo rojo:** Las unidades con estado PENDIENTE en la liquidación siempre se muestran con fondo rojo, independientemente de otros estados

**Motivación:** La regla automática del primer mes era frágil y difícil de mantener. Darle el control explícito al administrador mediante el checkbox es más flexible y predecible.

---

#### v5.1-0311 — Documentación del proyecto

**Lanzamiento:** 3 de noviembre

**Cambios:**

- Carpeta `docs/` con historial de versiones, manual de usuario, arquitectura técnica y memoria de sesión.

---

#### v5.2-0311 — Tilde "sin interés" rápido

**Lanzamiento:** 3 de noviembre

**Cambios:**

- **Toggle "sin interés" sin regenerar la liquidación:** recalcula solo interés, total y saldo de las unidades afectadas en una única transacción (`aplicar_sin_interes()` en `pg_db.py`).
- **Pantalla actualizada al instante:** interés, TOTAL, Saldo, total del pie y el monto del modal de pago se actualizan sin recargar; el tilde se deshabilita mientras espera y se revierte con aviso si hay error.
- **Menos consultas por request:** los `ensure_*` de columnas (`ALTER TABLE`) corren una sola vez por proceso en lugar de en cada request.

**Motivación:** el tilde tardaba varios segundos y la pantalla mostraba montos viejos.

---

#### v5.3-0311 — Regla de versionado

**Lanzamiento:** 3 de noviembre

**Cambios:**

- Regla de versionado en `CLAUDE.md`: cuándo sube la versión menor y cuándo la mayor; la mayor se consulta con el usuario antes del commit.

---

#### v5.4-0411 — Continuar en otra PC

**Lanzamiento:** 4 de noviembre

**Cambios:**

- `docs/memoria_sesion_claude.md`: estado actualizado, sección "Continuar en otra PC" (clonar, `.env`, Session pooler de Supabase por IPv6, BD de producción).
- `CLAUDE.md`: indica leer la memoria de sesión al empezar y actualizarla al terminar.

---

#### v5.5-0411 — Memoria de Claude en el repo (sin claves)

**Lanzamiento:** 4 de noviembre

**Cambios:**

- `docs/memoria_claude/`: copia de las notas de memoria de Claude de la PC original (consorcio), con contraseñas, tokens y emails reemplazados por `***`.

---

### v10.x — Lineamientos jurídicos (Paraná, Entre Ríos)

#### v11.1-1211 — Borrar comprobantes y archivos

**Lanzamiento:** 12 de noviembre (rama `feat/borrar-archivos`)
**Versión actual**

- **Quitar comprobante:** nuevo botón rojo en Facturas, al lado de "ver". Pide confirmación, deja la factura sin comprobante y borra el archivo.
- **Reemplazar comprobante:** al subir uno nuevo se borra el archivo anterior. Antes quedaba guardado sin uso.
- **Eliminar una factura:** también borra su comprobante.
- **Eliminar un consorcio:** también borra todos sus archivos del almacenamiento (comprobantes y adjuntos de notificaciones). Se corrigió el aviso de confirmación, que decía "Los datos NO se borran" y no era cierto: siempre se borraron.
- **Archivo usado por dos facturas:** no se borra mientras alguna lo siga usando.
- **Archivos viejos en el disco:** también se borran.
- **Si el almacenamiento falla al borrar:** la factura igual queda sin comprobante y la app avisa que el archivo no se pudo borrar.
- **Límite conocido:** "Revertir" una operación en el Log de Movimientos vuelve a poner el comprobante en la factura, pero el archivo ya no existe. Al abrirlo, la app avisa que no se encontró y que hay que volver a adjuntarlo.
- **Pruebas:** `probar_storage.py` pasó de 26 a 37 controles. Dio OK en disco, en el S3 local y en Supabase Storage de `consorcio-tst`. Las 17 pruebas dan OK.

---

#### v11.0-1211 — Comprobantes y adjuntos en Supabase Storage

**Lanzamiento:** 12 de noviembre (en producción el mismo día; Storage activado en Render)

- **Por qué:** en Render el disco se borra con cada deploy, así que los comprobantes de facturas y los adjuntos de notificaciones que se subían se perdían.
- Nuevo `storage.py`: guarda, lee y borra archivos en un bucket S3 **privado**. En producción será Supabase Storage (Storage → S3 Connection). Variables: `STORAGE_S3_ENDPOINT`, `STORAGE_S3_REGION`, `STORAGE_S3_BUCKET` (por defecto `comprobantes`, se crea solo), `STORAGE_S3_ACCESS_KEY_ID`, `STORAGE_S3_SECRET_ACCESS_KEY`. **Sin esas variables usa el disco**, como antes (instalaciones de escritorio, pruebas).
- El navegador nunca entra al bucket: la app controla la sesión, lee el archivo y lo sirve. Cada archivo queda bajo la carpeta de su consorcio (`<consorcio_id>/facturas/...`, `<consorcio_id>/notificaciones/...`), así que un consorcio no ve los de otro.
- Archivos subidos antes de esta versión: si no están en Storage, se buscan en el disco como antes.
- Backup y Exportación leen los comprobantes desde Storage (a partir de las facturas que tienen comprobante). La Exportación avisa en `LEEME.txt` si algún comprobante registrado no se encontró.
- Una imagen que no se puede leer ahora da un aviso en vez de un error 500.
- Reemplaza el intento de la v6.0 (rama `supabase-storage`, que no se sube): mismo diseño, rehecho sobre la v10.4 y usando la conexión S3 de Supabase (librería `boto3`) en vez de la API propia.
- Pruebas: `pruebas/probar_storage.py`, 26 controles, OK en disco, en S3 local y en Supabase Storage de `consorcio-tst` (ver `docs/pruebas_realizadas.md`). `entorno_prueba.py` también rechaza un almacenamiento de producción.
- **Para activarlo en Render** (cuando se decida el merge): crear en Supabase de producción una clave S3 y cargar las cinco variables en Render. Sin ellas la app sigue usando el disco.

---

#### v10.4-1111 — Usar la app en una PC con base local

**Lanzamiento:** 11 de noviembre

- Sin cambios en la app. Nuevo `pruebas/servidor_local.py`: levanta la app en `http://127.0.0.1:5000` contra una base **local** (solo local: rechaza consorcio-tst y producción), para usarla en el navegador sin Supabase ni Google. Como el login con Google no funciona en local, agrega la ruta `/__login_local` (entra con un usuario de la base; solo desde la misma PC y sin proxy). No es parte de la app: Render arranca `app.py` con gunicorn y nunca carga este archivo.
- Uso: `pruebas/correr_en_docker.sh pruebas/servidor_local.py` y abrir `http://127.0.0.1:5000/__login_local`.

---

#### v10.3-1111 — Pruebas viejas actualizadas con escenario propio

**Lanzamiento:** 11 de noviembre

- Sin cambios en la app. Nuevo `pruebas/escenario.py`: consorcio temporal armado desde cero (2 UF, expensa $100.000, tasa 3 %) que se borra al terminar, con ayudas para fecha, generar, cerrar, pagar, controles y un usuario no administrador real.
- Reescritas con la lógica v9.x/v10: `probar_pagina_error`, `probar_anular_pagos`, `probar_libre_deuda`, `probar_fecha_sistema`, `probar_switch_interes` (ahora: interés al cerrar) y `probar_saldo_a_favor`. Terminan con código 1 si algo falla.
- Corrida completa: las 16 pruebas OK contra la base local (ver `docs/pruebas_realizadas.md`, v10.3).

---

#### v10.2-1111 — Pruebas contra una base local

**Lanzamiento:** 11 de noviembre

- Sin cambios en la app. `pruebas/entorno_prueba.py` acepta, además de `consorcio-tst`, una base **local** (127.0.0.1 / localhost) y sigue rechazando producción. Nuevo `pruebas/correr_en_docker.sh`: corre cualquier prueba en un contenedor de Python 3.12 con las dependencias, sin instalar nada en la PC.
- Corrida completa contra la copia del 03/11 en una base local: ver `docs/pruebas_realizadas.md` (v10.2). Ninguna falla es del código; quedan 6 pruebas viejas para actualizar.

---

#### v10.1-0911 — Pendientes de pruebas para seguir en otra PC

**Lanzamiento:** 9 de noviembre

- Solo documentación: en `docs/memoria_sesion_claude.md` ("DONDE QUEDAMOS") quedan anotados los resultados de las pruebas, las que hay que repetir (se cortaron por falta de red), las pruebas viejas a actualizar y la limpieza de la base de prueba.

---

#### v10.0-0911 — Interés sin capitalizar, libro del fondo, clasificación de gastos, exportación y alertas

**Lanzamiento:** 9 de noviembre

**Por qué es versión mayor:** cambian reglas de cálculo que alteran resultados (interés y saldo del Fondo de Reserva). Confirmado por el usuario ("hagamos del 1 al 5", tras el ejemplo del interés y el aviso de 10.0).

**Cambios (puntos 1 a 5 del análisis del documento "Lineamientos jurídicos para el sistema de consorcios"):**

1. **Interés sin capitalizar (CCyC 770 y 903).** La liquidación guarda aparte qué parte de la deuda anterior son intereses impagos (`liquidaciones.deuda_interes`); el interés del cierre se calcula sobre el **capital** (deuda anterior − intereses impagos). Los pagos se imputan primero a intereses. La tasa se registra **con fecha de vigencia y fundamento** (tabla `tasas_mora`, Configuración → Intereses por mora); cada liquidación usa la vigente el día 1 de su mes y, al cerrar, queda congelada (`liquidaciones.tasa_aplicada`). No se pueden cargar ni borrar tasas con vigencia en un período ya cerrado. Switch "Capitalizar intereses" (apagado por defecto). Ejemplo: 3 meses sin pagar $100.000 al 3 % → enero $418.000 (antes $418.362,70).
2. **Libro del Fondo de Reserva (§4).** Reemplaza la regla v8.0 (fondo = saldo de caja): saldo efectivo = saldo inicial (nuevo campo en Apertura) + aportes **cobrados** + otros ingresos al fondo − pagos con el fondo. Aportes liquidados sin cobrar y compromisos (facturas a pagar con el fondo) se muestran aparte. Pantalla nueva **Más → Fondo de Reserva** y cuadro en el PDF de la liquidación. El saldo para pagar facturas con el fondo sale del libro.
3. **Exportación completa del consorcio (J09).** **Más → Exportación completa** (solo admin): ZIP con todas las tablas del consorcio en CSV y JSON, el Log de Movimientos, los comprobantes y un LEEME. Sin usuarios ni la clave de firma de recibos. Reemplaza el botón Backup (de la época Excel).
4. **Clasificación del gasto (§3.1, CCyC 2048).** Campos separados: naturaleza (ordinaria/extraordinaria), frecuencia (recurrente/no recurrente), con qué se paga (expensas/fondo) y respaldo (acta, autorización). El `tipo` de siempre se deduce de ellos; un gasto pagado con el fondo conserva su naturaleza. Los gastos anteriores toman la clasificación de su tipo. El PDF separa ordinarios y extraordinarios y muestra la frecuencia.
5. **Administración y alertas (§6, §7).** Configuración → Administración: CUIT, domicilio, mandato (desde/hasta, instrumento), registro de administradores Ord. 9.131 (estado, organismo, número, fecha), cierre del ejercicio y ascensor. **Más → Vencimientos y alertas** con badge en el menú: plazos legales (rendición anual 60 días, certificado de deuda 3 días hábiles, datos personales 10 días / 5 hábiles, reclamos 48 h hábiles, entrega de documentación 15 hábiles, certificado mensual del ascensor), mandato por vencer, registro no inscripto. El PDF muestra CUIT y registro (solo afirma la inscripción si el estado es Inscripto).

6. **Documentación.** Manual de usuario reescrito para la v10.0 (el anterior decía v5.0, no tenía Cobranzas y explicaba al revés el signo de la deuda inicial) y visible dentro de la app en **Más → Ayuda y manual** (`/ayuda`). Diagramas técnicos (arquitectura, datos, estados, cálculos, secuencias) en `docs/diagramas.md`, que no se muestran en la app (pedido del usuario).

- Prueba: `pruebas/probar_v10.py` (50/50 OK) y las anteriores.

---

### v9.x — Cobranzas separada de Liquidación

#### v9.8-0911 — Arreglos de seguridad

**Lanzamiento:** 9 de noviembre

**Cambios (revisión de seguridad pedida por el usuario):**

- **Crítico — cuentas nuevas:** una cuenta de Google nueva queda **inactiva** hasta que un admin la habilite (antes cualquier cuenta entraba). El primer usuario del sistema sigue siendo admin.
- **Crítico/alto — permisos:** crear y eliminar consorcios y "Resetear datos" exigen ser **admin** (antes cualquier usuario logueado podía borrar un consorcio entero, que borra en cascada todos sus datos y no se puede revertir desde el Log).
- **Alto — CSRF:** los POST que vienen de otro sitio (encabezado Origin/Referer distinto) se rechazan con 403; cookie de sesión `SameSite=Lax`, `HttpOnly` y `Secure` en Render.
- **Medio:** el rol de admin se toma de la base en cada pedido (quitarlo tiene efecto en el acto); `SECRET_KEY` obligatoria en Render (sin ella la app no arranca; ya no hay clave por defecto en el código).
- **Medio — validaciones del servidor:** importes de gastos, caja, facturas, extras, pagos, unidades y apertura rechazan "nan", "inf", texto y negativos donde no corresponde; tipo de caja solo ENTRADA/SALIDA; el aporte FONDO_RESERVA no se carga a mano; porcentajes entre 0 y 100; no se cargan, editan ni borran gastos de una liquidación **cerrada** (antes solo lo impedía la pantalla); no se paga una factura con fecha en un mes de Caja cerrado ni dos veces; una factura pagada no se puede modificar reenviando el formulario con su id.
- **Medio:** `iniciar_red.bat` (red local) ya no corre en modo debug.
- **Bajo:** `.env`, `.env.local`, `privado/` y `gen_nov.py` en `.gitignore`; subidas limitadas a 16 MB.
- Prueba: `pruebas/probar_seguridad.py` (24/24 OK) y las anteriores sin fallas.

---

#### v9.7-0811 — "MONTO A PAGAR" en la planilla

**Lanzamiento:** 8 de noviembre

**Cambios (pedido del usuario):** en la tabla de UF del PDF de liquidación, la última columna se llama **MONTO A PAGAR** (en mayúsculas) en lugar de "Saldo". Prueba: `pruebas/probar_pdf_planilla.py` 15/15 OK y revisión visual (también con columna Interés).

---

#### v9.6-0811 — Planilla de liquidación horizontal

**Lanzamiento:** 8 de noviembre

**Cambios (pedido del usuario), PDF resumen de la liquidación:**

- Hoja **A4 horizontal**; las 24 UF y los totales entran en la primera hoja.
- Columnas nuevas por UF: **Liquidado mes ant.** (total de la liquidación anterior) y **Pago anterior** (lo que pagó de esa liquidación), antes de Deuda. Orden: UF, Descripción, Prop./Inquilino, %, Liquidado mes ant., Pago anterior, Deuda, [Interés], Expensas, Total, Pagado, Saldo.
- El cuadro **Total gastos / Total a cobrar / Cobrado / Pendiente** pasa de arriba a **inmediatamente debajo de la tabla de UF** (sin partirse entre hojas).
- Fix: el nombre del edificio se superponía con el subtítulo; el total de la columna Pagado no entraba.
- Prueba: `pruebas/probar_pdf_planilla.py` (15/15 OK) y revisión visual de las páginas.

---

#### v9.5-0811 — Registro del reset de datos de Perú 376

**Lanzamiento:** 8 de noviembre

**Cambios:** sin cambios de código. Se documenta en `docs/memoria_sesion_claude.md` el reset de movimientos de Perú 376 en producción pedido por el usuario (gastos, facturas, caja y liquidaciones borrados; apertura en cero; fecha del sistema 01/10/2026), revertible desde el Log de Movimientos.

---

#### v9.4-0811 — Gasto vinculado a su factura y observación del pago

**Lanzamiento:** 8 de noviembre

**Cambios (pedido del usuario):**

- **Borrar una factura (o su pago) ya no deja el gasto "trabado":** cada gasto queda vinculado a la factura que lo generó (`gastos.factura_id`). Al borrar la factura el gasto queda sin vínculo y en Gastos Mensuales aparece el botón **"Emitir factura de este gasto"** en cualquier gasto sin factura (antes solo en los Variables). Los gastos con factura muestran un ícono verde.
- Emitir la factura desde el gasto la vincula: al pagarla se actualiza ese mismo gasto, **no se duplica**. Lo mismo al borrar el pago en Caja y volver a pagar, y al volver a emitir la factura de un gasto recurrente.
- Los gastos anteriores se vinculan solos con su factura (mismo concepto e importe, mes de pago o de la factura), una vez por consorcio.
- **Observación del pago:** el modal Registrar Pago de Facturas tiene un campo "Observación" (`facturas.observacion`), que se muestra debajo de la descripción en la lista.
- Fix: guardar una factura **sin proveedor** daba error 500 (proveedor vacío → NULL).
- Prueba: `pruebas/probar_factura_vinculo.py` (16/16 OK) y `probar_factura_con_fondo.py` (14/14 OK).

---

#### v9.3-0811 — Pagar una factura con el Fondo de Reserva

**Lanzamiento:** 8 de noviembre

**Cambios (pedido del usuario):**

- El modal **Registrar Pago** de Facturas tiene el switch **"Pagar con Fondo de Reserva"**, con el saldo disponible del fondo y un aviso si el importe lo supera (no bloquea).
- Pagada con el fondo, la factura queda con categoría `FONDO_RESERVA`, la salida de Caja también (descripción "[Fondo de Reserva] ...") y el gasto se registra como `VARIABLE_FR`: **no genera gasto para la liquidación**; se ve en "Gastos con Fondo de Reserva".
- Si la factura es de un gasto recurrente (cargado como ordinario al guardarla), ese gasto pasa a `VARIABLE_FR` en vez de duplicarse, si su liquidación sigue abierta.
- Prueba: `pruebas/probar_factura_con_fondo.py` (14/14 OK).

---

#### v9.2-0711 — El interés se decide al cerrar la liquidación

**Lanzamiento:** 7 de noviembre

**Cambios (regla del usuario, reemplaza a la v9.1):**

- Mientras la liquidación está **abierta** no lleva interés.
- Al **cerrarla** se abre una ventana con las unidades que tienen deuda anterior, el interés que les corresponde (**tasa × deuda anterior**) y un **switch por unidad** (activado por defecto; "todas / ninguna" arriba). Las tildadas quedan con el interés sumado al total, congelado con la liquidación; las demás sin interés.
- La liquidación cerrada y el PDF resumen muestran la columna **Interés** (en el PDF solo si alguna unidad lo tiene). El recibo muestra "Interés sobre deuda anterior".
- **Cobranzas ya no cobra interés** (se quita el switch de la v9.1): se cobra el total de la liquidación. Para no cobrar el interés después de cerrar, se puede usar la bonificación.

---

#### v9.1-0711 — El interés se decide al cobrar (reemplazada por la v9.2)

**Lanzamiento:** 7 de noviembre

**Cambios (regla del usuario):**

- La **liquidación no lleva interés**: se quitan la columna Interés y el switch de la pantalla Liquidación. La deuda que pasa a la liquidación siguiente va sin interés.
- En **Cobranzas**, al registrar un pago con fecha posterior al vencimiento de la liquidación, aparece el switch **"Cobrar interés"** (activado por defecto): interés = tasa × saldo adeudado, **una sola vez** por unidad y liquidación. Se puede desactivar para no cobrarlo. "Pago Completo" tiene el mismo switch.
- El interés cobrado se guarda en el pago (`pagos.interes`) y entra en Caja como ingreso aparte (categoría **Intereses**); no cambia lo que la unidad debe. Se ve en la columna Interés de Cobranzas ("si paga hoy" / "cobrado"), en el historial de pagos, en el recibo ("Interés por pago fuera de término") y en el WhatsApp de las vencidas.
- Fix: el recibo PDF fallaba si el mes tenía facturas extraordinarias (`col_w_det` sin definir).

---

#### v9.0-0711 — Se cobra sobre la liquidación cerrada (pantalla Cobranzas)

**Lanzamiento:** 7 de noviembre
**Por qué es mayor:** cambia qué significa "cerrada", dónde y cuándo se registran los pagos y la regla del interés, y los pagos pasan a una tabla nueva (migración automática). Aprobado por el usuario. La migración a Supabase Storage pasa a **10.0**.

**Concepto nuevo (pedido del usuario):**

| Momento | Liquidación | Pagos |
|---|---|---|
| Mes de los gastos | **Abierta**: se cargan gastos, el monto se recalcula | se cobra la última cerrada |
| Cambia el mes, no hay más gastos | **Se cierra**: monto fijo | — |
| Mes de la liquidación | Cerrada, no cambia | se cobra contra ella en **Cobranzas** |
| Al generar / mientras está abierta la siguiente | lo impago pasa como deuda anterior (o saldo a favor) | cuando se cierra la siguiente, se cobra contra esa |

**Cambios:**

- **Pantalla nueva Cobranzas** (`/cobranzas`, menú al lado de Liquidación): registrar pago (monto, fecha = fecha del sistema, bonificación), pago completo, anular (admin; un pago, una unidad o todos), recibos, WhatsApp, "Notificar a todos", filtro "solo pendientes" e historial de pagos. Siempre cobra contra la **última liquidación cerrada**; las anteriores se pueden consultar.
- **Liquidación** queda para generar, sin interés, extras, notas, cerrar/reabrir y PDF: sin botones de pago. Se **cierra** desde el día 1 del mes de la liquidación (según la fecha del sistema) y con la anterior cerrada; al cerrar se recalcula y el monto queda fijo. **Reabrir** solo admin y solo si no tiene pagos (y la siguiente no está cerrada).
- **Tabla `pagos`** (fecha, monto, bonificación, vínculo con Caja), auditada. El estado de pago de cada fila (`monto_pagado`, `tipo_pago`, `saldo_pendiente`, `fecha_pago`) se calcula desde ahí. Migración automática (una vez por consorcio, `config.pagos_migrados`): los pagos viejos se vinculan con sus entradas "Expensas P - … - UF n" y bonificaciones de Caja.
- **Deuda anterior** = total de la liquidación anterior − sus pagos (negativa = saldo a favor). Se actualiza en la liquidación abierta con cada pago hasta que se cierra.
- **Interés** = tasa × lo que seguía **impago el día del vencimiento** de la liquidación anterior, cobrado en la siguiente (aunque después se cancele). Ya no hay recargo dentro de la misma liquidación. Saldo a favor sin interés; deuda de apertura sin interés el 1er mes.
- **Caja:** el mes M se bloquea cuando se cierra la liquidación que lleva sus gastos (M+1). Editar/borrar en Caja el cobro de un pago actualiza/borra el pago.
- **Fecha del sistema:** pagos (por defecto y como máximo), cierres, interés y deuda usan la fecha del sistema; los pagos con fecha posterior no se cuentan. Al cambiarla se recalculan las liquidaciones abiertas.
- **Libre deuda:** según la última liquidación cerrada.

---

### v8.x — Fondo de Reserva = saldo de caja

#### v8.1-0611 — Saldo de caja a la fecha de cierre de la liquidación

**Lanzamiento:** 6 de noviembre

**Cambios:**

- Se guarda la **fecha de cierre** de cada liquidación (`liquidaciones_estado.fecha_cierre`, fecha del sistema al cerrar; se borra al reabrir).
- El saldo de caja de la liquidación (PDF "Ingresos y egresos", encabezado del PDF y tarjeta SALDO EN CAJA) se informa a la **fecha de cierre**; si está abierta, a la fecha del sistema; si se cerró antes de este cambio, a fin de mes (`fecha_corte_liquidacion()`). Antes era siempre el último día del mes, y no coincidía con la fecha de generación del PDF.

---

#### v8.0-0611 — El Fondo de Reserva del mes es el saldo de caja del mes anterior

**Lanzamiento:** 6 de noviembre
**Por qué es mayor:** cambia la regla de cálculo del Fondo de Reserva (aprobado por el usuario). La migración a Supabase Storage pasa a **9.0**.

**Cambios:**

- Regla aclarada por el usuario: el **Fondo de Reserva del mes X = saldo de caja al cierre del mes X-1** (ej.: liquidación de octubre → caja al 30/09 = $ 249.736,46). `get_resumen_fondo(mes_gastos)` devuelve ese saldo; `get_saldo_fondo()` usa el mes anterior a la fecha del sistema.
- Deja de usarse el cálculo "saldo inicial + aportes liquidados − gastos con el fondo" (v6.0–v6.6) y los campos de saldo inicial del fondo en Configuración.
- Sin cambios en lo que se cobra: el aporte mensual se sigue cobrando en las expensas y los extraordinarios pagados con el fondo siguen sin cobrarse.
- Liquidación: tarjeta y panel del fondo muestran el saldo de caja al cierre del mes anterior, el aporte que se cobra y lo pagado con el fondo. Gastos y plano usan el mismo valor.

---

### v7.x — Saldo a favor

#### v7.3-0611 — PDF resumen sin "Fondo de Reserva disponible"

**Lanzamiento:** 6 de noviembre

**Cambios:**

- Se quita la línea "Fondo de Reserva disponible" del cuadro "Base de la expensa" del PDF resumen (pedido del usuario).

---

#### v7.2-0611 — PDF resumen: gastos ordinarios, base de la expensa e ingresos/egresos

**Lanzamiento:** 6 de noviembre

**Cambios:**

- PDF resumen, página 2: tabla **"Gastos Ordinarios — {mes de gastos}"** solo con gastos ordinarios (sin el aporte al fondo ni extraordinarios), total "TOTAL GASTOS ORDINARIOS".
- Cuadro nuevo **"Base de la expensa"**: gastos ordinarios + aporte al Fondo de Reserva (+ extraordinarios a cobrar) = total a repartir; y el saldo disponible del fondo.
- "Estado financiero" pasa a **"Ingresos y egresos — {mes de la liquidación}"**: saldo de caja al cierre del mes anterior + ingresos por pagos de expensas − egresos por pagos ordinarios = saldo de caja al cierre del mes (otros ingresos, pagos con el fondo y bonificaciones solo si los hay). `pg_db.get_resumen_caja_periodo()`.
- Pantalla Liquidación, tarjeta **GASTOS PAGADOS**: ahora suma las facturas pagadas en el mes de gastos (aunque no hayan generado movimiento en Caja) más las salidas de Caja que no vienen de una factura (`get_gastos_pagados_periodo()`). Antes sumaba solo Caja y daba $ 0 con facturas marcadas pagadas sin Caja.

---

#### v7.1-0611 — Totales en el PDF resumen y en la pantalla Liquidación

**Lanzamiento:** 6 de noviembre

**Cambios:**

- PDF resumen: la fila TOTAL ahora incluye la suma de la columna **Deuda** (neta: un saldo a favor resta). Columnas de importes más anchas para que entren los totales.
- Pantalla Liquidación: el pie de la tabla estaba corrido una columna (el total quedaba bajo "Extra" y lo abonado bajo "TOTAL"; "Saldo" sin total). Ahora cada total va bajo su columna y se agregan los de **Interés**, **Extra** y **Saldo**. Interés y saldo se recalculan al usar el switch de interés.

---

#### v7.0-0611 — Pagos de más: saldo a favor para el mes siguiente

**Lanzamiento:** 6 de noviembre
**Por qué es mayor:** cambia el cálculo cuando una unidad paga de más (antes el excedente se perdía) y la mora con saldo a favor. Aprobado por el usuario. La migración a Supabase Storage pasa a **8.0**.

**Cambios:**

- El formulario de pago ya no limita el monto al saldo; si se paga de más avisa cuánto queda a favor.
- Pago de más: la unidad queda **pagada** y el excedente se guarda como saldo negativo (`saldo_pendiente < 0`) = **saldo a favor**. El cobro completo entra a Caja.
- Mes siguiente: `deuda_anterior` negativa = saldo a favor, que reduce el total (`_deuda_desde_mes_anterior`). Si el saldo a favor cubre todo el mes, la unidad queda pagada sin abonar y el resto sigue a favor.
- Interés: el saldo a favor nunca genera interés; la mora del mes (vencido y sin pagos) se cobra solo sobre la parte de las expensas que el saldo a favor no cubre.
- Pantallas: "a favor" en verde en deuda anterior y en saldo ("a favor próx. mes"); recibo PDF con "SALDO A FAVOR".
- Unidades: la vista del saldo inicial mostraba el signo al revés del cálculo (positivo decía "A favor"); ahora positivo = **Deuda** y negativo = **A favor**, igual que en la liquidación.

---

### v6.x — Fondo de reserva y gastos extraordinarios

#### v6.6-0611 — Fix: el aporte al fondo cuenta cuando se cobra

**Lanzamiento:** 6 de noviembre

**Cambios:**

- Saldo del fondo respecto del saldo inicial (al mes P): un **aporte** entra al fondo cuando se cobra, es decir en la liquidación siguiente a su mes; cuenta si esa liquidación es posterior a P. Antes se tomaba el mes del gasto, y el aporte de P (que se cobra en P+1) quedaba afuera. Un **gasto pagado con el fondo** sigue contando por su propio mes.
- Caso real: Perú 376 con saldo inicial del fondo $ 0 a sep-2026 y aporte de septiembre $ 80.000 cobrado en octubre → el fondo pasa a mostrar $ 80.000 (antes $ 0).

---

#### v6.5-0611 — Estado de la liquidación debajo del título

**Lanzamiento:** 6 de noviembre

**Cambios:**

- Pantalla Liquidación: el aviso de estado pasa de la barra de botones a debajo del título ("Liquidación ABIERTA" verde, "Liquidación CERRADA" rojo, "Sin generar" gris).
- La palabra "Liquidación" del título (y su ícono) se colorea: verde si está abierta, rojo si está cerrada.

---

#### v6.4-0611 — Anular pagos y fecha del sistema en los formularios

**Lanzamiento:** 6 de noviembre

**Cambios:**

- **Anular pago** (solo administradores, liquidación abierta): botón por unidad y "Anular todos los pagos" del período en Liquidación. Deja la fila sin pago, borra de Caja la entrada "Expensas <período> - … - UF <n>" y la bonificación si la hubo, y recalcula el interés. Todo en una transacción, auditada: se revierte desde el Log de Movimientos. No anula si algún cobro está en Caja de un mes con liquidación cerrada (`pg_db.anular_pagos`, `POST /liquidacion/<periodo>/anular-pagos`).
- Los formularios (pagos, pago completo, caja, facturas, gastos, plano, presupuestos) proponían la fecha **real** del navegador; ahora proponen la **fecha del sistema** (`hoy_sistema` en el context processor). Así, con una fecha fijada, el pago queda registrado con esa fecha.

---

#### v6.3-0611 — Fix: error 500 en Liquidación cerrada o sin generar

**Lanzamiento:** 6 de noviembre

**Cambios:**

- Causa real del error 500 en `/liquidacion/2026-10` (obtenida con la página de error de la v6.2): `UnboundLocalError: cannot access local variable '_cal'`. La ruta `liquidacion()` tenía `import calendar as _cal` dentro de un `if` que solo corre si la liquidación existe y está abierta; ese import vuelve local a `_cal` en toda la función, así que con la liquidación **cerrada o sin generar** fallaba más abajo. Error antiguo (no de esta sesión); en la base de prueba no aparecía porque octubre está abierta. Se quitó el import local (ya estaba importado arriba).
- La v6.1 (períodos mal cargados) atacó otra causa posible; queda como protección extra.

---

#### v6.2-0611 — Detalle de errores para administradores

**Lanzamiento:** 6 de noviembre

**Cambios:**

- Página de error 500 propia: a los administradores les muestra el detalle técnico (traceback, página, versión, consorcio, fecha del sistema) para diagnosticar sin acceso al log de Render; a los demás, un mensaje simple. Siempre queda en el log. No usa `base.html`, por si el error viene de ahí.
- Motivo: después de la v6.1, `/liquidacion/2026-10` con fecha 06/10 seguía dando error 500 en producción y no se reproduce en la base de prueba.

---

#### v6.1-0611 — Fix: error 500 por períodos mal cargados en el fondo

**Lanzamiento:** 6 de noviembre

**Cambios:**

- El cálculo del saldo del fondo ignora gastos con período mal formado (vacío, "2026-9"): antes daban error 500 en Gastos, Liquidación, Plano y PDF (reportado al liquidar octubre con fecha 06/10).
- Red de seguridad: si el cálculo del fondo falla por otro motivo, la pantalla se muestra igual con el fondo en 0, un aviso, y el error queda en el log.

---

#### v6.0-0611 — Fondo de reserva con saldo y gastos extraordinarios separados

**Lanzamiento:** 6 de noviembre
**Por qué es mayor:** cambia cómo se arman las expensas (los extraordinarios pagados con el fondo dejan de cobrarse, las facturas extraordinarias se cobran como línea aparte) y corrige datos existentes. Aprobado por el usuario. La migración a Supabase Storage, que estaba planeada como 6.0, pasa a ser 7.0.

**Cambios:**

- **Base de las expensas** = gastos ordinarios y recurrentes + **aporte del período** al fondo (+ extraordinarios a cobrar, como línea aparte). El saldo acumulado del fondo nunca se cobra.
- **Gastos extraordinarios** (tipo nuevo en "Agregar gasto"): cada uno se **paga con el fondo** (`VARIABLE_FR`: no se cobra y se descuenta del saldo) o queda **pendiente** y se cobra en las expensas siguientes (`EXTRAORDINARIO`: no toca el fondo). Botón para cambiar el modo mientras la liquidación que lo cobra esté abierta (recalcula).
- **Saldo del fondo** = saldo inicial + aportes liquidados − gastos pagados con el fondo (`get_resumen_fondo()`). Campos nuevos en Configuración → Fondo de Reserva: saldo inicial y mes.
- **Liquidación:** la tarjeta del fondo muestra el saldo disponible (antes, solo el aporte del mes); paneles nuevos con el desglose de las expensas y la cuenta del fondo (anterior + aporte − usado = saldo) y aviso de extraordinarios pendientes.
- **Gastos:** desglose ordinarios / aporte / base ordinaria / extraordinarios a cobrar / total a repartir; tabla de extraordinarios con su modo; saldo del fondo.
- **PDF resumen:** gastos rotulados por tipo, total a repartir, fondo en el estado financiero, tabla de pagados con el fondo. **Plano:** saldo disponible (antes "acumulado pendiente de cobro").
- Pagar una factura marcada **extraordinaria** crea el gasto como extraordinario a cobrar (antes, con la categoría de la factura como tipo, mezclado con los ordinarios).
- **Migración automática** (una vez por proceso y consorcio, auditada): gastos cobrados como ordinarios cuya factura se pagó con el fondo (categoría FONDO_RESERVA, mismo mes e importe) pasan a "pagado con el fondo" y se recalcula su liquidación si está abierta.
- Pruebas: `docs/pruebas_realizadas.md` y `pruebas/probar_fondo_reserva.py`, `pruebas/diagnostico_fondo.py`.

---

#### v5.9-0611 — Documentación de pruebas

**Lanzamiento:** 6 de noviembre

**Cambios:**

- `docs/pruebas_realizadas.md`: entorno de pruebas y resultados (con tablas) de las pruebas de v5.6 (libre deuda), diagnóstico del switch de interés, v5.7 y v5.8 (fecha del sistema).
- `pruebas/`: scripts para repetirlas contra la base de prueba (`entorno_prueba.py`, `diagnostico_intereses.py`, `probar_switch_interes.py`, `probar_libre_deuda.py`, `probar_fecha_sistema.py`).
- Regla en `CLAUDE.md` y en la memoria: registrar las pruebas de cada cambio.
- Sin cambios en la app.

---

#### v5.8-0611 — Fecha del sistema como vista (sin pagos posteriores, sin guardar)

**Lanzamiento:** 6 de noviembre

**Cambios:**

- Con fecha del sistema fijada, los **pagos con fecha posterior no se cuentan**: la unidad aparece pendiente (con su mora si ya venció) y una nota "pagó el DD/MM/AAAA". Antes, fijando 06/10 octubre aparecía todo "Pagado" por pagos del 03/11.
- La simulación es **solo de lectura** (`get_liquidacion(simular=True)` → `_simular_a_fecha()`): liquidación, estado de cuenta, plano, PDF resumen, libre deuda y el switch muestran los valores a esa fecha, pero la base **no se modifica**. Reemplaza el "recalcular y guardar" de la v5.7.
- Lo que escribe usa siempre datos y fecha reales: generar liquidación, pagos, pago completo, switch (guarda con fecha real y muestra el simulado). Los recibos firmados y su verificación usan los datos reales.
- Al fijar o quitar la fecha se normalizan los intereses guardados de las liquidaciones abiertas con la fecha real (corrige lo que haya guardado la v5.7 con una fecha fijada).

---

#### v5.7-0611 — Fecha del sistema (intereses calculados a una fecha)

**Lanzamiento:** 6 de noviembre

**Cambios:**

- La "Fecha Simulada" de la Zona de Pruebas pasa a ser la **Fecha del sistema**, con su propia tarjeta arriba de todo en Configuración. Con una fecha fijada la app trabaja como si hoy fuera ese día: intereses y mora (vencimiento), período actual, fechas sugeridas de pagos/caja/facturas/presupuestos, libre deuda y la marca "Generado el" de los PDFs. El vencimiento de checkpoints sigue con la fecha real (borra archivos).
- La fórmula de interés no cambia: la fecha solo decide si ya pasó el vencimiento.
- Al fijar o quitar la fecha se **recalculan los intereses de todas las liquidaciones abiertas** (`recalcular_intereses_abiertas()`), respetando el switch "sin interés" de cada unidad; las cerradas no se tocan.
- Aviso visible mientras está fijada: franja amarilla bajo la barra superior en todas las páginas y etiqueta con la fecha en la barra.
- Fix: guardar el formulario principal de Configuración borraba la fecha (y cualquier dato que ese form no mandaba). Ahora cada form solo actualiza sus campos.

---

#### v5.6-0611 — Certificado de libre deuda

**Lanzamiento:** 6 de noviembre

**Cambios:**

- Unidades: botón por unidad para emitir un **certificado de libre deuda** (PDF). Solo se habilita si la unidad tiene pagada en TOTAL la última liquidación emitida (abierta o cerrada); si no, el botón aparece deshabilitado con el monto adeudado. La validación se repite en el servidor.
- Datos del certificado: número correlativo por consorcio, unidad, titular, "sin deuda hasta el período X inclusive", solicitante, destino, validez en días (sugerida desde Configuración → Libre Deuda, default 30), firma con el campo *Administrador*.
- Tabla nueva `libres_deuda` (creada sola con `ensure_libres_deuda()`, auditada). Listado de emitidos en Unidades, con PDF y opción **Anular** (solo admin).
- Verificación pública por QR: `/libre-deuda/verificar/<consorcio>/<numero>/<codigo>` (HMAC con `clave_firma` sobre los datos registrados). Muestra válido / vencido / anulado / inválido.

---

## Decisiones de diseño importantes

### Por qué se migró de Excel a PostgreSQL (v1 → v2)

Excel funcionó bien como prototipo pero mostró sus límites al escalar:

- **Multiusuario:** Excel no soporta escrituras concurrentes sin riesgo de corrupción
- **Multi-consorcio:** Manejar N consorcios con N archivos Excel se vuelve inmanejable
- **Acceso remoto:** No es posible deployar un sistema basado en archivos locales en la nube
- **Seguridad:** Sin autenticación ni control de acceso por rol
- **Integridad referencial:** Excel no tiene claves foráneas ni transacciones atómicas

Supabase fue elegido por su capa gratuita generosa, su interfaz web para inspección de datos, soporte a PostgreSQL estándar y fácil integración con Python via `psycopg2`.

### Por qué el Fondo de Reserva se separó de los gastos ordinarios (v4.0)

El Fondo de Reserva es un concepto contable distinto: no se consume en el período actual sino que se acumula para imprevistos futuros. Sumarlo a los gastos ordinarios distorsionaba la cuota informada (hacía parecer que el costo mensual era mayor al real) y generaba confusión al rendir cuentas. La separación alinea el sistema con la práctica estándar de administración de consorcios en Argentina.

### Por qué la mora del primer mes se volvió manual (v4.7 → v5.0)

La regla automática "no cobrar mora en el primer mes de apertura" fue correcta en su origen, pero generó casos edge: ¿qué pasa si un consorcio ya existía antes de ingresar al sistema? ¿Qué pasa si se recrea un período de apertura? La solución más robusta es dar control explícito al administrador con el checkbox "sin interés", en lugar de inferir el comportamiento desde la estructura de datos.

### Por qué el running balance de Caja parte del saldo histórico (v4.6)

En un sistema de caja real, el saldo de hoy es la suma de todos los movimientos desde el inicio, no solo de la página visible. Mostrar el saldo desde cero en cada página era incorrecto contablemente y generaba confusión al auditar movimientos históricos.

---

*Documento generado el 2 de noviembre de 2026. Actualizar con cada nueva versión.*
