# Pendientes

Lo que se dejó para después, con el motivo. Actualizar al cerrar cada sesión de trabajo:
agregar lo nuevo, tachar (borrar) lo resuelto.

Última actualización: 10/11/2026.

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
- [ ] **Revisar `docs/decisiones-liquidaciones.md` contra la v9.7 del sistema actual.** Entre el 06 y el 08/11 se subieron a `master` 25 commits (de la 5.5 a la 9.7), con cambios de reglas: saldo a favor, interés decidido al cerrar con un switch por unidad, cobranza sobre la liquidación cerrada, fondo de reserva igual al saldo de caja del mes anterior, entre otros.

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

- [ ] **Archivos en Supabase Storage (v6.0)**:
  - El código está listo y probado en la rama `supabase-storage`.
  - El commit `b231ea9` (versión 6.0-0511) está **solo en local, sin push**.
  - **No va a Render por ahora**, por decisión del 05/11.
- [ ] **Flask en Docker** (rama local `feat/docker-flask`, sin push): `Dockerfile`, `compose.yaml` y `ProxyFix`. Está trabado porque desde esta red no se llega a la base de Supabase.
- [ ] **Cambiar la contraseña de la base de producción**: quedó expuesta en `gen_nov.py`, en un tar.gz viejo y en un chat. Después, actualizar `DATABASE_URL` en Render y borrar `gen_nov.py`.
- [ ] **Importes exactos** (paso A3 del plan): pasar `pg_db.py` de `float` a `Decimal`.
- [ ] **Confirmar en Render** que el tilde "sin interés" (v5.2) responde rápido.
- [ ] **Rama `feat/entorno-local`**: tiene el backup diario cifrado (GitHub Actions) y el entorno local. Está en GitHub, pero sin merge a `master`.
