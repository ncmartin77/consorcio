# Pendientes

Lo que se dejó para después, con el motivo. Actualizar al cerrar cada sesión de trabajo:
agregar lo nuevo, tachar (borrar) lo resuelto.

Última actualización: 12/11/2026.

---

## Carril B — plataforma nueva (esta carpeta, rama `feat/plataforma`)

### Etapa 1 — Plataforma y seguridad (casi completa)

- [ ] **MFA para perfiles administrativos** (TOTP). Lo pide el documento v0.1, sección 6. Se dejó para avanzar con la etapa 2.
- [ ] **Gestión de usuarios desde la API**: cambiar y recuperar contraseña, desactivar usuarios, invitar a una administración. Hoy solo existe el alta por línea de comandos (`make usuario`).
- [ ] **Roles y permisos finos**: el documento prevé las tablas `roles`, `permisos` y `accesos_consorcio` (acceso por consorcio y por unidad). Hoy hay tres roles fijos en `membresias`: `admin`, `operador` y `consulta`.
- [ ] **Lectura de la auditoría** para administradores, con un rol o vista aparte. Hoy la aplicación solo puede insertar.
- [ ] **Límite de intentos de login**: es en memoria y sirve para una sola instancia de la API. Si hay varias, pasarlo a la base.

### Etapa 3 — Liquidaciones (en curso)

- [x] Motor de expensas puro y pruebas (`internal/expensas`).
- [ ] Guardar gastos, proveedores, liquidaciones y cuenta corriente en la base (migración `00004`).
- [ ] API de liquidación: borrador → calculada → aprobada → emitida, con snapshot.
- [ ] PDF de la liquidación (worker).
- [ ] Comparar contra el sistema actual: cada diferencia tiene que explicarse con una decisión.
- [x] Revisar las decisiones contra la última versión del sistema actual (v10.1): hecho el 10/11, ver "Revisión del 10/11" en `docs/decisiones-liquidaciones.md`.
- [ ] En la base: tasas de mora con vigencia y fundamento, clasificación de gastos (naturaleza, habitualidad, financiación y respaldo), reapertura auditada y libro del fondo de reserva.

### Etapa 2 — Inmuebles y personas (hecha; quedó afuera)

- [ ] **Coeficientes que no suman 100 %**: la plataforma exige exactamente 100 %. En el sistema actual, el grupo GENERAL de Edificio Brasil suma **100,001 %**. Al migrar (B5) hay que decidir entre ajustar una unidad o aceptar una tolerancia.
- [ ] **Corregir errores de carga**: un vínculo o una tabla de coeficientes cargados mal no se pueden anular; solo se cierran con fecha. Falta una "anulación" auditada. A propósito, no hay DELETE.
- [ ] **Titularidad**: no se controla que los porcentajes de los propietarios vigentes de una unidad sumen 100 %.
- [ ] **Faltan endpoints**: editar consorcios y grupos de prorrateo, y desactivar personas.
- [ ] **Listas sin paginar**: la búsqueda de personas corta en 200.
- [ ] **Migrar los datos del sistema actual** (B5):
  - Propietarios e inquilinos: hoy son texto en `unidades`; van a `personas` y `unidad_personas`.
  - Porcentajes por categoría: van a grupos y coeficientes con vigencia.
  - Teléfonos y mails de envío.

### Infraestructura

- [ ] **Proxy HTTPS (Nginx) delante de la API.** Al agregarlo:
  - Tomar la IP real de `X-Forwarded-For` solo si viene del proxy. Hoy no se usa `middleware.RealIP` a propósito.
  - La cookie ya sale `Secure` fuera de `APP_ENV=local`.
- [ ] **Frontend Vue 3 + TypeScript** (`web/`): no existe todavía.
- [ ] **Cola de trabajos del worker** (`trabajos_pendientes` con `FOR UPDATE SKIP LOCKED`): llega con la primera tarea real, por ejemplo los PDF de las liquidaciones.
- [ ] **Base de Supabase (`consorcio-tst`) inaccesible desde la red del Senado**: el pooler (puertos 5432 y 6543) está bloqueado y no se puede abrir. Por eso la base es local. Usar Supabase como base solo desde otra red.
- [ ] **`make up` y `make up-supabase` se pisan**: el último que se corre decide dónde van los archivos (S3 local o Supabase Storage).
- [ ] **Claves de Supabase Storage**: están solo en esta PC (`deploy/.env.supabase`, fuera de git). En otra PC hay que generarlas de nuevo en Supabase → Storage → S3 Connection.
- [ ] **Base `legado`**: es la copia de producción del 03/11. Para refrescarla, correr `scripts/restaurar_legado.sh <backup.dump.age>` con un backup nuevo.

### Decisiones de la sección 11 del documento v0.1

Tomadas el 06/11: ver `docs/decisiones-liquidaciones.md` (interés simple, mora del mes
como hoy pero con fecha guardada, imputación a intereses y después a lo más viejo, saldo
a favor, mayor resto, etc.). Siguen abiertas:

- [ ] Contabilidad general y cuenta separada del fondo de reserva (después del MVP).
- [ ] Traspaso de consorcios entre administraciones (después del MVP).
- [ ] Roles exactos y portal de propietarios (después del MVP).
- [ ] Integración bancaria (después del MVP; en el MVP los pagos se cargan a mano con referencia única).

---

## Carril A — sistema actual (Flask, en producción en Render)

- [x] Base local de pruebas `consorcio_pruebas` (10/11): copia del 03/11 en el Postgres local, con usuario propio. Ver la bitácora.
- [x] Correr las pruebas de la v10.1 contra la base local (11/11): ninguna falla es del código. Ver `docs/pruebas_realizadas.md` (v10.2) en la rama `feat/lineamientos-v10`.
- [x] Actualizar las 6 pruebas viejas del sistema actual (11/11, v10.3): ahora usan un escenario propio y las 16 pruebas dan OK.
- [x] **Merge a `master` y deploy en Render** (12/11): `master` pasó de la v9.7 a la **v11.0-1211** (incluye v9.8 seguridad, v10.x lineamientos y v11.0 Storage). `SECRET_KEY` confirmada en Render por el usuario.
  - [x] Confirmado por el usuario en la app: dice **v11.0-1211** (12/11).
  - [ ] Limpiar el consorcio temporal "Prueba v10 lineamientos" de `consorcio-tst` (en la base local no quedó).
- [ ] **Nunca subir ni mergear la rama `supabase-storage`.** En la PC original tiene un commit con claves (`6495413`). La migración a Storage quedó planeada para una versión mayor futura.

- [x] **Archivos en Supabase Storage** (12/11, v11.0, rama `feat/storage-v10` en GitHub, sin merge): comprobantes y adjuntos van a un bucket privado. Las pruebas dieron OK en disco, en el S3 local y en `consorcio-tst`. Ver la bitácora.
- [x] **Storage activo en producción** (12/11): bucket privado `comprobantes` en el Supabase de producción, clave S3 propia y las cinco variables `STORAGE_S3_*` en Render (las cargó el usuario). Se adjuntó un comprobante, se vio, y después de un deploy manual se siguió viendo.
- [ ] **Subir a Storage los comprobantes viejos** que están en el disco de Render, si es que quedó alguno (Render borra el disco en cada deploy, así que puede que no quede nada). Hay que revisarlo desde una red que llegue a la base de producción: `facturas.archivo_pdf` con ruta y sin archivo.
- [x] **Borrar archivos** (12/11, v11.1, rama `feat/borrar-archivos` en GitHub, **sin merge**). El usuario decidió que se puedan borrar:
  - quitar el comprobante de una factura;
  - al reemplazarlo o eliminar la factura, se borra el archivo;
  - al eliminar un consorcio, se borran todos sus archivos.
- [ ] **Merge de la v11.1 a `master`** (= deploy), cuando el usuario lo decida.
- [ ] **Adjunto de notificación de la v6.0 en `consorcio-tst`:** `notificaciones/38f0f808d87c.pdf` (formato viejo, sin la carpeta del consorcio). Es de prueba; se puede borrar.
- [ ] **Flask en Docker** (rama local `feat/docker-flask`, sin push): `Dockerfile`, `compose.yaml` y `ProxyFix`. Está trabado porque desde esta red no se llega a la base de Supabase.
- [x] **Contraseña de la base de producción cambiada** (12/11, el usuario, en Supabase y en `DATABASE_URL` de Render). Se revisó el historial de GitHub: no tiene contraseñas reales, solo ejemplos.
  - [ ] En la PC original: borrar `gen_nov.py` y el tar.gz viejo, y actualizar `ORIGEN_DATABASE_URL` en `.env.local` si se usa.
- [ ] **Importes exactos** (paso A3 del plan): pasar `pg_db.py` de `float` a `Decimal`.
- [ ] **Confirmar en Render** que el tilde "sin interés" (v5.2) responde rápido.
- [ ] **Rama `feat/entorno-local`**: tiene el backup diario cifrado (GitHub Actions) y el entorno local. Está en GitHub, pero sin merge a `master`.
