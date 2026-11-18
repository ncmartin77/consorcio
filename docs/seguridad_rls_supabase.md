# Incidente de seguridad: base de datos expuesta por la API de Supabase

**Fecha de detección y corrección:** 18/11/2026 · **Versión del arreglo:** 11.5-1811 · **Estado:** corregido en producción y en `consorcio-tst`

---

## Resumen

Toda la base de datos de producción (25 tablas: usuarios, permisos, pagos, caja, liquidaciones,
log de auditoría, configuración…) se podía **leer y modificar desde internet sin iniciar sesión**,
usando solo la clave pública del proyecto Supabase. Se cerró el mismo día, sin cambios para los
usuarios y sin interrumpir la app.

## Qué problema había

### Cómo funciona Supabase

Además de la base PostgreSQL, Supabase publica automáticamente el esquema `public` como una
**API REST** (`https://<proyecto>.supabase.co/rest/v1/<tabla>`) y una API GraphQL. Para usarla
alcanza con la **clave anon/publishable**, que **no es secreta**: está pensada para ir dentro de
una página web. Lo que decide qué filas puede ver o tocar quien usa esa clave es **RLS**
(Row Level Security, seguridad por filas) más los permisos de los roles `anon` (sin sesión) y
`authenticated`.

### Qué pasaba en el sistema

- La app **no usa** esa API: Flask se conecta directo a Postgres con el usuario `postgres`
  (`DATABASE_URL`). Por eso nunca se pensó en ella.
- `pg_db.py` crea las tablas con `CREATE TABLE IF NOT EXISTS` en el esquema `public`. Supabase
  les da por defecto **todos los permisos** a `anon` y `authenticated`.
- **Ninguna tabla tenía RLS activado.**

Resultado: con la clave pública, cualquiera podía hacer `GET`, `POST`, `PATCH` y `DELETE` sobre
todas las tablas. Se comprobó con un pedido real (pidiendo solo el conteo, sin traer datos):

```
GET /rest/v1/usuarios   (solo con la clave pública)   →  HTTP 200, 3 filas
```

El Security Advisor de Supabase lo marcaba como **ERROR** (`rls_disabled_in_public`, 25 tablas).
Además había un aviso menor: la función del log de auditoría `audit_registrar()` tenía el
`search_path` sin fijar (`function_search_path_mutable`).

### Qué agravaba el riesgo

- **El repositorio es público** y la documentación nombra el proyecto Supabase, así que se sabía
  a qué proyecto apuntar.
- La tabla `config` guarda la `clave_firma` (HMAC de los QR de recibos) y `usuarios` /
  `permisos_consorcio` controlan quién es administrador: con acceso de escritura se podía, por
  ejemplo, activar una cuenta propia como admin.

### ¿Lo usó alguien?

En los logs de las últimas 24 h no hubo ningún pedido a `/rest/` ni a `/graphql/`. Supabase no
permite consultar más atrás en una sola ventana, así que **no se puede descartar** un acceso
anterior.

## Cómo se arregló

### 1. En la base (prueba primero, después producción)

Se aplicó este SQL, primero en `consorcio-tst` y, ya verificado, en producción (SQL Editor del
dashboard):

```sql
-- RLS en todas las tablas de public, sin políticas: nadie entra por la API
do $$
declare t record;
begin
  for t in select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'public' and c.relkind in ('r','p') loop
    execute format('alter table public.%I enable row level security', t.relname);
  end loop;
end $$;

-- Quitar los permisos de los roles de la API (también para las tablas futuras)
revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated, public;
alter default privileges for role postgres in schema public revoke all on tables    from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on functions from anon, authenticated, public;

-- Aviso menor del Advisor
alter function public.audit_registrar() set search_path = public, pg_temp;
```

**Por qué no afecta a la app:** Flask se conecta como `postgres`, que es dueño de las 25 tablas y
además tiene `BYPASSRLS`. RLS y los `REVOKE` solo afectan a los roles de la API.

### 2. En el código (v11.5, para que no vuelva a pasar)

- **`pg_db.ensure_rls()`** (nueva): una vez por proceso, activa RLS en toda tabla de `public` que
  no lo tenga y, si existen los roles de Supabase, repite los `REVOKE`. Cubre las tablas que la app
  crea sola más adelante (por ejemplo las del módulo Obras, que todavía no existen en la base). En
  un Postgres local sin los roles `anon`/`authenticated`, esa parte se saltea.
- **`app.py`**: `before_request` llama a `ensure_rls()` al final de los `ensure_*`, en su propio
  `try`, así corre aunque falle alguno anterior.
- **`audit_registrar()`**: el `SET search_path = public, pg_temp` va dentro del
  `CREATE OR REPLACE FUNCTION`. Si no, `ensure_auditoria()` recrearía la función en cada arranque
  y borraría el arreglo hecho en la base.
- El SQL de `ensure_rls()` no usa `%` (psycopg2 lo interpretaría como parámetro): usa
  `quote_ident()`.

### 3. Orden de publicación

Como el repo es público, el commit con la explicación se dejó **local** hasta que producción
estuvo cerrada y verificada; recién después se hizo push (rama `seguridad/rls-supabase`).

## Verificación

| Verificación | Antes | Después (tst y producción) |
|---|---|---|
| Tablas de `public` con RLS | 0 / 25 | **25 / 25** |
| Tablas accesibles por `anon` / `authenticated` | 25 | **0** |
| `GET /rest/v1/usuarios`, `config`, `pagos`, `audit_log` con la clave pública | 200 | **401** `permission denied` |
| `POST /rest/v1/config` con la clave pública | posible | **401** |
| Security Advisor | 1 ERROR + 1 WARN | solo INFO `rls_enabled_no_policy` (es lo buscado) |
| Rol de la app (`postgres`) | 25 tablas | **25 tablas, sin cambios** |
| Prueba con rollback en tst: leer 25 tablas, insert/update/delete en `tareas`, trigger de auditoría | — | **OK**: 25 leídas, update 1 fila, 3 registros en `audit_log` |
| App en Render (`/login`, `/verificar`) | — | **200** |

Detalle en [`pruebas_realizadas.md`](pruebas_realizadas.md) (v11.5-1811).

## Decisiones

- **No se rota la `clave_firma`.** Rotarla eliminaría el riesgo de recibos falsificados si alguien
  la leyó antes del arreglo, pero invalidaría los QR de todos los recibos ya emitidos. Decisión del
  usuario: dejarla.

## Pendientes

- Correr la suite de `pruebas/` con el código v11.5 contra `consorcio-tst` y mergear
  `seguridad/rls-supabase` a `master`.
- Opcional: desactivar la Data API en el dashboard (Integrations → Data API), ya que la app no
  la usa.
- Revisar por qué las tablas del módulo Obras (`obras`, `presupuestos_obra`, `cuotas_obra`) no
  existen en ninguna base aunque la v11.3 está desplegada (¿`ensure_obras()` falla en silencio?).

## Cómo revisarlo de nuevo

En el SQL Editor de Supabase:

```sql
select count(*) total,
  count(*) filter (where c.relrowsecurity) con_rls,
  count(*) filter (where has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE')) anon_con_acceso
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r','p');
-- Esperado: total = con_rls, anon_con_acceso = 0
```

y Dashboard → Advisors → Security: no tiene que aparecer `rls_disabled_in_public`.
