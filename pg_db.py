"""
Capa de acceso a PostgreSQL (Supabase).
Misma API pública que excel_db.py — reemplaza completamente al Excel como BD.
Requiere: psycopg2-binary, variable de entorno DATABASE_URL.
"""
import os
import re
import threading
import secrets
import hashlib
import hmac as _hmac
import calendar as _calendar
import json
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta

import psycopg2
import psycopg2.errors
import psycopg2.extras
from psycopg2 import sql as _sql
from psycopg2.pool import ThreadedConnectionPool

# ── Entorno ───────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(__file__)
_APP_ENV = os.environ.get("APP_ENV", "produccion").lower()
if _APP_ENV not in ("produccion", "pruebas"):
    _APP_ENV = "produccion"

DATA_DIR = (
    os.path.join(_BASE_DIR, "data")
    if _APP_ENV == "produccion"
    else os.path.join(_BASE_DIR, "data", "pruebas")
)
DB_PATH = os.path.join(DATA_DIR, "edificio_brasil.xlsx")
FACTURAS_DIR = os.path.join(DATA_DIR, "facturas")

# ── Thread-local: consorcio activo ────────────────────────────────────────────
_tls = threading.local()


def get_data_dir() -> str:
    return getattr(_tls, "data_dir", DATA_DIR)


def get_db_path() -> str:
    return getattr(_tls, "db_path", DB_PATH)


def get_facturas_dir() -> str:
    return getattr(_tls, "facturas_dir", FACTURAS_DIR)


def set_active_consorcio(data_dir_abs: str, db_path_abs: str):
    _tls.data_dir = data_dir_abs
    _tls.db_path = db_path_abs
    _tls.facturas_dir = os.path.join(data_dir_abs, "facturas")
    parts = data_dir_abs.rstrip("/\\").split(os.sep)
    last = parts[-1]
    _tls.consorcio_id = "edificio_brasil" if last == "data" else last


def _cid() -> str:
    cid = getattr(_tls, "consorcio_id", None)
    if not cid:
        raise RuntimeError("No hay consorcio activo. Llamar set_active_consorcio primero.")
    return cid


# ── Connection pool ───────────────────────────────────────────────────────────
_pool: ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> ThreadedConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                dsn = os.environ.get("DATABASE_URL")
                if not dsn:
                    raise RuntimeError("DATABASE_URL no configurado")
                _pool = ThreadedConnectionPool(1, 10, dsn)
    return _pool


@contextmanager
def _conn(write: bool = True):
    pool = _get_pool()
    c = pool.getconn()
    if c.closed:                      # la cortó el servidor (Supabase): descartarla y pedir otra
        pool.putconn(c, close=True)
        c = pool.getconn()
    try:
        if write:
            _aplicar_contexto_auditoria(c)
        yield c
        c.commit()
    except Exception:
        try:
            c.rollback()
        except Exception:
            pass                      # conexión rota: se descarta abajo
        raise
    finally:
        pool.putconn(c, close=bool(c.closed))


def _fetchall(sql: str, params=()):
    with _conn(write=False) as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def _fetchone(sql: str, params=()):
    with _conn(write=False) as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def _exec(sql: str, params=()):
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(sql, params)


def _insert_returning(sql: str, params=()) -> int:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]


# ── No-ops para compatibilidad ────────────────────────────────────────────────
def _get_drive(): return None
def sync_from_drive(): pass


# ── Consorcios ────────────────────────────────────────────────────────────────

def list_consorcios() -> list:
    rows = _fetchall("SELECT id, nombre, descripcion FROM consorcios ORDER BY created_at")
    result = []
    for r in rows:
        cid = r["id"]
        result.append({
            "id": cid,
            "nombre": r["nombre"],
            "descripcion": r["descripcion"] or "",
            "data_dir": "data" if cid == "edificio_brasil" else os.path.join("data", cid),
            "db_file": "edificio_brasil.xlsx" if cid == "edificio_brasil" else "base.xlsx",
        })
    return result


def get_consorcio(cid: str) -> dict | None:
    for c in list_consorcios():
        if c["id"] == cid:
            c = dict(c)
            c["data_dir_abs"] = os.path.join(_BASE_DIR, c["data_dir"])
            c["db_path_abs"] = os.path.join(_BASE_DIR, c["data_dir"], c["db_file"])
            return c
    return None


def create_consorcio(nombre: str, descripcion: str = "") -> dict:
    import uuid
    cid = uuid.uuid4().hex[:8]
    _exec("INSERT INTO consorcios (id, nombre, descripcion) VALUES (%s, %s, %s)", (cid, nombre, descripcion))
    _init_config(cid)
    rel_dir = os.path.join("data", cid)
    abs_dir = os.path.join(_BASE_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)
    return {
        "id": cid,
        "nombre": nombre,
        "descripcion": descripcion,
        "data_dir": rel_dir,
        "db_file": "base.xlsx",
        "data_dir_abs": abs_dir,
        "db_path_abs": os.path.join(abs_dir, "base.xlsx"),
    }


def _init_config(cid: str):
    defaults = [
        ("edificio_nombre", ""), ("edificio_direccion", ""), ("alias_cbu", ""),
        ("titular_cuenta", ""), ("administrador", ""), ("telefono", ""),
        ("email", ""), ("whatsapp", ""), ("tasa_mora", "7"),
        ("dia_vencimiento", "15"), ("fondo_reserva_mensual", "0"),
        ("fecha_simulada", ""), ("dias_cobro", ""), ("horario_cobro", ""),
        ("direccion_cobro", ""), ("texto_anuncio", ""),
    ]
    with _conn() as c:
        with c.cursor() as cur:
            for clave, valor in defaults:
                cur.execute(
                    "INSERT INTO config (consorcio_id, clave, valor) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (cid, clave, valor)
                )


def delete_consorcio(cid: str):
    _exec("DELETE FROM consorcios WHERE id = %s", (cid,))


def update_consorcio_nombre(cid: str, nombre: str, descripcion: str = ""):
    _exec("UPDATE consorcios SET nombre=%s, descripcion=%s WHERE id=%s", (nombre, descripcion, cid))


# ── Config ────────────────────────────────────────────────────────────────────

def get_config() -> dict:
    rows = _fetchall("SELECT clave, valor FROM config WHERE consorcio_id = %s", (_cid(),))
    return {r["clave"]: r["valor"] or "" for r in rows}


def save_config(data: dict):
    with _conn() as c:
        with c.cursor() as cur:
            for k, v in data.items():
                cur.execute(
                    "INSERT INTO config (consorcio_id, clave, valor) VALUES (%s,%s,%s) "
                    "ON CONFLICT (consorcio_id, clave) DO UPDATE SET valor = EXCLUDED.valor",
                    (_cid(), k, str(v) if v is not None else "")
                )


def get_fecha_simulada(cfg: dict = None) -> date | None:
    """Fecha del sistema fijada en Configuración (config 'fecha_simulada'), o None si no hay."""
    fs = ((cfg if cfg is not None else get_config()).get("fecha_simulada") or "").strip()
    try:
        return datetime.strptime(fs, "%Y-%m-%d").date() if fs else None
    except ValueError:
        return None


def fecha_sistema(cfg: dict = None) -> date:
    """
    'Hoy' para toda la app: la fecha del sistema fijada en Configuración o, si no hay,
    la fecha real. Se usa para intereses/vencimientos, período actual y fechas por defecto.
    (El vencimiento de checkpoints sigue usando la fecha real: borra archivos.)
    """
    return get_fecha_simulada(cfg) or date.today()


def get_logo() -> dict | None:
    cfg = get_config()
    b64 = cfg.get("logo_b64", "")
    mime = cfg.get("logo_mime", "image/png")
    return {"b64": b64, "mime": mime} if b64 else None


def save_logo(b64_data: str, mime: str):
    save_config({"logo_b64": b64_data, "logo_mime": mime})


def delete_logo():
    _exec("DELETE FROM config WHERE consorcio_id=%s AND clave IN ('logo_b64','logo_mime')", (_cid(),))


def get_clave_firma() -> str:
    clave = get_config().get("clave_firma", "")
    if clave:
        return clave
    clave = secrets.token_hex(32)
    save_config({"clave_firma": clave})
    return clave


def generar_codigo_verificacion(row: dict, cfg: dict, clave_firma: str) -> str:
    campos = "|".join([
        str(row.get("periodo", "")),
        str(row.get("unidad", "")),
        str(row.get("descripcion", "")),
        f"{float(row.get('expensas', 0)):.2f}",
        f"{float(row.get('deuda_anterior', 0)):.2f}",
        f"{float(row.get('interes', 0)):.2f}",
        f"{float(row.get('total_a_pagar', 0)):.2f}",
        str(row.get("tipo_pago", "")),
        f"{float(row.get('monto_pagado', 0)):.2f}",
        str(row.get("fecha_pago", "")),
        str(cfg.get("edificio_nombre", "")),
    ])
    mac = _hmac.new(clave_firma.encode(), campos.encode(), hashlib.sha256)
    return mac.hexdigest()[:32]


# ── Categorías ────────────────────────────────────────────────────────────────

def get_categorias() -> list:
    rows = _fetchall(
        "SELECT nombre, descripcion FROM categorias WHERE consorcio_id = %s ORDER BY nombre",
        (_cid(),)
    )
    return [{"nombre": r["nombre"], "descripcion": r["descripcion"] or ""} for r in rows]


def add_categoria(nombre: str, descripcion: str = "") -> bool:
    try:
        _exec(
            "INSERT INTO categorias (consorcio_id, nombre, descripcion) VALUES (%s,%s,%s)",
            (_cid(), nombre, descripcion)
        )
        return True
    except psycopg2.errors.UniqueViolation:
        return False


def delete_categoria(nombre: str):
    _exec("DELETE FROM categorias WHERE consorcio_id=%s AND nombre=%s", (_cid(), nombre))


# ── Unidades ──────────────────────────────────────────────────────────────────

# Migraciones de columnas: se ejecutan una sola vez por proceso (antes corrían
# un ALTER TABLE en cada request, con lock exclusivo y un round-trip a Supabase).
_columnas_ok: set = set()
_columnas_lock = threading.Lock()


def _ensure_columna(clave: str, sql: str):
    if clave in _columnas_ok:
        return
    with _columnas_lock:
        if clave in _columnas_ok:
            return
        _exec(sql)
        _columnas_ok.add(clave)


def ensure_deuda_inicial_fecha():
    _ensure_columna("unidades.deuda_inicial_fecha",
                    "ALTER TABLE unidades ADD COLUMN IF NOT EXISTS deuda_inicial_fecha VARCHAR(7)")


def ensure_caja_factura_id():
    _ensure_columna("caja.factura_id",
                    "ALTER TABLE caja ADD COLUMN IF NOT EXISTS factura_id INTEGER")


def ensure_factura_vinculos():
    """v9.4: gasto ↔ factura (gastos.factura_id) y observación del pago de la factura."""
    _ensure_columna("gastos.factura_id",
                    "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS factura_id INTEGER")
    _ensure_columna("facturas.observacion",
                    "ALTER TABLE facturas ADD COLUMN IF NOT EXISTS observacion TEXT")


def ensure_liq_sin_interes():
    _ensure_columna("liquidaciones.sin_interes",
                    "ALTER TABLE liquidaciones ADD COLUMN IF NOT EXISTS sin_interes BOOLEAN DEFAULT FALSE")


def get_unidades(solo_activas=False) -> list:
    sql = "SELECT * FROM unidades WHERE consorcio_id = %s"
    if solo_activas:
        sql += " AND activo = TRUE"
    sql += " ORDER BY numero"
    unidades = _fetchall(sql, (_cid(),))
    if not unidades:
        return []

    pcts = _fetchall(
        "SELECT numero, categoria, porcentaje FROM unidad_porcentajes WHERE consorcio_id = %s",
        (_cid(),)
    )
    pct_map: dict[str, dict] = {}
    for p in pcts:
        pct_map.setdefault(p["numero"], {})[p["categoria"]] = float(p["porcentaje"])

    result = []
    for u in unidades:
        row = dict(u)
        row["deuda_inicial"] = float(row["deuda_inicial"]) if row["deuda_inicial"] else 0.0
        row["deuda_inicial_fecha"] = row.get("deuda_inicial_fecha") or ""
        row["activo"] = bool(row["activo"])
        for cat, pct in pct_map.get(row["numero"], {}).items():
            row[f"pct_{cat}"] = pct
        result.append(row)
    return result


def get_unidad(numero) -> dict | None:
    for u in get_unidades():
        if str(u["numero"]) == str(numero):
            return u
    return None


def save_unidad(data: dict):
    numero = str(data.get("numero", ""))
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("""
                INSERT INTO unidades
                    (consorcio_id, numero, descripcion, propietario, inquilino, activo, piso, deuda_inicial,
                     deuda_inicial_fecha, propietario_mail, propietario_celular, inquilino_mail, inquilino_celular,
                     envio_destinatario, envio_canal)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (consorcio_id, numero) DO UPDATE SET
                    descripcion         = EXCLUDED.descripcion,
                    propietario         = EXCLUDED.propietario,
                    inquilino           = EXCLUDED.inquilino,
                    activo              = EXCLUDED.activo,
                    piso                = EXCLUDED.piso,
                    deuda_inicial       = EXCLUDED.deuda_inicial,
                    deuda_inicial_fecha = EXCLUDED.deuda_inicial_fecha,
                    propietario_mail    = EXCLUDED.propietario_mail,
                    propietario_celular = EXCLUDED.propietario_celular,
                    inquilino_mail      = EXCLUDED.inquilino_mail,
                    inquilino_celular   = EXCLUDED.inquilino_celular,
                    envio_destinatario  = EXCLUDED.envio_destinatario,
                    envio_canal         = EXCLUDED.envio_canal
            """, (
                _cid(), numero,
                data.get("descripcion", "") or "",
                data.get("propietario", "") or "",
                data.get("inquilino", "") or "",
                bool(data.get("activo", True)),
                data.get("piso", "") or "",
                float(data.get("deuda_inicial", 0) or 0),
                data.get("deuda_inicial_fecha", "") or None,
                data.get("propietario_mail", "") or "",
                data.get("propietario_celular", "") or "",
                data.get("inquilino_mail", "") or "",
                data.get("inquilino_celular", "") or "",
                data.get("envio_destinatario", "propietario") or "propietario",
                data.get("envio_canal", "mail") or "mail",
            ))
            for cat in get_categorias():
                key = f"pct_{cat['nombre']}"
                if key in data:
                    cur.execute("""
                        INSERT INTO unidad_porcentajes (consorcio_id, numero, categoria, porcentaje)
                        VALUES (%s,%s,%s,%s)
                        ON CONFLICT (consorcio_id, numero, categoria)
                        DO UPDATE SET porcentaje = EXCLUDED.porcentaje
                    """, (_cid(), numero, cat["nombre"], float(data[key] or 0)))


def save_unidad_envio(numero: str, destinatario: str, canal: str):
    _exec(
        "UPDATE unidades SET envio_destinatario=%s, envio_canal=%s WHERE consorcio_id=%s AND numero=%s",
        (destinatario, canal, _cid(), str(numero))
    )


def delete_unidad(numero):
    _exec("DELETE FROM unidades WHERE consorcio_id=%s AND numero=%s", (_cid(), str(numero)))


# ── Gastos mensuales ──────────────────────────────────────────────────────────

def get_gastos(periodo: str) -> list:
    rows = _fetchall(
        "SELECT g.id, g.periodo, g.concepto, g.importe, g.tipo, f.id AS factura_id, "
        "f.estado AS factura_estado FROM gastos g "
        "LEFT JOIN facturas f ON f.id = g.factura_id AND f.consorcio_id = g.consorcio_id "
        "WHERE g.consorcio_id=%s AND g.periodo=%s ORDER BY g.id",
        (_cid(), periodo)
    )
    return [{
        "row": r["id"],
        "periodo": r["periodo"],
        "concepto": r["concepto"] or "",
        "importe": float(r["importe"]),
        "tipo": r["tipo"] or "FIJO",
        "factura_id": r["factura_id"],
        "factura_estado": r["factura_estado"] or "",
    } for r in rows]


def save_gasto(periodo: str, concepto: str, importe: float, tipo: str, row_num: int = None):
    if row_num:
        existing = _fetchone("SELECT tipo FROM gastos WHERE id=%s AND consorcio_id=%s", (row_num, _cid()))
        if existing and existing["tipo"] == "FONDO_RESERVA":
            # Solo permite cambiar el importe; tipo y concepto quedan fijos
            _exec(
                "UPDATE gastos SET importe=%s WHERE id=%s AND consorcio_id=%s",
                (importe, row_num, _cid())
            )
            return
        _exec(
            "UPDATE gastos SET periodo=%s, concepto=%s, importe=%s, tipo=%s WHERE id=%s AND consorcio_id=%s",
            (periodo, concepto, importe, tipo, row_num, _cid())
        )
    else:
        _exec(
            "INSERT INTO gastos (consorcio_id, periodo, concepto, importe, tipo) VALUES (%s,%s,%s,%s,%s)",
            (_cid(), periodo, concepto, importe, tipo)
        )


def delete_gasto(row_num: int):
    existing = _fetchone("SELECT tipo FROM gastos WHERE id=%s AND consorcio_id=%s", (row_num, _cid()))
    if existing and existing["tipo"] == "FONDO_RESERVA":
        return
    _exec("DELETE FROM gastos WHERE id=%s AND consorcio_id=%s", (row_num, _cid()))


def get_total_gastos(periodo: str) -> float:
    return sum(g["importe"] for g in get_gastos(periodo) if g.get("tipo") != "VARIABLE_FR")


# ── Caja diaria ───────────────────────────────────────────────────────────────

def get_caja(periodo: str, page: int = 1, per_page: int = 50):
    base = "FROM caja WHERE consorcio_id=%s AND to_char(fecha,'YYYY-MM')=%s"
    params = (_cid(), periodo)
    total = (_fetchone(f"SELECT COUNT(*) AS n {base}", params) or {}).get("n", 0)
    offset = (page - 1) * per_page
    rows = _fetchall(
        f"SELECT id, fecha, descripcion, tipo, categoria, importe, factura_id {base} "
        f"ORDER BY fecha, id LIMIT %s OFFSET %s",
        params + (per_page, offset)
    )
    return [{
        "row": r["id"],
        "fecha": r["fecha"].strftime("%Y-%m-%d") if r["fecha"] else "",
        "descripcion": r["descripcion"] or "",
        "tipo": r["tipo"] or "",
        "categoria": r["categoria"] or "",
        "importe": float(r["importe"]),
        "factura_id": r["factura_id"],
    } for r in rows], int(total)


def save_movimiento(fecha: str, descripcion: str, tipo: str, categoria: str, importe: float, row_num: int = None):
    if isinstance(fecha, str):
        fecha_d = datetime.strptime(fecha, "%Y-%m-%d").date()
    else:
        fecha_d = fecha
    if row_num:
        _exec(
            "UPDATE caja SET fecha=%s, descripcion=%s, tipo=%s, categoria=%s, importe=%s WHERE id=%s AND consorcio_id=%s",
            (fecha_d, descripcion, tipo, categoria, importe, row_num, _cid())
        )
        # Si el movimiento es el cobro de un pago de expensas, el pago acompaña el cambio (v9.0)
        pago = _fetchone("SELECT periodo FROM pagos WHERE consorcio_id=%s AND caja_id=%s", (_cid(), row_num))
        if pago:
            _exec("UPDATE pagos SET fecha=%s, monto=%s WHERE consorcio_id=%s AND caja_id=%s",
                  (fecha_d, importe, _cid(), row_num))
            _regenerar_siguiente(pago["periodo"])
        else:
            _exec("UPDATE pagos SET bonificacion=%s WHERE consorcio_id=%s AND bonif_caja_id=%s",
                  (importe, _cid(), row_num))
            _exec("UPDATE pagos SET interes=%s WHERE consorcio_id=%s AND interes_caja_id=%s",
                  (importe, _cid(), row_num))
    else:
        _exec(
            "INSERT INTO caja (consorcio_id, fecha, descripcion, tipo, categoria, importe) VALUES (%s,%s,%s,%s,%s,%s)",
            (_cid(), fecha_d, descripcion, tipo, categoria, importe)
        )


def delete_movimiento(row_num: int) -> bool:
    """
    Borra un movimiento de Caja. Devuelve False si está bloqueado: la caja del mes está cerrada
    (se cerró la liquidación que lleva los gastos de ese mes) o es el cobro de un pago que ya no
    se puede anular (no es de la última liquidación cerrada).
    """
    row = _fetchone(
        "SELECT fecha, categoria, descripcion, importe, factura_id FROM caja "
        "WHERE id=%s AND consorcio_id=%s",
        (row_num, _cid())
    )
    if row and row["fecha"]:
        if caja_mes_bloqueado(row["fecha"].strftime("%Y-%m")):
            return False
        pago = _fetchone("SELECT id, periodo FROM pagos WHERE consorcio_id=%s AND caja_id=%s",
                         (_cid(), row_num))
        if pago:
            if pago["periodo"] != periodo_cobranza():
                return False
            _exec("DELETE FROM pagos WHERE id=%s", (pago["id"],))
        else:
            _exec("UPDATE pagos SET bonificacion=0, bonif_motivo=NULL, bonif_caja_id=NULL "
                  "WHERE consorcio_id=%s AND bonif_caja_id=%s", (_cid(), row_num))
            _exec("UPDATE pagos SET interes=0, interes_caja_id=NULL "
                  "WHERE consorcio_id=%s AND interes_caja_id=%s", (_cid(), row_num))
        # Revert linked factura to PENDIENTE
        if row["factura_id"]:
            _exec(
                "UPDATE facturas SET estado='PENDIENTE', fecha_pago=NULL "
                "WHERE id=%s AND consorcio_id=%s",
                (row["factura_id"], _cid())
            )
        _exec("DELETE FROM caja WHERE id=%s AND consorcio_id=%s", (row_num, _cid()))
        if pago:
            _regenerar_siguiente(pago["periodo"])
        return True
    _exec("DELETE FROM caja WHERE id=%s AND consorcio_id=%s", (row_num, _cid()))
    return True


def get_ultimo_movimiento_caja() -> dict | None:
    row = _fetchone(
        "SELECT id, fecha, descripcion, tipo, categoria, importe FROM caja "
        "WHERE consorcio_id=%s ORDER BY id DESC LIMIT 1",
        (_cid(),)
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "fecha": row["fecha"].strftime("%Y-%m-%d") if row["fecha"] else "",
        "descripcion": row["descripcion"] or "",
        "tipo": row["tipo"] or "",
        "categoria": row["categoria"] or "",
        "importe": float(row["importe"]),
    }


# ── Liquidaciones ─────────────────────────────────────────────────────────────

def _liq_row(r) -> dict:
    fp = r["fecha_pago"]
    return {
        "row": r["id"],
        "periodo": r["periodo"],
        "unidad": r["unidad"],
        "descripcion": r["descripcion"] or "",
        "propietario": r["propietario"] or "",
        "inquilino": r["inquilino"] or "",
        "pct_aplicado": float(r["pct_aplicado"]) if r["pct_aplicado"] else 0.0,
        "expensas": float(r["expensas"]) if r["expensas"] else 0.0,
        "deuda_anterior": float(r["deuda_anterior"]) if r["deuda_anterior"] else 0.0,
        "interes": float(r["interes"]) if r["interes"] else 0.0,
        "total_a_pagar": float(r["total_a_pagar"]) if r["total_a_pagar"] else 0.0,
        "pagado": 1 if r["pagado"] else 0,
        "monto_pagado": float(r["monto_pagado"]) if r["monto_pagado"] else 0.0,
        "tipo_pago": r["tipo_pago"] or "PENDIENTE",
        "saldo_pendiente": float(r["saldo_pendiente"]) if r["saldo_pendiente"] else 0.0,
        "fecha_pago": fp.strftime("%Y-%m-%d") if fp else "",
        "extras": float(r["extras"]) if r["extras"] else 0.0,
        "sin_interes": bool(r["sin_interes"]) if r.get("sin_interes") is not None else False,
    }


def get_liquidacion(periodo: str, simular: bool = True) -> list:
    """
    Filas de la liquidación con su estado de pago (v9.0: calculado desde la tabla `pagos`).
    Con una fecha del sistema fijada y simular=True, los pagos con fecha posterior a ese día
    no se cuentan (quedan en `pago_posterior`). Recibos firmados y escrituras: simular=False.
    """
    rows = _fetchall(
        "SELECT * FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s ORDER BY unidad",
        (_cid(), periodo)
    )
    filas = [_liq_row(r) for r in rows]
    return _aplicar_pagos(periodo, filas, hasta=get_fecha_simulada() if simular else None)


def _aplicar_pagos(periodo: str, filas: list, hasta: date = None, pagos: list = None) -> list:
    """
    Completa en cada fila monto_pagado / fecha_pago / tipo_pago / saldo_pendiente / pagado con
    los pagos registrados contra la liquidación (tabla `pagos`). `hasta`: solo cuentan los pagos
    con fecha <= hasta (fecha del sistema fijada); los posteriores quedan en `pago_posterior`.
    """
    if not filas:
        return filas
    if pagos is None:
        pagos = get_pagos(periodo)
    hasta_iso = hasta.strftime("%Y-%m-%d") if hasta else None
    por_unidad: dict = {}
    for p in pagos:
        por_unidad.setdefault(str(p["unidad"]), []).append(p)
    for r in filas:
        lista = por_unidad.get(str(r["unidad"]), [])
        validos = [p for p in lista if not hasta_iso or p["fecha"] <= hasta_iso]
        posteriores = [p for p in lista if hasta_iso and p["fecha"] > hasta_iso]
        monto = round(sum(p["monto"] for p in validos), 2)
        tipo_pago, saldo, pagado = _estado_pago(r["total_a_pagar"], monto)
        r.update({
            "monto_pagado": monto,
            "fecha_pago": max((p["fecha"] for p in validos), default=""),
            "tipo_pago": tipo_pago,
            "saldo_pendiente": saldo if (monto > 0 or pagado) else 0.0,
            "pagado": 1 if pagado else 0,
            "pagos": validos,
            "interes_cobrado": round(sum(p.get("interes", 0) for p in validos), 2),
        })
        r.pop("pago_posterior", None)
        if posteriores:
            r["pago_posterior"] = {"fecha": min(p["fecha"] for p in posteriores),
                                   "monto": round(sum(p["monto"] for p in posteriores), 2)}
        if hasta_iso:
            r["simulado"] = True
    return filas


def _prev_periodo(periodo: str) -> str:
    y, m = int(periodo[:4]), int(periodo[5:7])
    return f"{y-1}-12" if m == 1 else f"{y}-{m-1:02d}"


def _next_periodo(periodo: str) -> str:
    y, m = int(periodo[:4]), int(periodo[5:7])
    return f"{y+1}-01" if m == 12 else f"{y}-{m+1:02d}"


def liquidacion_existe(periodo: str) -> bool:
    return _fetchone(
        "SELECT 1 FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s LIMIT 1",
        (_cid(), periodo)
    ) is not None


def _fecha_vencimiento(periodo: str, cfg: dict) -> date | None:
    """Día de vencimiento de la liquidación `periodo` (config dia_vencimiento; <=0 = fin de mes)."""
    try:
        dia_venc = int(cfg.get("dia_vencimiento", 15) or 15)
        yp, mp = int(periodo[:4]), int(periodo[5:7])
        ultimo_dia = _calendar.monthrange(yp, mp)[1]
        dia_venc_real = ultimo_dia if dia_venc <= 0 else min(dia_venc, ultimo_dia)
        return date(yp, mp, dia_venc_real)
    except Exception:
        return None


def _estado_pago(total: float, monto_pagado: float):
    """
    Devuelve (tipo_pago, saldo, pagado) según lo abonado contra el total.
    saldo < 0 = saldo A FAVOR (pagó de más, o el saldo a favor anterior cubre todo el mes):
    la unidad queda pagada y ese saldo pasa al mes siguiente (v7.0).
    """
    if total <= 0 or (monto_pagado >= total and monto_pagado > 0):
        return "TOTAL", round(total - monto_pagado, 2), True
    if monto_pagado > 0:
        return "PARCIAL", round(total - monto_pagado, 2), False
    return "PENDIENTE", total, False


def generar_liquidacion(periodo: str):
    """
    Genera / recalcula la liquidación ABIERTA de `periodo`. La fecha de referencia es la fecha del
    sistema (fijada o real): deuda anterior = total de la liquidación anterior − sus pagos con
    fecha <= hoy (negativa = saldo a favor). Mientras está abierta NO lleva interés: el interés se
    decide al CERRARLA (v9.2, `cerrar_liquidacion` con un switch por unidad). Si nada cambió no escribe.
    """
    if liq_esta_cerrada(periodo):
        return None

    mes_gastos = _prev_periodo(periodo)
    ensure_fondo_reserva_gasto(mes_gastos)
    hoy_iso = fecha_sistema().strftime("%Y-%m-%d")
    periodo_ant = _prev_periodo(periodo)

    unidades = get_unidades(solo_activas=True)
    gastos = get_gastos(mes_gastos)
    total_gastos = sum(g["importe"] for g in gastos if g.get("tipo") != "VARIABLE_FR")
    categorias = [c["nombre"] for c in get_categorias()]

    prev_liq = {str(r["unidad"]): r for r in (_liq_row(x) for x in _fetchall(
        "SELECT * FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s", (_cid(), periodo_ant)))}
    pagado_hoy: dict = {}
    for p in get_pagos(periodo_ant):
        if p["fecha"] <= hoy_iso:
            u = str(p["unidad"])
            pagado_hoy[u] = pagado_hoy.get(u, 0.0) + p["monto"]

    existentes = {str(r["unidad"]): r for r in (_liq_row(x) for x in _fetchall(
        "SELECT * FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s", (_cid(), periodo)))}
    all_extras = get_gastos_extra(periodo)

    expensas_ya = 0.0
    new_rows = []
    for idx, u in enumerate(unidades):
        numero = str(u["numero"])

        pct_vals = [float(u[f"pct_{c}"]) for c in categorias if u.get(f"pct_{c}")]
        pct = pct_vals[0] if len(pct_vals) == 1 else (sum(pct_vals) / len(pct_vals) if pct_vals else 0.0)

        if idx == len(unidades) - 1 and total_gastos > 0:
            expensas = round(total_gastos - expensas_ya, 2)
        else:
            expensas = round(total_gastos * pct / 100, 2)
            expensas_ya += expensas

        prev_row = prev_liq.get(numero)
        if not prev_row:
            try:
                deuda_anterior = round(float(u.get("deuda_inicial") or 0), 2)
            except (ValueError, TypeError):
                deuda_anterior = 0.0
        else:
            total_prev = float(prev_row["total_a_pagar"] or 0)
            deuda_anterior = round(total_prev - pagado_hoy.get(numero, 0.0), 2)
        interes = 0.0
        sin_interes = False

        extras_unidad = round(sum(
            float(e.get("monto") or 0)
            for e in all_extras
            if str(e.get("unidad", "")) == numero
        ), 2)

        total = round(expensas + deuda_anterior + interes + extras_unidad, 2)

        new_rows.append((
            _cid(), periodo, numero,
            u.get("descripcion", "") or "", u.get("propietario", "") or "", u.get("inquilino", "") or "",
            pct, expensas, deuda_anterior, interes, total, False,
            None, None, None, None,
            extras_unidad if extras_unidad else None,
            sin_interes,
        ))

    def _clave(numero, desc, prop, inq, pct, exp, deuda, interes, total, extras, sin_int):
        return (str(numero), desc or "", prop or "", inq or "", round(float(pct or 0), 4),
                round(float(exp or 0), 2), round(float(deuda or 0), 2), round(float(interes or 0), 2),
                round(float(total or 0), 2), round(float(extras or 0), 2), bool(sin_int))

    nuevas = {_clave(r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[16], r[17]) for r in new_rows}
    actuales = {_clave(r["unidad"], r["descripcion"], r["propietario"], r["inquilino"], r["pct_aplicado"],
                       r["expensas"], r["deuda_anterior"], r["interes"], r["total_a_pagar"], r["extras"],
                       r["sin_interes"]) for r in existentes.values()}
    if nuevas != actuales or len(new_rows) != len(existentes):
        with _conn() as c:
            with c.cursor() as cur:
                cur.execute("DELETE FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s", (_cid(), periodo))
                cur.executemany("""
                    INSERT INTO liquidaciones
                      (consorcio_id, periodo, unidad, descripcion, propietario, inquilino,
                       pct_aplicado, expensas, deuda_anterior, interes, total_a_pagar, pagado,
                       monto_pagado, tipo_pago, saldo_pendiente, fecha_pago, extras, sin_interes)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, new_rows)

    if get_liq_estado(periodo) != "ABIERTA":
        set_liq_estado(periodo, "ABIERTA")
    return get_liquidacion(periodo, simular=False)


def recalcular_intereses_abiertas() -> list:
    """
    Recalcula todas las liquidaciones NO cerradas a la fecha del sistema (se llama al cambiar
    esa fecha: deuda anterior e interés dependen de los pagos hasta ese día). Devuelve los períodos.
    """
    periodos = [r["periodo"] for r in _fetchall("""
        SELECT DISTINCT l.periodo FROM liquidaciones l
        WHERE l.consorcio_id = %s AND NOT EXISTS (
            SELECT 1 FROM liquidaciones_estado e
            WHERE e.consorcio_id = l.consorcio_id AND e.periodo = l.periodo AND e.estado = 'CERRADA')
        ORDER BY l.periodo
    """, (_cid(),))]
    for p in periodos:
        generar_liquidacion(p)
    return periodos


def ensure_pagos():
    _ensure_columna("tabla.pagos", """
        CREATE TABLE IF NOT EXISTS pagos (
            id             SERIAL PRIMARY KEY,
            consorcio_id   TEXT NOT NULL REFERENCES consorcios(id) ON DELETE CASCADE,
            periodo        VARCHAR(7) NOT NULL,
            unidad         TEXT NOT NULL,
            fecha          DATE NOT NULL,
            monto          NUMERIC(14,2) NOT NULL,
            bonificacion   NUMERIC(14,2) NOT NULL DEFAULT 0,
            bonif_motivo   TEXT,
            caja_id        INTEGER,
            bonif_caja_id  INTEGER,
            creado_en      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS pagos_consorcio_periodo ON pagos (consorcio_id, periodo)
    """)
    _ensure_columna("pagos.interes", """
        ALTER TABLE pagos ADD COLUMN IF NOT EXISTS interes NUMERIC(14,2) NOT NULL DEFAULT 0,
                          ADD COLUMN IF NOT EXISTS interes_caja_id INTEGER
    """)


def _pago_row(r) -> dict:
    return {
        "id": r["id"], "periodo": r["periodo"], "unidad": str(r["unidad"]),
        "fecha": r["fecha"].strftime("%Y-%m-%d") if r["fecha"] else "",
        "monto": float(r["monto"] or 0),
        "bonificacion": float(r["bonificacion"] or 0),
        "bonif_motivo": r["bonif_motivo"] or "",
        "caja_id": r["caja_id"], "bonif_caja_id": r["bonif_caja_id"],
        "interes": float(r.get("interes") or 0), "interes_caja_id": r.get("interes_caja_id"),
    }


def get_pagos(periodo: str, unidad: str = None) -> list:
    """Pagos registrados contra la liquidación `periodo` (orden: fecha, id)."""
    sql = "SELECT * FROM pagos WHERE consorcio_id=%s AND periodo=%s"
    params = [_cid(), periodo]
    if unidad is not None:
        sql += " AND unidad=%s"
        params.append(str(unidad))
    return [_pago_row(r) for r in _fetchall(sql + " ORDER BY fecha, id", tuple(params))]


def periodo_cobranza() -> str:
    """Liquidación sobre la que se cobra: la última CERRADA ('' si no hay ninguna)."""
    return get_ultima_liq_cerrada()


def caja_mes_bloqueado(mes: str) -> bool:
    """La Caja del mes M queda cerrada cuando se cierra la liquidación que lleva sus gastos (M+1)."""
    return liq_esta_cerrada(_next_periodo(mes))


def _error_cobro(periodo: str) -> str | None:
    if not liquidacion_existe(periodo):
        return f"No hay liquidación generada para {periodo}."
    if not liq_esta_cerrada(periodo):
        return (f"La liquidación de {periodo} todavía está abierta: se cobra recién cuando se cierra "
                f"(el monto queda fijo).")
    actual = periodo_cobranza()
    if periodo != actual:
        return f"Solo se registran o anulan pagos de la última liquidación cerrada ({actual})."
    return None


def info_cobranza(periodo: str, filas: list) -> dict:
    """Agrega a cada fila `saldo_a_pagar`. Devuelve datos de la pantalla de Cobranzas."""
    for r in filas:
        saldo = 0.0 if r["tipo_pago"] == "TOTAL" else (
            r["saldo_pendiente"] if r["tipo_pago"] == "PARCIAL" else r["total_a_pagar"])
        r["saldo_a_pagar"] = round(saldo, 2)
    venc = _fecha_vencimiento(periodo, get_config())
    return {"vencimiento": venc.strftime("%Y-%m-%d") if venc else ""}


def _regenerar_siguiente(periodo: str):
    """Los pagos de `periodo` cambian la deuda anterior / interés de la siguiente si está abierta."""
    sig = _next_periodo(periodo)
    if liquidacion_existe(sig) and not liq_esta_cerrada(sig):
        generar_liquidacion(sig)


def registrar_pago(periodo: str, unidad: str, monto: float, fecha: str = None,
                   bonificacion: float = 0.0, bonif_motivo: str = "", regenerar: bool = True) -> dict:
    """
    Registra un pago de expensas contra la liquidación CERRADA `periodo` (v9.0). Crea el pago,
    su entrada en Caja y, si hay bonificación, la salida en Caja (no cambia lo que se debe).
    El interés no se cobra acá: se define al cerrar la liquidación (v9.2). Las columnas
    pagos.interes / interes_caja_id quedan de la v9.1 (se siguen mostrando y anulando).
    Devuelve {"error": msg} o {"tipo", "saldo", "monto", "total_pagado"}.
    """
    err = _error_cobro(periodo)
    if err:
        return {"error": err}
    if not fecha:
        fecha = fecha_sistema().strftime("%Y-%m-%d")
    try:
        fecha_d = datetime.strptime(fecha, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"error": "Fecha de pago inválida."}
    if not monto or monto <= 0:
        return {"error": "El monto debe ser mayor a cero."}
    if fecha_d > fecha_sistema():
        return {"error": f"La fecha de pago ({fecha_d.strftime('%d/%m/%Y')}) es posterior a la fecha del sistema "
                         f"({fecha_sistema().strftime('%d/%m/%Y')})."}
    mes = fecha[:7]
    if caja_mes_bloqueado(mes):
        return {"error": f"La Caja de {mes} está cerrada (se cerró la liquidación {_next_periodo(mes)}): "
                         f"usá una fecha posterior."}
    row = _fetchone("SELECT * FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s AND unidad=%s",
                    (_cid(), periodo, str(unidad)))
    if not row:
        return {"error": f"La UF {unidad} no figura en la liquidación {periodo}."}

    total = float(row["total_a_pagar"] or 0)
    previo = sum(p["monto"] for p in get_pagos(periodo, unidad))
    total_pagado = round(previo + monto, 2)
    tipo_pago, saldo, _ = _estado_pago(total, total_pagado)

    persona = row["inquilino"] or row["propietario"] or f"Unidad {unidad}"
    sufijo = " (PARCIAL)" if tipo_pago == "PARCIAL" else ""
    caja_id = _insert_returning(
        "INSERT INTO caja (consorcio_id, fecha, descripcion, tipo, categoria, importe) "
        "VALUES (%s,%s,%s,'ENTRADA','Expensas',%s) RETURNING id",
        (_cid(), fecha_d, f"Expensas {periodo} - {persona} - UF {unidad}{sufijo}"[:200], round(monto, 2)))
    bonif_caja_id = None
    bonificacion = round(float(bonificacion or 0), 2)
    if bonificacion > 0:
        desc = f"Bonificación UF {unidad} {periodo}" + (f" - {bonif_motivo}" if bonif_motivo else "")
        bonif_caja_id = _insert_returning(
            "INSERT INTO caja (consorcio_id, fecha, descripcion, tipo, categoria, importe) "
            "VALUES (%s,%s,%s,'SALIDA','BONIFICACION',%s) RETURNING id",
            (_cid(), fecha_d, desc[:200], bonificacion))
    _exec("""
        INSERT INTO pagos (consorcio_id, periodo, unidad, fecha, monto, bonificacion, bonif_motivo,
                           caja_id, bonif_caja_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (_cid(), periodo, str(unidad), fecha_d, round(monto, 2), bonificacion,
          (bonif_motivo or None) if bonificacion > 0 else None, caja_id, bonif_caja_id))
    if regenerar:
        _regenerar_siguiente(periodo)
    return {"tipo": tipo_pago, "saldo": saldo, "monto": round(monto, 2), "total_pagado": total_pagado}


def anular_pagos(periodo: str, unidades: list = None, pago_id: int = None) -> tuple:
    """
    Anula pagos de la última liquidación cerrada: uno (pago_id), los de ciertas unidades, o
    todos. Borra también sus entradas (y bonificaciones) en Caja, en una sola transacción
    (auditada: se puede revertir desde el Log de Movimientos). Devuelve (ok, mensaje, cantidad).
    """
    err = _error_cobro(periodo)
    if err:
        return False, err, 0
    pagos = get_pagos(periodo)
    if pago_id is not None:
        pagos = [p for p in pagos if p["id"] == int(pago_id)]
    elif unidades is not None:
        pagos = [p for p in pagos if p["unidad"] in {str(u) for u in unidades}]
    if not pagos:
        return False, "No hay pagos registrados para anular.", 0
    for p in pagos:
        if caja_mes_bloqueado(p["fecha"][:7]):
            return False, (f"El pago de la UF {p['unidad']} del {p['fecha']} está en una Caja cerrada "
                           f"({p['fecha'][:7]}): no se anuló nada."), 0
    ids_caja = [i for p in pagos for i in (p["caja_id"], p["bonif_caja_id"], p.get("interes_caja_id")) if i]
    with _conn() as c:
        with c.cursor() as cur:
            if ids_caja:
                cur.execute("DELETE FROM caja WHERE consorcio_id=%s AND id = ANY(%s)", (_cid(), ids_caja))
            cur.execute("DELETE FROM pagos WHERE consorcio_id=%s AND id = ANY(%s)",
                        (_cid(), [p["id"] for p in pagos]))
    _regenerar_siguiente(periodo)
    return True, (f"Se anularon {len(pagos)} pago(s) de {periodo} y {len(ids_caja)} movimiento(s) de Caja."), len(pagos)


def pagar_todo(periodo: str, fecha_pago: str) -> tuple:
    """Paga el saldo de todas las unidades con deuda en la liquidación. Devuelve (cantidad, error)."""
    err = _error_cobro(periodo)
    if err:
        return 0, err
    n = 0
    for r in get_liquidacion(periodo, simular=False):
        if r["tipo_pago"] == "TOTAL":
            continue
        saldo = r["saldo_pendiente"] if r["tipo_pago"] == "PARCIAL" else r["total_a_pagar"]
        if saldo <= 0:
            continue
        res = registrar_pago(periodo, str(r["unidad"]), saldo, fecha_pago, regenerar=False)
        if res.get("error"):
            if n:
                _regenerar_siguiente(periodo)
            return n, res["error"]
        n += 1
    if n:
        _regenerar_siguiente(periodo)
    return n, None


def migrar_pagos_legacy() -> int:
    """
    v9.0: pasa los pagos guardados en las filas de liquidaciones (monto_pagado / fecha_pago) a la
    tabla `pagos`, vinculándolos con sus entradas "Expensas P - ... - UF n" de Caja (y las
    bonificaciones). Una sola vez por consorcio (config pagos_migrados=1). Devuelve los pagos creados.
    """
    cid = _cid()
    if cid in _pagos_migrados:
        return 0
    if str(get_config().get("pagos_migrados", "")) == "1":
        _pagos_migrados.add(cid)
        return 0
    creados = 0
    filas = _fetchall("SELECT periodo, unidad, monto_pagado, fecha_pago FROM liquidaciones "
                      "WHERE consorcio_id=%s AND COALESCE(monto_pagado, 0) > 0 ORDER BY periodo, unidad", (cid,))
    for f in filas:
        periodo, unidad = f["periodo"], str(f["unidad"])
        if _fetchone("SELECT 1 FROM pagos WHERE consorcio_id=%s AND periodo=%s AND unidad=%s",
                     (cid, periodo, unidad)):
            continue
        p_re, u_re = re.escape(periodo), re.escape(unidad)
        cobros = _fetchall("""
            SELECT id, fecha, importe FROM caja
            WHERE consorcio_id=%s AND tipo='ENTRADA' AND categoria='Expensas' AND descripcion ~ %s
              AND id NOT IN (SELECT caja_id FROM pagos WHERE consorcio_id=%s AND caja_id IS NOT NULL)
            ORDER BY fecha, id
        """, (cid, f"^Expensas {p_re} - .* - UF {u_re}( \\(PARCIAL\\))?$", cid))
        bonifs = _fetchall("""
            SELECT id, importe, descripcion FROM caja
            WHERE consorcio_id=%s AND tipo='SALIDA' AND categoria='BONIFICACION' AND descripcion ~ %s
            ORDER BY fecha, id
        """, (cid, f"^Bonificación UF {u_re} {p_re}( - .*)?$"))
        nuevos = [(c["fecha"], float(c["importe"]), c["id"]) for c in cobros]
        resto = round(float(f["monto_pagado"]) - sum(n[1] for n in nuevos), 2)
        if resto > 0.009:
            fecha_resto = f["fecha_pago"] or (nuevos[-1][0] if nuevos else date(int(periodo[:4]), int(periodo[5:7]), 1))
            nuevos.append((fecha_resto, resto, None))
        for i, (fecha, monto, caja_id) in enumerate(nuevos):
            b = bonifs[0] if (i == 0 and bonifs) else None
            motivo = None
            if b and " - " in (b["descripcion"] or ""):
                motivo = b["descripcion"].split(" - ", 1)[1]
            _exec("""
                INSERT INTO pagos (consorcio_id, periodo, unidad, fecha, monto, bonificacion, bonif_motivo,
                                   caja_id, bonif_caja_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (cid, periodo, unidad, fecha, round(monto, 2), float(b["importe"]) if b else 0,
                  motivo, caja_id, b["id"] if b else None))
            creados += 1
    save_config({"pagos_migrados": "1"})
    _pagos_migrados.add(cid)
    return creados


_pagos_migrados: set = set()


def get_años_con_liquidacion() -> list:
    rows = _fetchall(
        "SELECT DISTINCT CAST(LEFT(periodo, 4) AS INTEGER) as año FROM liquidaciones WHERE consorcio_id=%s ORDER BY 1",
        (_cid(),)
    )
    return [int(r["año"]) for r in rows] if rows else []


# ── Estado de liquidación ─────────────────────────────────────────────────────

def get_liq_estado(periodo: str) -> str:
    row = _fetchone(
        "SELECT estado FROM liquidaciones_estado WHERE consorcio_id=%s AND periodo=%s",
        (_cid(), periodo)
    )
    return row["estado"] if row else ""


def ensure_liq_fecha_cierre():
    _ensure_columna("liquidaciones_estado.fecha_cierre",
                    "ALTER TABLE liquidaciones_estado ADD COLUMN IF NOT EXISTS fecha_cierre DATE")


def set_liq_estado(periodo: str, estado: str):
    """Guarda el estado; al CERRAR registra la fecha de cierre (fecha del sistema), al reabrir la borra."""
    ensure_liq_fecha_cierre()
    fecha_cierre = fecha_sistema() if estado == "CERRADA" else None
    _exec("""
        INSERT INTO liquidaciones_estado (consorcio_id, periodo, estado, fecha_cierre)
        VALUES (%s,%s,%s,%s)
        ON CONFLICT (consorcio_id, periodo) DO UPDATE SET estado = EXCLUDED.estado,
            fecha_cierre = EXCLUDED.fecha_cierre
    """, (_cid(), periodo, estado, fecha_cierre))


def fecha_corte_liquidacion(periodo: str) -> date:
    """
    Fecha a la que se informa el saldo de caja de la liquidación `periodo` (v8.1):
    - CERRADA: la fecha en que se cerró (si se cerró antes de registrar la fecha, fin de mes);
    - ABIERTA o sin generar: la fecha del sistema (hoy de la app).
    Nunca antes del día anterior al inicio del mes.
    """
    ensure_liq_fecha_cierre()
    y, m = int(periodo[:4]), int(periodo[5:7])
    fin_mes = date(y, m, _calendar.monthrange(y, m)[1])
    row = _fetchone("SELECT estado, fecha_cierre FROM liquidaciones_estado WHERE consorcio_id=%s AND periodo=%s",
                    (_cid(), periodo))
    if row and row["estado"] == "CERRADA":
        corte = row["fecha_cierre"] or fin_mes
    else:
        corte = fecha_sistema()
    return max(corte, date(y, m, 1) - timedelta(days=1))


def liq_esta_cerrada(periodo: str) -> bool:
    return get_liq_estado(periodo) == "CERRADA"


def error_cierre(periodo: str) -> str | None:
    """Motivo por el que no se puede cerrar la liquidación (None si se puede). v9.0:
    se cierra cuando cambió el mes (desde el día 1 del mes de la liquidación, según la fecha
    del sistema) y la anterior ya está cerrada."""
    if not liquidacion_existe(periodo):
        return "No hay liquidación generada para cerrar."
    if liq_esta_cerrada(periodo):
        return f"La liquidación de {periodo} ya está cerrada."
    ant = _prev_periodo(periodo)
    if liquidacion_existe(ant) and not liq_esta_cerrada(ant):
        return f"Primero hay que cerrar la liquidación de {ant}."
    inicio = date(int(periodo[:4]), int(periodo[5:7]), 1)
    if fecha_sistema() < inicio:
        return (f"Todavía no cambió el mes: la liquidación de {periodo} se puede cerrar a partir del "
                f"{inicio.strftime('%d/%m/%Y')} (fecha del sistema: {fecha_sistema().strftime('%d/%m/%Y')}).")
    return None


def tasa_mora(cfg: dict = None) -> float:
    cfg = cfg if cfg is not None else get_config()
    return float(cfg.get("tasa_mora", 7) or 0)


def propuesta_intereses(filas: list, cfg: dict = None) -> list:
    """Unidades con deuda anterior (> 0) y el interés que les corresponde al cerrar:
    tasa × deuda anterior (v9.2). Para la ventana de cierre."""
    tasa = tasa_mora(cfg)
    return [{"unidad": str(r["unidad"]), "persona": r.get("inquilino") or r.get("propietario") or "",
             "deuda": round(r["deuda_anterior"], 2), "interes": round(r["deuda_anterior"] * tasa / 100, 2)}
            for r in filas if r["deuda_anterior"] > 0]


def cerrar_liquidacion(periodo: str, con_interes=None) -> str | None:
    """
    Recalcula a la fecha del sistema y congela la liquidación (v9.2). Al cerrar se decide el
    interés: a las unidades de `con_interes` (iterable de números de UF; None = ninguna) se les
    suma tasa × deuda anterior; a las demás, 0 (quedan con sin_interes). Devuelve error o None.
    """
    err = error_cierre(periodo)
    if err:
        return err
    filas = generar_liquidacion(periodo) or []
    elegidas = {str(u) for u in (con_interes or [])}
    valores = []
    for p in propuesta_intereses(filas):
        if p["unidad"] in elegidas and p["interes"] > 0:
            valores.append((p["interes"], False, p["unidad"]))
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("UPDATE liquidaciones SET interes=0, sin_interes=TRUE WHERE consorcio_id=%s AND periodo=%s "
                        "AND deuda_anterior > 0", (_cid(), periodo))
            for interes, sin_int, unidad in valores:
                cur.execute("""UPDATE liquidaciones SET interes=%s, sin_interes=%s,
                                   total_a_pagar = expensas + deuda_anterior + COALESCE(extras, 0) + %s
                               WHERE consorcio_id=%s AND periodo=%s AND unidad=%s""",
                            (interes, sin_int, interes, _cid(), periodo, unidad))
    set_liq_estado(periodo, "CERRADA")
    _regenerar_siguiente(periodo)
    return None


def error_reapertura(periodo: str) -> str | None:
    if not liquidacion_existe(periodo):
        return "No hay liquidación generada para reabrir."
    if not liq_esta_cerrada(periodo):
        return f"La liquidación de {periodo} ya está abierta."
    if liq_esta_cerrada(_next_periodo(periodo)):
        return f"No se puede reabrir: la liquidación siguiente ({_next_periodo(periodo)}) ya está cerrada."
    n = len(get_pagos(periodo))
    if n:
        return f"No se puede reabrir: tiene {n} pago(s) registrado(s). Anulalos primero en Cobranzas."
    return None


# ── Proveedores ───────────────────────────────────────────────────────────────

def _prov_dict(r) -> dict:
    return {
        "row": r["id"], "id": r["id"],
        "nombre": r["nombre"] or "", "cuit": r["cuit"] or "",
        "telefono": r["telefono"] or "", "email": r["email"] or "",
        "direccion": r["direccion"] or "", "categoria": r["categoria"] or "",
        "notas": r["notas"] or "", "gasto_recurrente": r["gasto_recurrente"] or "",
    }


def get_proveedores() -> list:
    rows = _fetchall("SELECT * FROM proveedores WHERE consorcio_id=%s ORDER BY id", (_cid(),))
    return [_prov_dict(r) for r in rows]


def get_proveedor(pid) -> dict | None:
    for p in get_proveedores():
        if str(p["id"]) == str(pid):
            return p
    return None


def save_proveedor(data: dict) -> int:
    _FIELDS = ["nombre", "cuit", "telefono", "email", "direccion", "categoria", "notas", "gasto_recurrente"]
    vals = [str(data.get(f, "") or "") for f in _FIELDS]
    pid = data.get("id")
    if pid:
        sets = ", ".join(f"{f}=%s" for f in _FIELDS)
        _exec(f"UPDATE proveedores SET {sets} WHERE id=%s AND consorcio_id=%s", vals + [pid, _cid()])
        return int(pid)
    return _insert_returning(
        f"INSERT INTO proveedores (consorcio_id, {', '.join(_FIELDS)}) "
        f"VALUES (%s, {', '.join(['%s']*len(_FIELDS))}) RETURNING id",
        [_cid()] + vals
    )


def delete_proveedor(pid):
    _exec("DELETE FROM proveedores WHERE id=%s AND consorcio_id=%s", (pid, _cid()))


# ── Gastos recurrentes ────────────────────────────────────────────────────────

def get_gastos_recurrentes() -> list:
    rows = _fetchall(
        "SELECT id, concepto, categoria FROM gastos_recurrentes WHERE consorcio_id=%s ORDER BY id",
        (_cid(),)
    )
    return [{"id": r["id"], "concepto": r["concepto"] or "", "categoria": r["categoria"] or ""} for r in rows]


def add_gasto_recurrente(concepto: str, categoria: str = "") -> int:
    return _insert_returning(
        "INSERT INTO gastos_recurrentes (consorcio_id, concepto, categoria) VALUES (%s,%s,%s) RETURNING id",
        (_cid(), concepto.strip(), categoria.strip())
    )


def delete_gasto_recurrente(gid: int):
    _exec("DELETE FROM gastos_recurrentes WHERE id=%s AND consorcio_id=%s", (gid, _cid()))


def update_gasto_recurrente(gid: int, concepto: str, categoria: str):
    _exec(
        "UPDATE gastos_recurrentes SET concepto=%s, categoria=%s WHERE id=%s AND consorcio_id=%s",
        (concepto.strip(), categoria.strip(), gid, _cid())
    )


# ── Tareas ────────────────────────────────────────────────────────────────────

def get_tareas() -> list:
    rows = _fetchall("SELECT id, descripcion FROM tareas WHERE consorcio_id=%s ORDER BY id", (_cid(),))
    return [{"id": r["id"], "descripcion": r["descripcion"] or ""} for r in rows]


def add_tarea(descripcion: str) -> dict:
    nid = _insert_returning(
        "INSERT INTO tareas (consorcio_id, descripcion) VALUES (%s,%s) RETURNING id",
        (_cid(), descripcion.strip())
    )
    return {"id": nid, "descripcion": descripcion.strip()}


def delete_tarea(tarea_id: int) -> bool:
    if not _fetchone("SELECT id FROM tareas WHERE id=%s AND consorcio_id=%s", (tarea_id, _cid())):
        return False
    _exec("DELETE FROM tareas WHERE id=%s AND consorcio_id=%s", (tarea_id, _cid()))
    return True


# ── Facturas ──────────────────────────────────────────────────────────────────

def _fac_dict(r) -> dict:
    def _d(v):
        return v.strftime("%Y-%m-%d") if v and hasattr(v, "strftime") else (str(v)[:10] if v else None)
    return {
        "row": r["id"], "id": r["id"],
        "fecha": _d(r["fecha"]),
        "proveedor_id": r["proveedor_id"],
        "proveedor_nombre": r["proveedor_nombre"] or "",
        "descripcion": r["descripcion"] or "",
        "importe": float(r["importe"]) if r["importe"] else 0.0,
        "estado": r["estado"] or "PENDIENTE",
        "fecha_pago": _d(r["fecha_pago"]),
        "categoria": r["categoria"] or "",
        "numero_factura": r["numero_factura"] or "",
        "extraordinario": bool(r["extraordinario"]),
        "archivo_pdf": r["archivo_pdf"] or "",
        "observacion": r.get("observacion") or "",
    }


def get_facturas(estado=None, mes=None, page=1, per_page=25):
    conds = ["consorcio_id=%s"]
    params = [_cid()]
    if estado:
        conds.append("estado=%s")
        params.append(estado)
    if mes:
        col = "fecha_pago" if estado == "PAGADA" else "COALESCE(fecha_pago, fecha)"
        conds.append(f"TO_CHAR({col}, 'YYYY-MM')=%s")
        params.append(mes)
    where = " AND ".join(conds)
    order = "fecha_pago DESC NULLS LAST, fecha DESC NULLS LAST, id DESC" if estado == "PAGADA" else "fecha DESC NULLS LAST, id DESC"
    total = (_fetchone(f"SELECT COUNT(*) AS n FROM facturas WHERE {where}", params) or {}).get("n", 0)
    offset = (page - 1) * per_page
    rows = _fetchall(
        f"SELECT * FROM facturas WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
        params + [per_page, offset]
    )
    return [_fac_dict(r) for r in rows], int(total)


def get_total_pendiente_facturas() -> float:
    row = _fetchone("SELECT COALESCE(SUM(importe),0) AS t FROM facturas WHERE consorcio_id=%s AND estado='PENDIENTE'", (_cid(),))
    return float(row["t"]) if row else 0.0


def get_factura_by_id(fid) -> dict | None:
    row = _fetchone("SELECT * FROM facturas WHERE id=%s AND consorcio_id=%s", (int(fid), _cid()))
    return _fac_dict(row) if row else None


def save_factura(data: dict) -> int:
    def _pd(v):
        if not v:
            return None
        if isinstance(v, str) and v.strip():
            try:
                return datetime.strptime(v, "%Y-%m-%d").date()
            except ValueError:
                return None
        return v if isinstance(v, date) else None

    fecha = _pd(data.get("fecha"))
    fecha_pago = _pd(data.get("fecha_pago"))
    ext = bool(data.get("extraordinario"))
    fid = data.get("id")

    _VALS = (
        fecha, (str(data.get("proveedor_id") or "").strip() or None),  # "" (sin proveedor) → NULL
        data.get("proveedor_nombre", "") or "",
        data.get("descripcion", "") or "",
        float(data.get("importe") or 0),
        data.get("estado", "PENDIENTE") or "PENDIENTE",
        fecha_pago,
        data.get("categoria", "") or "",
        data.get("numero_factura", "") or "",
        ext,
        data.get("archivo_pdf", "") or "",
    )

    if fid:
        _exec("""
            UPDATE facturas SET
                fecha=%s, proveedor_id=%s, proveedor_nombre=%s, descripcion=%s,
                importe=%s, estado=%s, fecha_pago=%s, categoria=%s,
                numero_factura=%s, extraordinario=%s, archivo_pdf=%s
            WHERE id=%s AND consorcio_id=%s
        """, _VALS + (fid, _cid()))
        return int(fid)

    new_id = _insert_returning("""
        INSERT INTO facturas
            (consorcio_id, fecha, proveedor_id, proveedor_nombre, descripcion,
             importe, estado, fecha_pago, categoria, numero_factura, extraordinario, archivo_pdf)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (_cid(),) + _VALS)

    # Factura emitida desde un gasto ya cargado (Gastos Mensuales): se vincula a ese gasto.
    gasto_id = data.get("gasto_id")
    if gasto_id and vincular_gasto_factura(int(gasto_id), new_id):
        return new_id

    desc = (data.get("descripcion") or "").strip()
    if desc and fecha:
        for gr in get_gastos_recurrentes():
            if gr["concepto"].strip().upper() == desc.upper():
                periodo = str(fecha)[:7]
                importe = float(data.get("importe") or 0)
                # Si quedó el gasto de una factura borrada, se reutiliza en vez de duplicarlo.
                huerfano = _fetchone(
                    "SELECT id FROM gastos WHERE consorcio_id=%s AND trim(periodo)=%s "
                    "AND upper(trim(concepto))=upper(trim(%s)) AND factura_id IS NULL "
                    "AND tipo <> 'FONDO_RESERVA' ORDER BY id LIMIT 1", (_cid(), periodo, gr["concepto"]))
                if not (huerfano and vincular_gasto_factura(huerfano["id"], new_id)):
                    _exec("INSERT INTO gastos (consorcio_id, periodo, concepto, importe, tipo, factura_id) "
                          "VALUES (%s,%s,%s,%s,%s,%s)", (_cid(), periodo, gr["concepto"], importe, "FIJO", new_id))
                break

    return new_id


def vincular_gasto_factura(gasto_id: int, fid: int) -> bool:
    """Vincula un gasto sin factura a la factura `fid`. False si el gasto no existe o ya tiene factura."""
    row = _fetchone("SELECT id FROM gastos WHERE id=%s AND consorcio_id=%s AND factura_id IS NULL "
                    "AND tipo <> 'FONDO_RESERVA'", (gasto_id, _cid()))
    if not row:
        return False
    _exec("UPDATE gastos SET factura_id=%s WHERE id=%s AND consorcio_id=%s", (fid, gasto_id, _cid()))
    return True


_vinculos_legacy_ok: set = set()


def vincular_gastos_facturas_legacy() -> int:
    """
    Una vez por proceso y consorcio (v9.4): vincula los gastos anteriores a la v9.4 con la factura
    que los generó (mismo concepto e importe; mes de pago o, para recurrentes, mes de la factura).
    Así esos gastos no muestran el botón "emitir factura" y pagar no los duplica.
    """
    cid = _cid()
    if cid in _vinculos_legacy_ok:
        return 0
    with _columnas_lock:
        if cid in _vinculos_legacy_ok:
            return 0
        pares = _fetchall("""
            SELECT g.id AS gid, f.id AS fid
            FROM gastos g
            JOIN facturas f ON f.consorcio_id = g.consorcio_id
             AND f.importe = g.importe
             AND upper(trim(g.concepto)) = upper(trim(left(coalesce(nullif(f.descripcion,''),
                                                                 f.proveedor_nombre, ''), 100)))
             AND trim(g.periodo) IN (to_char(f.fecha_pago,'YYYY-MM'), to_char(f.fecha,'YYYY-MM'))
            WHERE g.consorcio_id = %s AND g.factura_id IS NULL AND g.tipo <> 'FONDO_RESERVA'
              AND NOT EXISTS (SELECT 1 FROM gastos g2 WHERE g2.consorcio_id = f.consorcio_id
                              AND g2.factura_id = f.id)
            ORDER BY g.id, f.id
        """, (cid,))
        usados_g, usados_f, n = set(), set(), 0
        for p in pares:
            if p["gid"] in usados_g or p["fid"] in usados_f:
                continue
            _exec("UPDATE gastos SET factura_id=%s WHERE id=%s AND consorcio_id=%s", (p["fid"], p["gid"], cid))
            usados_g.add(p["gid"]); usados_f.add(p["fid"]); n += 1
        _vinculos_legacy_ok.add(cid)
        return n


def pagar_factura(fid: int, fecha_pago: str, con_fondo: bool = False, observacion: str = "") -> bool:
    """
    Marca la factura como PAGADA y registra la salida en Caja.
    con_fondo=True (pagada con el Fondo de Reserva): la factura y el movimiento de caja quedan
    con categoría FONDO_RESERVA y el gasto se registra como VARIABLE_FR, que NO entra en la
    liquidación (solo se informa en "Gastos con Fondo de Reserva").
    Si la factura ya tiene un gasto vinculado (gastos.factura_id, v9.4) se reutiliza: no se duplica.
    `observacion`: nota libre del pago (se guarda en la factura).
    """
    row = _fetchone("SELECT * FROM facturas WHERE id=%s AND consorcio_id=%s", (fid, _cid()))
    if not row:
        return False
    try:
        fecha_dt = datetime.strptime(fecha_pago, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        fecha_dt = fecha_sistema()

    es_fr = (row["categoria"] or "").upper() == "FONDO_RESERVA"
    categoria = "FONDO_RESERVA" if con_fondo else (row["categoria"] or "Proveedor")
    obs = (observacion or "").strip()[:500] or None
    if con_fondo:
        _exec("UPDATE facturas SET estado='PAGADA', fecha_pago=%s, categoria='FONDO_RESERVA', observacion=%s "
              "WHERE id=%s AND consorcio_id=%s", (fecha_dt, obs, fid, _cid()))
    else:
        _exec("UPDATE facturas SET estado='PAGADA', fecha_pago=%s, observacion=%s "
              "WHERE id=%s AND consorcio_id=%s", (fecha_dt, obs, fid, _cid()))

    proveedor = row["proveedor_nombre"] or f"Proveedor ID {row['proveedor_id']}"
    nro = row["numero_factura"] or ""
    desc = f"Pago factura {nro} - {proveedor} - {row['descripcion'] or ''}"
    if con_fondo:
        desc = f"[Fondo de Reserva] {desc}"
    importe = float(row["importe"]) if row["importe"] else 0.0
    save_movimiento(fecha=fecha_pago, descripcion=desc[:200], tipo="SALIDA",
                    categoria=categoria, importe=importe)
    # Link the caja entry back to this factura
    last = _fetchone("SELECT id FROM caja WHERE consorcio_id=%s ORDER BY id DESC LIMIT 1", (_cid(),))
    if last:
        _exec("UPDATE caja SET factura_id=%s WHERE id=%s", (fid, last["id"]))

    concepto = row["descripcion"] or proveedor
    vinculado = _fetchone("SELECT id, periodo, tipo FROM gastos WHERE consorcio_id=%s AND factura_id=%s "
                          "ORDER BY id LIMIT 1", (_cid(), fid))
    es_recurrente = any(gr["concepto"].strip().upper() == concepto.strip().upper()
                        for gr in get_gastos_recurrentes())
    if not vinculado and es_recurrente and row["fecha"]:
        # Recurrente anterior a la v9.4: su gasto se cargó al guardar la factura, sin vínculo.
        vinculado = _fetchone(
            "SELECT id, periodo, tipo FROM gastos WHERE consorcio_id=%s AND trim(periodo)=%s "
            "AND upper(trim(concepto))=upper(trim(%s)) AND factura_id IS NULL "
            "AND tipo <> 'FONDO_RESERVA' ORDER BY id DESC LIMIT 1",
            (_cid(), str(row["fecha"])[:7], concepto))
        if vinculado:
            _exec("UPDATE gastos SET factura_id=%s WHERE id=%s", (fid, vinculado["id"]))
    if vinculado:
        if liq_esta_cerrada(_next_periodo(vinculado["periodo"].strip())):
            return True  # ya liquidado en un período cerrado: no se toca
        tipo = "VARIABLE_FR" if con_fondo else vinculado["tipo"]
        _exec("UPDATE gastos SET tipo=%s, importe=%s WHERE id=%s AND consorcio_id=%s",
              (tipo, importe, vinculado["id"], _cid()))
        return True
    if es_fr and not con_fondo:
        # Factura FONDO_RESERVA sin gasto vinculado (anterior a la v9.4): no se crea gasto.
        return True
    if con_fondo:
        tipo = "VARIABLE_FR"
    else:
        tipo = "EXTRAORDINARIO" if row["extraordinario"] else (row["categoria"] or "FIJO")
    _exec("INSERT INTO gastos (consorcio_id, periodo, concepto, importe, tipo, factura_id) "
          "VALUES (%s,%s,%s,%s,%s,%s)", (_cid(), fecha_dt.strftime("%Y-%m"), concepto[:100], importe, tipo, fid))
    return True


def factura_en_liquidacion(fid) -> bool:
    f = get_factura_by_id(fid)
    if not f or f.get("estado") != "PAGADA":
        return False
    fp = f.get("fecha_pago") or ""
    return liq_esta_cerrada(_next_periodo(fp[:7])) if len(fp) >= 7 else False


def get_facturas_extraordinarias_periodo(periodo: str) -> list:
    rows = _fetchall(
        "SELECT * FROM facturas WHERE consorcio_id=%s AND estado='PAGADA' AND extraordinario=true "
        "AND TO_CHAR(fecha_pago,'YYYY-MM')=%s",
        (_cid(), periodo)
    )
    return [_fac_dict(r) for r in rows]


def delete_factura(fid) -> bool:
    if factura_en_liquidacion(fid):
        return False
    # Delete linked caja entry (payment movement)
    _exec("DELETE FROM caja WHERE factura_id=%s AND consorcio_id=%s", (fid, _cid()))
    # El gasto queda (se puede volver a emitir su factura desde Gastos Mensuales), sin vínculo.
    _exec("UPDATE gastos SET factura_id=NULL WHERE factura_id=%s AND consorcio_id=%s", (fid, _cid()))
    _exec("DELETE FROM facturas WHERE id=%s AND consorcio_id=%s", (fid, _cid()))
    return True


def set_factura_archivo_pdf(fid: int, ruta_relativa: str) -> bool:
    _exec("UPDATE facturas SET archivo_pdf=%s WHERE id=%s AND consorcio_id=%s",
          (ruta_relativa, fid, _cid()))
    return True


# ── Pedidos ───────────────────────────────────────────────────────────────────

def get_pedidos() -> list:
    rows = _fetchall(
        "SELECT * FROM pedidos WHERE consorcio_id=%s ORDER BY fecha DESC NULLS LAST, id DESC",
        (_cid(),)
    )
    return [{
        "row": r["id"], "id": r["id"],
        "fecha": r["fecha"].strftime("%Y-%m-%d") if r["fecha"] else None,
        "descripcion": r["descripcion"] or "", "categoria": r["categoria"] or "",
        "estado": r["estado"] or "PENDIENTE",
        "proveedor_elegido": r["proveedor_elegido"] or "", "notas": r["notas"] or "",
    } for r in rows]


def save_pedido(data: dict) -> int:
    v = data.get("fecha")
    if isinstance(v, str):
        try:
            fecha = datetime.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            fecha = fecha_sistema()
    else:
        fecha = v or fecha_sistema()
    pid = data.get("id")
    if pid:
        _exec("""UPDATE pedidos SET fecha=%s, descripcion=%s, categoria=%s, estado=%s,
                 proveedor_elegido=%s, notas=%s WHERE id=%s AND consorcio_id=%s""",
              (fecha, data.get("descripcion", ""), data.get("categoria", ""),
               data.get("estado", "PENDIENTE"), data.get("proveedor_elegido", ""),
               data.get("notas", ""), pid, _cid()))
        return int(pid)
    return _insert_returning("""
        INSERT INTO pedidos (consorcio_id, fecha, descripcion, categoria, estado, proveedor_elegido, notas)
        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (_cid(), fecha, data.get("descripcion", ""), data.get("categoria", ""),
           data.get("estado", "PENDIENTE"), data.get("proveedor_elegido", ""), data.get("notas", "")))


def delete_pedido(pid):
    _exec("DELETE FROM presupuestos WHERE pedido_id=%s AND consorcio_id=%s", (pid, _cid()))
    _exec("DELETE FROM pedidos WHERE id=%s AND consorcio_id=%s", (pid, _cid()))


# ── Presupuestos ──────────────────────────────────────────────────────────────

def get_presupuestos(pedido_id=None) -> list:
    if pedido_id:
        rows = _fetchall(
            "SELECT * FROM presupuestos WHERE consorcio_id=%s AND pedido_id=%s ORDER BY id",
            (_cid(), pedido_id)
        )
    else:
        rows = _fetchall("SELECT * FROM presupuestos WHERE consorcio_id=%s ORDER BY id", (_cid(),))
    return [{
        "row": r["id"], "id": r["id"],
        "pedido_id": r["pedido_id"], "proveedor_id": r["proveedor_id"],
        "proveedor_nombre": r["proveedor_nombre"] or "",
        "fecha": r["fecha"].strftime("%Y-%m-%d") if r["fecha"] else None,
        "importe": float(r["importe"]) if r["importe"] else 0.0,
        "notas": r["notas"] or "",
        "seleccionado": 1 if r["seleccionado"] else 0,
    } for r in rows]


def save_presupuesto(data: dict) -> int:
    v = data.get("fecha")
    if isinstance(v, str):
        try:
            fecha = datetime.strptime(v, "%Y-%m-%d").date()
        except ValueError:
            fecha = fecha_sistema()
    else:
        fecha = v or fecha_sistema()
    sel = bool(data.get("seleccionado"))
    pid = data.get("id")
    if pid:
        _exec("""UPDATE presupuestos SET pedido_id=%s, proveedor_id=%s, proveedor_nombre=%s,
                 fecha=%s, importe=%s, notas=%s, seleccionado=%s WHERE id=%s AND consorcio_id=%s""",
              (data.get("pedido_id"), data.get("proveedor_id"), data.get("proveedor_nombre", ""),
               fecha, float(data.get("importe") or 0), data.get("notas", ""), sel, pid, _cid()))
        return int(pid)
    return _insert_returning("""
        INSERT INTO presupuestos (consorcio_id, pedido_id, proveedor_id, proveedor_nombre,
            fecha, importe, notas, seleccionado)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (_cid(), data.get("pedido_id"), data.get("proveedor_id"),
           data.get("proveedor_nombre", ""), fecha,
           float(data.get("importe") or 0), data.get("notas", ""), sel))


def seleccionar_presupuesto(pres_id: int, pedido_id: int):
    row = _fetchone("SELECT proveedor_nombre FROM presupuestos WHERE id=%s AND consorcio_id=%s",
                    (pres_id, _cid()))
    proveedor_elegido = row["proveedor_nombre"] if row else ""
    _exec("UPDATE presupuestos SET seleccionado=(id=%s) WHERE pedido_id=%s AND consorcio_id=%s",
          (pres_id, pedido_id, _cid()))
    _exec("UPDATE pedidos SET proveedor_elegido=%s, estado='ADJUDICADO' WHERE id=%s AND consorcio_id=%s",
          (proveedor_elegido, pedido_id, _cid()))


def delete_presupuesto(pres_id):
    _exec("DELETE FROM presupuestos WHERE id=%s AND consorcio_id=%s", (pres_id, _cid()))


# ── Caja — saldos ─────────────────────────────────────────────────────────────

def get_gastos_pagados_periodo(periodo: str) -> float:
    """
    Total pagado en el mes `periodo`: facturas PAGADAS con fecha de pago en ese mes (tengan o
    no movimiento en Caja) + salidas de Caja del mes que no vienen de una factura (sin
    factura_id ni "Pago factura ..."), sin bonificaciones. Evita contar dos veces el pago de
    una factura y su salida de Caja.
    """
    fac = _fetchone(
        "SELECT COALESCE(SUM(importe),0) AS t FROM facturas WHERE consorcio_id=%s AND estado='PAGADA' "
        "AND to_char(fecha_pago,'YYYY-MM')=%s", (_cid(), periodo))
    caja = _fetchone(
        "SELECT COALESCE(SUM(importe),0) AS t FROM caja WHERE consorcio_id=%s AND tipo='SALIDA' "
        "AND to_char(fecha,'YYYY-MM')=%s AND factura_id IS NULL "
        "AND coalesce(descripcion,'') NOT LIKE 'Pago factura%%' "
        "AND upper(coalesce(categoria,'')) <> 'BONIFICACION'", (_cid(), periodo))
    return round(float(fac["t"]) + float(caja["t"]), 2)


def get_resumen_caja_periodo(periodo: str) -> dict:
    """
    Ingresos y egresos de Caja de la liquidación `periodo` (para el PDF resumen):
    saldo al cierre del mes anterior + ingresos − egresos = saldo a la fecha de cierre de la
    liquidación (o a la fecha del sistema si sigue abierta).
    Separa cobros de expensas, otros ingresos, pagos ordinarios, pagos con el fondo y
    bonificaciones, para que la cuenta siempre cierre con el saldo real de Caja.
    """
    y, m = int(periodo[:4]), int(periodo[5:7])
    primero = date(y, m, 1)
    ultimo = fecha_corte_liquidacion(periodo)   # cierre de la liquidación (o hoy si está abierta)
    anterior = primero - timedelta(days=1)
    saldo_anterior, _, _ = get_saldo_caja(hasta_fecha=anterior.strftime("%Y-%m-%d"))
    saldo_final, _, _ = get_saldo_caja(hasta_fecha=ultimo.strftime("%Y-%m-%d"))
    inicio = (get_config().get("saldo_inicial_caja_fecha") or "").strip()
    conds, params = ["consorcio_id=%s", "fecha >= %s", "fecha <= %s"], [_cid(), primero, ultimo]
    if inicio:
        conds.append("fecha >= %s")
        params.append(inicio)
    row = _fetchone(f"""
        SELECT
          COALESCE(SUM(CASE WHEN tipo='ENTRADA' AND categoria='Expensas' THEN importe END),0) AS ing_expensas,
          COALESCE(SUM(CASE WHEN tipo='ENTRADA' AND coalesce(categoria,'')<>'Expensas' THEN importe END),0) AS ing_otros,
          COALESCE(SUM(CASE WHEN tipo='SALIDA' AND upper(coalesce(categoria,''))='FONDO_RESERVA' THEN importe END),0) AS egr_fondo,
          COALESCE(SUM(CASE WHEN tipo='SALIDA' AND upper(coalesce(categoria,''))='BONIFICACION' THEN importe END),0) AS egr_bonif,
          COALESCE(SUM(CASE WHEN tipo='SALIDA' AND upper(coalesce(categoria,'')) NOT IN ('FONDO_RESERVA','BONIFICACION')
                            THEN importe END),0) AS egr_ordinarios
        FROM caja WHERE {' AND '.join(conds)}
    """, params)
    r = {k: round(float(v), 2) for k, v in row.items()}
    return {
        "periodo": periodo,
        "saldo_anterior": round(saldo_anterior, 2), "fecha_anterior": anterior.strftime("%Y-%m-%d"),
        "ingresos_expensas": r["ing_expensas"], "otros_ingresos": r["ing_otros"],
        "egresos_ordinarios": r["egr_ordinarios"], "egresos_fondo": r["egr_fondo"],
        "bonificaciones": r["egr_bonif"],
        "saldo_final": round(saldo_final, 2), "fecha_final": ultimo.strftime("%Y-%m-%d"),
    }


def get_saldo_caja(hasta_fecha=None):
    cfg = get_config()
    saldo_inicial = float(cfg.get("saldo_inicial_caja", 0) or 0)
    fecha_inicio = (cfg.get("saldo_inicial_caja_fecha") or "").strip()
    conds = ["consorcio_id=%s"]
    params = [_cid()]
    if fecha_inicio:
        conds.append("fecha >= %s")
        params.append(fecha_inicio)
    if hasta_fecha:
        conds.append("fecha <= %s")
        params.append(hasta_fecha)
    where = " AND ".join(conds)
    row = _fetchone(f"""
        SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN importe ELSE 0 END),0) AS entradas,
               COALESCE(SUM(CASE WHEN tipo='SALIDA'  THEN importe ELSE 0 END),0) AS salidas
        FROM caja WHERE {where}
    """, params)
    entradas, salidas = float(row["entradas"]), float(row["salidas"])
    return round(saldo_inicial + entradas - salidas, 2), round(entradas, 2), round(salidas, 2)


def get_fondo_reserva_periodo(periodo: str) -> float:
    row = _fetchone(
        "SELECT COALESCE(SUM(importe),0) AS total FROM gastos "
        "WHERE consorcio_id=%s AND periodo=%s AND tipo='FONDO_RESERVA'",
        (_cid(), periodo)
    )
    return round(float(row["total"]), 2)


def get_movimientos_periodo(periodo: str):
    row = _fetchone("""
        SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN importe ELSE 0 END),0) AS entradas,
               COALESCE(SUM(CASE WHEN tipo='SALIDA'  THEN importe ELSE 0 END),0) AS salidas
        FROM caja WHERE consorcio_id=%s AND to_char(fecha,'YYYY-MM')=%s
    """, (_cid(), periodo))
    return round(float(row["entradas"]), 2), round(float(row["salidas"]), 2)


def get_fondo_reserva() -> float:
    """Saldo disponible del fondo (v6.0). Antes sumaba solo los aportes."""
    return get_saldo_fondo()


def ensure_fondo_reserva_gasto(periodo: str):
    cfg = get_config()
    monto = float(cfg.get("fondo_reserva_mensual", 0) or 0)
    if monto <= 0:
        return
    exists = _fetchone(
        "SELECT 1 FROM gastos WHERE consorcio_id=%s AND periodo=%s AND tipo='FONDO_RESERVA' LIMIT 1",
        (_cid(), periodo)
    )
    if not exists:
        save_gasto(periodo, "Fondo de Reserva", monto, "FONDO_RESERVA")


# ── Fondo de reserva y gastos extraordinarios (v6.0) ─────────────────────────
# Tipos de gasto:
#   FIJO / VARIABLE / (otros)  → ordinarios: base de las expensas.
#   FONDO_RESERVA              → aporte del período al fondo (se cobra en las expensas).
#   EXTRAORDINARIO             → extraordinario A COBRAR: va en las expensas siguientes
#                                como línea aparte; NO se descuenta del fondo.
#   VARIABLE_FR                → extraordinario PAGADO CON EL FONDO: no se cobra en las
#                                expensas y se descuenta del saldo del fondo.
# Fondo de Reserva del mes X = saldo de caja al cierre del mes X-1 (v8.0).

TIPOS_EXTRAORDINARIOS = ("EXTRAORDINARIO", "VARIABLE_FR")
TIPOS_NO_ORDINARIOS = ("FONDO_RESERVA",) + TIPOS_EXTRAORDINARIOS


def get_desglose_gastos(periodo: str, gastos: list = None) -> dict:
    """Separa los gastos del mes en ordinarios, aporte al fondo y extraordinarios."""
    gastos = gastos if gastos is not None else get_gastos(periodo)
    ordinarios = [g for g in gastos if g.get("tipo") not in TIPOS_NO_ORDINARIOS]
    aporte = [g for g in gastos if g.get("tipo") == "FONDO_RESERVA"]
    a_cobrar = [g for g in gastos if g.get("tipo") == "EXTRAORDINARIO"]
    con_fondo = [g for g in gastos if g.get("tipo") == "VARIABLE_FR"]
    t = lambda lista: round(sum(g["importe"] for g in lista), 2)
    return {
        "ordinarios": ordinarios, "aporte": aporte,
        "extra_cobrar": a_cobrar, "extra_fondo": con_fondo,
        "total_ordinarios": t(ordinarios), "total_aporte": t(aporte),
        "total_extra_cobrar": t(a_cobrar), "total_extra_fondo": t(con_fondo),
        # Lo que se reparte entre las unidades (igual que get_total_gastos)
        "total_expensas": round(t(ordinarios) + t(aporte) + t(a_cobrar), 2),
    }


def get_resumen_fondo(mes_gastos: str, cfg: dict = None) -> dict:
    """
    Fondo de Reserva de la liquidación mes_gastos+1 (v8.0): es el SALDO DE CAJA al cierre de
    `mes_gastos` (el fondo del mes X es el saldo de caja del mes X-1). Además devuelve el aporte
    del mes (gasto FONDO_RESERVA, se cobra en las expensas) y lo pagado con el fondo
    (VARIABLE_FR, no se cobra; sale de la caja cuando se paga), solo informativos.
    """
    y, m = int(mes_gastos[:4]), int(mes_gastos[5:7])
    ultimo = date(y, m, _calendar.monthrange(y, m)[1])
    saldo, _, _ = get_saldo_caja(hasta_fecha=ultimo.strftime("%Y-%m-%d"))
    filas = _fetchall(
        "SELECT tipo, COALESCE(importe, 0) AS importe FROM gastos WHERE consorcio_id=%s "
        "AND tipo IN ('FONDO_RESERVA','VARIABLE_FR') AND trim(periodo)=%s", (_cid(), mes_gastos))
    return {
        "mes_gastos": mes_gastos,
        "fecha": ultimo.strftime("%Y-%m-%d"),
        "saldo": round(saldo, 2),
        "aporte": round(sum(float(f["importe"]) for f in filas if f["tipo"] == "FONDO_RESERVA"), 2),
        "usos": round(sum(float(f["importe"]) for f in filas if f["tipo"] == "VARIABLE_FR"), 2),
    }


def get_saldo_fondo() -> float:
    """Fondo de Reserva vigente: saldo de caja al cierre del mes anterior a la fecha del sistema."""
    hoy = fecha_sistema()
    return get_resumen_fondo(_prev_periodo(hoy.strftime("%Y-%m")))["saldo"]


def set_modo_extraordinario(gasto_id: int, modo: str) -> str | None:
    """
    Cambia un gasto extraordinario entre 'FONDO' (pagado con el fondo) y 'COBRAR'
    (se cobra en las expensas siguientes). Devuelve el período del gasto o None.
    """
    nuevo = {"FONDO": "VARIABLE_FR", "COBRAR": "EXTRAORDINARIO"}.get(modo)
    row = _fetchone("SELECT periodo, tipo FROM gastos WHERE id=%s AND consorcio_id=%s", (gasto_id, _cid()))
    if not nuevo or not row or row["tipo"] not in TIPOS_EXTRAORDINARIOS:
        return None
    _exec("UPDATE gastos SET tipo=%s WHERE id=%s AND consorcio_id=%s", (nuevo, gasto_id, _cid()))
    return row["periodo"]


_migracion_fondo_ok: set = set()


def migrar_gastos_pagados_con_fondo() -> list:
    """
    Una vez por proceso y consorcio: gastos cargados como ordinarios cuya factura se pagó
    con el fondo (categoría FONDO_RESERVA, mismo mes e importe) pasan a VARIABLE_FR, salvo
    que la liquidación que los cobra esté CERRADA o ya exista ese gasto como VARIABLE_FR.
    Devuelve los períodos de gastos corregidos (para recalcular su liquidación).
    """
    cid = _cid()
    if cid in _migracion_fondo_ok:
        return []
    with _columnas_lock:
        if cid in _migracion_fondo_ok:
            return []
        candidatos = _fetchall("""
            SELECT DISTINCT ON (g.id) g.id, g.periodo
            FROM gastos g
            JOIN facturas f ON f.consorcio_id = g.consorcio_id
             AND upper(coalesce(f.categoria,'')) = 'FONDO_RESERVA'
             AND f.importe = g.importe
             AND to_char(coalesce(f.fecha_pago, f.fecha), 'YYYY-MM') = g.periodo
            WHERE g.consorcio_id = %s
              AND g.tipo NOT IN ('FONDO_RESERVA','VARIABLE_FR','EXTRAORDINARIO')
              AND NOT EXISTS (SELECT 1 FROM gastos g2 WHERE g2.consorcio_id = g.consorcio_id
                              AND g2.periodo = g.periodo AND g2.tipo = 'VARIABLE_FR'
                              AND g2.importe = g.importe)
        """, (cid,))
        periodos = []
        for c in candidatos:
            if liq_esta_cerrada(_next_periodo(c["periodo"])):
                continue
            _exec("UPDATE gastos SET tipo='VARIABLE_FR' WHERE id=%s AND consorcio_id=%s", (c["id"], cid))
            periodos.append(c["periodo"])
        _migracion_fondo_ok.add(cid)
        return sorted(set(periodos))


# ── Historial / plano ─────────────────────────────────────────────────────────

def get_historial_unidades() -> dict:
    filas = [_liq_row(r) for r in _fetchall(
        "SELECT * FROM liquidaciones WHERE consorcio_id=%s ORDER BY unidad, periodo", (_cid(),))]
    hasta = get_fecha_simulada()
    por_periodo: dict = {}
    for f in filas:
        por_periodo.setdefault(f["periodo"], []).append(f)
    for p, fs in por_periodo.items():
        _aplicar_pagos(p, fs, hasta=hasta)
    claves = ("periodo", "descripcion", "propietario", "inquilino", "expensas", "deuda_anterior",
              "interes", "total_a_pagar", "monto_pagado", "tipo_pago", "saldo_pendiente", "fecha_pago")
    historial: dict = {}
    for f in filas:
        historial.setdefault(str(f["unidad"]), []).append({k: f[k] for k in claves})
    return historial


def get_apertura():
    cfg = get_config()
    saldo = float(cfg.get("saldo_inicial_caja", 0) or 0)
    fecha_caja = cfg.get("saldo_inicial_caja_fecha", "") or ""
    return saldo, fecha_caja, get_unidades()


def save_apertura(saldo_inicial: float, deudas: dict, fechas: dict = None, fecha_caja: str = ""):
    save_config({"saldo_inicial_caja": str(saldo_inicial),
                 "saldo_inicial_caja_fecha": fecha_caja or ""})
    fechas = fechas or {}
    with _conn() as c:
        with c.cursor() as cur:
            for numero, deuda in deudas.items():
                fecha = fechas.get(numero) or None
                cur.execute(
                    "UPDATE unidades SET deuda_inicial=%s, deuda_inicial_fecha=%s WHERE consorcio_id=%s AND numero=%s",
                    (deuda, fecha, _cid(), str(numero))
                )


def reset_datos_operativos():
    with _conn() as c:
        with c.cursor() as cur:
            for tabla in ("gastos", "caja", "facturas", "liquidaciones", "liquidaciones_estado"):
                cur.execute(f"DELETE FROM {tabla} WHERE consorcio_id=%s", (_cid(),))


def get_estado_plano(periodo: str) -> list:
    liq = {str(r["unidad"]): r for r in get_liquidacion(periodo)}
    resultado = []
    for u in get_unidades():
        num = str(u["numero"])
        lr = liq.get(num)
        tipo_pago = lr.get("tipo_pago", "PENDIENTE") if lr else "PENDIENTE"
        resultado.append({
            "numero": num,
            "descripcion": u.get("descripcion", ""),
            "propietario": u.get("propietario", ""),
            "inquilino": u.get("inquilino", ""),
            "piso": u.get("piso", "") or "",
            "activo": u.get("activo", True),
            "deuda_inicial": u.get("deuda_inicial", 0) or 0,
            "tiene_liquidacion": lr is not None,
            "pagado": 1 if tipo_pago == "TOTAL" else (2 if tipo_pago == "PARCIAL" else 0),
            "tipo_pago": tipo_pago,
            "total_a_pagar": lr["total_a_pagar"] if lr else 0,
            "monto_pagado": lr.get("monto_pagado", 0) if lr else 0,
            "saldo_pendiente": lr.get("saldo_pendiente", 0) if lr else 0,
            "expensas": lr["expensas"] if lr else 0,
            "deuda_anterior": lr["deuda_anterior"] if lr else 0,
            "interes": lr["interes"] if lr else 0,
            "pct": lr["pct_aplicado"] if lr else 0,
        })
    return resultado


# ── Libre deuda ───────────────────────────────────────────────────────────────
# Certificado de libre deuda por unidad. Se puede emitir si la unidad tiene
# pagada en TOTAL la última liquidación emitida del consorcio (abierta o
# cerrada): ese total ya incluye toda la deuda anterior. Cada certificado queda
# registrado en `libres_deuda` con número correlativo por consorcio y un código
# HMAC (clave_firma) que permite verificarlo con el QR aunque luego cambien los
# datos de la unidad.

LIBRE_DEUDA_VALIDEZ_DEFAULT = 30


def ensure_libres_deuda():
    _ensure_columna("tabla.libres_deuda", """
        CREATE TABLE IF NOT EXISTS libres_deuda (
            id             SERIAL PRIMARY KEY,
            consorcio_id   TEXT NOT NULL REFERENCES consorcios(id) ON DELETE CASCADE,
            numero         INTEGER NOT NULL,
            unidad         TEXT NOT NULL,
            descripcion    TEXT,
            propietario    TEXT,
            periodo_hasta  VARCHAR(7) NOT NULL,
            fecha_emision  DATE NOT NULL,
            validez_dias   INTEGER NOT NULL,
            solicitante    TEXT,
            destino        TEXT,
            emitido_por    TEXT,
            codigo         TEXT NOT NULL,
            anulado        BOOLEAN NOT NULL DEFAULT FALSE,
            creado_en      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (consorcio_id, numero)
        )
    """)


def _fmt_ar(n: float) -> str:
    """125430.5 -> '125.430,50'."""
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def get_ultimo_periodo_liquidado() -> str:
    """Último período con liquidación generada ('' si no hay ninguna)."""
    row = _fetchone("SELECT MAX(periodo) AS p FROM liquidaciones WHERE consorcio_id=%s", (_cid(),))
    return (row and row["p"]) or ""


def get_estado_libre_deuda() -> dict:
    """
    Estado de deuda de cada unidad según la última liquidación CERRADA (la que se está
    cobrando, v9.0). Devuelve {numero: {"libre": bool, "periodo": str, "saldo": float, "motivo": str}}.
    """
    periodo = periodo_cobranza()
    liq = {str(r["unidad"]): r for r in get_liquidacion(periodo)} if periodo else {}
    estado = {}
    for u in get_unidades():
        num = str(u["numero"])
        r = liq.get(num)
        if not periodo:
            estado[num] = {"libre": False, "periodo": "", "saldo": 0.0,
                           "motivo": "Todavía no hay liquidaciones cerradas."}
        elif not r:
            estado[num] = {"libre": False, "periodo": periodo, "saldo": 0.0,
                           "motivo": f"La unidad no figura en la liquidación {periodo}."}
        elif r["tipo_pago"] == "TOTAL" or r["total_a_pagar"] <= 0:
            estado[num] = {"libre": True, "periodo": periodo, "saldo": 0.0, "motivo": ""}
        else:
            saldo = r["saldo_pendiente"] if r["tipo_pago"] == "PARCIAL" else r["total_a_pagar"]
            estado[num] = {"libre": False, "periodo": periodo, "saldo": round(saldo, 2),
                           "motivo": f"Debe $ {_fmt_ar(saldo)} de la liquidación {periodo}."}
    return estado


def _codigo_libre_deuda(ld: dict, clave_firma: str) -> str:
    campos = "|".join([
        "LIBRE_DEUDA", _cid(), str(ld["numero"]), str(ld["unidad"]),
        str(ld["periodo_hasta"]), str(ld["fecha_emision"]), str(ld["validez_dias"]),
    ])
    return _hmac.new(clave_firma.encode(), campos.encode(), hashlib.sha256).hexdigest()[:32]


def _ld_row(r) -> dict:
    d = dict(r)
    fe = d["fecha_emision"]
    d["fecha_emision"] = fe.strftime("%Y-%m-%d") if hasattr(fe, "strftime") else str(fe)
    d["unidad"] = str(d["unidad"])
    for k in ("descripcion", "propietario", "solicitante", "destino", "emitido_por"):
        d[k] = d.get(k) or ""
    try:
        vence =datetime.strptime(d["fecha_emision"], "%Y-%m-%d").date() + timedelta(days=int(d["validez_dias"]))
        d["vence"] = vence.strftime("%Y-%m-%d")
    except Exception:
        d["vence"] = ""
    return d


def emitir_libre_deuda(unidad: str, fecha_emision: date, validez_dias: int,
                       solicitante: str, destino: str, emitido_por: str) -> tuple:
    """
    Emite y registra un certificado. Devuelve (True, cert) o (False, motivo).
    El estado de deuda se vuelve a validar acá (no se confía en la pantalla).
    """
    unidad = str(unidad)
    estado = get_estado_libre_deuda().get(unidad)
    if not estado:
        return False, f"La unidad {unidad} no existe."
    if not estado["libre"]:
        return False, estado["motivo"]
    u = get_unidad(unidad) or {}
    clave = get_clave_firma()
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # Serializa la numeración correlativa por consorcio
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"libres_deuda|{_cid()}",))
            cur.execute("SELECT COALESCE(MAX(numero), 0) + 1 AS n FROM libres_deuda WHERE consorcio_id=%s",
                        (_cid(),))
            ld = {
                "numero": cur.fetchone()["n"],
                "unidad": unidad,
                "periodo_hasta": estado["periodo"],
                "fecha_emision": fecha_emision.strftime("%Y-%m-%d"),
                "validez_dias": int(validez_dias),
            }
            codigo = _codigo_libre_deuda(ld, clave)
            cur.execute("""
                INSERT INTO libres_deuda (consorcio_id, numero, unidad, descripcion, propietario,
                    periodo_hasta, fecha_emision, validez_dias, solicitante, destino, emitido_por, codigo)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
            """, (_cid(), ld["numero"], unidad, u.get("descripcion", "") or "", u.get("propietario", "") or "",
                  ld["periodo_hasta"], fecha_emision, ld["validez_dias"],
                  solicitante or None, destino or None, emitido_por or None, codigo))
            return True, _ld_row(cur.fetchone())


def get_libres_deuda(limite: int = 50) -> list:
    rows = _fetchall(
        "SELECT * FROM libres_deuda WHERE consorcio_id=%s ORDER BY numero DESC LIMIT %s",
        (_cid(), limite),
    )
    return [_ld_row(r) for r in rows]


def get_libre_deuda(numero: int) -> dict | None:
    r = _fetchone("SELECT * FROM libres_deuda WHERE consorcio_id=%s AND numero=%s", (_cid(), int(numero)))
    return _ld_row(r) if r else None


def verificar_libre_deuda(numero: int, codigo: str) -> tuple:
    """Devuelve (cert | None, valido: bool). Recalcula el HMAC con los datos registrados."""
    cert = get_libre_deuda(numero)
    if not cert:
        return None, False
    esperado = _codigo_libre_deuda(cert, get_clave_firma())
    valido = _hmac.compare_digest((codigo or "").lower(), esperado) and \
        _hmac.compare_digest(esperado, cert["codigo"])
    return cert, valido


def anular_libre_deuda(numero: int) -> bool:
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("UPDATE libres_deuda SET anulado=TRUE WHERE consorcio_id=%s AND numero=%s AND NOT anulado",
                        (_cid(), int(numero)))
            return cur.rowcount > 0


# ── Notas del período ─────────────────────────────────────────────────────────

def get_notas_periodo(periodo: str) -> list:
    rows = _fetchall(
        "SELECT id, periodo, tipo, texto FROM notas_periodo WHERE consorcio_id=%s AND periodo=%s ORDER BY id",
        (_cid(), periodo)
    )
    return [{"id": r["id"], "periodo": r["periodo"], "tipo": r["tipo"] or "INFO", "texto": r["texto"] or ""}
            for r in rows]


def add_nota(periodo: str, tipo: str, texto: str) -> int:
    return _insert_returning(
        "INSERT INTO notas_periodo (consorcio_id, periodo, tipo, texto) VALUES (%s,%s,%s,%s) RETURNING id",
        (_cid(), periodo, tipo, texto)
    )


def delete_nota(nota_id: int) -> bool:
    if not _fetchone("SELECT id FROM notas_periodo WHERE id=%s AND consorcio_id=%s", (nota_id, _cid())):
        return False
    _exec("DELETE FROM notas_periodo WHERE id=%s AND consorcio_id=%s", (nota_id, _cid()))
    return True


# ── Gastos extra ──────────────────────────────────────────────────────────────

def get_gastos_extra(periodo: str) -> list:
    rows = _fetchall(
        "SELECT id, periodo, unidad, descripcion, monto FROM gastos_extra WHERE consorcio_id=%s AND periodo=%s ORDER BY id",
        (_cid(), periodo)
    )
    return [{
        "id": r["id"], "periodo": r["periodo"],
        "unidad": str(r["unidad"]) if r["unidad"] is not None else "",
        "descripcion": r["descripcion"] or "",
        "monto": float(r["monto"]) if r["monto"] else 0.0,
    } for r in rows]


def add_gasto_extra(periodo: str, unidad: str, descripcion: str, monto: float) -> int:
    return _insert_returning(
        "INSERT INTO gastos_extra (consorcio_id, periodo, unidad, descripcion, monto) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (_cid(), periodo, unidad, descripcion, monto)
    )


def delete_gasto_extra(extra_id: int) -> bool:
    if not _fetchone("SELECT id FROM gastos_extra WHERE id=%s AND consorcio_id=%s", (extra_id, _cid())):
        return False
    _exec("DELETE FROM gastos_extra WHERE id=%s AND consorcio_id=%s", (extra_id, _cid()))
    return True


# ── Checkpoint ────────────────────────────────────────────────────────────────

_CHECKPOINT_DIAS = 30

# Tablas a snapshotear, en orden de inserción (parents antes que children)
_CHECKPOINT_TABLES = [
    "config", "categorias", "unidades", "unidad_porcentajes",
    "gastos", "caja", "liquidaciones", "liquidaciones_estado",
    "proveedores", "gastos_recurrentes", "tareas", "facturas",
    "pedidos", "presupuestos", "notas_periodo", "gastos_extra",
]

# Tablas sin columna `id` serial (usan clave compuesta)
_TABLES_NO_ID = {"config", "categorias", "unidades", "unidad_porcentajes", "liquidaciones_estado"}


def _checkpoint_json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    from decimal import Decimal
    if isinstance(o, Decimal):
        return str(o)
    raise TypeError(f"Object of type {type(o)} is not JSON serializable")


def get_checkpoint_info() -> dict | None:
    try:
        cid = _cid()
    except RuntimeError:
        return None
    row = _fetchone(
        "SELECT consorcio_id, fecha_creacion, descripcion FROM checkpoints WHERE consorcio_id = %s",
        (cid,),
    )
    if not row:
        return None
    info = dict(row)
    fc = info["fecha_creacion"]
    fc_date = fc.date() if hasattr(fc, "date") else date.fromisoformat(str(fc)[:10])
    dias = (date.today() - fc_date).days
    info["fecha_creacion"] = fc.isoformat() if hasattr(fc, "isoformat") else str(fc)
    info["dias_transcurridos"] = dias
    info["dias_restantes"] = max(0, _CHECKPOINT_DIAS - dias)
    info["expirado"] = dias >= _CHECKPOINT_DIAS
    return info


def _eliminar_checkpoint():
    try:
        cid = _cid()
    except RuntimeError:
        return
    _exec("DELETE FROM checkpoints WHERE consorcio_id = %s", (cid,))


def consolidar_si_expirado() -> bool:
    try:
        info = get_checkpoint_info()
    except Exception:
        return False
    if not info:
        return False
    if info.get("expirado"):
        _eliminar_checkpoint()
        return True
    return False


def crear_checkpoint(descripcion: str = "") -> dict:
    import json
    cid = _cid()
    snapshot = {}
    for table in _CHECKPOINT_TABLES:
        rows = _fetchall(f"SELECT * FROM {table} WHERE consorcio_id = %s", (cid,))
        snapshot[table] = [dict(r) for r in rows]
    snapshot_json = json.dumps(snapshot, default=_checkpoint_json_default)
    _exec(
        """
        INSERT INTO checkpoints (consorcio_id, fecha_creacion, descripcion, snapshot)
        VALUES (%s, NOW(), %s, %s::jsonb)
        ON CONFLICT (consorcio_id) DO UPDATE
            SET fecha_creacion = NOW(),
                descripcion    = EXCLUDED.descripcion,
                snapshot       = EXCLUDED.snapshot
        """,
        (cid, descripcion, snapshot_json),
    )
    return get_checkpoint_info()


def rollback_checkpoint() -> bool:
    cid = _cid()
    row = _fetchone("SELECT snapshot FROM checkpoints WHERE consorcio_id = %s", (cid,))
    if not row:
        return False
    snapshot = row["snapshot"]  # psycopg2 deserializes JSONB → dict

    # Orden de borrado: children primero para respetar FKs
    delete_order = [
        "presupuestos", "unidad_porcentajes", "gastos_extra", "notas_periodo",
        "facturas", "tareas", "gastos_recurrentes", "proveedores",
        "liquidaciones_estado", "liquidaciones", "caja", "gastos",
        "pedidos", "unidades", "categorias", "config",
    ]

    with _conn() as c:
        with c.cursor() as cur:
            for table in delete_order:
                cur.execute(f"DELETE FROM {table} WHERE consorcio_id = %s", (cid,))

            for table in _CHECKPOINT_TABLES:
                rows = snapshot.get(table, [])
                if not rows:
                    continue
                cols = list(rows[0].keys())
                col_str = ", ".join(f'"{col}"' for col in cols)
                placeholders = ", ".join(["%s"] * len(cols))
                has_id = table not in _TABLES_NO_ID and "id" in cols
                if has_id:
                    sql = (
                        f'INSERT INTO {table} ({col_str}) '
                        f'OVERRIDING SYSTEM VALUE VALUES ({placeholders})'
                    )
                else:
                    sql = f'INSERT INTO {table} ({col_str}) VALUES ({placeholders})'
                for row_data in rows:
                    cur.execute(sql, [row_data[col] for col in cols])

            # Resetear sequences al max id real de toda la tabla (no solo del snapshot)
            for table in _CHECKPOINT_TABLES:
                if table in _TABLES_NO_ID:
                    continue
                cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                seq = cur.fetchone()
                if seq and seq[0]:
                    cur.execute(f"SELECT COALESCE(MAX(id), 1) FROM {table}")
                    table_max = cur.fetchone()[0]
                    cur.execute("SELECT setval(%s, %s)", (seq[0], table_max))

    _exec("DELETE FROM checkpoints WHERE consorcio_id = %s", (cid,))
    return True


# ── Usuarios y permisos ───────────────────────────────────────────────────────

def get_or_create_usuario(google_id: str, email: str, nombre: str, foto_url: str = "") -> dict:
    r = _fetchone("SELECT * FROM usuarios WHERE google_id = %s", (google_id,))
    if r:
        _exec("UPDATE usuarios SET nombre=%s, foto_url=%s WHERE google_id=%s", (nombre, foto_url, google_id))
        return {**dict(r), "nombre": nombre, "foto_url": foto_url}
    count = _fetchone("SELECT COUNT(*) AS n FROM usuarios")
    es_admin = count["n"] == 0
    # v9.8: una cuenta nueva queda INACTIVA hasta que un admin la habilite (antes cualquier cuenta
    # de Google entraba). El primer usuario del sistema es admin y queda activo.
    _exec(
        "INSERT INTO usuarios (email, nombre, google_id, foto_url, es_admin, activo) VALUES (%s,%s,%s,%s,%s,%s)",
        (email, nombre, google_id, foto_url, es_admin, es_admin),
    )
    return dict(_fetchone("SELECT * FROM usuarios WHERE google_id = %s", (google_id,)))


def get_usuario(uid: int) -> dict | None:
    r = _fetchone("SELECT * FROM usuarios WHERE id = %s", (uid,))
    return dict(r) if r else None


def list_usuarios() -> list:
    usuarios = [dict(r) for r in _fetchall("SELECT * FROM usuarios ORDER BY created_at")]
    for u in usuarios:
        perms = _fetchall("SELECT consorcio_id FROM permisos_consorcio WHERE usuario_id=%s", (u["id"],))
        u["consorcios_ids"] = [r["consorcio_id"] for r in perms]
    return usuarios


def toggle_usuario_activo(uid: int):
    _exec("UPDATE usuarios SET activo = NOT activo WHERE id = %s", (uid,))


def toggle_usuario_admin(uid: int):
    _exec("UPDATE usuarios SET es_admin = NOT es_admin WHERE id = %s", (uid,))


def set_permisos_consorcio(uid: int, consorcio_ids: list):
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute("DELETE FROM permisos_consorcio WHERE usuario_id = %s", (uid,))
            for cid in consorcio_ids:
                cur.execute(
                    "INSERT INTO permisos_consorcio (usuario_id, consorcio_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (uid, cid),
                )


def get_consorcios_usuario(uid: int) -> list:
    u = get_usuario(uid)
    if not u:
        return []
    if u["es_admin"]:
        return [c["id"] for c in list_consorcios()]
    rows = _fetchall("SELECT consorcio_id FROM permisos_consorcio WHERE usuario_id = %s", (uid,))
    return [r["consorcio_id"] for r in rows]


# ── Auditoría (log de movimientos con reversión) ──────────────────────────────
#
# Cada INSERT/UPDATE/DELETE en las tablas de negocio queda registrado en
# audit_log por un trigger de PostgreSQL, con la fila completa antes/después
# (JSONB). Todos los cambios de un mismo request HTTP comparten un op_id, que
# la app pasa a la transacción con set_config('app.audit_op', ...). Revertir
# una operación aplica los cambios inversos en orden contrario, en una sola
# transacción: si alguna fila fue modificada después, no se revierte nada.

_TABLAS_AUDITADAS = [
    "caja", "categorias", "config", "facturas", "gastos", "gastos_extra",
    "gastos_recurrentes", "liquidaciones", "liquidaciones_estado", "notas_periodo",
    "pedidos", "presupuestos", "proveedores", "tareas", "unidades", "unidad_porcentajes",
    "libres_deuda", "pagos",
]
_AUDIT_DIAS_RETENCION = 180

_audit_ready = False
_audit_lock = threading.Lock()


class ConflictoReversion(Exception):
    pass


def _sql_periodo_fila(col: str) -> str:
    """
    Período de liquidación al que pertenece una fila auditada (NULL si no aplica).
    Gastos del mes P alimentan la liquidación de P+1 (mes vencido). v9.0: la Caja del mes M
    pertenece a la liquidación M+1 (la que lleva sus gastos) y los pagos de P afectan a P+1.
    """
    return f"""CASE
        WHEN tabla IN ('liquidaciones','liquidaciones_estado','gastos_extra','notas_periodo')
            THEN {col}->>'periodo'
        WHEN tabla = 'caja' AND {col}->>'fecha' ~ '^[0-9]{{4}}-[0-9]{{2}}'
            THEN to_char(to_date(LEFT({col}->>'fecha', 7), 'YYYY-MM') + interval '1 month', 'YYYY-MM')
        WHEN tabla = 'pagos' AND {col}->>'periodo' ~ '^[0-9]{{4}}-[0-9]{{2}}$'
            THEN to_char(to_date({col}->>'periodo', 'YYYY-MM') + interval '1 month', 'YYYY-MM')
        WHEN tabla = 'gastos' AND {col}->>'periodo' ~ '^[0-9]{{4}}-[0-9]{{2}}$'
            THEN to_char(to_date({col}->>'periodo', 'YYYY-MM') + interval '1 month', 'YYYY-MM')
    END"""


# Período más antiguo que toca cada fila (antes o después del cambio)
_SQL_PERIODO = f"LEAST({_sql_periodo_fila('datos_antes')}, {_sql_periodo_fila('datos_despues')})"


def get_ultima_liq_cerrada() -> str:
    """Último período con liquidación CERRADA del consorcio activo ('' si ninguno)."""
    row = _fetchone(
        "SELECT MAX(periodo) AS p FROM liquidaciones_estado WHERE consorcio_id=%s AND estado='CERRADA'",
        (_cid(),),
    )
    return (row and row["p"]) or ""


def set_contexto_auditoria(usuario_email: str, descripcion: str):
    """Inicia una operación auditable para el request actual (thread-local)."""
    _tls.audit = {
        "op": uuid.uuid4().hex,
        "usuario": usuario_email or "",
        "desc": (descripcion or "")[:300],
    }


def limpiar_contexto_auditoria():
    _tls.audit = None


def _aplicar_contexto_auditoria(c):
    ctx = getattr(_tls, "audit", None)
    if not ctx:
        return
    with c.cursor() as cur:
        cur.execute(
            "SELECT set_config('app.audit_op', %s, true), set_config('app.audit_usuario', %s, true), "
            "set_config('app.audit_desc', %s, true), set_config('app.audit_consorcio', %s, true)",
            (ctx["op"], ctx["usuario"], ctx["desc"], getattr(_tls, "consorcio_id", "") or ""),
        )


def ensure_auditoria():
    """Crea (idempotente) la tabla audit_log, la función y los triggers. Una vez por proceso."""
    global _audit_ready
    if _audit_ready:
        return
    with _audit_lock:
        if _audit_ready:
            return
        with _conn(write=False) as c:
            with c.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id            BIGSERIAL PRIMARY KEY,
                        op_id         TEXT NOT NULL,
                        fecha         TIMESTAMPTZ NOT NULL DEFAULT now(),
                        tabla         TEXT NOT NULL,
                        accion        TEXT NOT NULL,
                        datos_antes   JSONB,
                        datos_despues JSONB,
                        usuario_email TEXT,
                        consorcio_id  TEXT,
                        descripcion   TEXT,
                        revertida_en  TIMESTAMPTZ,
                        revertida_por TEXT,
                        revertida_op  TEXT
                    );
                    CREATE INDEX IF NOT EXISTS audit_log_op_idx ON audit_log (op_id);
                    CREATE INDEX IF NOT EXISTS audit_log_cons_fecha_idx ON audit_log (consorcio_id, fecha DESC);
                    CREATE INDEX IF NOT EXISTS audit_log_fecha_idx ON audit_log (fecha);

                    CREATE OR REPLACE FUNCTION audit_registrar() RETURNS trigger
                    LANGUAGE plpgsql AS $$
                    DECLARE
                        v_antes   JSONB := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END;
                        v_despues JSONB := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END;
                    BEGIN
                        -- UPSERTs que no cambian nada (ej. guardar config) no se registran
                        IF TG_OP = 'UPDATE' AND v_antes = v_despues THEN
                            RETURN NULL;
                        END IF;
                        INSERT INTO audit_log (op_id, tabla, accion, datos_antes, datos_despues,
                                               usuario_email, consorcio_id, descripcion)
                        VALUES (
                            COALESCE(NULLIF(current_setting('app.audit_op', true), ''), gen_random_uuid()::text),
                            TG_TABLE_NAME, TG_OP, v_antes, v_despues,
                            NULLIF(current_setting('app.audit_usuario', true), ''),
                            COALESCE(COALESCE(v_despues, v_antes)->>'consorcio_id',
                                     NULLIF(current_setting('app.audit_consorcio', true), '')),
                            NULLIF(current_setting('app.audit_desc', true), '')
                        );
                        RETURN NULL;
                    END $$;
                """)
                for t in _TABLAS_AUDITADAS:
                    cur.execute("SELECT to_regclass(%s)", (f"public.{t}",))
                    if not cur.fetchone()[0]:
                        continue
                    # "zz_" para que corra después de los triggers de FK (cascadas)
                    cur.execute(_sql.SQL(
                        "DROP TRIGGER IF EXISTS zz_auditoria ON {t}; "
                        "CREATE TRIGGER zz_auditoria AFTER INSERT OR UPDATE OR DELETE ON {t} "
                        "FOR EACH ROW EXECUTE FUNCTION audit_registrar()"
                    ).format(t=_sql.Identifier(t)))
        _audit_ready = True


def get_operaciones_auditoria(limite: int = 50, offset: int = 0, usuario: str = "", tabla: str = "") -> list:
    """Operaciones (agrupadas por op_id) del consorcio activo, más recientes primero."""
    _exec("DELETE FROM audit_log WHERE fecha < now() - make_interval(days => %s)", (_AUDIT_DIAS_RETENCION,))
    filtros, params = ["consorcio_id = %s"], [_cid()]
    if usuario:
        filtros.append("usuario_email = %s")
        params.append(usuario)
    if tabla:
        filtros.append("op_id IN (SELECT op_id FROM audit_log WHERE tabla = %s)")
        params.append(tabla)
    rows = _fetchall(f"""
        SELECT op_id, MIN(fecha) AS fecha, MAX(usuario_email) AS usuario_email,
               MAX(descripcion) AS descripcion, COUNT(*) AS cambios,
               ARRAY_AGG(DISTINCT tabla) AS tablas,
               BOOL_OR(revertida_en IS NOT NULL) AS revertida,
               MAX(revertida_en) AS revertida_en, MAX(revertida_por) AS revertida_por,
               MIN({_SQL_PERIODO}) AS periodo_min
        FROM audit_log WHERE {" AND ".join(filtros)}
        GROUP BY op_id ORDER BY MIN(fecha) DESC, MIN(id) DESC
        LIMIT %s OFFSET %s
    """, (*params, limite + 1, offset))
    ultima = get_ultima_liq_cerrada()
    return [
        {**dict(r), "bloqueada": bool(ultima and r["periodo_min"] and r["periodo_min"] <= ultima)}
        for r in rows
    ]


def get_usuarios_auditoria() -> list:
    rows = _fetchall(
        "SELECT DISTINCT usuario_email FROM audit_log WHERE consorcio_id=%s AND usuario_email IS NOT NULL ORDER BY 1",
        (_cid(),),
    )
    return [r["usuario_email"] for r in rows]


def get_detalle_operacion(op_id: str) -> list:
    """Cambios de una operación, con la lista de campos modificados por fila."""
    rows = _fetchall(
        "SELECT * FROM audit_log WHERE op_id=%s AND consorcio_id=%s ORDER BY id",
        (op_id, _cid()),
    )
    detalle = []
    for r in rows:
        antes, despues = r["datos_antes"] or {}, r["datos_despues"] or {}
        claves = list(dict.fromkeys([*antes.keys(), *despues.keys()]))
        campos = [
            {"campo": k, "antes": antes.get(k), "despues": despues.get(k),
             "cambio": antes.get(k) != despues.get(k)}
            for k in claves if k != "consorcio_id"
        ]
        detalle.append({**dict(r), "campos": campos})
    return detalle


def get_bloqueo_operacion(op_id: str) -> str:
    """
    Motivo por el que la operación no se puede revertir por tocar un período con
    liquidación cerrada ('' si se puede). Sólo se revierte lo posterior a la última cerrada.
    """
    ultima = get_ultima_liq_cerrada()
    if not ultima:
        return ""
    p = _fetchone(f"SELECT MIN({_SQL_PERIODO}) AS p FROM audit_log WHERE op_id=%s", (op_id,))["p"]
    if p and p <= ultima:
        return (
            f"No se puede revertir: afecta el período {p} y la liquidación está cerrada "
            f"hasta {ultima}. Sólo se pueden revertir cambios posteriores a la última liquidación cerrada."
        )
    return ""


def revertir_operacion(op_id: str, usuario_email: str):
    """
    Deshace todos los cambios de una operación. Devuelve (ok, mensaje).
    La reversión queda registrada como una operación nueva (que a su vez se puede revertir).
    """
    cid = _cid()
    rows = _fetchall("SELECT * FROM audit_log WHERE op_id=%s ORDER BY id DESC", (op_id,))
    if not rows:
        return False, "Operación no encontrada."
    if any(r["consorcio_id"] != cid for r in rows):
        return False, "La operación pertenece a otro consorcio."
    if any(r["revertida_en"] for r in rows):
        return False, "La operación ya fue revertida."
    bloqueo = get_bloqueo_operacion(op_id)
    if bloqueo:
        return False, bloqueo

    desc_original = next((r["descripcion"] for r in rows if r["descripcion"]), "operación")
    nuevo_op = uuid.uuid4().hex
    try:
        with _conn(write=False) as c:
            with c.cursor() as cur:
                cur.execute(
                    "SELECT set_config('app.audit_op', %s, true), set_config('app.audit_usuario', %s, true), "
                    "set_config('app.audit_desc', %s, true)",
                    (nuevo_op, usuario_email or "", f"Reversión: {desc_original}"[:300]),
                )
                # Orden inverso; lo que choca con una FK (ej. hijos de un borrado en
                # cascada) se reintenta cuando ya se aplicó el resto.
                pendientes = list(rows)
                while pendientes:
                    trabados = []
                    for r in pendientes:
                        cur.execute("SAVEPOINT rev")
                        try:
                            _revertir_cambio(cur, r)
                        except psycopg2.errors.ForeignKeyViolation:
                            cur.execute("ROLLBACK TO SAVEPOINT rev")
                            trabados.append(r)
                            continue
                        except psycopg2.IntegrityError:
                            cur.execute("ROLLBACK TO SAVEPOINT rev")
                            raise ConflictoReversion(
                                f"No se puede revertir: el registro de '{r['tabla']}' ya existe "
                                "(fue recreado por otra operación)."
                            )
                        cur.execute("RELEASE SAVEPOINT rev")
                    if len(trabados) == len(pendientes):
                        raise ConflictoReversion(
                            "No se puede revertir: hay registros relacionados que cambiaron después. "
                            "Revertí primero las operaciones posteriores."
                        )
                    pendientes = trabados
                cur.execute(
                    "UPDATE audit_log SET revertida_en=now(), revertida_por=%s, revertida_op=%s WHERE op_id=%s",
                    (usuario_email or "", nuevo_op, op_id),
                )
    except ConflictoReversion as exc:
        return False, str(exc)
    return True, f"Operación revertida ({len(rows)} cambio(s))."


def _revertir_cambio(cur, r):
    tabla = r["tabla"]
    if tabla not in _TABLAS_AUDITADAS:
        raise ConflictoReversion(f"La tabla {tabla} no admite reversión.")
    t = _sql.Identifier(tabla)
    antes, despues = r["datos_antes"], r["datos_despues"]
    conflicto = ConflictoReversion(
        f"No se puede revertir: un registro de '{tabla}' fue modificado después por otra operación. "
        "Revertí primero las operaciones posteriores."
    )

    if r["accion"] == "INSERT":
        cur.execute(_sql.SQL("DELETE FROM {t} AS x WHERE to_jsonb(x) = %s::jsonb").format(t=t),
                    (json.dumps(despues),))
        if cur.rowcount != 1:
            raise conflicto

    elif r["accion"] == "DELETE":
        cur.execute(_sql.SQL(
            "INSERT INTO {t} OVERRIDING SYSTEM VALUE "
            "SELECT * FROM jsonb_populate_record(NULL::{t}, %s::jsonb)"
        ).format(t=t), (json.dumps(antes),))

    elif r["accion"] == "UPDATE":
        cols = [k for k in antes if antes.get(k) != (despues or {}).get(k)]
        if not cols:
            return
        asignaciones = _sql.SQL(", ").join(
            _sql.SQL("{c} = r.{c}").format(c=_sql.Identifier(k)) for k in cols
        )
        cur.execute(_sql.SQL(
            "UPDATE {t} AS x SET {a} FROM jsonb_populate_record(NULL::{t}, %s::jsonb) AS r "
            "WHERE to_jsonb(x) = %s::jsonb"
        ).format(t=t, a=asignaciones), (json.dumps(antes), json.dumps(despues)))
        if cur.rowcount != 1:
            raise conflicto
