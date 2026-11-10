# Bitácora de la plataforma nueva (carril B)

Qué se hizo, qué se decidió y por qué, por fecha. Lo más nuevo va primero.

Documentos relacionados:
- `docs/decisiones-liquidaciones.md`: reglas de cálculo acordadas para la etapa 3.
- `PENDIENTES.md`: lo que quedó para después.
- `~/Descargas/resumen_sistema_consorcios_v0_1.md` (fuera del repo): diseño original v0.1.
- `plan-consorcio.html` (raíz de `~/consorcio`, sin versionar: está solo en esta PC): plan con los carriles A y B.

---

## 10/11/2026

### Base local para probar el sistema actual (v10.1)

**Por qué:** las pruebas del sistema actual (`pruebas/probar_*.py`) solo corren contra Supabase `consorcio-tst`, y desde la red del Senado no se llega a esa base. Varias pruebas de la v10 se cortaron por eso.

**Qué se hizo**
- **`scripts/restaurar_legado.sh` acepta `BASE=` y `DUENO=`:** restaura la copia cifrada en cualquier base local, con un usuario dueño que no es superusuario. Nunca toca `consorcios` (la base de la plataforma) ni Supabase.
- **Base `consorcio_pruebas` creada** en el Postgres local (`127.0.0.1:55433`), con la copia del 03/11: 21 tablas y las mismas filas que `legado`.
  - Usuario `consorcio_pruebas`: dueño de su base y de sus 21 tablas, sin superusuario, sin crear bases ni saltear RLS.
  - Desde ese usuario se ve su base, pero no las tablas de `legado` (permiso denegado).
  - Conexión probada por TCP, como lo haría la app Flask. La clave es `pruebas-local`, solo para desarrollo.

**Para volver a crearla** (borra y recrea solo `consorcio_pruebas`):
```
BASE=consorcio_pruebas DUENO=consorcio_pruebas scripts/restaurar_legado.sh ../backups/consorcio_20261103_1504/
```

**Falta para correr las pruebas de la v10.1 acá:** ver `PENDIENTES.md`, carril A.

### Volver a descargar y tomar la última versión como referencia

**Qué se hizo**
- **Copia local actualizada sin borrar nada.** Las claves (`.env`, `deploy/.env.supabase`), el backup cifrado, `plan-consorcio.html` y las ramas locales siguen donde estaban.
- **Trabajo sin subir del 06/11:** el motor y la bitácora se subieron a `feat/plataforma`.
- **`master` local actualizado a la v9.7:** en GitHub tenía 25 commits nuevos (del 06 al 08/11, de la 5.5 a la 9.7).
- **`master` traído a `feat/plataforma`:** sin conflictos y con las pruebas en verde.
- **La última versión no estaba en `master`:** es la **v10.1, en la rama `feat/lineamientos-v10`** (09/11), que todavía no se mergeó. Se descargó como rama local.
- **Revisión de reglas:** se leyeron el historial y el código de la v10.1 (`pg_db.py`: interés, tasas, cierre, clasificación de gastos y fondo) y se compararon con las decisiones del 06/11.

**Decisiones del usuario**
1. **Trabajar sobre la última versión disponible (v10.1).** Para la mora del mes, eso significa **sin mora del mes**, como el sistema actual desde la v9.0. Reemplaza la decisión del 06/11.
2. **Interés simple, sobre el capital:** se confirma. Coincide con el "interés sin capitalizar" de la v10.
3. **Reabrir una liquidación cerrada:** se permite si no tiene pagos, la siguiente no está cerrada y lo hace un administrador. Reemplaza "emitida = inmutable".

**Se adopta de la v10.1**
- tasa de mora con vigencia y fundamento, congelada al cerrar
- clasificación de gastos: naturaleza, habitualidad, financiación y respaldo
- extraordinarios a cobrar en una línea aparte
- los gastos pagados con el fondo no se cobran
- libro del fondo de reserva

**Cambios en el motor**
- Sin mora del mes.
- Línea `Extraordinaria`.
- La base del interés queda documentada como "capital impago a la fecha de cierre".
- 10 pruebas en verde.

**Para tener en cuenta**
- La memoria de la v10 avisa que, en la PC original, la rama `supabase-storage` tiene un commit (`6495413`) con `.env.local` y claves. **Esa rama no se sube ni se mergea.** El commit local de esta PC (`b231ea9`) no tiene claves, pero tampoco se sube.
- La v10.1 dejó pruebas para repetir antes de mergearla a `master`. Están en su `docs/memoria_sesion_claude.md` ("DONDE QUEDAMOS"); son del carril A.

---

## 06/11/2026

### Etapa 3: motor de expensas (sin base de datos todavía)

**Qué se hizo**
- Nuevo paquete `internal/expensas`, de código puro: recibe gastos, coeficientes, deudas, tasas y fechas, y devuelve los cargos de cada unidad. No toca la base ni HTTP, así cada regla se prueba con números exactos.
  - `motor.go`:
    - Prorrateo por grupo con redondeo por **mayor resto**.
    - Fondo de reserva y cargos particulares.
    - Interés **simple** sobre el capital vencido.
    - **Mora del mes** con fecha de cálculo fija.
    - Condonación.
    - Saldo anterior con signo (positivo es deuda, negativo es saldo a favor).
  - `imputacion.go`: reparte un pago **primero a intereses** y después al capital, siempre del más viejo al más nuevo. Lo que sobra queda **a favor**.
- 8 pruebas del motor (17 casos):
  - el ejemplo del documento v0.1 (1.000.000 con 15/20/25/40 %)
  - tercios con centavos
  - empates de redondeo
  - notas de crédito
  - varios grupos
  - interés simple contra compuesto (500 contra 530)
  - deuda inicial sin interés
  - mora antes y después del vencimiento
  - saldo a favor
  - imputación en orden y sobrante
  - errores de entrada, entre ellos coeficientes que suman 100,001 %

**Qué falta de la etapa 3:** guardar gastos, liquidaciones y cuenta corriente en la base; la API (borrador → calculada → aprobada → emitida); el snapshot; el PDF; y comparar contra el sistema actual. Ver `PENDIENTES.md`.

### Decisiones de liquidación (sección 11 del documento v0.1)

Se repasó cómo liquida hoy el sistema actual (`pg_db.py`) y la configuración real de la copia del 03/11:
- Perú 376: mora del 5 %, fondo de reserva de 150.000.
- Brasil: mora del 7 %, fondo de reserva de 85.000.
- En los dos, el vencimiento es el último día del mes.

**Decidido por el usuario:**
1. **Interés simple** sobre el capital, no compuesto como hoy.
2. **Mora del mes como hoy**, pero con la fecha de cálculo guardada en la liquidación.
3. **Imputación: primero intereses, después lo más viejo** (art. 903 CCyC).
4. **Saldo a favor** cuando alguien paga de más. Hoy el excedente se pierde.

**Propuestas aceptadas:**
- mes vencido
- prorrateo por grupo
- mayor resto
- tasa y vencimiento por consorcio con vigencia
- condonación y bonificación auditadas
- cuenta corriente como única fuente del saldo
- sin facturación electrónica en el MVP

El detalle está en `docs/decisiones-liquidaciones.md`.

**Consecuencia:** al comparar con el sistema actual, los números no van a coincidir donde haya intereses arrastrados, pagos de más o redondeo. Está previsto así. Cada diferencia tiene que explicarse con una decisión; si no se explica, es un error.

### Etapa 2: inmuebles y personas

**Qué se hizo**
- **Migración `00003`:**
  - Tablas: `unidades`, `personas`, `unidad_personas` (vínculos), `grupos_prorrateo` y `unidad_coeficientes`.
  - Todas con `administracion_id`, RLS forzado y claves foráneas compuestas: nada puede quedar asociado a otro consorcio ni a otra administración.
- **API** bajo `/api/v1/administraciones/{id}/`: unidades, personas, vínculos (vigentes a una fecha o historial), grupos y tablas de coeficientes.
- **`internal/platform/api`:** ayudante común que verifica permisos por rol, abre la transacción con RLS, registra la auditoría en la misma transacción y traduce los errores de la base (409, 404, 400).
- **Tipo `fecha.Fecha`:** las fechas viajan como `"2026-11-01"`.
- **Porcentajes:** con `decimal.Decimal`, nunca `float`.
- **Pruebas por HTTP:**
  - validaciones
  - historia de vínculos (Ana vende a Juan el 01/07)
  - vigencias de coeficientes
  - el rol consulta no puede escribir
  - **14 intentos de la administración B de leer o escribir datos de A**: todos dan 404

**Decisiones**
- **Personas separadas de los usuarios:** un propietario no necesita iniciar sesión. Las personas pertenecen a la administración, así que una persona puede tener unidades en varios consorcios.
- **Vínculos con fechas `[desde, hasta)`:** no se borran, se cierran. La base no permite dos vínculos iguales con fechas superpuestas.
- **Tablas de coeficientes:** una tabla nueva rige desde una fecha y cierra la anterior, que queda guardada. Tiene que sumar **exactamente 100 %**.
- **Sin DELETE en vínculos ni coeficientes:** la historia no se pierde.
- **Hallazgo:** en el sistema actual, el grupo GENERAL de Edificio Brasil suma **100,001 %**. Va a haber que ajustarlo al migrar (anotado en `PENDIENTES.md`).

### Pendientes y memoria

- `PENDIENTES.md`, con todo lo que quedó para después, de los carriles A y B (pedido del usuario).
- La memoria de Claude tiene el estado del proyecto y las restricciones de red de esta PC.

---

## 05/11/2026

### Etapa 1: sesiones, auditoría y alta de usuarios

**Qué se hizo**
- **Migración `00002`:**
  - `sesiones`: solo guarda el SHA-256 del token.
  - `auditoria`: de solo agregado. La aplicación inserta, pero no lee, no cambia ni borra.
- **Login y logout** en `/api/v1/sesion`, y `GET /api/v1/me`:
  - Contraseñas con Argon2id, con los parámetros que recomienda OWASP; mínimo 12 caracteres.
  - Cookie HttpOnly y SameSite=Lax; además `Secure` fuera del entorno local.
  - La sesión vence a las 12 h, o a las 2 h sin uso.
- **Protección contra pedidos desde otros sitios (CSRF):** los cambios exigen el encabezado `X-Requested-With`.
- **Límite de intentos:** 10 fallos por IP en 15 minutos. Un email inexistente tarda lo mismo en responder que uno registrado.
- **Alta de usuarios:** `make usuario`. La contraseña se pide sin mostrarla y nunca va como argumento.
- **Worker:** borra las sesiones vencidas.

**Decisiones**
- **Sin `middleware.RealIP`:** confiaría en `X-Forwarded-For` de cualquiera. Se agrega cuando haya un proxy confiable.
- **El MFA queda para después**, para avanzar con la etapa 2.

### Archivos en S3 (SeaweedFS local o Supabase Storage)

**Qué se hizo**
- **Paquete `internal/platform/archivos`:** subir, bajar, consultar y borrar por la API S3.
  - Toda clave queda bajo `adm/<administracion_id>/`.
  - Se rechazan rutas con `..`, `/` o caracteres raros.
- **Comandos:** `make up-supabase` y `make test-supabase`. Usan `deploy/.env.supabase`, que está fuera de git.
- **Probado contra Supabase Storage** (`consorcio-tst`, bucket privado `plataforma`).

**Decisiones**
- **aws-sdk-go-v2 en lugar de minio-go:** Supabase pone la API S3 en una ruta (`/storage/v1/s3`), y minio-go no lo soporta.
- **Sin checksums CRC:** se desactivaron porque Supabase no los acepta.

### Docker local y copia de los datos

**Qué se hizo**
- El esqueleto de `plataforma/` corre en Docker: Postgres 17, migraciones, API y worker.
- Arreglos del esqueleto para que arranque:
  - faltaba `go.sum`
  - la API pasó al puerto **18080**, porque el 8080 lo usa `glpi-chat-app`
  - el caché de módulos de Go no tenía permisos de escritura
  - había una prueba que mandaba dos sentencias en una sola llamada
- **Copia del sistema actual:** la copia cifrada del 03/11 se restauró en la base local `legado` con `scripts/restaurar_legado.sh`. Trajo 21 tablas. El dump se descifra directo dentro del contenedor y nunca queda sin cifrar en disco.
- **Rama `feat/plataforma`:** sale de `master`, sin mezclarse con los cambios de Flask. Está en GitHub.

**Decisiones**
- **Base local en lugar de Supabase:** la red del Senado bloquea el pooler de Supabase (puertos 5432 y 6543) y no se puede abrir. Supabase Storage sí funciona, porque va por HTTPS.
- **Render no se toca por ahora.**
- **Rama `feat/docker-flask`:** el trabajo de Docker para la app Flask quedó ahí, local y sin push. Es del carril A.

### Carril A (sistema actual): lo que quedó hecho

- **Rama `supabase-storage`:** quedó en la versión 6.0-0511, con el commit **solo local, sin push**. No va a Render por ahora.
- **`master` y Render:** no se tocaron.
