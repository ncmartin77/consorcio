# Historial de Versiones — Sistema de Gestión de Consorcio

**Proyecto:** App Flask + PostgreSQL (Supabase) para administración de consorcios  
**Repositorio:** github.com/ncmartin77/consorcio  
**Deploy:** Render.com  
**Versión actual:** 5.5-0411

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
**Versión actual**

**Cambios:**

- `docs/memoria_claude/`: copia de las notas de memoria de Claude de la PC original (consorcio), con contraseñas, tokens y emails reemplazados por `***`.

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
