# Arquitectura Técnica — Sistema de Gestión de Consorcio

**Versión del sistema:** 5.0-0311  
**Repositorio:** https://github.com/ncmartin77/consorcio  
**URL producción:** https://consorcio-soo4.onrender.com

---

## 1. Diagrama de Arquitectura

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTE (Browser)                        │
│             Bootstrap 5 + Bootstrap Icons + Jinja2              │
│                 PWA: manifest.json + sw.js                      │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP/HTTPS
┌────────────────────────▼────────────────────────────────────────┐
│                    RENDER.COM (Free Tier)                        │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │  Gunicorn (2 workers, timeout 120s)                     │   │
│   │  ┌───────────────────────────────────────────────────┐  │   │
│   │  │  Flask Application (app.py)                       │  │   │
│   │  │  ┌────────────┐  ┌──────────┐  ┌──────────────┐  │  │   │
│   │  │  │  Routes /  │  │ pdf_gen  │  │  Authlib     │  │  │   │
│   │  │  │ Controllers│  │(ReportLab│  │ (Google OAuth│  │  │   │
│   │  │  └─────┬──────┘  └────┬─────┘  └──────────────┘  │  │   │
│   │  │        │              │                           │  │   │
│   │  │  ┌─────▼──────────────▼──────────────────────┐   │  │   │
│   │  │  │        pg_db.py (Business Logic)           │   │  │   │
│   │  │  │  ThreadedConnectionPool (1-10 conexiones)  │   │  │   │
│   │  │  │  Thread-local: _tls (consorcio por request)│   │  │   │
│   │  │  └──────────────────┬────────────────────────┘   │  │   │
│   │  └─────────────────────┼───────────────────────────┘  │   │
│   └────────────────────────┼────────────────────────────────┘   │
└────────────────────────────┼────────────────────────────────────┘
                             │ psycopg2 (TLS)
┌────────────────────────────▼────────────────────────────────────┐
│                  SUPABASE (ca-central-1)                         │
│              PostgreSQL — Project: eboskmenitazzwfobwkiq         │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────┐  │
│  │ Tablas de    │  │   audit_log   │  │     checkpoints      │  │
│  │ negocio      │  │  (JSONB diff) │  │  (snapshot JSONB)    │  │
│  │ (16 tablas)  │  │               │  │                      │  │
│  └──────────────┘  └───────────────┘  └──────────────────────┘  │
│  Trigger: zz_auditoria → audit_registrar() [AFTER INSERT/UPDATE/DELETE]
└─────────────────────────────────────────────────────────────────┘

Flujo de autenticación (OAuth):
Browser → /login/google → Google OAuth → /auth/callback → session Flask
```

### Flujo Multi-consorcio por request

```
HTTP Request
    │
    ├─ before_request: _authenticate()
    │      session["usuario_id"] → db.get_usuario() → g.usuario
    │
    ├─ before_request: _set_consorcio()
    │      session["consorcio_id"] → db.get_consorcio(cid)
    │      → db.set_active_consorcio(data_dir_abs, db_path_abs)
    │         → _tls.consorcio_id = cid   (thread-local)
    │      → db.consolidar_si_expirado()  (limpia checkpoint vencido)
    │
    ├─ before_request: _contexto_auditoria()
    │      → db.ensure_auditoria()        (idempotente)
    │      → db.ensure_deuda_inicial_fecha()
    │      → db.ensure_caja_factura_id()
    │      → db.ensure_liq_sin_interes()
    │      → db.set_contexto_auditoria(email, descripcion)
    │         → _tls.audit = {op: uuid, usuario, desc}
    │
    ├─ Route handler
    │      → pg_db functions → _conn() → _aplicar_contexto_auditoria()
    │         → SET app.audit_op / app.audit_usuario / app.audit_desc
    │         → SQL → trigger zz_auditoria → audit_log INSERT
    │      → render_template() → inject_version() context_processor
    │
    └─ teardown_request: _fin_auditoria()
           → db.limpiar_contexto_auditoria()
```

---

## 2. Stack Tecnológico

| Capa | Tecnología | Versión | Justificación |
|---|---|---|---|
| Framework web | Flask | >=3.0.0 | Minimalista, sin ORM, fácil de mantener en un solo dev |
| Servidor WSGI | Gunicorn | >=21.2.0 | Multi-worker para Render; 2 workers, timeout 120s |
| Base de datos | PostgreSQL via Supabase | — | Persistencia centralizada, accesible desde cualquier deploy |
| Driver BD | psycopg2-binary | >=2.9.9 | Driver nativo PostgreSQL, connection pooling |
| Pool de conexiones | `ThreadedConnectionPool` | psycopg2 | Min 1, max 10 conexiones; reutilización en multi-thread |
| Autenticación | Authlib + Google OAuth | >=1.3.0 | SSO sin gestión de contraseñas propias |
| Templates | Jinja2 (built-in Flask) | — | Integrado, sin SPA overhead |
| CSS/UI | Bootstrap 5 + Bootstrap Icons | CDN | Sin build step, familiaridad general |
| PDFs | ReportLab | >=4.0.0 | Generación programática de PDFs complejos |
| QR codes | qrcode[pil] | >=7.4.2 | QR en recibos para verificación HMAC |
| Imágenes | Pillow | >=10.0.0 | Conversión de comprobantes JPG/PNG→PDF |
| Deploy | Render.com | free tier | Auto-deploy desde GitHub, sin infra manual |
| BD gestionada | Supabase | — | PostgreSQL hosted, conexión directa psycopg2, ca-central-1 |
| PWA | `manifest.json` + `sw.js` | — | Instalable en móvil/desktop |

---

## 3. Estructura de Archivos y Responsabilidades

```
consorcio/
├── app.py                 # Routes Flask (controladores delgados)
│                          # Toda la lógica de presentación y validación de inputs
│                          # before_request: auth, consorcio, auditoría
│                          # Sin acceso directo a BD
│
├── pg_db.py               # Capa de datos + lógica de negocio
│                          # Pool de conexiones, thread-local, wrappers SQL
│                          # Toda la lógica: liquidaciones, intereses, checkpoints
│                          # Auditoría: trigger DDL, reversión de operaciones
│
├── pdf_gen.py             # Generación de PDFs (ReportLab, solo lectura de datos)
│                          # generar_pdf_resumen_edificio()
│                          # generar_recibo_pago()      (con HMAC + QR)
│                          # generar_pdf_liquidacion()  (sin uso en routes)
│
├── requirements.txt       # Dependencias Python
├── render.yaml            # Configuración de deploy en Render.com
├── version.txt            # Versión del sistema (formato X.Y-DDMM)
│
├── templates/             # Jinja2 + Bootstrap 5
│   ├── base.html          # Layout principal (navbar, flash messages, scripts)
│   ├── login.html         # Login Google OAuth
│   ├── consorcios.html    # Selector de consorcio
│   ├── config.html        # Configuración del edificio
│   ├── unidades.html      # ABM de unidades funcionales
│   ├── gastos.html        # Gastos mensuales + recurrentes + tareas
│   ├── caja.html          # Caja diaria con paginación
│   ├── liquidacion.html   # Vista principal de liquidación + pagos
│   ├── facturas.html      # Gestión de facturas + comprobantes
│   ├── proveedores.html   # ABM de proveedores
│   ├── presupuestos.html  # Pedidos y cotizaciones
│   ├── apertura.html      # Saldos iniciales
│   ├── estado_cuenta.html # Historial por unidad
│   ├── plano.html         # Vista plano del edificio (estado de pago)
│   ├── notificaciones.html# Envío de notificaciones a propietarios/inquilinos
│   ├── auditoria.html     # Log de operaciones (solo admin)
│   ├── auditoria_detalle.html # Diff fila por fila de una operación
│   ├── admin_usuarios.html# Gestión de usuarios y permisos (solo admin)
│   ├── verificar.html     # Verificación pública de autenticidad de recibos
│   └── recibo_publico.html# Página pública del recibo (PDF embebido)
│
├── static/
│   ├── style.css          # Estilos custom (mínimos, base Bootstrap)
│   ├── manifest.json      # PWA manifest
│   ├── sw.js              # Service Worker (caché offline)
│   └── icons/             # Íconos PWA (múltiples resoluciones)
│
├── data/                  # Datos locales (NO en git, excluido en Render)
│   ├── edificio_brasil.xlsx  # Consorcio legacy por defecto
│   └── <cid>/             # Directorio por consorcio (UUID hex 8 chars)
│       ├── base.xlsx      # Excel legacy (no usado en prod PostgreSQL)
│       └── facturas/      # Comprobantes PDF organizados por proveedor
│           └── <proveedor>/
│               └── YYYY-MM-DD_HHMMSS.pdf
│
├── _consorcios.json       # Índice local de consorcios (compatibilidad excel_db)
├── excel_db.py            # Capa de datos legada (Excel, reemplazada por pg_db.py)
├── migrar.py              # Script de migración Excel→columnas (idempotente)
├── CLAUDE.md              # Guía de desarrollo para Claude Code
└── docs/
    └── arquitectura_tecnica.md  # Este documento
```

---

## 4. Esquema de Base de Datos

### Tablas de negocio

#### `consorcios`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | TEXT PK | UUID hex de 8 chars (ej: `a1b2c3d4`) |
| `nombre` | TEXT | Nombre del consorcio |
| `descripcion` | TEXT | Descripción opcional |
| `created_at` | TIMESTAMPTZ | Fecha de creación |

#### `usuarios`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `email` | TEXT UNIQUE | Email de Google |
| `nombre` | TEXT | Nombre completo |
| `google_id` | TEXT UNIQUE | `sub` del token Google |
| `foto_url` | TEXT | Avatar de Google |
| `es_admin` | BOOLEAN | Superadmin del sistema |
| `activo` | BOOLEAN | Puede iniciar sesión |
| `created_at` | TIMESTAMPTZ | — |

> El primer usuario registrado recibe `es_admin=TRUE` automáticamente.

#### `permisos_consorcio`
| Columna | Tipo | Descripción |
|---|---|---|
| `usuario_id` | INTEGER FK → usuarios | — |
| `consorcio_id` | TEXT FK → consorcios | — |

#### `config`
| Columna | Tipo | Descripción |
|---|---|---|
| `consorcio_id` | TEXT FK | — |
| `clave` | TEXT | Clave de configuración |
| `valor` | TEXT | Valor de configuración |
| PK | `(consorcio_id, clave)` | — |

Claves de configuración importantes:
- `edificio_nombre`, `edificio_direccion`, `administrador`, `telefono`, `email`
- `alias_cbu`, `titular_cuenta`
- `tasa_mora` (%, default 7)
- `dia_vencimiento` (día del mes, default 15; 0 = último día)
- `fondo_reserva_mensual` (monto fijo mensual auto-insertado)
- `fecha_simulada` (YYYY-MM-DD, override de `date.today()`)
- `saldo_inicial_caja`, `saldo_inicial_caja_fecha`
- `clave_firma` (HMAC secret, generada con `secrets.token_hex(32)`)
- `url_app` (URL base para QR en recibos)
- `logo_b64`, `logo_mime` (logo del consorcio en base64)

#### `categorias`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT FK | — |
| `nombre` | TEXT | Nombre en MAYÚSCULAS (ej: `EXPENSAS`, `FONDO_RESERVA`) |
| `descripcion` | TEXT | Descripción opcional |
| UK | `(consorcio_id, nombre)` | — |

Las categorías definen cómo se distribuyen los gastos entre unidades. Cada categoría agrega una columna `pct_NOMBRE` lógica en `unidad_porcentajes`.

#### `unidades`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT FK | — |
| `numero` | TEXT | Identificador de la UF (ej: `1A`, `101`) |
| `descripcion` | TEXT | Descripción del departamento |
| `propietario` | TEXT | Nombre del propietario |
| `inquilino` | TEXT | Nombre del inquilino (opcional) |
| `activo` | BOOLEAN | Si participa en liquidaciones |
| `piso` | TEXT | Piso para vista de plano |
| `deuda_inicial` | NUMERIC | Saldo deudor al momento de apertura |
| `deuda_inicial_fecha` | VARCHAR(7) | Período (YYYY-MM) de la deuda inicial |
| `propietario_mail` | TEXT | — |
| `propietario_celular` | TEXT | — |
| `inquilino_mail` | TEXT | — |
| `inquilino_celular` | TEXT | — |
| `envio_destinatario` | TEXT | `propietario` o `inquilino` |
| `envio_canal` | TEXT | `mail` o `whatsapp` |
| UK | `(consorcio_id, numero)` | — |

#### `unidad_porcentajes`
| Columna | Tipo | Descripción |
|---|---|---|
| `consorcio_id` | TEXT | — |
| `numero` | TEXT | Número de unidad |
| `categoria` | TEXT | Nombre de categoría |
| `porcentaje` | NUMERIC | Porcentaje de participación (0-100) |
| PK | `(consorcio_id, numero, categoria)` | — |

#### `gastos`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT FK | — |
| `periodo` | VARCHAR(7) | YYYY-MM del mes al que corresponde el gasto |
| `concepto` | TEXT | Descripción del gasto |
| `importe` | NUMERIC | Monto |
| `tipo` | TEXT | `FIJO` / `VARIABLE` / `FONDO_RESERVA` / `VARIABLE_FR` |

Tipos de gasto:
- `FIJO`: gasto fijo mensual (se reparte entre unidades)
- `VARIABLE`: gasto variable (también se reparte)
- `FONDO_RESERVA`: gasto de fondo de reserva (separado del total de expensas)
- `VARIABLE_FR`: gasto variable pagado con fondo de reserva (no afecta la liquidación)

#### `caja`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT FK | — |
| `fecha` | DATE | Fecha del movimiento |
| `descripcion` | TEXT | Descripción |
| `tipo` | TEXT | `ENTRADA` o `SALIDA` |
| `categoria` | TEXT | Categoría (ej: `Expensas`, `FONDO_RESERVA`, `BONIFICACION`) |
| `importe` | NUMERIC | Monto absoluto (siempre positivo) |
| `factura_id` | INTEGER FK → facturas | Vincula pago de factura a su registro |

#### `facturas`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT FK | — |
| `fecha` | DATE | Fecha de emisión |
| `proveedor_id` | INTEGER FK → proveedores | Opcional |
| `proveedor_nombre` | TEXT | Nombre desnormalizado |
| `descripcion` | TEXT | Concepto de la factura |
| `importe` | NUMERIC | Monto |
| `estado` | TEXT | `PENDIENTE` o `PAGADA` |
| `fecha_pago` | DATE | Fecha en que se registró el pago |
| `categoria` | TEXT | Categoría del gasto |
| `numero_factura` | TEXT | Número de factura del proveedor |
| `extraordinario` | BOOLEAN | Si es gasto extraordinario (aparece en recibo) |
| `archivo_pdf` | TEXT | Ruta relativa al comprobante adjunto |

#### `proveedores`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT FK | — |
| `nombre` | TEXT | — |
| `cuit` | TEXT | — |
| `telefono`, `email`, `direccion` | TEXT | Datos de contacto |
| `categoria` | TEXT | Rubro |
| `notas` | TEXT | Notas internas |
| `gasto_recurrente` | TEXT | Concepto recurrente asociado (auto-link) |

#### `gastos_recurrentes`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT FK | — |
| `concepto` | TEXT | Concepto que se repite mensualmente |
| `categoria` | TEXT | Categoría del gasto |

Cuando se carga una factura con un concepto que coincide (case-insensitive) con un gasto recurrente, `save_factura()` auto-inserta el gasto en `gastos` para ese período.

#### `liquidaciones`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT FK | — |
| `periodo` | VARCHAR(7) | YYYY-MM de la liquidación |
| `unidad` | TEXT | Número de UF |
| `descripcion` | TEXT | Descripción del depto |
| `propietario` | TEXT | Nombre (desnormalizado al momento de liquidar) |
| `inquilino` | TEXT | Nombre (desnormalizado) |
| `pct_aplicado` | NUMERIC | Porcentaje de distribución aplicado |
| `expensas` | NUMERIC | Monto de expensas del mes |
| `deuda_anterior` | NUMERIC | Saldo del período anterior |
| `interes` | NUMERIC | Interés por mora calculado |
| `total_a_pagar` | NUMERIC | `expensas + deuda_anterior + interes + extras` |
| `pagado` | BOOLEAN | Si el pago fue completo |
| `monto_pagado` | NUMERIC | Monto efectivamente cobrado |
| `tipo_pago` | TEXT | `PENDIENTE` / `PARCIAL` / `TOTAL` |
| `saldo_pendiente` | NUMERIC | `total_a_pagar - monto_pagado` |
| `fecha_pago` | DATE | Fecha del último pago |
| `extras` | NUMERIC | Gastos extra específicos de la unidad |
| `sin_interes` | BOOLEAN | Flag: omitir interés en recálculos (default FALSE) |

#### `liquidaciones_estado`
| Columna | Tipo | Descripción |
|---|---|---|
| `consorcio_id` | TEXT | — |
| `periodo` | VARCHAR(7) | YYYY-MM |
| `estado` | TEXT | `ABIERTA` o `CERRADA` |
| PK | `(consorcio_id, periodo)` | — |

#### `notas_periodo`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT | — |
| `periodo` | VARCHAR(7) | YYYY-MM |
| `tipo` | TEXT | `AVISO` (destacado) o `INFO` |
| `texto` | TEXT | Contenido de la nota |

#### `gastos_extra`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT | — |
| `periodo` | VARCHAR(7) | — |
| `unidad` | TEXT | Número de UF |
| `descripcion` | TEXT | — |
| `monto` | NUMERIC | Monto del cargo extra |

#### `pedidos` y `presupuestos`
Gestión de pedidos de cotización a proveedores. Un pedido puede tener múltiples presupuestos (cotizaciones); al seleccionar uno, el pedido pasa a estado `ADJUDICADO`.

#### `tareas`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | — |
| `consorcio_id` | TEXT | — |
| `descripcion` | TEXT | Descripción de la tarea pendiente |

Checklist global mostrado en Gastos Mensuales. Operaciones 100% AJAX.

### Tablas de infraestructura

#### `audit_log`
| Columna | Tipo | Descripción |
|---|---|---|
| `id` | BIGSERIAL PK | — |
| `op_id` | TEXT | UUID hex compartido por todos los cambios del mismo request |
| `fecha` | TIMESTAMPTZ | Timestamp del cambio |
| `tabla` | TEXT | Nombre de la tabla afectada |
| `accion` | TEXT | `INSERT`, `UPDATE` o `DELETE` |
| `datos_antes` | JSONB | Row completo previo al cambio (NULL en INSERT) |
| `datos_despues` | JSONB | Row completo posterior al cambio (NULL en DELETE) |
| `usuario_email` | TEXT | Email del usuario que ejecutó la operación |
| `consorcio_id` | TEXT | Consorcio al que pertenece el cambio |
| `descripcion` | TEXT | Label legible de la operación (ej: "Gastos: guardar gasto") |
| `revertida_en` | TIMESTAMPTZ | Timestamp de la reversión (NULL si no fue revertida) |
| `revertida_por` | TEXT | Email del admin que revirtió |
| `revertida_op` | TEXT | `op_id` de la operación de reversión |

Índices: `audit_log_op_idx (op_id)`, `audit_log_cons_fecha_idx (consorcio_id, fecha DESC)`.
Retención: 180 días (purga automática al listar).

#### `checkpoints`
| Columna | Tipo | Descripción |
|---|---|---|
| `consorcio_id` | TEXT PK | Un checkpoint por consorcio |
| `fecha_creacion` | TIMESTAMPTZ | — |
| `descripcion` | TEXT | Descripción opcional del checkpoint |
| `snapshot` | JSONB | Dump completo de todas las tablas del consorcio |

---

## 5. Patrones de Código

### 5.1 Thread-local para consorcio activo

```python
_tls = threading.local()

def set_active_consorcio(data_dir_abs: str, db_path_abs: str):
    _tls.data_dir = data_dir_abs
    _tls.db_path = db_path_abs
    _tls.facturas_dir = os.path.join(data_dir_abs, "facturas")
    _tls.consorcio_id = ...  # derivado del path

def _cid() -> str:
    cid = getattr(_tls, "consorcio_id", None)
    if not cid:
        raise RuntimeError("No hay consorcio activo. Llamar set_active_consorcio primero.")
    return cid
```

`_cid()` se usa en **todas** las queries de negocio para filtrar por consorcio. Es imposible que una request lea datos de otro consorcio por error: si el thread-local no está seteado, la función lanza excepción inmediatamente.

### 5.2 Connection Pool y context manager

```python
_pool: ThreadedConnectionPool | None = None  # singleton lazy

@contextmanager
def _conn(write: bool = True):
    pool = _get_pool()
    c = pool.getconn()
    try:
        if write:
            _aplicar_contexto_auditoria(c)  # SET app.audit_* antes de queries
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        pool.putconn(c)  # devuelve al pool aunque haya excepción
```

- `write=False` en `_fetchall`/`_fetchone`: no llama a `_aplicar_contexto_auditoria` (optimización).
- El pool se inicializa lazy en el primer request, thread-safe con doble-check locking.

### 5.3 Wrappers SQL

```python
def _fetchall(sql, params=()) -> list[dict]:   # SELECT múltiple (RealDictCursor)
def _fetchone(sql, params=()) -> dict | None:   # SELECT único
def _exec(sql, params=()):                      # INSERT/UPDATE/DELETE sin retorno
def _insert_returning(sql, params=()) -> int:   # INSERT ... RETURNING id
```

Todas usan `psycopg2.extras.RealDictCursor`, que devuelve filas como diccionarios.

### 5.4 Funciones `ensure_*()`

Funciones idempotentes que agregan columnas/índices si no existen. Llamadas en `before_request` en **cada** request (el overhead es mínimo: una query DDL `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` que PostgreSQL resuelve en microsegundos si la columna ya existe).

```python
def ensure_deuda_inicial_fecha():
    _exec("ALTER TABLE unidades ADD COLUMN IF NOT EXISTS deuda_inicial_fecha VARCHAR(7)")

def ensure_caja_factura_id():
    _exec("ALTER TABLE caja ADD COLUMN IF NOT EXISTS factura_id INTEGER")

def ensure_liq_sin_interes():
    _exec("ALTER TABLE liquidaciones ADD COLUMN IF NOT EXISTS sin_interes BOOLEAN DEFAULT FALSE")
```

Este patrón reemplaza las migraciones tradicionales: no hay sistema de versiones de esquema, las columnas se agregan "on demand" al levantar la app.

### 5.5 Contexto de auditoría (thread-local + PostgreSQL `set_config`)

```python
# En before_request:
def set_contexto_auditoria(usuario_email, descripcion):
    _tls.audit = {"op": uuid.uuid4().hex, "usuario": usuario_email, "desc": descripcion}

# En _conn(write=True):
def _aplicar_contexto_auditoria(c):
    cur.execute(
        "SELECT set_config('app.audit_op', %s, true), ...",
        (ctx["op"], ctx["usuario"], ctx["desc"], consorcio_id)
    )
```

`set_config(..., true)` aplica el setting **solo para la transacción actual**. El trigger PostgreSQL lee estos settings con `current_setting('app.audit_op', true)` para registrar en `audit_log`.

### 5.6 Período de trabajo en sesión

```python
session["periodo_trabajo"]  # período de liquidación activo (YYYY-MM)
session["consorcio_id"]     # consorcio activo
```

El período de trabajo persiste entre requests. Si no está seteado, se usa el mes actual. El usuario puede cambiarlo desde cualquier pantalla con el selector de período.

---

## 6. Flujo de un Request Típico

### Ejemplo: registrar un pago de expensas

```
POST /liquidacion/pagar/2026-11/101
Form: monto_pagado=15000, fecha_pago=2026-11-05

1. Gunicorn worker recibe request

2. before_request: _authenticate()
   → session["usuario_id"] = 42
   → db.get_usuario(42) → {"email": "admin@consorcio.com", "activo": True}
   → g.usuario = {...}

3. before_request: _set_consorcio()
   → session["consorcio_id"] = "a1b2c3d4"
   → db.get_consorcio("a1b2c3d4") → {"data_dir_abs": "/app/data/a1b2c3d4", ...}
   → db.set_active_consorcio(...)
     → _tls.consorcio_id = "a1b2c3d4"
   → db.consolidar_si_expirado() → (no hay checkpoint vencido)

4. before_request: _contexto_auditoria()
   → db.ensure_auditoria()   (ya inicializado, sale rápido)
   → db.ensure_deuda_inicial_fecha(), ensure_caja_factura_id(), ensure_liq_sin_interes()
   → desc = "Liquidación: registrar pago (periodo: 2026-11, unidad: 101)"
   → db.set_contexto_auditoria("admin@consorcio.com", desc)
     → _tls.audit = {op: "f3a4...", usuario: "admin@...", desc: "..."}

5. marcar_pagado route handler:
   → db.liq_esta_cerrada("2026-11") → False (ABIERTA)
   → db.marcar_pagado("2026-11", "101", 15000.0, "2026-11-05")
     → _fetchone("SELECT * FROM liquidaciones WHERE ...")
       → _conn(write=False) → no audit context, commit
     → total_a_pagar = 15500.0, monto_anterior = 0.0
     → total_pagado = 15000.0, saldo = 500.0, tipo_pago = "PARCIAL"
     → _exec("UPDATE liquidaciones SET pagado=... WHERE ...")
       → _conn(write=True):
         → _aplicar_contexto_auditoria()
           → SET app.audit_op='f3a4...', app.audit_usuario='admin@...', ...
         → UPDATE ejecuta → trigger zz_auditoria → INSERT en audit_log
           {op_id: "f3a4...", tabla: "liquidaciones", accion: "UPDATE",
            datos_antes: {tipo_pago: "PENDIENTE", ...},
            datos_despues: {tipo_pago: "PARCIAL", monto_pagado: 15000, ...}}
         → commit()
     → db.save_movimiento("2026-11-05", "Expensas 2026-11 - Juan Pérez - UF 101 (PARCIAL)",
                           "ENTRADA", "Expensas", 15000.0)
       → INSERT en caja → trigger audit_log → commit

6. flash("UF 101: pago parcial de $15.000,00. Saldo pendiente: $500,00.", "warning")
   → redirect(url_for("liquidacion", periodo="2026-11"))

7. teardown_request: _fin_auditoria()
   → _tls.audit = None
```

---

## 7. Lógica de Negocio Crítica

### 7.1 Liquidación a mes vencido ("mes vencido")

La liquidación del período **P** se basa en los gastos del período **P-1**:

```
Gastos de Octubre 2026 (P-1)  →  Liquidación de Noviembre 2026 (P)
```

Funciones helper:
```python
def _prev_periodo(periodo):  # "2026-11" → "2026-10"
def _next_periodo(periodo):  # "2026-10" → "2026-11"
```

Cuando el usuario guarda un gasto del mes P, se recalcula automáticamente la liquidación de P+1 (si está ABIERTA o no existe).

### 7.2 Algoritmo de generación de liquidación (`generar_liquidacion`)

```
Para cada unidad activa (ordenadas por número):

1. Calcular pct (porcentaje de participación):
   - Si tiene 1 categoría: usa ese porcentaje
   - Si tiene múltiples: promedia
   - Si tiene 0: pct = 0

2. Calcular expensas del mes:
   - expensas = round(total_gastos * pct / 100, 2)
   - EXCEPCIÓN: la última unidad absorbe la diferencia de redondeo
     → expensas = round(total_gastos - sum(expensas_anteriores), 2)
   - Esto garantiza: sum(todas las expensas) == total_gastos exactamente

3. Calcular deuda_anterior:
   - Si no hay liquidación previa: deuda_inicial (de apertura)
   - Si la anterior fue pagada totalmente: 0.0
   - Si fue pago parcial: saldo_pendiente del período anterior
   - Si no pagó: total_a_pagar del período anterior

4. Calcular interés:
   - Si sin_interes = True: interes = 0
   - Si es el primer mes (deuda_inicial): no aplica interés sobre esa deuda
   - interes_deuda = deuda_anterior * tasa_mora
   - mora_corriente = expensas * tasa_mora (solo si hoy > fecha_vencimiento y sin pago)
   - interes = interes_deuda + mora_corriente

5. Calcular extras:
   - extras_unidad = sum(gastos_extra donde unidad == numero)

6. total_a_pagar = expensas + deuda_anterior + interes + extras_unidad

7. Preservar pagos ya registrados (monto_pagado, tipo_pago, fecha_pago)
   del registro anterior de la liquidación (si existía)
```

### 7.3 Inmutabilidad de liquidación CERRADA

Una liquidación CERRADA (`liquidaciones_estado.estado = 'CERRADA'`) es completamente inmutable:

| Operación | Comportamiento si CERRADA |
|---|---|
| `generar_liquidacion()` | Retorna sin hacer nada |
| `marcar_pagado()` | Retorna `{"tipo": "CERRADA"}` |
| `save_movimiento()` en route | Flash error, redirect |
| `delete_movimiento()` | Verifica período del movimiento, retorna `False` |
| `delete_factura()` | Verifica `factura_en_liquidacion()`, retorna `False` |
| Agregar gasto P → recalcula P+1 | Si P+1 CERRADA: solo flash info, no recalcula |
| Agregar nota/extra | Route retorna 400 |

Generar P+1 requiere que P esté CERRADA (validado en el route `generar_liquidacion`).

### 7.4 Fondo de Reserva

Tipo especial de gasto que no se distribuye entre unidades sino que se acumula:

- `FONDO_RESERVA`: gasto fijo mensual, auto-insertado por `ensure_fondo_reserva_gasto()`.
  Se configura con `fondo_reserva_mensual` en config.
- `VARIABLE_FR`: gasto variable pagado con fondo de reserva. No entra en `total_gastos`,
  no afecta las expensas de cada unidad. Su pago genera una SALIDA en Caja con
  categoría `FONDO_RESERVA`.
- El saldo acumulado del fondo se calcula sumando todos los gastos de tipo `FONDO_RESERVA`
  en todas las épocas del consorcio.

### 7.5 Interés por mora

```
tasa_mora = config["tasa_mora"] / 100  # ej: 7% → 0.07
dia_vencimiento = int(config["dia_vencimiento"])  # ej: 15
fecha_vencimiento = date(año_periodo, mes_periodo, min(dia_vencimiento, ultimo_dia_mes))

interes_deuda  = deuda_anterior * tasa_mora
mora_corriente = expensas * tasa_mora  # solo si hoy > fecha_vencimiento y monto_pagado == 0
interes        = interes_deuda + mora_corriente
```

El flag `sin_interes` por unidad permite eximir a unidades específicas del interés (se usa para acuerdos de pago). Se puede aplicar individualmente o a todas las unidades a la vez.

### 7.6 Pago de facturas y su impacto en caja

Cuando se paga una factura (`pagar_factura`):

1. Actualiza `facturas.estado = 'PAGADA'`, `facturas.fecha_pago`
2. Inserta SALIDA en `caja` con descripción del pago
3. Actualiza `caja.factura_id` del último movimiento insertado (FK de integridad)
4. Si el concepto NO es recurrente y NO es FONDO_RESERVA: inserta en `gastos`
5. Triggerea el recálculo de la liquidación del período siguiente

Si se elimina el movimiento de caja de un pago:
- Se revierte la factura a `PENDIENTE`
- Si el movimiento corresponde a un pago de expensas (descripción matchea patrón
  `"Expensas YYYY-MM.*UF \d+"`), se revierte también el estado de pago en `liquidaciones`

### 7.7 Checkpoint y Rollback

```
crear_checkpoint(descripcion):
  1. Dump de 16 tablas del consorcio activo como JSONB
  2. INSERT OR REPLACE en checkpoints (un checkpoint por consorcio)
  Expiry: 30 días; consolidar_si_expirado() lo elimina automáticamente

rollback_checkpoint():
  1. Lee snapshot de checkpoints
  2. DELETE en orden children-first (respetar FKs)
  3. INSERT en orden parents-first con OVERRIDING SYSTEM VALUE (preserva IDs)
  4. Resetea sequences al MAX(id) real de cada tabla
  5. Elimina el checkpoint
```

La operación de rollback es atómica (todo en una transacción). Tablas sin `id` serial usan INSERT sin `OVERRIDING SYSTEM VALUE`.

### 7.8 Auto-aplicación de mora

En cada request a `/liquidacion/<periodo>`, si la liquidación existe, está ABIERTA y `hoy > fecha_vencimiento`, se llama `generar_liquidacion(periodo)` automáticamente para recalcular el interés de mora corriente.

---

## 8. Variables de Entorno y Configuración

| Variable | Requerida | Descripción | Default |
|---|---|---|---|
| `DATABASE_URL` | Sí | PostgreSQL connection string de Supabase | — |
| `SECRET_KEY` | Sí | Clave Flask para firmar cookies de sesión | `"edificio-brasil-secret-2024"` (inseguro) |
| `APP_ENV` | No | `"produccion"` o `"pruebas"` | `"produccion"` |
| `APP_HOST` | No | Bind address de Flask | `"127.0.0.1"` |
| `GOOGLE_CLIENT_ID` | No | OAuth Google Client ID | — (login Google deshabilitado) |
| `GOOGLE_CLIENT_SECRET` | No | OAuth Google Client Secret | — |

En Render.com:
- `DATABASE_URL`: apunta a Supabase (`postgresql://postgres.eboskmenitazzwfobwkiq:...`)
- `SECRET_KEY`: generado por Render (`generateValue: true`)
- `APP_ENV`: `"produccion"` (hardcodeado en `render.yaml`)
- `APP_HOST`: no seteado (Flask se bindea a 127.0.0.1, Gunicorn maneja el bind externo)

En desarrollo local:
```bash
export DATABASE_URL="postgresql://..."
export SECRET_KEY="dev-secret-key"
export APP_ENV="pruebas"
export APP_HOST="0.0.0.0"  # para acceso desde la red local
python app.py
```

### Simulación de fecha

```python
# En config de la app (tabla config):
# clave: "fecha_simulada", valor: "2026-03-20"
# Afecta a _fecha_hoy() en app.py → usada en toda la app
# Útil para testear períodos pasados o futuros sin cambiar el reloj del sistema
```

---

## 9. Deploy y CI/CD

### Ciclo de deploy

```
Desarrollador
    │
    ├── Edita código localmente
    │
    ├── git commit -m "descripción"
    │       └── post-commit hook (local) → git push automático
    │
    └── Push a GitHub (rama master)
            │
            └── Render.com detecta el push (webhook)
                    │
                    ├── pip install -r requirements.txt
                    │
                    ├── gunicorn app:app --workers 2 --timeout 120
                    │
                    └── App disponible en https://consorcio-soo4.onrender.com
```

### Configuración de Render (`render.yaml`)

```yaml
services:
  - type: web
    name: consorcio
    env: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app --workers 2 --timeout 120
    envVars:
      - key: DATABASE_URL
        sync: false          # Seteado manualmente en Render dashboard
      - key: SECRET_KEY
        generateValue: true  # Generado automáticamente por Render
      - key: APP_ENV
        value: produccion
```

### Consideraciones del free tier de Render

- La instancia se duerme tras 15 minutos de inactividad
- El primer request después del sleep tarda ~30 segundos (cold start)
- PostgreSQL vive en Supabase (no en Render), por lo que los datos persisten
- Límite de 512 MB RAM; con 2 workers es suficiente para carga baja

### Supabase

- Project ID: `eboskmenitazzwfobwkiq`
- Región: `ca-central-1` (Canadá Central)
- Conexión directa psycopg2 (no Supabase client JS)
- Pool: mín 1, máx 10 conexiones (ajustado al free tier de Supabase)
- La tabla `audit_log` y los triggers se crean con `ensure_auditoria()` (DDL en runtime, no en migración)

---

## 10. Seguridad

### 10.1 Autenticación y autorización

```
Autenticación: exclusivamente Google OAuth (Authlib)
    → No hay contraseñas propias en la app
    → El email de Google es el identificador del usuario

Autorización:
    → es_admin: puede ver/modificar todos los consorcios, usuarios y auditoría
    → Usuario normal: solo ve los consorcios asignados via permisos_consorcio
    → Primer usuario registrado es admin automáticamente

Endpoints públicos (_PUBLIC_ENDPOINTS):
    "static", "login", "login_google", "auth_callback", "logout",
    "verificar_recibo", "recibo_publico", "recibo_publico_pdf"

Endpoints de admin (_ADMIN_ENDPOINTS):
    "admin_usuarios", "admin_toggle_activo", "admin_toggle_admin", "admin_set_permisos"
    → Verificados con _require_admin() en el route handler
```

### 10.2 HMAC en recibos (verificación de autenticidad)

Cada recibo PDF incluye un código de verificación y un QR:

```python
def _token_recibo_publico(clave, cid, periodo, unidad) -> str:
    key = clave.encode("utf-8")
    msg = f"{cid}|{periodo}|{unidad}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:32]
```

Token en URL pública: `/recibo/publico/<cid>/<periodo>/<unidad>/<token>`  
Comparación: `hmac.compare_digest(token, expected)` (resistente a timing attacks)

Para el QR de verificación en el PDF:

```python
def generar_codigo_verificacion(row, cfg, clave_firma) -> str:
    campos = "|".join([periodo, unidad, descripcion, expensas, deuda_anterior,
                       interes, total_a_pagar, tipo_pago, monto_pagado,
                       fecha_pago, edificio_nombre])
    return hmac.new(clave_firma.encode(), campos.encode(), sha256).hexdigest()[:32]
```

La clave `clave_firma` se genera automáticamente con `secrets.token_hex(32)` y se guarda en la tabla `config`. Si se pierde, los QR de recibos anteriores quedan invalidados.

### 10.3 Protección contra path traversal (comprobantes)

```python
full_path = os.path.join(db.get_data_dir(), factura["archivo_pdf"])
real_path = os.path.realpath(full_path)
real_data = os.path.realpath(db.get_data_dir())
if not real_path.startswith(real_data + os.sep) or not os.path.isfile(real_path):
    abort()
```

### 10.4 Aislamiento de datos por consorcio

- Todas las queries de negocio incluyen `WHERE consorcio_id = %s` con `_cid()`
- `_cid()` lanza excepción si no hay consorcio activo en el thread-local
- El consorcio activo se setea en `before_request` desde la sesión del usuario autenticado
- Los archivos de facturas se almacenan en subdirectorios `data/<cid>/` separados

### 10.5 Auditoría

- Trigger `zz_auditoria` registra TODO cambio en las 16 tablas de negocio
- El trigger corre `AFTER INSERT OR UPDATE OR DELETE`, con nombre `zz_*` para ejecutar después de cascadas FK
- UPDATEs que no cambian nada (upserts idempotentes en `save_config`) no generan registro
- Retención: 180 días (purga automática)
- Las operaciones cerradas (período ≤ última liquidación CERRADA) no se pueden revertir
- La reversión de una operación se registra como nueva operación (también reversible)

### 10.6 Validaciones en carga de archivos

```python
_ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "tiff", "bmp"}
# Imágenes se convierten a PDF vía Pillow (RGBA/P/LA → RGB antes de guardar)
# Nombre de archivo: timestamp YYYY-MM-DD_HHMMSS.pdf (sin input del usuario)
# Directorio: sanitizado (lowercase, sin tildes, solo [a-z0-9_-])
# Validación de nombre para notificaciones: regex ^[a-f0-9]{12}\.(pdf|jpg|...)$
```

---

## 11. Funcionalidades del Sistema (Mapa de Routes)

| Módulo | Method | URL | Descripción |
|---|---|---|---|
| Auth | GET | `/login` | Pantalla de login |
| Auth | GET | `/login/google` | Inicia OAuth Google |
| Auth | GET | `/auth/callback` | Callback OAuth |
| Auth | GET | `/logout` | Cierra sesión |
| Consorcios | GET | `/consorcios` | Lista de consorcios |
| Consorcios | POST | `/consorcios/nuevo` | Crear consorcio |
| Consorcios | GET | `/consorcios/<cid>/abrir` | Activar consorcio |
| Consorcios | POST | `/consorcios/<cid>/eliminar` | Eliminar del índice |
| Config | GET/POST | `/config` | Configuración del edificio |
| Unidades | GET | `/unidades` | ABM de unidades |
| Unidades | POST | `/unidades/save` | Crear/editar unidad |
| Gastos | GET | `/gastos[/<periodo>]` | Gastos mensuales |
| Gastos | POST | `/gastos/save` | Guardar gasto |
| Caja | GET | `/caja[/<periodo>]` | Caja diaria |
| Caja | POST | `/caja/save` | Registrar movimiento |
| Liquidación | GET | `/liquidacion[/<periodo>]` | Vista de liquidación |
| Liquidación | POST | `/liquidacion/generar/<periodo>` | Generar liquidación |
| Liquidación | POST | `/liquidacion/cerrar/<periodo>` | Cerrar liquidación |
| Liquidación | POST | `/liquidacion/reabrir/<periodo>` | Reabrir liquidación |
| Liquidación | POST | `/liquidacion/pagar/<periodo>/<unidad>` | Registrar pago |
| Liquidación | POST | `/liquidacion/pagar-todo/<periodo>` | Pago masivo |
| Liquidación | GET | `/liquidacion/pdf/<periodo>` | PDF resumen edificio |
| Liquidación | GET | `/liquidacion/recibo/<periodo>/<unidad>` | PDF recibo individual |
| Recibo público | GET | `/recibo/publico/<cid>/<periodo>/<unidad>/<token>` | Recibo público (HMAC) |
| Recibo público | GET | `/recibo/publico/.../<token>/pdf` | PDF recibo público |
| Verificación | GET | `/verificar[/<periodo>/<unidad>/<codigo>]` | Verificar autenticidad |
| Facturas | GET | `/facturas` | Lista de facturas |
| Facturas | POST | `/facturas/save` | Guardar factura |
| Facturas | POST | `/facturas/pagar/<fid>` | Pagar factura |
| Facturas | POST | `/facturas/<fid>/upload` | Adjuntar comprobante |
| Facturas | GET | `/facturas/<fid>/comprobante` | Ver comprobante |
| Proveedores | GET | `/proveedores` | Lista de proveedores |
| Presupuestos | GET | `/presupuestos` | Pedidos y cotizaciones |
| Apertura | GET/POST | `/apertura` | Saldos iniciales |
| Plano | GET | `/plano[/<periodo>]` | Vista plano edificio |
| Estado cuenta | GET | `/estado-cuenta` | Historial por unidad |
| Notificaciones | GET | `/notificaciones` | Envío de notificaciones |
| Checkpoint | POST | `/checkpoint/crear` | Crear snapshot |
| Checkpoint | POST | `/checkpoint/rollback` | Restaurar snapshot |
| Admin | GET | `/admin/usuarios` | Gestión de usuarios |
| Admin | GET | `/admin/auditoria` | Log de operaciones |
| Admin | POST | `/admin/auditoria/<op_id>/revertir` | Revertir operación |
| Utils | GET | `/backup` | Descargar backup ZIP |
| Utils | POST | `/set-periodo` | Cambiar período de trabajo |
| Utils | GET | `/logo` | Servir logo del consorcio |
| AJAX | POST | `/tareas/add` | Agregar tarea |
| AJAX | POST | `/tareas/delete/<id>` | Eliminar tarea |
| AJAX | POST | `/liquidacion/<periodo>/notas/add` | Agregar nota |
| AJAX | POST | `/liquidacion/<periodo>/extras/add` | Agregar gasto extra |
| AJAX | POST | `/liquidacion/<periodo>/sin-interes/<unidad>` | Toggle sin_interes |

---

## 12. Notas de Desarrollo y Convenciones

- **Idioma:** todo en español (código, mensajes, commits, documentación)
- **Versión:** `version.txt` en formato `X.Y-DDMM`; incrementar en cada commit
- **Commits:** descriptivos en español; post-commit hook hace push automático
- **Controladores delgados:** `app.py` solo valida inputs, llama a `pg_db.py` y renderiza. Sin lógica de negocio en routes
- **Migraciones de esquema:** via `ensure_*()` en `before_request` (no hay sistema de migraciones tradicional)
- **`fecha_simulada`:** usar para testear períodos sin cambiar el reloj del sistema
- **No hay tests automatizados:** el testing es manual vía `APP_ENV=pruebas`
- **Backup:** el botón en el navbar descarga un ZIP de la base de datos (solo archivos locales como comprobantes PDF; los datos de PostgreSQL están en Supabase)
