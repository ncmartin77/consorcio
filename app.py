"""
App Flask - Administración de Consorcio Edificio Brasil
Correr con: python app.py  o  flask run
"""
import os
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
import io

import excel_db as db
from pdf_gen import generar_pdf_liquidacion, generar_pdf_resumen_edificio, generar_recibo_pago

app = Flask(__name__)
app.secret_key = "edificio-brasil-secret-2024"


def _periodo_actual():
    today = date.today()
    return f"{today.year}-{today.month:02d}"


# ---------------------------------------------------------------------------
# INDEX
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("liquidacion"))


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
        }
        db.save_config(data)
        flash("Configuración guardada.", "success")
        return redirect(url_for("config"))

    cfg = db.get_config()
    categorias = db.get_categorias()
    return render_template("config.html", cfg=cfg, categorias=categorias)


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
    return render_template("unidades.html", unidades=unidades_list, categorias=categorias)


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
        "deuda_inicial": float(deuda_ini) if deuda_ini else 0.0,
    }
    for cat in categorias:
        key = f"pct_{cat['nombre']}"
        val = request.form.get(key, "0").strip()
        try:
            data[key] = float(val) if val else 0.0
        except ValueError:
            data[key] = 0.0

    if not data["numero"]:
        flash("El número de unidad es obligatorio.", "danger")
        return redirect(url_for("unidades"))

    db.save_unidad(data)
    flash("Unidad guardada.", "success")
    return redirect(url_for("unidades"))


@app.route("/unidades/delete/<numero>", methods=["POST"])
def delete_unidad(numero):
    db.delete_unidad(numero)
    flash("Unidad eliminada.", "success")
    return redirect(url_for("unidades"))


# ---------------------------------------------------------------------------
# GASTOS MENSUALES
# ---------------------------------------------------------------------------

def _recalcular_liq_si_posible(periodo):
    """Genera o recalcula la liquidación del período, salvo que haya pagos registrados."""
    liq = db.get_liquidacion(periodo)
    pagados = [r for r in liq if r.get("tipo_pago") in ("TOTAL", "PARCIAL")]
    if pagados:
        flash("Gasto guardado. Hay pagos registrados — recalculá manualmente con el botón Generar.", "warning")
    else:
        db.generar_liquidacion(periodo)
        flash("Gasto guardado. Liquidación actualizada.", "success")


@app.route("/gastos")
@app.route("/gastos/<periodo>")
def gastos(periodo=None):
    if not periodo:
        periodo = _periodo_actual()
    db.ensure_fondo_reserva_gasto(periodo)  # Agregar automáticamente si no existe
    gastos_list = db.get_gastos(periodo)
    total = db.get_total_gastos(periodo)
    return render_template("gastos.html", gastos=gastos_list, periodo=periodo, total=total)


@app.route("/gastos/save", methods=["POST"])
def save_gasto():
    periodo = request.form.get("periodo", _periodo_actual())
    concepto = request.form.get("concepto", "").strip()
    importe = request.form.get("importe", "0")
    tipo = request.form.get("tipo", "FIJO")
    row_num = request.form.get("row_num")

    try:
        importe = float(importe.replace(",", "."))
    except ValueError:
        importe = 0.0

    if not concepto:
        flash("El concepto es obligatorio.", "danger")
        return redirect(url_for("gastos", periodo=periodo))

    db.save_gasto(periodo, concepto, importe, tipo, int(row_num) if row_num else None)
    _recalcular_liq_si_posible(periodo)
    return redirect(url_for("gastos", periodo=periodo))


@app.route("/gastos/delete/<int:row_num>/<periodo>", methods=["POST"])
def delete_gasto(row_num, periodo):
    db.delete_gasto(row_num)
    _recalcular_liq_si_posible(periodo)
    return redirect(url_for("gastos", periodo=periodo))


# ---------------------------------------------------------------------------
# CAJA DIARIA
# ---------------------------------------------------------------------------

@app.route("/caja")
@app.route("/caja/<periodo>")
def caja(periodo=None):
    if not periodo:
        periodo = _periodo_actual()
    movimientos = db.get_caja(periodo)
    entradas = sum(m["importe"] for m in movimientos if m["tipo"] == "ENTRADA")
    salidas = sum(m["importe"] for m in movimientos if m["tipo"] == "SALIDA")
    saldo = entradas - salidas
    return render_template("caja.html",
                           movimientos=movimientos,
                           periodo=periodo,
                           entradas=entradas,
                           salidas=salidas,
                           saldo=saldo)


@app.route("/caja/save", methods=["POST"])
def save_movimiento():
    periodo = request.form.get("periodo", _periodo_actual())
    fecha = request.form.get("fecha", "")
    descripcion = request.form.get("descripcion", "").strip()
    tipo = request.form.get("tipo", "ENTRADA")
    categoria = request.form.get("categoria", "").strip()
    importe = request.form.get("importe", "0")
    row_num = request.form.get("row_num")

    try:
        importe = float(importe.replace(",", "."))
    except ValueError:
        importe = 0.0

    if not fecha or not descripcion:
        flash("Fecha y descripción son obligatorios.", "danger")
        return redirect(url_for("caja", periodo=periodo))

    db.save_movimiento(fecha, descripcion, tipo, categoria, importe,
                       int(row_num) if row_num else None)
    flash("Movimiento guardado.", "success")
    return redirect(url_for("caja", periodo=periodo))


@app.route("/caja/delete/<int:row_num>/<periodo>", methods=["POST"])
def delete_movimiento(row_num, periodo):
    db.delete_movimiento(row_num)
    flash("Movimiento eliminado.", "success")
    return redirect(url_for("caja", periodo=periodo))


# ---------------------------------------------------------------------------
# LIQUIDACIÓN
# ---------------------------------------------------------------------------

@app.route("/liquidacion")
@app.route("/liquidacion/<periodo>")
def liquidacion(periodo=None):
    if not periodo:
        periodo = _periodo_actual()
    liq = db.get_liquidacion(periodo)
    gastos = db.get_gastos(periodo)
    total_gastos = db.get_total_gastos(periodo)
    total_a_pagar = sum(r["total_a_pagar"] for r in liq)
    total_deuda = sum(r["deuda_anterior"] for r in liq)
    pendientes = sum(1 for r in liq if r.get("tipo_pago", "PENDIENTE") not in ("TOTAL",))
    total_cobrado = sum(r.get("monto_pagado", 0) for r in liq)
    saldo_caja, _, _ = db.get_saldo_caja()  # balance acumulado total
    entradas, salidas = db.get_movimientos_periodo(periodo)  # solo este mes
    fondo = db.get_fondo_reserva()
    return render_template("liquidacion.html",
                           liq=liq,
                           gastos=gastos,
                           periodo=periodo,
                           total_gastos=total_gastos,
                           total_a_pagar=total_a_pagar,
                           total_deuda=total_deuda,
                           pendientes=pendientes,
                           total_cobrado=total_cobrado,
                           saldo_caja=saldo_caja,
                           entradas_caja=entradas,
                           salidas_caja=salidas,
                           fondo_reserva=fondo)


@app.route("/liquidacion/generar/<periodo>", methods=["POST"])
def generar_liquidacion(periodo):
    db.generar_liquidacion(periodo)
    flash(f"Liquidación generada para {periodo}.", "success")
    return redirect(url_for("liquidacion", periodo=periodo))


@app.route("/liquidacion/pagar/<periodo>/<unidad>", methods=["POST"])
def marcar_pagado(periodo, unidad):
    monto_str = request.form.get("monto_pagado", "0").strip().replace(",", ".")
    fecha_pago = request.form.get("fecha_pago") or date.today().strftime("%Y-%m-%d")
    try:
        monto = float(monto_str)
    except ValueError:
        monto = 0.0
    resultado = db.marcar_pagado(periodo, unidad, monto, fecha_pago)
    if resultado:
        tipo = resultado["tipo"]
        if tipo == "PENDIENTE":
            flash(f"Pago de UF {unidad} revertido.", "warning")
        elif tipo == "PARCIAL":
            flash(f"UF {unidad}: pago parcial de ${monto:,.2f}. Saldo pendiente: ${resultado['saldo']:,.2f}.", "warning")
        else:
            flash(f"UF {unidad}: pago total registrado.", "success")
    return redirect(url_for("liquidacion", periodo=periodo))


@app.route("/liquidacion/pdf/<periodo>")
def descargar_pdf(periodo):
    """PDF resumen del edificio completo."""
    liq = db.get_liquidacion(periodo)
    if not liq:
        flash("No hay liquidación generada para este período.", "warning")
        return redirect(url_for("liquidacion", periodo=periodo))
    gastos = db.get_gastos(periodo)
    cfg = db.get_config()
    saldo_caja, _, _ = db.get_saldo_caja()
    fondo = db.get_fondo_reserva()
    pdf_bytes = generar_pdf_resumen_edificio(liq, gastos, cfg, periodo, saldo_caja, fondo)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"resumen_edificio_{periodo}.pdf"
    )


@app.route("/liquidacion/recibo/<periodo>/<unidad>")
def descargar_recibo(periodo, unidad):
    """Recibo de pago individual por unidad."""
    liq = db.get_liquidacion(periodo)
    row = next((r for r in liq if str(r["unidad"]) == str(unidad)), None)
    if not row or row.get("tipo_pago", "PENDIENTE") == "PENDIENTE":
        flash("No hay pago registrado para esta unidad.", "warning")
        return redirect(url_for("liquidacion", periodo=periodo))
    cfg = db.get_config()
    pdf_bytes = generar_recibo_pago(row, cfg, periodo)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"recibo_{unidad}_{periodo}.pdf"
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
    return render_template("proveedores.html", proveedores=lista)


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
    lista = db.get_facturas(estado=estado)
    provs = db.get_proveedores()
    total_pendiente = sum(f["importe"] for f in lista if f["estado"] == "PENDIENTE")
    return render_template("facturas.html", facturas=lista, proveedores=provs,
                           estado_filtro=estado, total_pendiente=total_pendiente)


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
        "importe": float(importe) if importe else 0.0,
        "estado": "PENDIENTE",
        "fecha_pago": None,
        "categoria": request.form.get("categoria", "").strip(),
        "numero_factura": request.form.get("numero_factura", "").strip(),
    }
    if not data["descripcion"] or not data["fecha"]:
        flash("Fecha y descripción son obligatorias.", "danger")
        return redirect(url_for("facturas"))
    db.save_factura(data)
    flash("Factura guardada.", "success")
    return redirect(url_for("facturas"))


@app.route("/facturas/pagar/<int:fid>", methods=["POST"])
def pagar_factura(fid):
    fecha_pago = request.form.get("fecha_pago") or date.today().strftime("%Y-%m-%d")
    ok = db.pagar_factura(fid, fecha_pago)
    if ok:
        periodo = fecha_pago[:7]
        flash("Factura pagada. Se registró en Caja Diaria y Gastos Mensuales.", "success")
        _recalcular_liq_si_posible(periodo)
    else:
        flash("No se encontró la factura.", "danger")
    return redirect(url_for("facturas"))


@app.route("/facturas/delete/<int:fid>", methods=["POST"])
def delete_factura(fid):
    db.delete_factura(fid)
    flash("Factura eliminada.", "success")
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
        "fecha": request.form.get("fecha", date.today().strftime("%Y-%m-%d")),
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
        "fecha": request.form.get("fecha", date.today().strftime("%Y-%m-%d")),
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
# RESET (pruebas)
# ---------------------------------------------------------------------------

@app.route("/config/reset", methods=["POST"])
def reset_datos():
    db.reset_datos_operativos()
    flash("Datos reseteados: liquidaciones, gastos y caja borrados.", "success")
    return redirect(url_for("config"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    db._init_db() if not os.path.exists(db.DB_PATH) else None
    app.run(debug=True, port=5000)
