"""
App Flask - Administración de Consorcios
Correr con: python app.py  o  flask run
"""
import os
import re
import base64
import hmac as _hmac_mod
import hashlib
import calendar as _cal
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session, g, abort
import io
from authlib.integrations.flask_client import OAuth

import pg_db as db
import storage
storage.LOCAL_ROOT = os.path.join(db.DATA_DIR, "archivos")
from pdf_gen import generar_pdf_liquidacion, generar_pdf_resumen_edificio, generar_recibo_pago, generar_libre_deuda

app = Flask(__name__)
# Seguridad (v9.8): SECRET_KEY obligatoria en el servidor (Render define RENDER=true). Sin ella,
# cualquiera podría firmar una sesión de admin. En una PC local sin SECRET_KEY se usa una clave
# aleatoria por proceso (las sesiones se cierran al reiniciar la app).
_secret = os.environ.get("SECRET_KEY", "").strip()
if not _secret:
    if os.environ.get("RENDER"):
        raise RuntimeError("Falta la variable de entorno SECRET_KEY: la app no arranca sin ella en el servidor.")
    import secrets as _secrets
    _secret = _secrets.token_hex(32)
app.secret_key = _secret
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",                         # el navegador no la manda en POST de otros sitios
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),  # solo por HTTPS en el servidor
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,                   # subidas de hasta 16 MB
)

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=os.environ.get("GOOGLE_CLIENT_ID"),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

_MESES = ["Enero","Febrero","Marzo","Abril","Mayo","Junio",
          "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]

@app.template_filter("mes_largo")
def mes_largo(periodo):
    try:
        return f"{_MESES[int(periodo[5:7]) - 1]} {periodo[:4]}"
    except Exception:
        return periodo


@app.template_filter("fecha_ar")
def fecha_ar(iso):
    """'2026-11-06' -> '06/11/2026'."""
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) >= 10 else s


_PUBLIC_ENDPOINTS = {"static", "login", "login_google", "auth_callback", "logout", "verificar_recibo", "recibo_publico", "recibo_publico_pdf", "verificar_libre_deuda"}


def _token_recibo_publico(clave: str, cid: str, periodo: str, unidad: str) -> str:
    key = (clave or "consorcio_fallback").encode("utf-8")
    msg = f"{cid}|{periodo}|{unidad}".encode("utf-8")
    return _hmac_mod.new(key, msg, hashlib.sha256).hexdigest()[:32]

_ADMIN_ENDPOINTS = {"admin_usuarios", "admin_toggle_activo", "admin_toggle_admin", "admin_set_permisos"}


def _importe(valor, minimo: float = 0.0, cero: bool = True):
    """
    Importe de un formulario validado en el servidor (v9.8): número finito (no "nan"/"inf"),
    >= minimo y, si cero=False, distinto de 0. Devuelve el float redondeado o None si no es válido.
    """
    import math
    try:
        v = float(str(valor if valor is not None else "").strip().replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(v) or v < minimo or (not cero and v == 0):
        return None
    return round(v, 2)


def _mismo_origen(url: str) -> bool:
    from urllib.parse import urlsplit
    return urlsplit(url).netloc.lower() == request.host.lower()


@app.before_request
def _proteccion_csrf():
    """
    CSRF (v9.8): un POST/PUT/PATCH/DELETE solo se acepta si viene de esta misma app. Los navegadores
    mandan el encabezado Origin (o Referer) en esos pedidos; si es de otro sitio se rechaza.
    Se suma a la cookie de sesión SameSite=Lax.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origen = request.headers.get("Origin")
    if origen and origen != "null":
        if not _mismo_origen(origen):
            abort(403)
        return
    referer = request.headers.get("Referer")
    if referer and not _mismo_origen(referer):
        abort(403)


@app.before_request
def _authenticate():
    if request.endpoint in _PUBLIC_ENDPOINTS or request.endpoint is None:
        return
    uid = session.get("usuario_id")
    if not uid:
        return redirect(url_for("login"))
    u = db.get_usuario(uid)
    if not u or not u["activo"]:
        session.clear()
        flash("Tu cuenta está desactivada o pendiente de aprobación. Contactá al administrador.", "warning")
        return redirect(url_for("login"))
    # El rol se toma siempre de la base: quitar el admin tiene efecto en el acto (v9.8)
    session["es_admin"] = bool(u["es_admin"])
    g.usuario = u


@app.before_request
def _set_consorcio():
    """Activa el consorcio de la sesión antes de cada request."""
    if request.endpoint in _PUBLIC_ENDPOINTS | _ADMIN_ENDPOINTS | {
        "consorcios", "nuevo_consorcio", "abrir_consorcio", "eliminar_consorcio"
    }:
        return
    cid = session.get("consorcio_id")
    if cid:
        c = db.get_consorcio(cid)
        if c:
            db.set_active_consorcio(c["data_dir_abs"], c["db_path_abs"])
            db.consolidar_si_expirado()
            return
    if request.endpoint not in (None, "consorcios", "nuevo_consorcio", "abrir_consorcio"):
        return redirect(url_for("consorcios"))


# Descripción legible de cada acción para el log de auditoría
_DESC_AUDITORIA = {
    "config": "Configuración: guardar",
    "add_gasto_recurrente": "Configuración: agregar gasto recurrente",
    "edit_gasto_recurrente": "Configuración: editar gasto recurrente",
    "delete_gasto_recurrente": "Configuración: eliminar gasto recurrente",
    "add_categoria": "Configuración: agregar categoría",
    "delete_categoria": "Configuración: eliminar categoría",
    "save_unidad": "Unidades: guardar unidad",
    "save_unidad_envio": "Unidades: cambiar envío",
    "delete_unidad": "Unidades: eliminar unidad",
    "emitir_libre_deuda": "Unidades: emitir libre deuda",
    "anular_libre_deuda": "Unidades: anular libre deuda",
    "save_gasto": "Gastos: guardar gasto",
    "delete_gasto": "Gastos: eliminar gasto",
    "modo_extraordinario": "Gastos: extraordinario pagado con fondo / a cobrar",
    "tareas_add": "Tareas: agregar",
    "tareas_delete": "Tareas: completar/eliminar",
    "save_movimiento": "Caja: guardar movimiento",
    "delete_movimiento": "Caja: eliminar movimiento",
    "eliminar_ultimo_movimiento": "Caja: eliminar último movimiento",
    "generar_liquidacion": "Liquidación: generar",
    "cerrar_liquidacion": "Liquidación: cerrar",
    "reabrir_liquidacion": "Liquidación: reabrir",
    "cobranzas_pagar_todo": "Cobranzas: pago completo",
    "cobranzas_pagar": "Cobranzas: registrar pago",
    "cobranzas_anular": "Cobranzas: anular pago(s)",
    "notas_add": "Liquidación: agregar nota",
    "notas_delete": "Liquidación: eliminar nota",
    "extras_add": "Liquidación: agregar gasto extra",
    "extras_delete": "Liquidación: eliminar gasto extra",
    "save_proveedor": "Proveedores: guardar",
    "delete_proveedor": "Proveedores: eliminar",
    "save_factura": "Facturas: guardar",
    "pagar_factura": "Facturas: pagar",
    "delete_factura": "Facturas: eliminar",
    "upload_comprobante": "Facturas: adjuntar comprobante",
    "quitar_comprobante": "Facturas: quitar comprobante",
    "save_pedido": "Presupuestos: guardar pedido",
    "delete_pedido": "Presupuestos: eliminar pedido",
    "save_cotizacion": "Presupuestos: guardar cotización",
    "seleccionar_cotizacion": "Presupuestos: seleccionar cotización",
    "delete_cotizacion": "Presupuestos: eliminar cotización",
    "apertura": "Apertura: guardar saldos iniciales",
    "reset_datos": "Configuración: resetear datos",
    "fijar_fecha_sistema": "Configuración: fecha del sistema",
    "rollback_checkpoint": "Checkpoint: rollback",
    "add_tasa_mora": "Configuración: registrar tasa de mora",
    "delete_tasa_mora": "Configuración: eliminar tasa de mora",
    "vencimiento_add": "Vencimientos: registrar",
    "vencimiento_cumplido": "Vencimientos: marcar cumplido",
    "vencimiento_delete": "Vencimientos: eliminar",
}


@app.before_request
def _contexto_auditoria():
    """Agrupa todos los cambios en la BD de este request bajo una misma operación."""
    if request.endpoint in _PUBLIC_ENDPOINTS or request.endpoint is None:
        return
    try:
        db.ensure_libres_deuda()  # antes de la auditoría, para que la tabla reciba su trigger
        db.ensure_pagos()
        db.ensure_v10()           # tablas nuevas antes de la auditoría (reciben su trigger)
        db.ensure_auditoria()
        db.ensure_deuda_inicial_fecha()
        db.ensure_caja_factura_id()
        db.ensure_factura_vinculos()
        db.ensure_liq_sin_interes()
        db.ensure_liq_fecha_cierre()
    except Exception as exc:
        app.logger.warning(f"[Auditoría] No se pudo inicializar: {exc}")
    if session.get("consorcio_id"):
        try:
            db.set_contexto_auditoria(session.get("usuario_email", ""),
                                      "Migración v6.0: gastos pagados con el fondo de reserva")
            for p_gasto in db.migrar_gastos_pagados_con_fondo():
                p_liq = db._next_periodo(p_gasto)
                if db.liquidacion_existe(p_liq) and not db.liq_esta_cerrada(p_liq):
                    db.generar_liquidacion(p_liq)
                app.logger.info(f"[v6.0] Gasto de {p_gasto} pasado a 'pagado con fondo'")
        except Exception as exc:
            app.logger.warning(f"[v6.0] Migración de gastos con fondo: {exc}")
        try:
            db.set_contexto_auditoria(session.get("usuario_email", ""),
                                      "Migración v9.4: vincular gastos con su factura")
            n_vinc = db.vincular_gastos_facturas_legacy()
            if n_vinc:
                app.logger.info(f"[v9.4] {n_vinc} gasto(s) vinculados con su factura")
        except Exception as exc:
            app.logger.warning(f"[v9.4] Vínculo gastos-facturas: {exc}")
        try:
            db.set_contexto_auditoria(session.get("usuario_email", ""),
                                      "Migración v9.0: pagos de expensas a la tabla de pagos")
            n_pagos = db.migrar_pagos_legacy()
            if n_pagos:
                app.logger.info(f"[v9.0] {n_pagos} pago(s) pasados a la tabla pagos")
        except Exception as exc:
            app.logger.warning(f"[v9.0] Migración de pagos: {exc}")
    desc = _DESC_AUDITORIA.get(request.endpoint, request.endpoint)
    if request.view_args:
        desc += " (" + ", ".join(f"{k}: {v}" for k, v in request.view_args.items()) + ")"
    db.set_contexto_auditoria(session.get("usuario_email", ""), desc)


@app.teardown_request
def _fin_auditoria(exc):
    db.limpiar_contexto_auditoria()


@app.context_processor
def inject_version():
    try:
        _vpath = os.path.join(os.path.dirname(__file__), "version.txt")
        with open(_vpath) as _f:
            _ver = _f.read().strip()
    except Exception:
        _ver = "?"
    cid = session.get("consorcio_id")
    c = db.get_consorcio(cid) if cid else None
    checkpoint_info = db.get_checkpoint_info() if cid else None
    logo_url = url_for("servir_logo") if (cid and db.get_logo()) else ""
    try:
        fecha_fijada = db.get_fecha_simulada() if cid else None
    except Exception:  # páginas públicas sin consorcio activo
        fecha_fijada = None
    alertas_n = 0
    if cid and session.get("usuario_id") and request.endpoint not in _PUBLIC_ENDPOINTS:
        try:   # v10.0: vencidos o por vencer (≤ 7 días) para el badge del menú
            alertas_n = sum(1 for a in db.get_alertas() if a["nivel"] in ("danger", "warning"))
        except Exception:
            alertas_n = 0
    return {
        "app_version": _ver,
        "app_env": db._APP_ENV,
        "drive_activo": db._get_drive() is not None,
        "consorcio_nombre": c["nombre"] if c else "",
        "consorcio_id": cid or "",
        "checkpoint_info": checkpoint_info,
        "usuario_nombre": session.get("usuario_nombre", ""),
        "usuario_foto": session.get("usuario_foto", ""),
        "es_admin": session.get("es_admin", False),
        "logo_url": logo_url,
        "periodo_trabajo": session.get("periodo_trabajo") or "",
        "fecha_sistema_fijada": fecha_fijada,
        # "Hoy" que proponen los formularios (fecha del sistema si está fijada)
        "hoy_sistema": (fecha_fijada or date.today()).strftime("%Y-%m-%d"),
        "alertas_n": alertas_n,
    }


def _fecha_hoy():
    """'Hoy' de la app: la fecha del sistema fijada en Configuración o la fecha real."""
    return db.fecha_sistema()


def _periodo_actual():
    today = _fecha_hoy()
    return f"{today.year}-{today.month:02d}"


def _get_periodo_trabajo():
    """Período de liquidación activo en la sesión (o el mes actual si no está seteado)."""
    return session.get("periodo_trabajo") or _periodo_actual()


def _set_periodo_trabajo(periodo_liq: str):
    """Guarda el período de liquidación en sesión."""
    session["periodo_trabajo"] = periodo_liq


# ---------------------------------------------------------------------------
# CONSORCIOS
# ---------------------------------------------------------------------------

@app.route("/set-periodo", methods=["POST"])
def set_periodo():
    periodo = request.form.get("periodo", "").strip()
    if periodo:
        _set_periodo_trabajo(periodo)
    return redirect(request.referrer or url_for("liquidacion", periodo=periodo))


@app.route("/")
def index():
    if not session.get("consorcio_id"):
        return redirect(url_for("consorcios"))
    return redirect(url_for("liquidacion"))


@app.route("/consorcios")
def consorcios():
    lista = db.list_consorcios()
    if not session.get("es_admin"):
        allowed = db.get_consorcios_usuario(session["usuario_id"])
        lista = [c for c in lista if c["id"] in allowed]
    return render_template("consorcios.html", consorcios=lista)


@app.route("/consorcios/nuevo", methods=["POST"])
def nuevo_consorcio():
    block = _require_admin()
    if block:
        return block
    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    if not nombre:
        flash("El nombre del consorcio es obligatorio.", "danger")
        return redirect(url_for("consorcios"))
    c = db.create_consorcio(nombre, descripcion)
    session["consorcio_id"] = c["id"]
    flash(f"Consorcio «{nombre}» creado. Configurá los datos básicos antes de comenzar.", "success")
    return redirect(url_for("config"))


@app.route("/consorcios/<cid>/abrir")
def abrir_consorcio(cid):
    if not session.get("es_admin"):
        allowed = db.get_consorcios_usuario(session["usuario_id"])
        if cid not in allowed:
            flash("No tenés acceso a ese consorcio.", "warning")
            return redirect(url_for("consorcios"))
    c = db.get_consorcio(cid)
    if not c:
        flash("Consorcio no encontrado.", "danger")
        return redirect(url_for("consorcios"))
    session["consorcio_id"] = cid
    db.set_active_consorcio(c["data_dir_abs"], c["db_path_abs"])
    return redirect(url_for("liquidacion"))


@app.route("/consorcios/<cid>/eliminar", methods=["POST"])
def eliminar_consorcio(cid):
    block = _require_admin()
    if block:
        return block
    c = db.get_consorcio(cid)
    if not c:
        flash("Consorcio no encontrado.", "danger")
        return redirect(url_for("consorcios"))
    db.delete_consorcio(cid)
    if session.get("consorcio_id") == cid:
        session.pop("consorcio_id", None)
    flash(f"Consorcio «{c['nombre']}» eliminado con todos sus datos.", "info")
    # Archivos del consorcio (comprobantes y adjuntos) en el almacenamiento (v11.1)
    try:
        n = storage.borrar_prefijo(f"{cid}/")
        if n:
            app.logger.info(f"[Storage] consorcio {cid} eliminado: {n} archivo(s) borrado(s)")
    except storage.StorageError as exc:
        app.logger.error(f"[Storage] no se pudieron borrar los archivos del consorcio {cid}: {exc}")
        flash("Los datos se borraron, pero no se pudieron borrar todos sus archivos adjuntos. "
              "Avisá al administrador del sistema.", "warning")
    return redirect(url_for("consorcios"))


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------

@app.route("/login")
def login():
    if session.get("usuario_id"):
        return redirect(url_for("consorcios"))
    return render_template("login.html")


@app.route("/login/google")
def login_google():
    redirect_uri = url_for("auth_callback", _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route("/auth/callback")
def auth_callback():
    token = google.authorize_access_token()
    info = token.get("userinfo")
    if not info:
        flash("No se pudo obtener información de Google.", "danger")
        return redirect(url_for("login"))
    u = db.get_or_create_usuario(
        google_id=info["sub"],
        email=info["email"],
        nombre=info.get("name", info["email"]),
        foto_url=info.get("picture", ""),
    )
    if not u["activo"]:
        flash(f"Tu cuenta ({u['email']}) está pendiente de aprobación o desactivada. "
              "Pedile al administrador que la habilite.", "warning")
        return redirect(url_for("login"))
    session["usuario_id"] = u["id"]
    session["usuario_email"] = u["email"]
    session["usuario_nombre"] = u["nombre"]
    session["usuario_foto"] = u.get("foto_url", "")
    session["es_admin"] = u["es_admin"]
    return redirect(url_for("consorcios"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# ADMIN - Gestión de usuarios
# ---------------------------------------------------------------------------

def _require_admin():
    if not session.get("es_admin"):
        flash("Acceso restringido a administradores.", "danger")
        return redirect(url_for("consorcios"))
    return None


@app.route("/admin/usuarios")
def admin_usuarios():
    block = _require_admin()
    if block:
        return block
    return render_template(
        "admin_usuarios.html",
        usuarios=db.list_usuarios(),
        todos_consorcios=db.list_consorcios(),
    )


@app.route("/admin/usuarios/<int:uid>/toggle_activo", methods=["POST"])
def admin_toggle_activo(uid):
    block = _require_admin()
    if block:
        return block
    db.toggle_usuario_activo(uid)
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/<int:uid>/toggle_admin", methods=["POST"])
def admin_toggle_admin(uid):
    block = _require_admin()
    if block:
        return block
    if uid == session.get("usuario_id"):
        flash("No podés quitarte el rol admin a vos mismo.", "warning")
        return redirect(url_for("admin_usuarios"))
    db.toggle_usuario_admin(uid)
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/<int:uid>/permisos", methods=["POST"])
def admin_set_permisos(uid):
    block = _require_admin()
    if block:
        return block
    db.set_permisos_consorcio(uid, request.form.getlist("consorcio_ids"))
    flash("Permisos actualizados.", "success")
    return redirect(url_for("admin_usuarios"))


# ---------------------------------------------------------------------------
# AUDITORÍA (sólo administradores)
# ---------------------------------------------------------------------------

_AUDIT_POR_PAGINA = 50


@app.route("/admin/auditoria")
def auditoria():
    block = _require_admin()
    if block:
        return block
    pagina = max(request.args.get("pagina", 1, type=int), 1)
    usuario = request.args.get("usuario", "")
    tabla = request.args.get("tabla", "")
    ops = db.get_operaciones_auditoria(_AUDIT_POR_PAGINA, (pagina - 1) * _AUDIT_POR_PAGINA, usuario, tabla)
    hay_mas = len(ops) > _AUDIT_POR_PAGINA
    return render_template(
        "auditoria.html", ops=ops[:_AUDIT_POR_PAGINA], pagina=pagina, hay_mas=hay_mas,
        usuario=usuario, tabla=tabla, usuarios=db.get_usuarios_auditoria(),
        tablas=db._TABLAS_AUDITADAS,
    )


@app.route("/admin/auditoria/<op_id>")
def auditoria_detalle(op_id):
    block = _require_admin()
    if block:
        return block
    cambios = db.get_detalle_operacion(op_id)
    if not cambios:
        flash("Operación no encontrada.", "warning")
        return redirect(url_for("auditoria"))
    return render_template("auditoria_detalle.html", op_id=op_id, cambios=cambios,
                           bloqueo=db.get_bloqueo_operacion(op_id))


@app.route("/admin/auditoria/<op_id>/revertir", methods=["POST"])
def auditoria_revertir(op_id):
    block = _require_admin()
    if block:
        return block
    ok, msg = db.revertir_operacion(op_id, session.get("usuario_email", ""))
    flash(msg, "success" if ok else "danger")
    return redirect(request.referrer or url_for("auditoria"))


# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

@app.route("/config", methods=["GET", "POST"])
def config():
    if request.method == "POST":
        data = {
            "edificio_nombre": request.form.get("edificio_nombre", ""),
            "edificio_direccion": request.form.get("edificio_direccion", ""),
            "alias_cbu": request.form.get("alias_cbu", ""),
            "titular_cuenta": request.form.get("titular_cuenta", ""),
            "administrador": request.form.get("administrador", ""),
            "telefono": request.form.get("telefono", ""),
            "email": request.form.get("email", ""),
            "whatsapp": request.form.get("whatsapp", ""),
            "tasa_mora": request.form.get("tasa_mora", "7"),
            "dia_vencimiento": request.form.get("dia_vencimiento", "15"),
            "fondo_reserva_mensual": request.form.get("fondo_reserva_mensual", "0"),
            "dias_cobro": request.form.get("dias_cobro", ""),
            "horario_cobro": request.form.get("horario_cobro", ""),
            "direccion_cobro": request.form.get("direccion_cobro", ""),
            "texto_anuncio": request.form.get("texto_anuncio", ""),
            "url_app": request.form.get("url_app", "http://localhost:5000"),
            # v10.0: administrador, mandato y registro (Ord. 9.131), ejercicio y ascensor
            "admin_cuit": request.form.get("admin_cuit", ""),
            "admin_domicilio": request.form.get("admin_domicilio", ""),
            "admin_mandato_desde": request.form.get("admin_mandato_desde", ""),
            "admin_mandato_hasta": request.form.get("admin_mandato_hasta", ""),
            "admin_designacion": request.form.get("admin_designacion", ""),
            "registro_organismo": request.form.get("registro_organismo", ""),
            "registro_numero": request.form.get("registro_numero", ""),
            "registro_fecha": request.form.get("registro_fecha", ""),
            "registro_estado": request.form.get("registro_estado", ""),
            "ejercicio_cierre": request.form.get("ejercicio_cierre", ""),
        }
        # Cada form de Configuración manda solo sus campos: no pisar los que no vienen
        data = {k: v for k, v in data.items() if k in request.form}
        if "form_administracion" in request.form:   # checkbox: si no viene, está apagado
            data["tiene_ascensor"] = "1" if request.form.get("tiene_ascensor") else "0"
        if "form_intereses" in request.form:
            data["capitalizar_intereses"] = "1" if request.form.get("capitalizar_intereses") else "0"
        if data.get("registro_estado") and data["registro_estado"] not in db.ESTADOS_REGISTRO:
            data.pop("registro_estado")
        if data.get("ejercicio_cierre") and not re.fullmatch(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])",
                                                             data["ejercicio_cierre"]):
            flash("Cierre de ejercicio inválido: usá el formato MM-DD (ej. 12-31).", "danger")
            data.pop("ejercicio_cierre")
        # Solo lo envía el form del resumen: si no viene, no se pisa el valor guardado
        if "libre_deuda_validez_dias" in request.form:
            try:
                data["libre_deuda_validez_dias"] = str(max(1, int(request.form["libre_deuda_validez_dias"])))
            except ValueError:
                pass
        db.save_config(data)
        flash("Configuración guardada.", "success")
        return redirect(url_for("config"))

    cfg = db.get_config()
    categorias = db.get_categorias()
    gastos_recurrentes = db.get_gastos_recurrentes()
    return render_template("config.html", cfg=cfg, categorias=categorias,
                           gastos_recurrentes=gastos_recurrentes,
                           tasas_mora=db.get_tasas_mora(), tasa_vigente=db.tasa_mora(cfg),
                           estados_registro=db.ESTADOS_REGISTRO)


@app.route("/config/tasa-mora/add", methods=["POST"])
def add_tasa_mora():
    """v10.0: la tasa de mora se registra con fecha de vigencia y fundamento."""
    tasa = _importe(request.form.get("tasa", "").replace(",", "."), minimo=0.0)
    if tasa is None or tasa > 100:
        flash("La tasa debe ser un número entre 0 y 100.", "danger")
        return redirect(url_for("config") + "#intereses")
    err = db.add_tasa_mora(request.form.get("vigente_desde", ""), tasa,
                           (request.form.get("fundamento") or "").strip()[:500])
    if err:
        flash(err, "danger")
    else:
        db.save_config({"tasa_mora": str(db.tasa_mora())})   # compatibilidad: tasa vigente hoy
        db.recalcular_intereses_abiertas()
        flash("Tasa de mora registrada.", "success")
    return redirect(url_for("config") + "#intereses")


@app.route("/config/tasa-mora/<int:tid>/delete", methods=["POST"])
def delete_tasa_mora(tid):
    err = db.delete_tasa_mora(tid)
    flash(err or "Tasa eliminada.", "danger" if err else "success")
    if not err:
        db.save_config({"tasa_mora": str(db.tasa_mora())})
    return redirect(url_for("config") + "#intereses")


@app.route("/config/fecha-sistema", methods=["POST"])
def fijar_fecha_sistema():
    """Fija (o quita) la fecha del sistema. La simulación se aplica al mostrar; la base no cambia."""
    valor = "" if request.form.get("accion") == "quitar" else request.form.get("fecha_sistema", "").strip()
    if valor:
        try:
            from datetime import datetime as _dt
            _dt.strptime(valor, "%Y-%m-%d")
        except ValueError:
            flash("Fecha inválida.", "danger")
            return redirect(url_for("config") + "#fecha-sistema")
    db.save_config({"fecha_simulada": valor})
    # Las liquidaciones abiertas se recalculan a la nueva fecha (deuda e interés según los pagos hasta ese día)
    db.recalcular_intereses_abiertas()
    if valor:
        flash(f"El sistema trabaja como si hoy fuera {fecha_ar(valor)}: pagos, cierres e intereses usan esa "
              f"fecha y no se cuentan los pagos registrados después.", "warning")
    else:
        flash("El sistema volvió a la fecha real.", "success")
    return redirect(url_for("config") + "#fecha-sistema")


@app.route("/config/recurrente/add", methods=["POST"])
def add_gasto_recurrente():
    concepto = request.form.get("concepto", "").strip()
    categoria = request.form.get("categoria", "").strip()
    if concepto:
        db.add_gasto_recurrente(concepto, categoria)
        flash(f"Gasto recurrente '{concepto}' agregado.", "success")
    return redirect(url_for("config"))


@app.route("/config/recurrente/delete/<int:gid>", methods=["POST"])
def delete_gasto_recurrente(gid):
    db.delete_gasto_recurrente(gid)
    flash("Gasto recurrente eliminado.", "success")
    return redirect(url_for("config"))


@app.route("/config/recurrente/edit/<int:gid>", methods=["POST"])
def edit_gasto_recurrente(gid):
    concepto = request.form.get("concepto", "").strip()
    categoria = request.form.get("categoria", "").strip()
    if concepto:
        db.update_gasto_recurrente(gid, concepto, categoria)
        flash("Gasto recurrente actualizado.", "success")
    return redirect(url_for("config"))


@app.route("/config/categoria/add", methods=["POST"])
def add_categoria():
    nombre = request.form.get("nombre", "").strip().upper().replace(" ", "_")
    descripcion = request.form.get("descripcion", "")
    if nombre:
        ok = db.add_categoria(nombre, descripcion)
        if not ok:
            flash(f"La categoría '{nombre}' ya existe.", "warning")
        else:
            flash(f"Categoría '{nombre}' agregada.", "success")
    return redirect(url_for("config"))


@app.route("/config/categoria/delete/<nombre>", methods=["POST"])
def delete_categoria(nombre):
    db.delete_categoria(nombre)
    flash(f"Categoría '{nombre}' eliminada.", "success")
    return redirect(url_for("config"))


# ---------------------------------------------------------------------------
# UNIDADES
# ---------------------------------------------------------------------------

@app.route("/unidades")
def unidades():
    unidades_list = db.get_unidades()
    categorias = db.get_categorias()
    return render_template("unidades.html", unidades=unidades_list, categorias=categorias,
                           estado_ld=db.get_estado_libre_deuda(),
                           libres_deuda=db.get_libres_deuda(),
                           validez_ld=_validez_libre_deuda(db.get_config()),
                           ld_nuevo=request.args.get("ld", type=int))


# ---------------------------------------------------------------------------
# LIBRE DEUDA
# ---------------------------------------------------------------------------

def _validez_libre_deuda(cfg: dict) -> int:
    try:
        return max(1, int(cfg.get("libre_deuda_validez_dias") or db.LIBRE_DEUDA_VALIDEZ_DEFAULT))
    except ValueError:
        return db.LIBRE_DEUDA_VALIDEZ_DEFAULT


def _url_verificacion_libre_deuda(cfg: dict, cert: dict) -> str:
    url_app = cfg.get("url_app", "http://localhost:5000").rstrip("/")
    return f"{url_app}/libre-deuda/verificar/{session.get('consorcio_id', '')}/{cert['numero']}/{cert['codigo']}"


@app.route("/unidades/<numero>/libre-deuda", methods=["POST"])
def emitir_libre_deuda(numero):
    cfg = db.get_config()
    try:
        validez = max(1, int(request.form.get("validez_dias") or _validez_libre_deuda(cfg)))
    except ValueError:
        validez = _validez_libre_deuda(cfg)
    ok, res = db.emitir_libre_deuda(
        numero, _fecha_hoy(), validez,
        request.form.get("solicitante", "").strip()[:200],
        request.form.get("destino", "").strip()[:200],
        session.get("usuario_email", ""),
    )
    if not ok:
        flash(f"No se puede emitir el libre deuda de la unidad {numero}: {res}", "danger")
        return redirect(url_for("unidades"))
    flash(f"Libre deuda N° {res['numero']:04d} emitido para la unidad {numero}.", "success")
    return redirect(url_for("unidades", ld=res["numero"]) + "#libres-deuda")


@app.route("/libre-deuda/<int:numero>/pdf")
def libre_deuda_pdf(numero):
    cert = db.get_libre_deuda(numero)
    if not cert:
        flash("Certificado no encontrado.", "warning")
        return redirect(url_for("unidades"))
    cfg = db.get_config()
    logo = db.get_logo()
    pdf_bytes = generar_libre_deuda(
        cert, cfg,
        url_verificacion=_url_verificacion_libre_deuda(cfg, cert),
        logo_bytes=base64.b64decode(logo["b64"]) if logo else None,
    )
    return send_file(io.BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=False,
                     download_name=f"libre_deuda_{numero:04d}_uf_{cert['unidad']}.pdf")


@app.route("/libre-deuda/<int:numero>/anular", methods=["POST"])
def anular_libre_deuda(numero):
    block = _require_admin()
    if block:
        return block
    if db.anular_libre_deuda(numero):
        flash(f"Libre deuda N° {numero:04d} anulado.", "success")
    else:
        flash("El certificado no existe o ya estaba anulado.", "warning")
    return redirect(url_for("unidades") + "#libres-deuda")


@app.route("/libre-deuda/verificar/<cid>/<int:numero>/<codigo>")
def verificar_libre_deuda(cid, numero, codigo):
    """Verificación pública (QR) de un certificado de libre deuda."""
    c = db.get_consorcio(cid)
    cert, valido, cfg = None, False, {}
    if c:
        db.set_active_consorcio(c["data_dir_abs"], c["db_path_abs"])
        db.ensure_libres_deuda()
        cert, valido = db.verificar_libre_deuda(numero, codigo)
        cfg = db.get_config()
    if not cert:
        estado = "no_encontrado"
    elif not valido:
        estado = "invalido"
    elif cert["anulado"]:
        estado = "anulado"
    elif cert["vence"] and cert["vence"] < _fecha_hoy().strftime("%Y-%m-%d"):
        estado = "vencido"
    else:
        estado = "valido"
    return render_template("verificar_libre_deuda.html", estado=estado, cert=cert, cfg=cfg,
                           numero=numero)


@app.route("/unidades/save", methods=["POST"])
def save_unidad():
    categorias = db.get_categorias()
    deuda_ini = request.form.get("deuda_inicial", "0").strip().replace(",", ".")
    data = {
        "numero": request.form.get("numero", "").strip(),
        "descripcion": request.form.get("descripcion", "").strip(),
        "propietario": request.form.get("propietario", "").strip(),
        "inquilino": request.form.get("inquilino", "").strip(),
        "activo": 1 if request.form.get("activo") else 0,
        "piso": request.form.get("piso", "").strip(),
        "deuda_inicial": _importe(deuda_ini or "0", minimo=float("-inf")),  # negativo = saldo a favor
        "deuda_inicial_fecha": request.form.get("deuda_inicial_fecha", "").strip() or None,
        "propietario_mail":    request.form.get("propietario_mail", "").strip(),
        "propietario_celular": request.form.get("propietario_celular", "").strip(),
        "inquilino_mail":      request.form.get("inquilino_mail", "").strip(),
        "inquilino_celular":   request.form.get("inquilino_celular", "").strip(),
        "envio_destinatario":  request.form.get("envio_destinatario", "propietario"),
        "envio_canal":         request.form.get("envio_canal", "mail"),
    }
    for cat in categorias:
        key = f"pct_{cat['nombre']}"
        val = _importe(request.form.get(key, "0").strip() or "0")
        if val is None or val > 100:
            flash(f"El porcentaje {cat['nombre']} debe ser un número entre 0 y 100.", "danger")
            return redirect(url_for("unidades"))
        data[key] = val
    if data["deuda_inicial"] is None:
        flash("La deuda inicial debe ser un número.", "danger")
        return redirect(url_for("unidades"))

    if not data["numero"]:
        flash("El número de unidad es obligatorio.", "danger")
        return redirect(url_for("unidades"))

    db.save_unidad(data)
    flash("Unidad guardada.", "success")
    return redirect(url_for("unidades"))


@app.route("/unidades/<numero>/envio", methods=["POST"])
def save_unidad_envio(numero):
    destinatario = request.form.get("envio_destinatario", "propietario")
    canal = request.form.get("envio_canal", "mail")
    db.save_unidad_envio(numero, destinatario, canal)
    return "", 204


@app.route("/unidades/delete/<numero>", methods=["POST"])
def delete_unidad(numero):
    db.delete_unidad(numero)
    flash("Unidad eliminada.", "success")
    return redirect(url_for("unidades"))


# ---------------------------------------------------------------------------
# NOTIFICACIONES
# ---------------------------------------------------------------------------
import uuid as _uuid

@app.route("/notificaciones")
def notificaciones():
    unidades = db.get_unidades(solo_activas=True)
    periodo = _periodo_actual()
    liq = db.get_liquidacion(periodo)
    liq_map = {str(r["unidad"]): r for r in liq}
    cfg = db.get_config()
    return render_template("notificaciones.html",
                           unidades=unidades,
                           liq_map=liq_map,
                           periodo=periodo,
                           cfg=cfg)


@app.route("/notificaciones/upload", methods=["POST"])
def notificaciones_upload():
    import time
    f = request.files.get("archivo")
    if not f or not f.filename:
        return {"error": "Sin archivo"}, 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".pdf", ".jpg", ".jpeg", ".png", ".gif"):
        return {"error": "Tipo no permitido"}, 400
    uid = _uuid.uuid4().hex[:12]
    nombre = uid + ext
    try:
        storage.guardar(f"{db._cid()}/notificaciones/{nombre}", f.read(), _MIME_ADJUNTOS[ext])
    except storage.StorageError as exc:
        app.logger.error(f"[Storage] adjunto de notificación: {exc}")
        return {"error": "No se pudo guardar el archivo. Intentá de nuevo."}, 503
    url = request.host_url.rstrip("/") + f"/notificaciones/ver/{nombre}"
    return {"url": url, "nombre": f.filename}


_MIME_ADJUNTOS = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                  ".png": "image/png", ".gif": "image/gif"}


@app.route("/notificaciones/ver/<nombre>")
def notificaciones_ver(nombre):
    if not re.match(r'^[a-f0-9]{12}\.(pdf|jpg|jpeg|png|gif)$', nombre):
        abort(404)
    try:
        data = storage.leer(f"{db._cid()}/notificaciones/{nombre}")
    except storage.StorageError as exc:
        app.logger.error(f"[Storage] adjunto de notificación: {exc}")
        abort(503)
    if data is None:
        data = _leer_disco_viejo(os.path.join("notificaciones", nombre))
        if data is None:
            abort(404)
    return send_file(io.BytesIO(data), mimetype=_MIME_ADJUNTOS[os.path.splitext(nombre)[1].lower()],
                     download_name=nombre)


def _leer_disco_viejo(ruta_relativa: str) -> bytes | None:
    """Archivos subidos antes de la v11.0: estaban en el disco, dentro de la carpeta del consorcio."""
    real_data = os.path.realpath(db.get_data_dir())
    real_path = os.path.realpath(os.path.join(real_data, ruta_relativa))
    if real_path.startswith(real_data + os.sep) and os.path.isfile(real_path):
        with open(real_path, "rb") as fh:
            return fh.read()
    return None


# ---------------------------------------------------------------------------
# GASTOS MENSUALES
# ---------------------------------------------------------------------------

def _recalcular_liq_si_posible(periodo):
    """Cuando se guarda un gasto del mes P, recalcula la liquidación de P+1.
    - Si está CERRADA: no modifica nada (inmutable).
    - Si está ABIERTA o no existe: regenera preservando pagos ya registrados.
    """
    periodo_liq = db._next_periodo(periodo)
    if db.liq_esta_cerrada(periodo_liq):
        flash(f"La liquidación de {periodo_liq} está cerrada — el gasto se reflejará en el mes siguiente.", "info")
    else:
        db.generar_liquidacion(periodo_liq)


def _resumen_fondo_seguro(mes_gastos, cfg=None):
    """Resumen del fondo; si el cálculo falla, la pantalla se muestra igual (con aviso y log)."""
    try:
        return db.get_resumen_fondo(mes_gastos, cfg)
    except Exception:
        import traceback
        app.logger.error(f"[fondo] Error calculando el saldo del fondo ({mes_gastos}): {traceback.format_exc()}")
        flash("No se pudo calcular el saldo del Fondo de Reserva: se muestra en 0. Avisá al administrador del sistema.",
              "warning")
        return {"mes_gastos": mes_gastos, "fecha": "", "saldo": 0.0, "aporte": 0.0, "usos": 0.0}


@app.route("/gastos")
@app.route("/gastos/<periodo>")
def gastos(periodo=None):
    if not periodo:
        # Gastos del mes anterior al período de liquidación activo
        periodo = db._prev_periodo(_get_periodo_trabajo())
    else:
        _set_periodo_trabajo(db._next_periodo(periodo))
    db.ensure_fondo_reserva_gasto(periodo)
    todos_gastos = db.get_gastos(periodo)
    desglose     = db.get_desglose_gastos(periodo, todos_gastos)
    gastos_list  = desglose["ordinarios"]
    gastos_fondo = desglose["aporte"]
    extraordinarios = [g for g in todos_gastos if g.get("tipo") in db.TIPOS_EXTRAORDINARIOS]
    total        = desglose["total_ordinarios"]
    total_fondo  = desglose["total_aporte"]
    total_expensas = desglose["total_expensas"]
    resumen_fondo = _resumen_fondo_seguro(periodo)
    prox_periodo = db._next_periodo(periodo)
    liq_prox_cerrada = db.liq_esta_cerrada(prox_periodo)
    liq_prox_existe = db.liquidacion_existe(prox_periodo)
    liq_actual_existe = db.liquidacion_existe(periodo)
    liq_actual_cerrada = db.liq_esta_cerrada(periodo)

    # Estado de cada gasto recurrente en el período
    gastos_recurrentes = db.get_gastos_recurrentes()
    todas_facturas, _ = db.get_facturas(per_page=10000)
    facturas_periodo = [f for f in todas_facturas
                        if str(f.get("fecha") or "")[:7] == periodo]
    recurrentes_estado = []
    for gr in gastos_recurrentes:
        concepto_up = gr["concepto"].strip().upper()
        factura = next((f for f in facturas_periodo
                        if f.get("descripcion", "").strip().upper() == concepto_up), None)
        # Última factura del mismo concepto en períodos anteriores (para pre-cargar)
        anteriores = sorted(
            [f for f in todas_facturas
             if f.get("descripcion", "").strip().upper() == concepto_up
             and str(f.get("fecha") or "")[:7] < periodo],
            key=lambda f: str(f.get("fecha") or ""), reverse=True
        )
        recurrentes_estado.append({**gr, "factura": factura,
                                   "ultima_anterior": anteriores[0] if anteriores else None})

    proveedores = db.get_proveedores()
    tareas = db.get_tareas()
    return render_template("gastos.html", gastos=gastos_list, extraordinarios=extraordinarios,
                           gastos_fondo=gastos_fondo, desglose=desglose, resumen_fondo=resumen_fondo,
                           periodo=periodo, total=total,
                           total_fondo=total_fondo, total_expensas=total_expensas,
                           prox_periodo=prox_periodo, liq_prox_cerrada=liq_prox_cerrada,
                           liq_prox_existe=liq_prox_existe,
                           liq_actual_existe=liq_actual_existe,
                           liq_actual_cerrada=liq_actual_cerrada,
                           recurrentes_estado=recurrentes_estado,
                           proveedores=proveedores, tareas=tareas)


@app.route("/gastos/save", methods=["POST"])
def save_gasto():
    periodo = request.form.get("periodo", _periodo_actual())
    concepto = request.form.get("concepto", "").strip()
    importe = request.form.get("importe", "0")
    tipo = request.form.get("tipo", "FIJO")
    row_num = request.form.get("row_num")
    usar_fondo_reserva = request.form.get("usar_fondo_reserva") == "1"

    importe = _importe(importe)
    if importe is None:
        flash("El importe debe ser un número mayor o igual a cero.", "danger")
        return redirect(url_for("gastos", periodo=periodo))
    tipo = (tipo or "FIJO").strip()[:30] or "FIJO"

    if not concepto:
        flash("El concepto es obligatorio.", "danger")
        return redirect(url_for("gastos", periodo=periodo))

    # Período cerrado (v9.8): no se cargan ni modifican gastos de una liquidación CERRADA,
    # aunque el formulario se mande a mano (antes solo lo impedía la pantalla).
    periodos = {periodo}
    previo = None
    if row_num and str(row_num).isdigit():
        previo = db._fetchone("SELECT periodo, tipo FROM gastos WHERE id=%s AND consorcio_id=%s",
                              (int(row_num), db._cid()))
        if not previo:
            flash("Gasto no encontrado.", "warning")
            return redirect(url_for("gastos", periodo=periodo))
        periodos.add(previo["periodo"].strip())
    cerrados = sorted(p for p in periodos if db.liq_esta_cerrada(db._next_periodo(p)))
    if cerrados:
        flash(f"Los gastos de {', '.join(cerrados)} ya están en una liquidación cerrada: no se pueden modificar.",
              "danger")
        return redirect(url_for("gastos", periodo=periodo))
    # El aporte al fondo (FONDO_RESERVA) lo crea el sistema: no se carga a mano
    if tipo == "FONDO_RESERVA" and not (previo and previo["tipo"] == "FONDO_RESERVA"):
        flash("Tipo de gasto inválido.", "danger")
        return redirect(url_for("gastos", periodo=periodo))

    # v10.0: clasificación en campos separados (naturaleza / habitualidad / financiación + respaldo).
    # El tipo que usa el cálculo se deduce de ellos. Sin estos campos (form anterior) se usa el tipo.
    clasificacion = None
    if request.form.get("naturaleza") and not (previo and previo["tipo"] == "FONDO_RESERVA"):
        clasificacion = {
            "naturaleza": request.form.get("naturaleza"),
            "habitualidad": request.form.get("habitualidad") or "NO_RECURRENTE",
            "financiacion": request.form.get("financiacion") or "EXPENSAS",
            "respaldo": request.form.get("respaldo", ""),
        }
        if (clasificacion["naturaleza"] not in db.NATURALEZAS
                or clasificacion["habitualidad"] not in db.HABITUALIDADES
                or clasificacion["financiacion"] not in db.FINANCIACIONES):
            flash("Clasificación del gasto inválida.", "danger")
            return redirect(url_for("gastos", periodo=periodo))
    # Extraordinario: pagado con el fondo (VARIABLE_FR, no se cobra y se descuenta del fondo)
    # o a cobrar en las expensas siguientes (EXTRAORDINARIO, no toca el fondo).
    elif tipo == "EXTRAORDINARIO" and request.form.get("modo_extraordinario") == "FONDO":
        tipo = "VARIABLE_FR"
    elif usar_fondo_reserva and tipo == "VARIABLE":  # compatibilidad con el form anterior
        tipo = "VARIABLE_FR"

    db.save_gasto(periodo, concepto, importe, tipo, int(row_num) if row_num else None,
                  clasificacion=clasificacion)
    _recalcular_liq_si_posible(periodo)
    return redirect(url_for("gastos", periodo=periodo))


@app.route("/gastos/<int:gid>/extraordinario/<modo>", methods=["POST"])
def modo_extraordinario(gid, modo):
    """Cambia un gasto extraordinario entre pagado con el fondo y a cobrar en las expensas."""
    row = db._fetchone("SELECT periodo FROM gastos WHERE id=%s AND consorcio_id=%s", (gid, db._cid()))
    if not row:
        flash("Gasto no encontrado.", "warning")
        return redirect(url_for("gastos"))
    periodo = row["periodo"]
    if db.liq_esta_cerrada(db._next_periodo(periodo)):
        flash(f"La liquidación de {db._next_periodo(periodo)} está cerrada: no se puede cambiar.", "danger")
        return redirect(url_for("gastos", periodo=periodo))
    if db.set_modo_extraordinario(gid, modo.upper()):
        _recalcular_liq_si_posible(periodo)
        flash("Gasto extraordinario: " + ("se paga con el fondo de reserva." if modo.upper() == "FONDO"
                                          else "se cobra en las expensas siguientes."), "success")
    return redirect(url_for("gastos", periodo=periodo))


@app.route("/gastos/delete/<int:row_num>/<periodo>", methods=["POST"])
def delete_gasto(row_num, periodo):
    previo = db._fetchone("SELECT periodo FROM gastos WHERE id=%s AND consorcio_id=%s", (row_num, db._cid()))
    if previo and db.liq_esta_cerrada(db._next_periodo(previo["periodo"].strip())):
        flash(f"Los gastos de {previo['periodo'].strip()} ya están en una liquidación cerrada: "
              "no se pueden borrar.", "danger")
        return redirect(url_for("gastos", periodo=periodo))
    db.delete_gasto(row_num)
    _recalcular_liq_si_posible(periodo)
    return redirect(url_for("gastos", periodo=periodo))


# ---------------------------------------------------------------------------
# TAREAS PENDIENTES (AJAX)
# ---------------------------------------------------------------------------

@app.route("/tareas/add", methods=["POST"])
def tareas_add():
    descripcion = (request.form.get("descripcion") or "").strip()
    if not descripcion:
        return jsonify({"error": "descripcion requerida"}), 400
    tarea = db.add_tarea(descripcion)
    return jsonify(tarea)


@app.route("/tareas/delete/<int:tarea_id>", methods=["POST"])
def tareas_delete(tarea_id):
    db.delete_tarea(tarea_id)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# CAJA DIARIA
# ---------------------------------------------------------------------------

@app.route("/caja")
@app.route("/caja/<periodo>")
def caja(periodo=None):
    if not periodo:
        periodo = _get_periodo_trabajo()
    else:
        _set_periodo_trabajo(periodo)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 50
    # v9.0: la Caja del mes se cierra al cerrar la liquidación que lleva sus gastos (mes siguiente)
    liq_cerrada = db.caja_mes_bloqueado(periodo)
    movimientos, total = db.get_caja(periodo, page=page, per_page=per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    # Summaries always over the full month (not just the page)
    todos, _ = db.get_caja(periodo, page=1, per_page=10000)
    entradas = sum(m["importe"] for m in todos if m["tipo"] == "ENTRADA")
    salidas = sum(m["importe"] for m in todos if m["tipo"] == "SALIDA")
    saldo_mes = round(entradas - salidas, 2)
    saldo_acumulado, _, _ = db.get_saldo_caja()
    saldo_anterior = round(saldo_acumulado - saldo_mes, 2)
    # Starting saldo for the running-balance column on this page
    offset = (page - 1) * per_page
    saldo_pagina = saldo_anterior
    for m in todos[:offset]:
        saldo_pagina += m["importe"] if m["tipo"] == "ENTRADA" else -m["importe"]
    saldo_pagina = round(saldo_pagina, 2)
    ultimo_movimiento = db.get_ultimo_movimiento_caja()
    return render_template("caja.html",
                           movimientos=movimientos,
                           periodo=periodo,
                           entradas=entradas,
                           salidas=salidas,
                           saldo=saldo_mes,
                           saldo_anterior=saldo_anterior,
                           saldo_acumulado=saldo_acumulado,
                           saldo_pagina=saldo_pagina,
                           liq_cerrada=liq_cerrada,
                           ultimo_movimiento=ultimo_movimiento,
                           page=page, total_pages=total_pages, total=total)


@app.route("/caja/save", methods=["POST"])
def save_movimiento():
    periodo = request.form.get("periodo", _periodo_actual())
    fecha = request.form.get("fecha", "")
    row_num_chk = request.form.get("row_num")
    meses = {fecha[:7]} if fecha else {periodo}
    if row_num_chk and row_num_chk.isdigit():
        previo = db._fetchone("SELECT fecha FROM caja WHERE id=%s AND consorcio_id=%s",
                              (int(row_num_chk), db._cid()))
        if previo and previo["fecha"]:
            meses.add(previo["fecha"].strftime("%Y-%m"))
    bloqueados = sorted(m for m in meses if db.caja_mes_bloqueado(m))
    if bloqueados:
        flash(f"La Caja de {', '.join(bloqueados)} está cerrada (se cerró la liquidación que lleva esos gastos). "
              f"No se pueden registrar ni modificar movimientos.", "danger")
        return redirect(url_for("caja", periodo=periodo))
    descripcion = request.form.get("descripcion", "").strip()
    tipo = request.form.get("tipo", "ENTRADA")
    categoria = request.form.get("categoria", "").strip()
    importe = _importe(request.form.get("importe", "0"), cero=False)
    row_num = request.form.get("row_num")

    if tipo not in ("ENTRADA", "SALIDA"):
        flash("Tipo de movimiento inválido.", "danger")
        return redirect(url_for("caja", periodo=periodo))
    if importe is None:
        flash("El importe debe ser un número mayor a cero.", "danger")
        return redirect(url_for("caja", periodo=periodo))

    if not fecha or not descripcion:
        flash("Fecha y descripción son obligatorios.", "danger")
        return redirect(url_for("caja", periodo=periodo))

    db.save_movimiento(fecha, descripcion, tipo, categoria, importe,
                       int(row_num) if row_num else None)
    flash("Movimiento guardado.", "success")
    return redirect(url_for("caja", periodo=periodo))


@app.route("/caja/delete/<int:row_num>/<periodo>", methods=["POST"])
def delete_movimiento(row_num, periodo):
    ok = db.delete_movimiento(row_num)
    if ok is False:
        flash("No se puede eliminar: la Caja de ese mes está cerrada, o es el cobro de un pago que ya no se "
              "puede anular (solo los de la última liquidación cerrada).", "danger")
    else:
        flash("Movimiento eliminado.", "success")
    return redirect(url_for("caja", periodo=periodo))


@app.route("/caja/eliminar-ultimo", methods=["POST"])
def eliminar_ultimo_movimiento():
    periodo = request.form.get("periodo", _periodo_actual())
    ultimo = db.get_ultimo_movimiento_caja()
    if not ultimo:
        flash("No hay movimientos para eliminar.", "warning")
        return redirect(url_for("caja", periodo=periodo))
    ok = db.delete_movimiento(ultimo["id"])
    if ok is False:
        flash(f"No se puede eliminar: la Caja de {ultimo['fecha'][:7]} está cerrada o es el cobro de un "
              f"pago que ya no se puede anular.", "danger")
    else:
        signo = "+" if ultimo["tipo"] == "ENTRADA" else "-"
        flash(
            f"Último movimiento eliminado: {ultimo['descripcion']} "
            f"({signo}${ultimo['importe']:,.2f})",
            "success"
        )
    return redirect(url_for("caja", periodo=periodo))


# ---------------------------------------------------------------------------
# LIQUIDACIÓN
# ---------------------------------------------------------------------------

@app.route("/liquidacion")
@app.route("/liquidacion/<periodo>")
def liquidacion(periodo=None):
    if not periodo:
        periodo = _get_periodo_trabajo()
    else:
        _set_periodo_trabajo(periodo)

    # Liquidación abierta: se mantiene al día (pagos de la anterior, interés al vencimiento).
    # generar_liquidacion no escribe si nada cambió.
    if db.liquidacion_existe(periodo) and not db.liq_esta_cerrada(periodo):
        try:
            db.generar_liquidacion(periodo)
        except Exception as exc:
            app.logger.warning(f"Recalcular liquidación {periodo}: {exc}")

    liq = db.get_liquidacion(periodo)
    mes_gastos = db._prev_periodo(periodo)  # gastos del mes anterior
    gastos = db.get_gastos(mes_gastos)
    total_gastos = db.get_total_gastos(mes_gastos)
    total_a_pagar = sum(r["total_a_pagar"] for r in liq)
    total_deuda = sum(r["deuda_anterior"] for r in liq)
    pendientes = sum(1 for r in liq if r.get("tipo_pago", "PENDIENTE") not in ("TOTAL",))
    total_cobrado = sum(r.get("monto_pagado", 0) for r in liq)
    # Saldo de caja a la fecha de cierre de la liquidación (o a hoy si está abierta)
    saldo_al_default = db.fecha_corte_liquidacion(periodo).strftime("%Y-%m-%d")
    saldo_al = request.args.get("saldo_al", saldo_al_default)
    saldo_caja, _, _ = db.get_saldo_caja(hasta_fecha=saldo_al)
    # Entradas = propietarios pagando en el período de la liquidación
    # Salidas = facturas/gastos pagados en el mes ANTERIOR (que generaron esta liquidación)
    entradas, _ = db.get_movimientos_periodo(periodo)
    salidas = db.get_gastos_pagados_periodo(mes_gastos)  # facturas pagadas en el mes + salidas de caja sin factura
    fondo = _resumen_fondo_seguro(mes_gastos)
    desglose = db.get_desglose_gastos(mes_gastos, gastos)
    liq_cerrada = db.liq_esta_cerrada(periodo)
    liq_generada = db.liquidacion_existe(periodo)
    notas = db.get_notas_periodo(periodo)
    extras = db.get_gastos_extra(periodo)
    # Agrupar extras por unidad para lookup rápido en template
    extras_por_unidad = {}
    for e in extras:
        extras_por_unidad.setdefault(str(e["unidad"]), []).append(e)
    unidades = db.get_unidades(solo_activas=True)
    unidades_map = {str(u["numero"]): u for u in unidades}
    cfg = db.get_config()
    return render_template("liquidacion.html",
                           liq=liq,
                           gastos=gastos,
                           periodo=periodo,
                           mes_gastos=mes_gastos,
                           total_gastos=total_gastos,
                           total_a_pagar=total_a_pagar,
                           total_deuda=total_deuda,
                           pendientes=pendientes,
                           total_cobrado=total_cobrado,
                           cfg=cfg,
                           saldo_caja=saldo_caja,
                           saldo_al=saldo_al,
                           saldo_al_default=saldo_al_default,
                           entradas_caja=entradas,
                           salidas_caja=salidas,
                           fondo=fondo,
                           desglose=desglose,
                           liq_cerrada=liq_cerrada,
                           liq_generada=liq_generada,
                           notas=notas,
                           extras=extras,
                           extras_por_unidad=extras_por_unidad,
                           unidades=unidades,
                           unidades_map=unidades_map,
                           error_cierre=db.error_cierre(periodo) if (liq_generada and not liq_cerrada) else None,
                           propuesta_interes=db.propuesta_intereses(liq, cfg, periodo) if (liq_generada and not liq_cerrada) else [],
                           tasa_mora=db.tasa_mora(cfg, periodo),
                           capitaliza=db.capitaliza_intereses(cfg),
                           periodo_cobranza=db.periodo_cobranza())


@app.route("/liquidacion/generar/<periodo>", methods=["POST"])
def generar_liquidacion(periodo):
    if db.liq_esta_cerrada(periodo):
        flash(f"La liquidación de {periodo} está CERRADA y no puede modificarse.", "warning")
        return redirect(url_for("liquidacion", periodo=periodo))
    # Validar que la liquidación del mes anterior esté CERRADA
    periodo_anterior = db._prev_periodo(periodo)
    if db.liquidacion_existe(periodo_anterior) and not db.liq_esta_cerrada(periodo_anterior):
        flash(
            f"La liquidación de {mes_largo(periodo_anterior)} debe estar CERRADA antes de generar la de {mes_largo(periodo)}.",
            "danger"
        )
        return redirect(url_for("gastos", periodo=db._prev_periodo(periodo)))
    try:
        db.generar_liquidacion(periodo)
        flash(f"Liquidación generada/actualizada para {periodo}.", "success")
    except Exception as e:
        import traceback
        flash(f"Error al generar liquidación: {type(e).__name__}: {e}", "danger")
        app.logger.error(f"Error en generar_liquidacion({periodo}): {traceback.format_exc()}")
    return redirect(url_for("liquidacion", periodo=periodo))


@app.route("/liquidacion/cerrar/<periodo>", methods=["POST"])
def cerrar_liquidacion(periodo):
    # Switch por unidad en la ventana de cierre: las tildadas llevan interés sobre su deuda anterior
    err = db.cerrar_liquidacion(periodo, con_interes=request.form.getlist("interes_uf"))
    if err:
        flash(err, "warning")
        return redirect(url_for("liquidacion", periodo=periodo))
    flash(f"Liquidación de {mes_largo(periodo)} cerrada: el monto quedó fijo y ya se puede cobrar en Cobranzas.",
          "success")
    return redirect(url_for("cobranzas", periodo=periodo))


@app.route("/liquidacion/reabrir/<periodo>", methods=["POST"])
def reabrir_liquidacion(periodo):
    block = _require_admin()
    if block:
        return block
    err = db.error_reapertura(periodo)
    if err:
        flash(err, "warning")
    else:
        db.set_liq_estado(periodo, "ABIERTA")
        flash(f"Liquidación de {mes_largo(periodo)} reabierta.", "success")
    return redirect(url_for("liquidacion", periodo=periodo))


# ---------------------------------------------------------------------------
# COBRANZAS (v9.0): pagos de expensas sobre la última liquidación cerrada
# ---------------------------------------------------------------------------

@app.route("/cobranzas")
@app.route("/cobranzas/<periodo>")
def cobranzas(periodo=None):
    actual = db.periodo_cobranza()
    periodo = periodo or actual
    liq = db.get_liquidacion(periodo) if periodo else []
    info = db.info_cobranza(periodo, liq) if periodo else {"vencimiento": ""}
    cobrable = bool(periodo) and periodo == actual
    cfg = db.get_config()
    unidades_map = {str(u["numero"]): u for u in db.get_unidades(solo_activas=False)}
    cid = session.get("consorcio_id", "")
    clave_firma = db.get_clave_firma()
    url_app = cfg.get("url_app", "http://localhost:5000").rstrip("/")
    recibo_tokens = {
        str(r["unidad"]): _token_recibo_publico(clave_firma, cid, periodo, str(r["unidad"]))
        for r in liq if r.get("tipo_pago", "PENDIENTE") != "PENDIENTE"
    }
    pagos = []
    for r in liq:
        for p in r.get("pagos", []):
            pagos.append({**p, "persona": r["inquilino"] or r["propietario"]})
    pagos.sort(key=lambda p: (p["fecha"], p["id"]), reverse=True)
    cerradas = [r["periodo"] for r in db._fetchall(
        "SELECT periodo FROM liquidaciones_estado WHERE consorcio_id=%s AND estado='CERRADA' "
        "ORDER BY periodo DESC LIMIT 24", (db._cid(),))]
    return render_template(
        "cobranzas.html", periodo=periodo, periodo_cobranza=actual, cobrable=cobrable,
        liq=liq, pagos=pagos, cfg=cfg, unidades_map=unidades_map, cerradas=cerradas,
        liq_abierta=db.liquidacion_existe(db._next_periodo(actual)) and not db.liq_esta_cerrada(db._next_periodo(actual)) if actual else False,
        total_a_pagar=round(sum(r["total_a_pagar"] for r in liq), 2),
        total_cobrado=round(sum(r["monto_pagado"] for r in liq), 2),
        pendientes=sum(1 for r in liq if r["tipo_pago"] != "TOTAL"),
        recibo_tokens=recibo_tokens,
        recibo_base_url=f"{url_app}/recibo/publico/{cid}/{periodo}",
        vencimiento=info["vencimiento"],
    )


@app.route("/cobranzas/<periodo>/pagar/<unidad>", methods=["POST"])
def cobranzas_pagar(periodo, unidad):
    def _num(campo):
        v = _importe(request.form.get(campo) or "0")
        return v if v is not None else 0.0  # inválido / negativo / "nan" → 0 (el pago con 0 se rechaza)
    fecha_pago = request.form.get("fecha_pago") or _fecha_hoy().strftime("%Y-%m-%d")
    monto, bonif = _num("monto_pagado"), _num("bonificacion")
    res = db.registrar_pago(periodo, unidad, monto, fecha_pago, bonif,
                            (request.form.get("bonif_motivo") or "").strip())
    if res.get("error"):
        flash(res["error"], "danger")
    elif res["tipo"] == "PARCIAL":
        flash(f"UF {unidad}: pago parcial de ${monto:,.2f}. Saldo pendiente: ${res['saldo']:,.2f}.", "warning")
    elif res["saldo"] < 0:
        flash(f"UF {unidad}: pago total registrado. Pagó de más: queda un saldo a favor de "
              f"$ {-res['saldo']:,.2f} para la liquidación siguiente.", "success")
    else:
        flash(f"UF {unidad}: pago total registrado.", "success")
    if not res.get("error") and bonif > 0:
        flash(f"Bonificación de ${bonif:,.2f} registrada en Caja Diaria.", "info")
    return redirect(url_for("cobranzas", periodo=periodo))


@app.route("/cobranzas/<periodo>/pagar-todo", methods=["POST"])
def cobranzas_pagar_todo(periodo):
    fecha_pago = request.form.get("fecha_pago") or _fecha_hoy().strftime("%Y-%m-%d")
    n, err = db.pagar_todo(periodo, fecha_pago)
    if err:
        flash(err, "danger")
    if n:
        flash(f"{n} unidad(es) marcada(s) como pagadas.", "success")
    elif not err:
        flash("No hay unidades con saldo pendiente.", "info")
    return redirect(url_for("cobranzas", periodo=periodo))


@app.route("/cobranzas/<periodo>/anular", methods=["POST"])
def cobranzas_anular(periodo):
    """Anula un pago (form 'pago_id'), los de una unidad ('unidad') o todos. Solo administradores."""
    block = _require_admin()
    if block:
        return block
    pago_id = request.form.get("pago_id", "").strip()
    unidad = request.form.get("unidad", "").strip()
    ok, msg, _n = db.anular_pagos(periodo, [unidad] if unidad else None,
                                  pago_id=int(pago_id) if pago_id.isdigit() else None)
    flash(msg, "success" if ok else "warning")
    return redirect(url_for("cobranzas", periodo=periodo))


# ---------------------------------------------------------------------------
# NOTAS Y GASTOS EXTRA DEL PERÍODO
# ---------------------------------------------------------------------------

@app.route("/liquidacion/<periodo>/notas/add", methods=["POST"])
def notas_add(periodo):
    if db.liq_esta_cerrada(periodo):
        return jsonify({"error": "Liquidación cerrada"}), 400
    tipo = request.form.get("tipo", "INFO")
    texto = request.form.get("texto", "").strip()
    if not texto:
        return jsonify({"error": "Texto requerido"}), 400
    nid = db.add_nota(periodo, tipo, texto)
    return jsonify({"id": nid, "tipo": tipo, "texto": texto})


@app.route("/liquidacion/<periodo>/notas/<int:nid>/delete", methods=["POST"])
def notas_delete(periodo, nid):
    if db.liq_esta_cerrada(periodo):
        return jsonify({"error": "Liquidación cerrada"}), 400
    db.delete_nota(nid)
    return jsonify({"ok": True})


@app.route("/liquidacion/<periodo>/extras/add", methods=["POST"])
def extras_add(periodo):
    if db.liq_esta_cerrada(periodo):
        return jsonify({"error": "Liquidación cerrada"}), 400
    unidad = request.form.get("unidad", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    monto_str = request.form.get("monto", "0").replace(",", ".")
    if not unidad or not descripcion:
        return jsonify({"error": "Unidad y descripción requeridos"}), 400
    monto = _importe(monto_str, minimo=float("-inf"), cero=False)  # puede ser negativo (descuento)
    if monto is None:
        return jsonify({"error": "Monto inválido"}), 400
    eid = db.add_gasto_extra(periodo, unidad, descripcion, monto)
    # Si la liquidación está abierta, regenerar para actualizar totales
    if db.liquidacion_existe(periodo) and not db.liq_esta_cerrada(periodo):
        db.generar_liquidacion(periodo)
    return jsonify({"id": eid, "unidad": unidad, "descripcion": descripcion, "monto": monto})


@app.route("/liquidacion/<periodo>/extras/<int:eid>/delete", methods=["POST"])
def extras_delete(periodo, eid):
    if db.liq_esta_cerrada(periodo):
        return jsonify({"error": "Liquidación cerrada"}), 400
    db.delete_gasto_extra(eid)
    if db.liquidacion_existe(periodo) and not db.liq_esta_cerrada(periodo):
        db.generar_liquidacion(periodo)
    return jsonify({"ok": True})


@app.route("/liquidacion/pdf/<periodo>")
def descargar_pdf(periodo):
    """PDF resumen del edificio completo."""
    liq = db.get_liquidacion(periodo)
    if not liq:
        flash("No hay liquidación generada para este período.", "warning")
        return redirect(url_for("liquidacion", periodo=periodo))
    mes_gastos_pdf = db._prev_periodo(periodo)
    gastos = db.get_gastos(mes_gastos_pdf)
    cfg = db.get_config()
    yp2, mp2 = int(periodo[:4]), int(periodo[5:7])
    hasta_pdf = db.fecha_corte_liquidacion(periodo).strftime("%Y-%m-%d")  # cierre de la liquidación (o hoy)
    saldo_caja, _, _ = db.get_saldo_caja(hasta_fecha=hasta_pdf)
    fondo = _resumen_fondo_seguro(mes_gastos_pdf, cfg)
    notas = db.get_notas_periodo(periodo)
    extras = db.get_gastos_extra(periodo)
    _logo = db.get_logo()
    _logo_bytes = base64.b64decode(_logo["b64"]) if _logo else None
    try:
        caja_mes = db.get_resumen_caja_periodo(periodo)
    except Exception:
        app.logger.exception("[pdf] resumen de caja")
        caja_mes = None
    # Liquidación anterior por UF: "Liquidado mes ant." y "Pago anterior" en la planilla
    anterior = {str(r["unidad"]): r for r in db.get_liquidacion(mes_gastos_pdf)}
    pdf_bytes = generar_pdf_resumen_edificio(liq, gastos, cfg, periodo, saldo_caja, fondo,
                                             notas=notas, extras=extras, logo_bytes=_logo_bytes,
                                             caja_mes=caja_mes, anterior=anterior)
    _meses_pdf = ["enero","febrero","marzo","abril","mayo","junio",
                  "julio","agosto","septiembre","octubre","noviembre","diciembre"]
    _mes_str = _meses_pdf[int(periodo[5:7]) - 1] + "_" + periodo[:4]
    _edificio_str = cfg.get("edificio_nombre", "edificio").lower().replace(" ", "_")
    import re as _re
    _edificio_str = _re.sub(r"[^a-z0-9_]", "", _edificio_str)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"liquidacion_{_mes_str}_{_edificio_str}.pdf"
    )


@app.route("/liquidacion/recibo/<periodo>/<unidad>")
def descargar_recibo(periodo, unidad):
    """Resumen de expensas individual por unidad."""
    liq = db.get_liquidacion(periodo, simular=False)  # recibo firmado: datos reales
    row = next((r for r in liq if str(r["unidad"]) == str(unidad)), None)
    if not row or row.get("tipo_pago", "PENDIENTE") == "PENDIENTE":
        flash("No hay pago registrado para esta unidad.", "warning")
        return redirect(url_for("cobranzas", periodo=periodo))
    cfg = db.get_config()
    mes_gastos = db._prev_periodo(periodo)
    gastos = db.get_gastos(mes_gastos)
    facturas_extras = db.get_facturas_extraordinarias_periodo(mes_gastos)

    clave_firma = db.get_clave_firma()
    codigo = db.generar_codigo_verificacion(row, cfg, clave_firma)
    url_app = cfg.get("url_app", "http://localhost:5000").rstrip("/")
    url_verificacion = f"{url_app}/verificar/{periodo}/{unidad}/{codigo}"

    _logo = db.get_logo()
    _logo_bytes = base64.b64decode(_logo["b64"]) if _logo else None
    pdf_bytes = generar_recibo_pago(
        row, cfg, periodo, gastos, facturas_extras,
        codigo_verificacion=codigo,
        url_verificacion=url_verificacion,
        logo_bytes=_logo_bytes,
    )
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"resumen_expensas_{unidad}_{periodo}.pdf"
    )


def _recibo_publico_get_row(cid, periodo, unidad, token):
    """Validates HMAC token and returns (row, cfg, clave, url_app) or aborts."""
    from flask import abort
    c = db.get_consorcio(cid)
    if not c:
        abort(404)
    db.set_active_consorcio(c["data_dir_abs"], c["db_path_abs"])
    clave = db.get_clave_firma()
    expected = _token_recibo_publico(clave, cid, periodo, unidad)
    if not _hmac_mod.compare_digest(token, expected):
        abort(403)
    liq = db.get_liquidacion(periodo, simular=False)  # recibo firmado: datos reales
    row = next((r for r in liq if str(r["unidad"]) == str(unidad)), None)
    if not row or row.get("tipo_pago", "PENDIENTE") == "PENDIENTE":
        abort(404)
    cfg = db.get_config()
    url_app = cfg.get("url_app", "http://localhost:5000").rstrip("/")
    return row, cfg, clave, url_app


@app.route("/recibo/publico/<cid>/<periodo>/<unidad>/<token>")
def recibo_publico(cid, periodo, unidad, token):
    """Página de descarga/impresión del recibo, con PDF embebido."""
    row, cfg, clave, url_app = _recibo_publico_get_row(cid, periodo, unidad, token)
    codigo = db.generar_codigo_verificacion(row, cfg, clave)
    url_verificacion = f"{url_app}/verificar/{periodo}/{unidad}/{codigo}"
    pdf_url = f"{url_app}/recibo/publico/{cid}/{periodo}/{unidad}/{token}/pdf"
    edificio = cfg.get("edificio_nombre", "Consorcio")
    return render_template(
        "recibo_publico.html",
        periodo=periodo,
        unidad=unidad,
        edificio=edificio,
        pdf_url=pdf_url,
        url_verificacion=url_verificacion,
    )


@app.route("/recibo/publico/<cid>/<periodo>/<unidad>/<token>/pdf")
def recibo_publico_pdf(cid, periodo, unidad, token):
    """Genera y sirve el PDF del recibo on-the-fly, validado por HMAC."""
    row, cfg, clave, url_app = _recibo_publico_get_row(cid, periodo, unidad, token)
    mes_gastos = db._prev_periodo(periodo)
    gastos = db.get_gastos(mes_gastos)
    facturas_extras = db.get_facturas_extraordinarias_periodo(mes_gastos)
    codigo = db.generar_codigo_verificacion(row, cfg, clave)
    url_verificacion = f"{url_app}/verificar/{periodo}/{unidad}/{codigo}"
    _logo2 = db.get_logo()
    _logo_bytes2 = base64.b64decode(_logo2["b64"]) if _logo2 else None
    pdf_bytes = generar_recibo_pago(
        row, cfg, periodo, gastos, facturas_extras,
        codigo_verificacion=codigo,
        url_verificacion=url_verificacion,
        logo_bytes=_logo_bytes2,
    )
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"recibo_{periodo}_{unidad}.pdf"
    )


@app.route("/verificar")
@app.route("/verificar/<periodo>/<unidad>/<codigo>")
def verificar_recibo(periodo=None, unidad=None, codigo=None):
    """Página de verificación de autenticidad de un recibo."""
    if not periodo or not unidad or not codigo:
        return render_template("verificar.html", estado="formulario")

    liq = db.get_liquidacion(periodo, simular=False)  # recibo firmado: datos reales
    row = next((r for r in liq if str(r["unidad"]) == str(unidad)), None)
    if not row:
        return render_template("verificar.html", estado="no_encontrado",
                               periodo=periodo, unidad=unidad)

    cfg = db.get_config()
    clave_firma = db.get_clave_firma()
    codigo_esperado = db.generar_codigo_verificacion(row, cfg, clave_firma)

    import hmac as _hmac_mod
    valido = _hmac_mod.compare_digest(codigo.lower(), codigo_esperado.lower())

    return render_template(
        "verificar.html",
        estado="valido" if valido else "invalido",
        row=row,
        cfg=cfg,
        periodo=periodo,
        unidad=unidad,
        codigo=codigo,
    )


# ---------------------------------------------------------------------------
# PLANO DEL EDIFICIO
# ---------------------------------------------------------------------------

@app.route("/plano")
@app.route("/plano/<periodo>")
def plano(periodo=None):
    if not periodo:
        periodo = _periodo_actual()
    unidades = db.get_estado_plano(periodo)
    fondo = db.get_fondo_reserva()
    # Agrupar por piso manteniendo orden (pisos descendente)
    pisos = {}
    for u in unidades:
        p = u["piso"] if u["piso"] else "Sin asignar"
        pisos.setdefault(p, []).append(u)
    # Ordenar pisos: numéricos de mayor a menor, luego los de texto
    def piso_sort_key(p):
        try:
            return (0, -int(p))
        except (ValueError, TypeError):
            return (1, p)
    pisos_ordenados = sorted(pisos.items(), key=lambda x: piso_sort_key(x[0]))
    return render_template("plano.html", unidades=unidades, pisos=pisos_ordenados,
                           periodo=periodo, fondo=fondo)


# ---------------------------------------------------------------------------
# PROVEEDORES
# ---------------------------------------------------------------------------

@app.route("/proveedores")
def proveedores():
    lista = db.get_proveedores()
    gastos_recurrentes = db.get_gastos_recurrentes()
    return render_template("proveedores.html", proveedores=lista,
                           gastos_recurrentes=gastos_recurrentes)


@app.route("/proveedores/save", methods=["POST"])
def save_proveedor():
    data = {
        "id": request.form.get("id") or None,
        "nombre": request.form.get("nombre", "").strip(),
        "cuit": request.form.get("cuit", "").strip(),
        "telefono": request.form.get("telefono", "").strip(),
        "email": request.form.get("email", "").strip(),
        "direccion": request.form.get("direccion", "").strip(),
        "categoria": request.form.get("categoria", "").strip(),
        "notas": request.form.get("notas", "").strip(),
        "gasto_recurrente": request.form.get("gasto_recurrente", "").strip(),
    }
    if not data["nombre"]:
        flash("El nombre del proveedor es obligatorio.", "danger")
        return redirect(url_for("proveedores"))
    db.save_proveedor(data)
    flash("Proveedor guardado.", "success")
    return redirect(url_for("proveedores"))


@app.route("/proveedores/delete/<int:pid>", methods=["POST"])
def delete_proveedor(pid):
    db.delete_proveedor(pid)
    flash("Proveedor eliminado.", "success")
    return redirect(url_for("proveedores"))


# ---------------------------------------------------------------------------
# FACTURAS
# ---------------------------------------------------------------------------

@app.route("/facturas")
def facturas():
    estado = request.args.get("estado")
    mes = request.args.get("mes", "")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 25
    lista, total = db.get_facturas(estado=estado, mes=mes, page=page, per_page=per_page)
    total_pages = max(1, (total + per_page - 1) // per_page)
    provs = db.get_proveedores()
    total_pendiente = db.get_total_pendiente_facturas()
    gastos_recurrentes = db.get_gastos_recurrentes()
    try:
        saldo_fondo = db.get_saldo_fondo()
    except Exception:
        app.logger.exception("No se pudo calcular el saldo del fondo de reserva")
        saldo_fondo = None
    return render_template("facturas.html", facturas=lista, proveedores=provs,
                           saldo_fondo=saldo_fondo,
                           estado_filtro=estado, mes_filtro=mes,
                           total_pendiente=total_pendiente,
                           gastos_recurrentes=gastos_recurrentes,
                           page=page, total_pages=total_pages, total=total)


@app.route("/facturas/save", methods=["POST"])
def save_factura():
    importe = request.form.get("importe", "0").strip().replace(",", ".")
    # Buscar nombre del proveedor
    prov_id = request.form.get("proveedor_id", "").strip()
    prov = db.get_proveedor(prov_id) if prov_id else None
    data = {
        "id": request.form.get("id") or None,
        "fecha": request.form.get("fecha", ""),
        "proveedor_id": prov_id,
        "proveedor_nombre": prov["nombre"] if prov else request.form.get("proveedor_nombre", "").strip(),
        "descripcion": request.form.get("descripcion", "").strip(),
        "importe": _importe(importe, cero=False),
        "estado": "PENDIENTE",
        "fecha_pago": None,
        "categoria": request.form.get("categoria", "").strip(),
        "numero_factura": request.form.get("numero_factura", "").strip(),
        "extraordinario": 1 if request.form.get("extraordinario") else 0,
        "gasto_id": request.form.get("gasto_id", "").strip() or None,
    }
    if data["importe"] is None:
        flash("El importe de la factura debe ser un número mayor a cero.", "danger")
        return redirect(url_for("facturas"))
    if data["id"]:
        # La pantalla no edita facturas; un pedido armado a mano no puede "despagar" una factura
        # pagada (dejaría su salida de Caja y su gasto sin factura pagada) (v9.8).
        existente = db.get_factura_by_id(data["id"]) if str(data["id"]).isdigit() else None
        if not existente:
            flash("Factura no encontrada.", "danger")
            return redirect(url_for("facturas"))
        if existente.get("estado") == "PAGADA":
            flash("No se puede modificar una factura pagada.", "danger")
            return redirect(url_for("facturas"))
    if not data["descripcion"] or not data["fecha"]:
        flash("Fecha y descripción son obligatorias.", "danger")
        return redirect(url_for("facturas"))
    db.save_factura(data)
    flash("Factura guardada." + (" Quedó vinculada al gasto: al pagarla no se duplica."
                                 if data["gasto_id"] else ""), "success")
    return redirect(url_for("facturas"))


@app.route("/facturas/pagar/<int:fid>", methods=["POST"])
def pagar_factura(fid):
    fecha_pago = request.form.get("fecha_pago") or _fecha_hoy().strftime("%Y-%m-%d")
    try:
        date.fromisoformat(fecha_pago)
    except ValueError:
        flash("Fecha de pago inválida.", "danger")
        return redirect(url_for("facturas"))
    if db.caja_mes_bloqueado(fecha_pago[:7]):
        flash(f"La Caja de {fecha_pago[:7]} está cerrada (se cerró la liquidación que lleva esos gastos): "
              "no se puede registrar el pago con esa fecha.", "danger")
        return redirect(url_for("facturas"))
    factura = db.get_factura_by_id(fid)
    if factura and factura.get("estado") == "PAGADA":
        flash("La factura ya está pagada.", "warning")
        return redirect(url_for("facturas"))
    if factura:
        fecha_emision = str(factura.get("fecha") or "")
        if fecha_emision and fecha_pago < fecha_emision:
            flash(f"La fecha de pago ({fecha_pago}) no puede ser anterior a la fecha de emisión de la factura ({fecha_emision}).", "danger")
            return redirect(url_for("facturas"))
    con_fondo = bool(request.form.get("con_fondo"))
    ok = db.pagar_factura(fid, fecha_pago, con_fondo=con_fondo,
                          observacion=request.form.get("observacion", ""))
    if ok:
        periodo = fecha_pago[:7]
        if con_fondo:
            flash("Factura pagada con el Fondo de Reserva. Se registró en Caja Diaria y no se "
                  "cobra en la liquidación.", "success")
            if factura and str(factura.get("fecha") or "")[:7] not in ("", periodo):
                _recalcular_liq_si_posible(str(factura["fecha"])[:7])
        else:
            flash("Factura pagada. Se registró en Caja Diaria y Gastos Mensuales.", "success")
        _recalcular_liq_si_posible(periodo)
    else:
        flash("No se encontró la factura.", "danger")
    return redirect(url_for("facturas"))


@app.route("/facturas/delete/<int:fid>", methods=["POST"])
def delete_factura(fid):
    factura = db.get_factura_by_id(fid)
    ruta = (factura or {}).get("archivo_pdf") or ""
    ok = db.delete_factura(fid)
    if ok:
        flash("Factura eliminada.", "success")
        if ruta and not _borrar_comprobante(ruta):
            flash("No se pudo borrar el archivo del comprobante.", "warning")
    else:
        flash("No se puede eliminar: la factura ya fue incluida en una liquidación cerrada.", "danger")
    return redirect(url_for("facturas"))


# ---------------------------------------------------------------------------
# PRESUPUESTOS
# ---------------------------------------------------------------------------

@app.route("/presupuestos")
def presupuestos():
    pedidos = db.get_pedidos()
    # Agregar conteo de cotizaciones por pedido
    for p in pedidos:
        cots = db.get_presupuestos(pedido_id=p["id"])
        p["cant_cotizaciones"] = len(cots)
        p["mejor_precio"] = min((c["importe"] for c in cots), default=None)
    return render_template("presupuestos.html", pedidos=pedidos)


@app.route("/presupuestos/pedido/save", methods=["POST"])
def save_pedido():
    data = {
        "id": request.form.get("id") or None,
        "fecha": request.form.get("fecha", _fecha_hoy().strftime("%Y-%m-%d")),
        "descripcion": request.form.get("descripcion", "").strip(),
        "categoria": request.form.get("categoria", "").strip(),
        "estado": request.form.get("estado", "ABIERTO"),
        "proveedor_elegido": request.form.get("proveedor_elegido", "").strip(),
        "notas": request.form.get("notas", "").strip(),
    }
    if not data["descripcion"]:
        flash("La descripción del pedido es obligatoria.", "danger")
        return redirect(url_for("presupuestos"))
    db.save_pedido(data)
    flash("Pedido guardado.", "success")
    return redirect(url_for("presupuestos"))


@app.route("/presupuestos/pedido/delete/<int:pid>", methods=["POST"])
def delete_pedido(pid):
    db.delete_pedido(pid)
    flash("Pedido y sus cotizaciones eliminados.", "success")
    return redirect(url_for("presupuestos"))


@app.route("/presupuestos/pedido/<int:pedido_id>")
def detalle_pedido(pedido_id):
    pedidos = db.get_pedidos()
    pedido = next((p for p in pedidos if str(p["id"]) == str(pedido_id)), None)
    if not pedido:
        flash("Pedido no encontrado.", "danger")
        return redirect(url_for("presupuestos"))
    cotizaciones = db.get_presupuestos(pedido_id=pedido_id)
    provs = db.get_proveedores()
    return render_template("detalle_pedido.html", pedido=pedido,
                           cotizaciones=cotizaciones, proveedores=provs)


@app.route("/presupuestos/cotizacion/save", methods=["POST"])
def save_cotizacion():
    pedido_id = request.form.get("pedido_id")
    importe = request.form.get("importe", "0").strip().replace(",", ".")
    prov_id = request.form.get("proveedor_id", "").strip()
    prov = db.get_proveedor(prov_id) if prov_id else None
    data = {
        "id": request.form.get("id") or None,
        "pedido_id": pedido_id,
        "proveedor_id": prov_id,
        "proveedor_nombre": prov["nombre"] if prov else request.form.get("proveedor_nombre_libre", "").strip(),
        "fecha": request.form.get("fecha", _fecha_hoy().strftime("%Y-%m-%d")),
        "importe": float(importe) if importe else 0.0,
        "notas": request.form.get("notas", "").strip(),
        "seleccionado": 0,
    }
    db.save_presupuesto(data)
    flash("Cotización guardada.", "success")
    return redirect(url_for("detalle_pedido", pedido_id=pedido_id))


@app.route("/presupuestos/cotizacion/seleccionar/<int:pres_id>/<int:pedido_id>", methods=["POST"])
def seleccionar_cotizacion(pres_id, pedido_id):
    db.seleccionar_presupuesto(pres_id, pedido_id)
    flash("Cotización seleccionada. Pedido marcado como ADJUDICADO.", "success")
    return redirect(url_for("detalle_pedido", pedido_id=pedido_id))


@app.route("/presupuestos/cotizacion/delete/<int:pres_id>/<int:pedido_id>", methods=["POST"])
def delete_cotizacion(pres_id, pedido_id):
    db.delete_presupuesto(pres_id)
    flash("Cotización eliminada.", "success")
    return redirect(url_for("detalle_pedido", pedido_id=pedido_id))


# ---------------------------------------------------------------------------
# ESTADO DE CUENTA
# ---------------------------------------------------------------------------

@app.route("/estado-cuenta")
def estado_cuenta():
    historial = db.get_historial_unidades()
    unidades = db.get_unidades()
    return render_template("estado_cuenta.html", historial=historial, unidades=unidades)


# ---------------------------------------------------------------------------
# APERTURA / SALDOS INICIALES
# ---------------------------------------------------------------------------

@app.route("/apertura", methods=["GET", "POST"])
def apertura():
    if request.method == "POST":
        saldo_raw = request.form.get("saldo_inicial_caja", "0").replace(",", ".")
        saldo_inicial = _importe(saldo_raw or "0", minimo=float("-inf"))
        if saldo_inicial is None:
            flash("El saldo inicial de caja debe ser un número.", "danger")
            return redirect(url_for("apertura"))
        deudas = {}
        fechas = {}
        for key, val in request.form.items():
            if key.startswith("deuda_"):
                numero = key[6:]
                v = _importe(val.strip() or "0", minimo=float("-inf"))  # negativo = saldo a favor
                if v is None:
                    flash(f"La deuda inicial de la UF {numero} debe ser un número.", "danger")
                    return redirect(url_for("apertura"))
                deudas[numero] = v
            elif key.startswith("fecha_deuda_"):
                numero = key[12:]
                fechas[numero] = val.strip() or None
        fondo_inicial = None
        if (request.form.get("fondo_saldo_inicial") or "").strip():   # vacío = no se toca
            fondo_inicial = _importe(request.form["fondo_saldo_inicial"].strip().replace(",", "."),
                                     minimo=float("-inf"))
            if fondo_inicial is None:
                flash("El saldo inicial del Fondo de Reserva debe ser un número.", "danger")
                return redirect(url_for("apertura"))
        try:
            fecha_caja = request.form.get("saldo_inicial_caja_fecha", "").strip()
            db.save_apertura(saldo_inicial, deudas, fechas, fecha_caja, fondo_inicial=fondo_inicial,
                             fondo_fecha=request.form.get("fondo_saldo_inicial_fecha", "").strip() or fecha_caja)
            flash(f"Saldos iniciales guardados. Saldo de caja: $ {saldo_inicial:,.2f}", "success")
        except Exception as e:
            flash(f"Error al guardar: {e}", "danger")
        return redirect(url_for("apertura"))
    saldo_inicial, fecha_caja, unidades = db.get_apertura()
    cfg = db.get_config()
    return render_template("apertura.html", saldo_inicial=saldo_inicial,
                           fecha_caja=fecha_caja, unidades=unidades,
                           fondo_inicial=cfg.get("fondo_saldo_inicial", ""),
                           fondo_fecha=cfg.get("fondo_saldo_inicial_fecha", ""))


# ---------------------------------------------------------------------------
# COMPROBANTES DE FACTURAS (upload / visualización)
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "tiff", "bmp"}

def _sanitize_dirname(name: str) -> str:
    """Convierte un nombre de proveedor en un nombre de directorio seguro."""
    name = name.strip().lower()
    for src, dst in [("áàäâ", "a"), ("éèëê", "e"), ("íìïî", "i"), ("óòöô", "o"), ("úùüû", "u"), ("ñ", "n")]:
        for c in src:
            name = name.replace(c, dst)
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-z0-9_\-]", "", name)
    return name or "sin_proveedor"

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in _ALLOWED_EXTENSIONS

@app.route("/facturas/<int:fid>/upload", methods=["POST"])
def upload_comprobante(fid):
    """Recibe un archivo (PDF o imagen), lo convierte a PDF si es necesario y lo adjunta a la factura."""
    file = request.files.get("comprobante")
    if not file or file.filename == "":
        flash("No se seleccionó ningún archivo.", "danger")
        return redirect(url_for("facturas"))
    if not _allowed_file(file.filename):
        flash("Tipo de archivo no permitido. Use PDF, PNG, JPG, GIF, TIFF o BMP.", "danger")
        return redirect(url_for("facturas"))
    factura = db.get_factura_by_id(fid)
    if not factura:
        flash("Factura no encontrada.", "danger")
        return redirect(url_for("facturas"))
    proveedor_dir = _sanitize_dirname(factura.get("proveedor_nombre") or "")
    from datetime import datetime as _dt
    timestamp = _dt.now().strftime("%Y-%m-%d_%H%M%S")
    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext == "pdf":
        datos = file.read()
    else:
        from PIL import Image
        try:
            img = Image.open(file.stream)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "PDF", resolution=150)
        except Exception:
            flash("No se pudo leer la imagen. Probá con otro archivo.", "danger")
            return redirect(url_for("facturas"))
        datos = buf.getvalue()
    ruta = f"facturas/{proveedor_dir}/{timestamp}.pdf"
    try:
        storage.guardar(_clave_comprobante(ruta), datos, "application/pdf")
    except storage.StorageError as exc:
        app.logger.error(f"[Storage] comprobante de la factura {fid}: {exc}")
        flash("No se pudo guardar el comprobante. Intentá de nuevo en unos minutos.", "danger")
        return redirect(url_for("facturas"))
    anterior = factura.get("archivo_pdf") or ""
    db.set_factura_archivo_pdf(fid, ruta)
    if anterior and anterior != ruta:
        _borrar_comprobante(anterior)       # reemplazo: el archivo viejo ya no se usa
    flash("Comprobante adjuntado correctamente.", "success")
    return redirect(url_for("facturas"))


@app.route("/facturas/<int:fid>/comprobante/quitar", methods=["POST"])
def quitar_comprobante(fid):
    """Quita el comprobante adjunto de una factura y borra el archivo (v11.1)."""
    factura = db.get_factura_by_id(fid)
    if not factura or not factura.get("archivo_pdf"):
        flash("Esta factura no tiene comprobante adjunto.", "warning")
        return redirect(url_for("facturas"))
    ruta = factura["archivo_pdf"]
    db.set_factura_archivo_pdf(fid, "")
    if _borrar_comprobante(ruta):
        flash("Comprobante quitado.", "success")
    else:
        flash("Se quitó el comprobante de la factura, pero no se pudo borrar el archivo.", "warning")
    return redirect(url_for("facturas"))


def _borrar_comprobante(ruta: str) -> bool:
    """Borra el archivo de un comprobante (en el almacenamiento y, si es viejo, en el disco),
    salvo que otra factura del consorcio todavía lo use. Devuelve False si no se pudo."""
    if ruta in db.get_rutas_comprobantes():
        return True                          # otra factura lo sigue usando: no se borra
    try:
        storage.borrar(_clave_comprobante(ruta))
        real_data = os.path.realpath(db.get_data_dir())
        real_path = os.path.realpath(os.path.join(real_data, ruta))
        if real_path.startswith(real_data + os.sep) and os.path.isfile(real_path):
            os.remove(real_path)
        return True
    except (storage.StorageError, OSError) as exc:
        app.logger.error(f"[Storage] no se pudo borrar el comprobante {ruta}: {exc}")
        return False


@app.route("/facturas/<int:fid>/comprobante")
def ver_comprobante(fid):
    """Sirve el PDF adjunto de una factura directamente en el navegador."""
    factura = db.get_factura_by_id(fid)
    if not factura or not factura.get("archivo_pdf"):
        flash("Esta factura no tiene comprobante adjunto.", "warning")
        return redirect(url_for("facturas"))
    try:
        data = _leer_comprobante(factura["archivo_pdf"])
    except storage.StorageError as exc:
        app.logger.error(f"[Storage] ver comprobante de la factura {fid}: {exc}")
        flash("No se pudo obtener el comprobante en este momento. Intentá de nuevo.", "danger")
        return redirect(url_for("facturas"))
    if data is None:
        flash("El archivo del comprobante no se encontró. Volvé a adjuntarlo.", "danger")
        return redirect(url_for("facturas"))
    return send_file(io.BytesIO(data), mimetype="application/pdf",
                     download_name=f"comprobante_factura_{fid}.pdf")


def _clave_comprobante(ruta: str) -> str:
    """Clave en el almacenamiento: <consorcio_id>/<ruta guardada en facturas.archivo_pdf>."""
    return f"{db._cid()}/{ruta.replace(chr(92), '/')}"


def _leer_comprobante(ruta: str) -> bytes | None:
    """Lee un comprobante del almacenamiento; si no está, prueba el disco (archivos viejos)."""
    data = storage.leer(_clave_comprobante(ruta))
    if data is not None:
        return data
    return _leer_disco_viejo(ruta)


def _comprobantes_para_zip():
    """(ruta, bytes) de cada comprobante adjunto del consorcio activo. Los que no se pueden
    leer se informan en la lista de faltantes en vez de cortar todo el ZIP."""
    encontrados, faltantes = [], []
    for ruta in db.get_rutas_comprobantes():
        try:
            data = _leer_comprobante(ruta)
        except storage.StorageError as exc:
            app.logger.warning(f"[Storage] comprobante {ruta}: {exc}")
            data = None
        if data is None:
            faltantes.append(ruta)
        else:
            encontrados.append((ruta.replace(chr(92), "/"), data))
    return encontrados, faltantes


# ---------------------------------------------------------------------------
# BACKUP
# ---------------------------------------------------------------------------

@app.route("/backup")
def backup():
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        db_path = db.get_db_path()
        if os.path.isfile(db_path):
            zf.write(db_path, os.path.basename(db_path))
        comprobantes, _faltantes = _comprobantes_para_zip()
        for ruta, data in comprobantes:
            zf.writestr(ruta, data)
    buf.seek(0)
    fecha = _fecha_hoy().strftime("%Y%m%d_%H%M")
    cid = session.get("consorcio_id", "consorcio")
    c = db.get_consorcio(cid)
    nombre_safe = re.sub(r"[^a-z0-9_]", "", (c["nombre"] if c else cid).lower().replace(" ", "_"))
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"backup_{nombre_safe}_{fecha}.zip"
    )


# ---------------------------------------------------------------------------
# EXPORTACIÓN COMPLETA DEL CONSORCIO (v10.0)
# ---------------------------------------------------------------------------

@app.route("/exportar")
def exportar_consorcio():
    """ZIP con todas las tablas del consorcio (CSV + JSON), los comprobantes adjuntos y un LEEME.
    Sirve de respaldo y para entregar la documentación en un cambio de administración (CCyC 2067).
    Solo administradores: contiene datos personales (Ley 25.326)."""
    block = _require_admin()
    if block:
        return block
    import csv
    import json as _json
    import zipfile
    from decimal import Decimal

    def _txt(v):
        if v is None:
            return ""
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        if isinstance(v, (dict, list)):
            return _json.dumps(v, ensure_ascii=False, default=str)
        return str(v)

    datos = db.exportar_consorcio()
    cfg = db.get_config()
    cid = session.get("consorcio_id", "consorcio")
    c = db.get_consorcio(cid)
    nombre = c["nombre"] if c else cid
    ahora = datetime.now()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        resumen = []
        completo = {}
        for tabla, (cols, filas) in sorted(datos.items()):
            s = io.StringIO()
            w = csv.writer(s, delimiter=";")
            w.writerow(cols)
            for f in filas:
                w.writerow([_txt(v) for v in f])
            zf.writestr(f"datos/{tabla}.csv", "﻿" + s.getvalue())   # BOM: Excel abre bien los acentos
            completo[tabla] = [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in zip(cols, f)} for f in filas]
            resumen.append(f"  - datos/{tabla}.csv: {len(filas)} fila(s)")
        zf.writestr("datos/consorcio_completo.json",
                    _json.dumps(completo, ensure_ascii=False, indent=1, default=str))
        comprobantes, faltantes = _comprobantes_para_zip()
        for ruta, data in comprobantes:
            # ruta = "facturas/<proveedor>/<fecha>.pdf" → "comprobantes/<proveedor>/<fecha>.pdf"
            zf.writestr("comprobantes/" + ruta.split("/", 1)[-1], data)
        n_comp = len(comprobantes)
        leeme = [
            f"EXPORTACIÓN COMPLETA — {nombre}",
            f"Generada el {ahora.strftime('%d/%m/%Y %H:%M')} por {session.get('usuario_email', '')}",
            f"Versión del sistema: {_leer_version()}",
            f"Fecha del sistema: {_fecha_hoy().strftime('%d/%m/%Y')}",
            "",
            "Contenido:",
            *resumen,
            "  - datos/consorcio_completo.json: las mismas tablas en un solo archivo JSON",
            f"  - comprobantes/: {n_comp} archivo(s) adjunto(s) a facturas",
            *([f"  - ATENCIÓN: {len(faltantes)} comprobante(s) registrado(s) no se encontraron:"]
              + [f"      {r}" for r in faltantes] if faltantes else []),
            "",
            "Notas:",
            "  - Los CSV usan ';' como separador y fechas AAAA-MM-DD.",
            "  - audit_log es el Log de Movimientos (últimos 180 días): quién cambió qué y cuándo.",
            "  - No incluye usuarios ni permisos de la aplicación, ni la clave con que se firman los recibos.",
            "  - Contiene datos personales (Ley 25.326): guardar y transmitir con confidencialidad.",
            "  - Este archivo es un respaldo de los registros del sistema. No reemplaza los libros",
            "    rubricados ni la documentación original exigida por el CCyC (art. 2067).",
            "",
            f"Edificio: {cfg.get('edificio_nombre', '')} — {cfg.get('edificio_direccion', '')}",
            f"Administración: {cfg.get('administrador', '')}",
        ]
        zf.writestr("LEEME.txt", "﻿" + "\r\n".join(leeme))
    buf.seek(0)
    nombre_safe = re.sub(r"[^a-z0-9_]", "", nombre.lower().replace(" ", "_"))
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"exportacion_{nombre_safe}_{ahora.strftime('%Y%m%d_%H%M')}.zip")


def _leer_version():
    try:
        with open(os.path.join(os.path.dirname(__file__), "version.txt")) as f:
            return f.read().strip()
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# LIBRO DEL FONDO DE RESERVA (v10.0)
# ---------------------------------------------------------------------------

@app.route("/fondo")
def fondo_reserva():
    try:
        libro = db.get_libro_fondo()
    except Exception:
        app.logger.exception("[fondo] libro del fondo")
        flash("No se pudo calcular el libro del Fondo de Reserva. Avisá al administrador del sistema.", "danger")
        return redirect(url_for("liquidacion"))
    return render_template("fondo.html", libro=libro)


# ---------------------------------------------------------------------------
# VENCIMIENTOS Y ALERTAS (v10.0)
# ---------------------------------------------------------------------------

@app.route("/vencimientos")
def vencimientos():
    return render_template("vencimientos.html", alertas=db.get_alertas(), vencimientos=db.get_vencimientos(),
                           tipos=db.TIPOS_VENCIMIENTO)


@app.route("/vencimientos/add", methods=["POST"])
def vencimiento_add():
    err = db.add_vencimiento(request.form.get("tipo", ""), request.form.get("fecha_inicio", ""),
                             request.form.get("descripcion", ""), request.form.get("fecha_vencimiento", ""),
                             request.form.get("observacion", ""))
    flash(err or "Vencimiento registrado.", "danger" if err else "success")
    return redirect(url_for("vencimientos"))


@app.route("/vencimientos/<int:vid>/cumplido", methods=["POST"])
def vencimiento_cumplido(vid):
    fecha = "" if request.form.get("accion") == "desmarcar" else (request.form.get("fecha") or _fecha_hoy().strftime("%Y-%m-%d"))
    if not db.set_vencimiento_cumplido(vid, fecha):
        flash("Fecha inválida.", "danger")
    return redirect(url_for("vencimientos"))


@app.route("/vencimientos/<int:vid>/delete", methods=["POST"])
def vencimiento_delete(vid):
    db.delete_vencimiento(vid)
    flash("Vencimiento eliminado.", "success")
    return redirect(url_for("vencimientos"))


# ---------------------------------------------------------------------------
# AYUDA: manual de usuario (v10.0)
# ---------------------------------------------------------------------------

@app.route("/ayuda")
def ayuda():
    """Muestra docs/manual_usuario.md dentro de la app (el Markdown se dibuja en el navegador):
    el repo es la única fuente del manual. Los diagramas técnicos (docs/diagramas.md) no van acá."""
    try:
        with open(os.path.join(os.path.dirname(__file__), "docs", "manual_usuario.md"), encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        texto = "# Manual no disponible\n\nNo se encontró `docs/manual_usuario.md`."
    return render_template("ayuda.html", texto=texto)


# ---------------------------------------------------------------------------
# RESET (pruebas)
# ---------------------------------------------------------------------------

@app.route("/config/reset", methods=["POST"])
def reset_datos():
    block = _require_admin()
    if block:
        return block
    db.reset_datos_operativos()
    flash("Datos reseteados: liquidaciones, gastos y caja borrados.", "success")
    return redirect(url_for("config"))


# ---------------------------------------------------------------------------
# CHECKPOINT / ROLLBACK
# ---------------------------------------------------------------------------

@app.route("/checkpoint/crear", methods=["POST"])
def crear_checkpoint():
    descripcion = request.form.get("descripcion", "").strip()
    db.crear_checkpoint(descripcion)
    flash("Checkpoint creado. Podés hacer rollback en cualquier momento durante el próximo mes.", "success")
    return redirect(url_for("config"))


@app.route("/checkpoint/rollback", methods=["POST"])
def rollback_checkpoint():
    ok = db.rollback_checkpoint()
    if ok:
        flash("Rollback realizado. Los datos volvieron al estado del checkpoint.", "success")
    else:
        flash("No hay checkpoint activo para restaurar.", "warning")
    return redirect(url_for("config"))


@app.route("/checkpoint/eliminar", methods=["POST"])
def eliminar_checkpoint():
    db._eliminar_checkpoint()
    flash("Checkpoint eliminado (consolidado manualmente).", "info")
    return redirect(url_for("config"))


# ---------------------------------------------------------------------------
# LOGO
# ---------------------------------------------------------------------------

@app.route("/logo")
def servir_logo():
    logo = db.get_logo()
    if not logo:
        return "", 404
    img_bytes = base64.b64decode(logo["b64"])
    return send_file(io.BytesIO(img_bytes), mimetype=logo["mime"])


@app.route("/config/logo/upload", methods=["POST"])
def upload_logo():
    f = request.files.get("logo")
    if not f or not f.filename:
        flash("Seleccioná un archivo de imagen.", "warning")
        return redirect(url_for("config"))
    allowed = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"}
    mime = f.mimetype or "image/png"
    if mime not in allowed:
        flash("Formato no soportado. Usá PNG, JPG, GIF, WEBP o SVG.", "danger")
        return redirect(url_for("config"))
    data = f.read()
    if len(data) > 512 * 1024:
        flash("El logo no puede superar 512 KB.", "danger")
        return redirect(url_for("config"))
    db.save_logo(base64.b64encode(data).decode(), mime)
    flash("Logo actualizado.", "success")
    return redirect(url_for("config"))


@app.route("/config/logo/delete", methods=["POST"])
def delete_logo():
    db.delete_logo()
    flash("Logo eliminado.", "info")
    return redirect(url_for("config"))


# ---------------------------------------------------------------------------
# ERRORES INTERNOS
# ---------------------------------------------------------------------------

@app.errorhandler(500)
def error_interno(e):
    """
    Error 500: siempre queda el traceback en el log. A los administradores se les muestra
    el detalle en pantalla (para diagnosticar sin acceso al log de Render); al resto, un
    mensaje simple. La página no usa base.html, por si el error viene de ahí.
    """
    import traceback
    from markupsafe import escape
    orig = getattr(e, "original_exception", None) or e
    detalle = "".join(traceback.format_exception(type(orig), orig, orig.__traceback__))
    app.logger.error(f"Error 500 en {request.method} {request.path}:\n{detalle}")
    try:
        with open(os.path.join(os.path.dirname(__file__), "version.txt")) as _f:
            version = _f.read().strip()
    except Exception:
        version = "?"
    cuerpo = ("<p>Ocurrió un error inesperado. Avisá al administrador del sistema.</p>"
              f'<p><a href="{url_for("index")}">Volver al inicio</a></p>')
    if session.get("es_admin"):
        cuerpo = (
            "<p>Ocurrió un error inesperado. Como sos administrador, abajo está el detalle técnico: "
            "copialo completo y pasáselo a quien mantiene el sistema.</p>"
            f"<p><b>Página:</b> {escape(request.method)} {escape(request.path)}<br>"
            f"<b>Versión:</b> {escape(version)}<br>"
            f"<b>Consorcio:</b> {escape(session.get('consorcio_id', ''))}<br>"
            f"<b>Fecha del sistema fijada:</b> {escape(_fecha_fijada_segura())}</p>"
            f'<pre style="white-space:pre-wrap;background:#f6f6f6;border:1px solid #ccc;padding:12px;'
            f'font-size:12px">{escape(detalle)}</pre>'
            f'<p><a href="{url_for("index")}">Volver al inicio</a></p>'
        )
    html = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Error del sistema</title></head>'
            '<body style="font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px">'
            f'<h2 style="color:#c00000">Error del sistema</h2>{cuerpo}</body></html>')
    return html, 500


def _fecha_fijada_segura() -> str:
    try:
        return db.get_config().get("fecha_simulada", "") or "(no)"
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db.sync_from_drive()
    host = os.environ.get("APP_HOST", "127.0.0.1")
    # Modo debug solo si la app escucha únicamente en esta PC: en la red local (iniciar_red.bat,
    # 0.0.0.0) la consola de depuración quedaría accesible desde otras computadoras.
    app.run(debug=host in ("127.0.0.1", "localhost"), host=host, port=5000)
