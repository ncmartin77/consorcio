"""
Capa de acceso a PostgreSQL (Supabase).
Misma API pública que excel_db.py — reemplaza completamente al Excel como BD.
Requiere: psycopg2-binary, variable de entorno DATABASE_URL.
"""
import os
import threading
import secrets
import hashlib
import hmac as _hmac
import calendar as _calendar
from contextlib import contextmanager
from datetime import date, datetime

import psycopg2
import psycopg2.extras
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
def _conn():
    pool = _get_pool()
    c = pool.getconn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        pool.putconn(c)


def _fetchall(sql: str, params=()):
    with _conn() as c:
        with c.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def _fetchone(sql: str, params=()):
    with _conn() as c:
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
                     propietario_mail, propietario_celular, inquilino_mail, inquilino_celular,
                     envio_destinatario, envio_canal)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (consorcio_id, numero) DO UPDATE SET
                    descripcion         = EXCLUDED.descripcion,
                    propietario         = EXCLUDED.propietario,
                    inquilino           = EXCLUDED.inquilino,
                    activo              = EXCLUDED.activo,
                    piso                = EXCLUDED.piso,
                    deuda_inicial       = EXCLUDED.deuda_inicial,
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
        "SELECT id, periodo, concepto, importe, tipo FROM gastos WHERE consorcio_id=%s AND periodo=%s ORDER BY id",
        (_cid(), periodo)
    )
    return [{
        "row": r["id"],
        "periodo": r["periodo"],
        "concepto": r["concepto"] or "",
        "importe": float(r["importe"]),
        "tipo": r["tipo"] or "FIJO",
    } for r in rows]


def save_gasto(periodo: str, concepto: str, importe: float, tipo: str, row_num: int = None):
    if row_num:
        existing = _fetchone("SELECT tipo FROM gastos WHERE id=%s AND consorcio_id=%s", (row_num, _cid()))
        if existing and existing["tipo"] == "FONDO_RESERVA":
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

def get_caja(periodo: str) -> list:
    rows = _fetchall(
        "SELECT id, fecha, descripcion, tipo, categoria, importe FROM caja "
        "WHERE consorcio_id=%s AND to_char(fecha,'YYYY-MM')=%s ORDER BY fecha, id",
        (_cid(), periodo)
    )
    return [{
        "row": r["id"],
        "fecha": r["fecha"].strftime("%Y-%m-%d") if r["fecha"] else "",
        "descripcion": r["descripcion"] or "",
        "tipo": r["tipo"] or "",
        "categoria": r["categoria"] or "",
        "importe": float(r["importe"]),
    } for r in rows]


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
    else:
        _exec(
            "INSERT INTO caja (consorcio_id, fecha, descripcion, tipo, categoria, importe) VALUES (%s,%s,%s,%s,%s,%s)",
            (_cid(), fecha_d, descripcion, tipo, categoria, importe)
        )


def delete_movimiento(row_num: int) -> bool:
    row = _fetchone("SELECT fecha FROM caja WHERE id=%s AND consorcio_id=%s", (row_num, _cid()))
    if row and row["fecha"]:
        if liq_esta_cerrada(row["fecha"].strftime("%Y-%m")):
            return False
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
    }


def get_liquidacion(periodo: str) -> list:
    rows = _fetchall(
        "SELECT * FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s ORDER BY unidad",
        (_cid(), periodo)
    )
    return [_liq_row(r) for r in rows]


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


def generar_liquidacion(periodo: str):
    if liq_esta_cerrada(periodo):
        return None

    mes_gastos = _prev_periodo(periodo)
    ensure_fondo_reserva_gasto(mes_gastos)
    cfg = get_config()
    tasa_mora = float(cfg.get("tasa_mora", 7)) / 100

    fs = (cfg.get("fecha_simulada") or "").strip()
    if fs:
        try:
            hoy = datetime.strptime(fs, "%Y-%m-%d").date()
        except ValueError:
            hoy = date.today()
    else:
        hoy = date.today()

    try:
        dia_venc = int(cfg.get("dia_vencimiento", 15) or 15)
        yp, mp = int(periodo[:4]), int(periodo[5:7])
        ultimo_dia = _calendar.monthrange(yp, mp)[1]
        dia_venc_real = ultimo_dia if dia_venc <= 0 else min(dia_venc, ultimo_dia)
        fecha_vencimiento = date(yp, mp, dia_venc_real)
    except Exception:
        fecha_vencimiento = None

    unidades = get_unidades(solo_activas=True)
    gastos = get_gastos(mes_gastos)
    total_gastos = sum(g["importe"] for g in gastos if g.get("tipo") != "VARIABLE_FR")
    categorias = [c["nombre"] for c in get_categorias()]

    prev_liq = {str(r["unidad"]): r for r in get_liquidacion(_prev_periodo(periodo))}
    pagos_previos = {str(r["unidad"]): r for r in get_liquidacion(periodo)}
    all_extras = get_gastos_extra(periodo)

    _exec("DELETE FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s", (_cid(), periodo))

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
        es_deuda_inicial = False
        if not prev_row:
            try:
                deuda_anterior = float(u.get("deuda_inicial") or 0)
            except (ValueError, TypeError):
                deuda_anterior = 0.0
            es_deuda_inicial = True  # primer mes: no aplicar interés sobre saldo inicial
        elif prev_row["pagado"] == 1:
            deuda_anterior = 0.0
        elif prev_row.get("tipo_pago") == "PARCIAL":
            deuda_anterior = round(prev_row.get("saldo_pendiente", prev_row["total_a_pagar"]), 2)
        else:
            deuda_anterior = round(prev_row["total_a_pagar"], 2)

        pago = pagos_previos.get(numero, {})
        monto_pagado = float(pago.get("monto_pagado") or 0)
        fecha_pago_str = pago.get("fecha_pago", "")

        interes_deuda = 0.0 if es_deuda_inicial else round(deuda_anterior * tasa_mora, 2)
        mora_corriente = 0.0
        if fecha_vencimiento and hoy > fecha_vencimiento and monto_pagado == 0:
            mora_corriente = round(expensas * tasa_mora, 2)
        interes = round(interes_deuda + mora_corriente, 2)

        extras_unidad = round(sum(
            float(e.get("monto") or 0)
            for e in all_extras
            if str(e.get("unidad", "")) == numero
        ), 2)

        total = round(expensas + deuda_anterior + interes + extras_unidad, 2)

        if monto_pagado >= total and monto_pagado > 0:
            tipo_pago, saldo, pagado_flag = "TOTAL", 0.0, True
        elif monto_pagado > 0:
            tipo_pago, saldo, pagado_flag = "PARCIAL", round(total - monto_pagado, 2), False
        else:
            tipo_pago, saldo, pagado_flag = "PENDIENTE", total, False

        fecha_pago_d = None
        if fecha_pago_str:
            try:
                fecha_pago_d = datetime.strptime(fecha_pago_str, "%Y-%m-%d").date()
            except Exception:
                pass

        new_rows.append((
            _cid(), periodo, numero,
            u.get("descripcion", "") or "", u.get("propietario", "") or "", u.get("inquilino", "") or "",
            pct, expensas, deuda_anterior, interes, total, pagado_flag,
            monto_pagado if monto_pagado > 0 else None,
            tipo_pago if monto_pagado > 0 else None,
            saldo if monto_pagado > 0 else None,
            fecha_pago_d,
            extras_unidad if extras_unidad else None,
        ))

    with _conn() as c:
        with c.cursor() as cur:
            cur.executemany("""
                INSERT INTO liquidaciones
                  (consorcio_id, periodo, unidad, descripcion, propietario, inquilino,
                   pct_aplicado, expensas, deuda_anterior, interes, total_a_pagar, pagado,
                   monto_pagado, tipo_pago, saldo_pendiente, fecha_pago, extras)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, new_rows)

    set_liq_estado(periodo, "ABIERTA")
    return get_liquidacion(periodo)


def marcar_pagado(periodo: str, unidad: str, monto_pagado: float, fecha_pago: str = None):
    if liq_esta_cerrada(periodo):
        return {"tipo": "CERRADA", "saldo": 0}
    if not fecha_pago:
        fecha_pago = date.today().strftime("%Y-%m-%d")

    row = _fetchone(
        "SELECT * FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s AND unidad=%s",
        (_cid(), periodo, str(unidad))
    )
    if not row:
        return None

    tipo_actual = row["tipo_pago"] or "PENDIENTE"
    if tipo_actual == "TOTAL":
        return {"tipo": "TOTAL", "saldo": 0}
    if monto_pagado <= 0:
        return None

    total_a_pagar = float(row["total_a_pagar"]) if row["total_a_pagar"] else 0.0
    monto_anterior = float(row["monto_pagado"]) if row["monto_pagado"] else 0.0
    total_pagado = round(monto_anterior + monto_pagado, 2)

    saldo = round(total_a_pagar - total_pagado, 2)
    if saldo <= 0:
        tipo_pago, saldo, pagado_flag = "TOTAL", 0.0, True
    else:
        tipo_pago, pagado_flag = "PARCIAL", False

    try:
        fecha_dt = datetime.strptime(fecha_pago, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        fecha_dt = date.today()

    _exec("""
        UPDATE liquidaciones SET
            pagado=%s, monto_pagado=%s, tipo_pago=%s, saldo_pendiente=%s, fecha_pago=%s
        WHERE consorcio_id=%s AND periodo=%s AND unidad=%s
    """, (pagado_flag, total_pagado, tipo_pago, saldo, fecha_dt, _cid(), periodo, str(unidad)))

    desc_persona = row["inquilino"] or row["propietario"] or f"Unidad {unidad}"
    sufijo = "(PARCIAL)" if tipo_pago == "PARCIAL" else ""
    save_movimiento(
        fecha=fecha_pago,
        descripcion=f"Expensas {periodo} - {desc_persona} - UF {unidad} {sufijo}".strip(),
        tipo="ENTRADA",
        categoria="Expensas",
        importe=round(monto_pagado, 2),
    )
    return {"tipo": tipo_pago, "saldo": saldo, "monto": monto_pagado, "total_pagado": total_pagado}


def marcar_todos_pagado(periodo: str, fecha_pago: str) -> int:
    if liq_esta_cerrada(periodo):
        return 0
    pendientes = [r for r in get_liquidacion(periodo) if r.get("tipo_pago", "PENDIENTE") == "PENDIENTE"]
    for r in pendientes:
        marcar_pagado(periodo, str(r["unidad"]), r["total_a_pagar"], fecha_pago)
    return len(pendientes)


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


def set_liq_estado(periodo: str, estado: str):
    _exec("""
        INSERT INTO liquidaciones_estado (consorcio_id, periodo, estado)
        VALUES (%s,%s,%s)
        ON CONFLICT (consorcio_id, periodo) DO UPDATE SET estado = EXCLUDED.estado
    """, (_cid(), periodo, estado))


def liq_esta_cerrada(periodo: str) -> bool:
    return get_liq_estado(periodo) == "CERRADA"


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
    }


def get_facturas(estado=None) -> list:
    if estado:
        rows = _fetchall(
            "SELECT * FROM facturas WHERE consorcio_id=%s AND estado=%s ORDER BY fecha DESC NULLS LAST, id DESC",
            (_cid(), estado)
        )
    else:
        rows = _fetchall(
            "SELECT * FROM facturas WHERE consorcio_id=%s ORDER BY fecha DESC NULLS LAST, id DESC",
            (_cid(),)
        )
    return [_fac_dict(r) for r in rows]


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
        fecha, data.get("proveedor_id"),
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

    desc = (data.get("descripcion") or "").strip()
    if desc and fecha:
        for gr in get_gastos_recurrentes():
            if gr["concepto"].strip().upper() == desc.upper():
                save_gasto(str(fecha)[:7], gr["concepto"], float(data.get("importe") or 0), "FIJO")
                break

    return new_id


def pagar_factura(fid: int, fecha_pago: str) -> bool:
    row = _fetchone("SELECT * FROM facturas WHERE id=%s AND consorcio_id=%s", (fid, _cid()))
    if not row:
        return False
    try:
        fecha_dt = datetime.strptime(fecha_pago, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        fecha_dt = date.today()

    _exec("UPDATE facturas SET estado='PAGADA', fecha_pago=%s WHERE id=%s AND consorcio_id=%s",
          (fecha_dt, fid, _cid()))

    proveedor = row["proveedor_nombre"] or f"Proveedor ID {row['proveedor_id']}"
    nro = row["numero_factura"] or ""
    desc = f"Pago factura {nro} - {proveedor} - {row['descripcion'] or ''}"
    importe = float(row["importe"]) if row["importe"] else 0.0
    save_movimiento(fecha=fecha_pago, descripcion=desc[:200], tipo="SALIDA",
                    categoria=row["categoria"] or "Proveedor", importe=importe)

    concepto = row["descripcion"] or proveedor
    es_recurrente = any(gr["concepto"].strip().upper() == concepto.strip().upper()
                        for gr in get_gastos_recurrentes())
    es_fr = (row["categoria"] or "").upper() == "FONDO_RESERVA"
    if not es_recurrente and not es_fr:
        save_gasto(fecha_dt.strftime("%Y-%m"), concepto[:100], importe, row["categoria"] or "FIJO")
    return True


def factura_en_liquidacion(fid) -> bool:
    for f in get_facturas():
        if str(f["id"]) != str(fid):
            continue
        if f.get("estado") != "PAGADA":
            return False
        fp = f.get("fecha_pago") or ""
        if len(fp) >= 7:
            return liquidacion_existe(_next_periodo(fp[:7]))
    return False


def get_facturas_extraordinarias_periodo(periodo: str) -> list:
    return [f for f in get_facturas(estado="PAGADA")
            if f.get("extraordinario") and (f.get("fecha_pago") or "")[:7] == periodo]


def delete_factura(fid) -> bool:
    if factura_en_liquidacion(fid):
        return False
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
            fecha = date.today()
    else:
        fecha = v or date.today()
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
            fecha = date.today()
    else:
        fecha = v or date.today()
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

def get_saldo_caja():
    cfg = get_config()
    saldo_inicial = float(cfg.get("saldo_inicial_caja", 0) or 0)
    row = _fetchone("""
        SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN importe ELSE 0 END),0) AS entradas,
               COALESCE(SUM(CASE WHEN tipo='SALIDA'  THEN importe ELSE 0 END),0) AS salidas
        FROM caja WHERE consorcio_id=%s
    """, (_cid(),))
    entradas, salidas = float(row["entradas"]), float(row["salidas"])
    return round(saldo_inicial + entradas - salidas, 2), round(entradas, 2), round(salidas, 2)


def get_movimientos_periodo(periodo: str):
    row = _fetchone("""
        SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN importe ELSE 0 END),0) AS entradas,
               COALESCE(SUM(CASE WHEN tipo='SALIDA'  THEN importe ELSE 0 END),0) AS salidas
        FROM caja WHERE consorcio_id=%s AND to_char(fecha,'YYYY-MM')=%s
    """, (_cid(), periodo))
    return round(float(row["entradas"]), 2), round(float(row["salidas"]), 2)


def get_fondo_reserva() -> float:
    row = _fetchone(
        "SELECT COALESCE(SUM(importe),0) AS total FROM gastos WHERE consorcio_id=%s AND tipo='FONDO_RESERVA'",
        (_cid(),)
    )
    return round(float(row["total"]), 2)


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


# ── Historial / plano ─────────────────────────────────────────────────────────

def get_historial_unidades() -> dict:
    rows = _fetchall("""
        SELECT periodo, unidad, descripcion, propietario, inquilino,
               expensas, deuda_anterior, interes, total_a_pagar,
               monto_pagado, tipo_pago, saldo_pendiente, fecha_pago
        FROM liquidaciones WHERE consorcio_id=%s ORDER BY unidad, periodo
    """, (_cid(),))
    historial: dict = {}
    for r in rows:
        fp = r["fecha_pago"]
        historial.setdefault(str(r["unidad"]), []).append({
            "periodo": r["periodo"],
            "descripcion": r["descripcion"] or "",
            "propietario": r["propietario"] or "",
            "inquilino": r["inquilino"] or "",
            "expensas": float(r["expensas"]) if r["expensas"] else 0.0,
            "deuda_anterior": float(r["deuda_anterior"]) if r["deuda_anterior"] else 0.0,
            "interes": float(r["interes"]) if r["interes"] else 0.0,
            "total_a_pagar": float(r["total_a_pagar"]) if r["total_a_pagar"] else 0.0,
            "monto_pagado": float(r["monto_pagado"]) if r["monto_pagado"] else 0.0,
            "tipo_pago": r["tipo_pago"] or "PENDIENTE",
            "saldo_pendiente": float(r["saldo_pendiente"]) if r["saldo_pendiente"] else 0.0,
            "fecha_pago": fp.strftime("%Y-%m-%d") if fp else "",
        })
    return historial


def get_apertura():
    return float(get_config().get("saldo_inicial_caja", 0) or 0), get_unidades()


def save_apertura(saldo_inicial: float, deudas: dict):
    save_config({"saldo_inicial_caja": str(saldo_inicial)})
    with _conn() as c:
        with c.cursor() as cur:
            for numero, deuda in deudas.items():
                cur.execute(
                    "UPDATE unidades SET deuda_inicial=%s WHERE consorcio_id=%s AND numero=%s",
                    (deuda, _cid(), str(numero))
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
    _exec(
        "INSERT INTO usuarios (email, nombre, google_id, foto_url, es_admin, activo) VALUES (%s,%s,%s,%s,%s,TRUE)",
        (email, nombre, google_id, foto_url, es_admin),
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
