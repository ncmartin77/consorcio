# Memoria de Sesion — Sistema de Gestión de Consorcio

> Leer al inicio de cada sesion de Claude Code (o Claude Desktop) para tener contexto inmediato sin explorar el codigo.
> **Ultima actualizacion: 04/11/2026.** Primero leer "Estado al 04/11/2026" y "Proximos pasos".

---

## Datos del proyecto

| Campo | Valor |
|---|---|
| **Proyecto** | Sistema de gestión de consorcios de edificio |
| **Stack** | Flask + PostgreSQL (Supabase) + Supabase Storage + Jinja2 + Bootstrap 5 |
| **Repo** | https://github.com/ncmartin77/consorcio (**publico**; rama de produccion: `master`) |
| **Deploy** | https://consorcio-soo4.onrender.com (Render.com free tier, **auto-deploy en cada push a `master`**) |
| **Directorio local** | WSL Debian `/home/norberto/consorcio` (desde Windows: `\\wsl.localhost\Debian\home\norberto\consorcio`) |
| **Git en WSL** | `"/mnt/c/Program Files/Git/bin/git.exe"` (siempre con ruta completa) |
| **Version en produccion** | `5.5-0411` (en `version.txt` de `master`) |
| **Supabase PRODUCCION** | Project ID `eboskxnitazzwfobwkiq` (ojo: notas viejas decian `eboskmenitazzwfobwkiq`, era un error de tipeo), region ca-central-1. Pooler: `aws-1-ca-central-1.pooler.supabase.com:6543`, usuario `postgres.eboskxnitazzwfobwkiq` |
| **Supabase PRUEBA** | Proyecto `consorcio-tst`, ID `rbwjkgqvfaxxvcwaywtj`, region us-east-1. Pooler: `aws-0-us-east-1.pooler.supabase.com:6543`, usuario `postgres.rbwjkgqvfaxxvcwaywtj`. Bucket `comprobantes` (privado) ya creado |
| **Consorcios en DB** | Edificio Brasil y Peru 376 (`consorcio_id = '28693516'`) |
| **Usuario admin** | usuario id 1 en tabla `usuarios` (cuenta Google personal del usuario; es el `DEV_LOGIN_EMAIL` de las pruebas) |
| **MCP Supabase** | `~/.mcp.json` en WSL. El token cargado es rechazado (401 "JWT could not be decoded"): probablemente es una API key `sb_secret_*` y el MCP necesita un **Personal Access Token** (`sbp_...`, Supabase → Account → Access Tokens) |
| **Idioma de trabajo** | Espanol (responder siempre en espanol) |

---

## Archivos criticos

| Archivo | Rol |
|---|---|
| `app.py` | Rutas Flask |
| `pg_db.py` | Toda la logica y acceso a datos (PostgreSQL/Supabase) |
| `storage.py` | Archivos (comprobantes, adjuntos): Supabase Storage o disco local — **solo en rama `supabase-storage`** |
| `pdf_gen.py` | Generacion de PDFs |
| `version.txt` | Version actual — **incrementar en cada commit** |
| `templates/` | Plantillas Jinja2 + Bootstrap 5 |
| `copiar_esquema.py`, `correr_local.py`, `entorno_local.py`, `.env.local.ejemplo` | Entorno de pruebas local — **solo en rama `supabase-storage`** |
| `.env.local` | Claves de prueba + conexion read-only a produccion. **No versionado; existe solo en la PC original** |

---

## Reglas de trabajo

1. **Version** (`X.Y-DDMM`, DDMM = dia-mes del commit): menor en cada commit; **mayor solo ante cambios de fondo y consultando al usuario antes** (seccion "Versionado" en `CLAUDE.md`). Registrar cada version en `docs/historial_versiones.md`.
2. **Git siempre con ruta completa**: `"/mnt/c/Program Files/Git/bin/git.exe"`. En la PC original **no hay hook post-commit**: el push es manual. Verificar con `git log origin/master -1`.
3. **Push a `master` = deploy a produccion.** Cambios a probar: rama → prueba local → recien despues merge a `master` + push (seccion "Pruebas locales antes de subir" en `CLAUDE.md`).
4. **Nunca versionar secretos** (el repo es publico): `DATABASE_URL`, contraseñas, `sb_secret_*`, tokens van en `.env.local` / `.env` (en `.gitignore`) o en el dashboard de Render. Antes de cada commit, revisar el diff buscando claves.
5. **Nunca pedir ni escribir la contraseña de produccion en archivos**: el usuario la pega el mismo en `.env.local` (se saca de Render → consorcio → Environment → `DATABASE_URL`). Supabase no muestra la contraseña; resetearla rompe Render hasta actualizar `DATABASE_URL`.
6. El script suelto `gen_nov.py` (fuera de git) tiene la contraseña de produccion escrita y **usa el Project ID equivocado: nunca funciono**. No commitearlo; se puede borrar.

---

## Logica de negocio no obvia

- **Mes vencido**: la liquidacion del periodo P usa los gastos del periodo P-1. Si se editan gastos de septiembre, afecta la liquidacion de octubre.
- **Periodo de trabajo**: `session["periodo_trabajo"]` persiste en sesion. La ruta de gastos usa `_prev_periodo(periodo_trabajo)` automaticamente.
- **Patron `ensure_*()`**: para migraciones de columnas; se llaman en `before_request` pero ejecutan el `ALTER TABLE` **una sola vez por proceso** (helper `_ensure_columna()` en `pg_db.py`). Para una columna nueva, usar ese helper.
- **Toggle `sin_interes`**: NO regenera la liquidacion. `aplicar_sin_interes(periodo, valor, unidad=None)` recalcula solo interes/total/saldo en una transaccion. Calculo de interes compartido con `generar_liquidacion` via `_params_interes`, `_calcular_interes`, `_estado_pago` — si cambia la formula de mora, cambiarla ahi.
- **Archivos (rama `supabase-storage`)**: clave en Storage = `<consorcio_id>/<facturas.archivo_pdf>` para comprobantes (`archivo_pdf` sigue siendo `facturas/<proveedor>/<timestamp>.pdf`) y `notificaciones/<uid>.<ext>` para adjuntos. `_leer_comprobante()` busca en Storage y, si no esta, en la ruta vieja en disco. Bucket privado: la app descarga y sirve el archivo (nunca URL publica). Sin `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` → disco local `data/archivos/`.
- **Claves `sb_secret_*`** (nuevas de Supabase) van solo en el header `apikey` (no son JWT); las legacy `service_role` (JWT `eyJ...`) tambien en `Authorization: Bearer`. Probado OK contra `consorcio-tst`.
- **Login de prueba** (`/login/dev`): solo si `DEV_LOGIN_EMAIL` esta definida **y** el pedido viene de 127.0.0.1/::1 sin `X-Forwarded-For`. Busca el usuario por email; si no existe lo crea.
- **`factura_id` en caja**: FK que sincroniza facturas con movimientos de caja (delete en cascada).
- **`sin_interes`**: flag booleano en liquidaciones por unidad; se preserva al recalcular.
- **`get_facturas()`** / **`get_caja()`** devuelven tupla `(lista, total)` — no olvidar el unpacking.
- **`tojson` en `onclick`**: NO usar `{{ obj|tojson }}` dentro de atributos HTML con comillas dobles — usar atributos `data-*`.
- **FONDO_RESERVA**: `save_gasto` permite actualizar solo el importe.
- **`factura_en_liquidacion`**: usa `liq_esta_cerrada()`, NO `liquidacion_existe()`.

---

## Estado al 04/11/2026

### Migraciones
| Migracion | Estado |
|---|---|
| Base de datos Excel → PostgreSQL (Supabase) | ✅ **Hecha y en produccion** (desde octubre 2026) |
| Archivos (comprobantes de facturas, adjuntos de notificaciones) → Supabase Storage | 🟡 **Codigo listo y probado en local, NO aplicado en produccion** (rama `supabase-storage`) |

**Por que la de archivos:** en Render free el disco se borra en cada deploy y cada vez que el servicio "duerme" (~15 min sin uso). Los comprobantes subidos desaparecian. Al 04/11 **ninguna factura de produccion tenia comprobante**, asi que no se perdio nada. El logo ya se guardaba en la BD (`config.logo_b64`), no tiene el problema.

### Rama `supabase-storage` (solo en la PC original, sin push)
Commits sobre `master` (5.5-0411):
1. `feat: comprobantes y adjuntos en Supabase Storage` — `storage.py`, rutas `upload_comprobante`, `ver_comprobante`, `notificaciones_upload`, `notificaciones_ver`, `backup` (incluye comprobantes leyendo de Storage), `db.get_rutas_comprobantes()`.
2. `feat: entorno de pruebas local (Supabase de prueba) y login de prueba` — `correr_local.py`, `copiar_esquema.py`, `entorno_local.py`, `.env.local.ejemplo`, login de prueba, `.gitignore` (`.env`, `.env.local`), seccion en `CLAUDE.md`.
3. `fix: identificador correcto del proyecto Supabase de produccion`.
4. `fix(copiar_esquema): asociar secuencias a su columna y verificar ids`.
5. Actualizacion de esta memoria.

**Probado en local contra `consorcio-tst` (con copia de datos de produccion, 391 filas, 21 tablas, 14 secuencias OK):** login de prueba; adjuntar imagen a factura 31 de Peru 376 → convertida a PDF → en Storage → se ve con el boton azul → incluida en backup → **sigue disponible despues de reiniciar el servidor**; adjuntos de notificaciones suben y se ven; nombre malicioso rechazado; nada guardado en disco; sin errores en el log.

### Decisiones tomadas
- Storage: **Supabase Storage** (no guardar archivos en la BD).
- Pruebas: **proyecto Supabase de prueba** + **login de prueba solo local** (no se agrego localhost en Google).
- Version para subir la rama: **6.0** (cambio de arquitectura; el usuario lo aprobo).
- Docker: **no por ahora** (no esta instalado; el entorno con venv funciona). Queda como idea para mas adelante: probar igual que Render (Linux + gunicorn) y levantar en otra PC sin instalar Python.

### Proximos pasos (en orden)
1. **Usuario:** en Render → consorcio → Environment agregar `SUPABASE_URL=https://eboskxnitazzwfobwkiq.supabase.co` y `SUPABASE_SERVICE_KEY=<secret key del proyecto REAL>` (Supabase → Project Settings → API Keys). Opcional: `SUPABASE_BUCKET` (default `comprobantes`).
2. **Claude:** en `supabase-storage`: `version.txt` → `6.0-DDMM`, entrada en `docs/historial_versiones.md`, merge a `master`, revisar diff (sin claves), push → Render despliega.
3. Verificar en produccion: adjuntar un comprobante, verlo, esperar que Render duerma/reinicie y verlo de nuevo.
4. Pendiente desde 03/11: que el usuario confirme en Render que el tilde "sin interes" (v5.2) anda rapido.
5. Recomendado: cambiar la contraseña de la BD de produccion (quedo expuesta en `gen_nov.py`, en el tar.gz viejo y en un chat) y actualizar `DATABASE_URL` en Render y en `.env.local`. Borrar `gen_nov.py`.
6. Quedo una pregunta abierta: el usuario escribio "go + el resto, ¿lo hacemos luego?" — confirmar si quiere avanzar ya con los pasos 1–2.

### Historial de la sesion 03–04/11/2026
- **v5.2** — tilde "sin interes" lento y sin actualizar montos: ahora recalcula solo las unidades afectadas (`aplicar_sin_interes`) y la pantalla actualiza interes/TOTAL/Saldo/pie/modal de pago. Los `ensure_*` (ALTER TABLE) pasaron a correr una vez por proceso.
- **v5.3** — regla de versionado en `CLAUDE.md` (menor siempre; mayor consultando).
- **v5.4** — esta memoria con seccion "Continuar en otra PC"; `CLAUDE.md` indica leerla.
- **v5.5** — `docs/memoria_claude/`: notas de memoria de la PC original, **sin claves** (el tar.gz original tenia la contraseña; el repo es publico).
- Rama `supabase-storage` (ver arriba).

---

## Pruebas locales (rama `supabase-storage`)

- Venv de Windows: `C:\Users\Maria\.venvs\consorcio` (en WSL **no hay Python**). Python base: `C:\Users\Maria\AppData\Local\Programs\Python\Python312`.
- `.env.local` (no versionado) en la carpeta del proyecto: `DATABASE_URL` (prueba), `ORIGEN_DATABASE_URL` (produccion, solo lectura), `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` / `SUPABASE_BUCKET` (prueba), `SECRET_KEY`, `APP_ENV=pruebas`, `DEV_LOGIN_EMAIL`.
- Copiar produccion → prueba: `python copiar_esquema.py --datos --reemplazar` (produccion read-only; aborta si origen = destino; borra y recrea solo en prueba).
- Levantar: `python correr_local.py` → http://localhost:5000 → boton "Entrar en modo prueba local". Aborta si `.env.local` apunta a produccion.
- Desde Claude Desktop, el preview usa `.claude/launch.json` (no versionado) con `runtimeExecutable` = python del venv y `runtimeArgs` = ruta UNC a `correr_local.py`.

---

## Continuar en otra PC

Codigo y este contexto: GitHub. Datos: Supabase. **La rama `supabase-storage` solo esta en GitHub si se hizo push de la rama** (no despliega: Render solo despliega `master`).

1. Clonar: `git clone https://github.com/ncmartin77/consorcio.git` y, si existe en GitHub, `git switch supabase-storage`.
2. `python -m venv venv` → activar → `pip install -r requirements.txt`.
3. Recrear `.env.local` desde `.env.local.ejemplo` (los valores no estan en el repo):
   - prueba: Supabase `consorcio-tst` → Connect (pooler) y Project Settings → API Keys;
   - produccion (solo para `copiar_esquema.py`): contraseña desde Render → `DATABASE_URL`, host pooler de la tabla de arriba.
4. **Conexion a Supabase**: el host directo `db.<id>.supabase.co` es **solo IPv6**; en PCs sin IPv6 falla con "could not translate host name". Usar el **pooler**.
5. Abrir Claude Code/Desktop en la carpeta del repo: lee `CLAUDE.md` automaticamente; pedirle que lea tambien este archivo.
6. Opcional: MCP de Supabase con un Personal Access Token (`sbp_...`).

Notas viejas de la PC original (sin claves): `docs/memoria_claude/` — pueden estar desactualizadas; este archivo manda. `data/` y `_consorcios.json` no se versionan (datos de prueba de la epoca Excel).

---

## Pendientes / mejoras conocidas

- Aplicar la migracion de archivos a produccion (ver "Proximos pasos").
- Docker para pruebas locales (opcional, mas adelante).
- Diseno del PDF de resumen puede mejorar.
- No hay envio automatico de emails (solo generacion de PDF/WhatsApp manual).
- Render free tier: cold start de ~30 seg despues de inactividad.

---

## Consultas SQL utiles

```sql
-- Liquidaciones de un periodo
SELECT unidad, total_a_pagar, pagado, sin_interes
FROM liquidaciones
WHERE periodo='2026-10' AND consorcio_id='28693516';

-- Gastos de un mes
SELECT * FROM gastos
WHERE periodo='2026-09' AND consorcio_id='28693516';

-- Movimientos de caja de un mes
SELECT * FROM caja
WHERE consorcio_id='28693516'
  AND TO_CHAR(fecha, 'YYYY-MM') = '2026-10';

-- Facturas con comprobante adjunto
SELECT id, descripcion, archivo_pdf FROM facturas
WHERE consorcio_id='28693516' AND archivo_pdf <> '';
```

---

*Este archivo es la fuente de verdad del contexto de sesion. Actualizarlo si cambian reglas, estado o version del proyecto.*
