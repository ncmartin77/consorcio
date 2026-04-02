"""
Generación de PDFs de liquidación con ReportLab.
Formato basado en ejemplo.pdf: una página por unidad.
"""
import io
from datetime import date
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT


def _fmt(val):
    """Formatea número como moneda argentina."""
    try:
        return f"$ {float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "$ 0,00"


def _mes_nombre(periodo: str):
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    try:
        m = int(periodo[5:7])
        y = periodo[:4]
        return f"{meses[m-1]}/{y[-2:]}"
    except Exception:
        return periodo


def generar_pdf_liquidacion(liquidacion_rows: list, gastos: list, config: dict, periodo: str) -> bytes:
    """
    Genera un PDF con una página por unidad funcional.
    Retorna bytes del PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle("title", fontSize=13, fontName="Helvetica-Bold",
                                 alignment=TA_CENTER, spaceAfter=4)
    style_subtitle = ParagraphStyle("subtitle", fontSize=10, fontName="Helvetica-Bold",
                                    alignment=TA_CENTER, spaceAfter=2)
    style_normal = ParagraphStyle("normal", fontSize=9, fontName="Helvetica",
                                  alignment=TA_LEFT, spaceAfter=2)
    style_small = ParagraphStyle("small", fontSize=8, fontName="Helvetica",
                                 alignment=TA_LEFT, spaceAfter=1)
    style_center = ParagraphStyle("center", fontSize=9, fontName="Helvetica",
                                  alignment=TA_CENTER)
    style_right = ParagraphStyle("right", fontSize=9, fontName="Helvetica",
                                 alignment=TA_RIGHT)

    edificio = config.get("edificio_nombre", "EDIFICIO")
    direccion = config.get("edificio_direccion", "")
    alias = config.get("alias_cbu", "")
    titular = config.get("titular_cuenta", "")
    admin = config.get("administrador", "")
    telefono = config.get("telefono", "")
    email = config.get("email", "")
    whatsapp = config.get("whatsapp", "")
    dia_venc = config.get("dia_vencimiento", "15")
    total_gastos = sum(g["importe"] for g in gastos)
    mes_nombre = _mes_nombre(periodo)
    año = periodo[:4]
    mes_num = int(periodo[5:7])
    # Fecha de vencimiento: dia_vencimiento del mes siguiente
    next_mes = mes_num + 1 if mes_num < 12 else 1
    next_año = int(año) if mes_num < 12 else int(año) + 1
    fecha_venc = f"{dia_venc}/{next_mes:02d}/{next_año}"

    story = []

    for idx, row in enumerate(liquidacion_rows):
        ocupante = row.get("inquilino") or row.get("propietario") or ""
        unidad_num = row["unidad"]
        descripcion = row.get("descripcion", "")

        # ---- CABECERA ----
        story.append(Paragraph(edificio.upper(), style_title))
        if direccion:
            story.append(Paragraph(direccion, style_subtitle))
        story.append(Spacer(1, 0.2 * cm))

        # Período y totales
        header_data = [
            ["PERÍODO", "TOTAL GASTOS EDIFICIO", "VENCIMIENTO"],
            [mes_nombre.upper(), _fmt(total_gastos), fecha_venc],
        ]
        header_table = Table(header_data, colWidths=[5 * cm, 8 * cm, 5 * cm])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, 1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, 1), [colors.HexColor("#e8f0fe")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.3 * cm))

        # ---- DATOS DE LA UNIDAD ----
        unit_data = [
            ["DEPTO.", "UNIDAD", "PROPIETARIO / INQUILINO", "% U.F."],
            [descripcion, str(unidad_num), ocupante.upper(), f"{row['pct_aplicado']:.2f}%"],
        ]
        unit_table = Table(unit_data, colWidths=[3 * cm, 3 * cm, 9 * cm, 3 * cm])
        unit_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e6da4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, 1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, 1), [colors.HexColor("#dce8f8")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(unit_table)
        story.append(Spacer(1, 0.3 * cm))

        # ---- TABLA DE IMPORTES ----
        importe_data = [
            ["EXPENSAS", "DEUDA ANTERIOR", "INTERÉS MORA", "TOTAL A PAGAR"],
            [
                _fmt(row["expensas"]),
                _fmt(row["deuda_anterior"]) if row["deuda_anterior"] else "-",
                _fmt(row["interes"]) if row["interes"] else "-",
                _fmt(row["total_a_pagar"]),
            ],
        ]
        importe_table = Table(importe_data, colWidths=[4.5 * cm, 4.5 * cm, 4.5 * cm, 4.5 * cm])
        importe_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a5c")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 1), (-1, 1), 11),
            ("TEXTCOLOR", (3, 1), (3, 1), colors.HexColor("#c00000")),
            ("ROWBACKGROUNDS", (0, 1), (-1, 1), [colors.HexColor("#fff3cd")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(importe_table)
        story.append(Spacer(1, 0.4 * cm))

        # ---- DETALLE DE GASTOS ----
        story.append(Paragraph("DETALLE DE GASTOS DEL MES", ParagraphStyle(
            "det", fontSize=9, fontName="Helvetica-Bold",
            alignment=TA_CENTER, spaceAfter=3,
            textColor=colors.HexColor("#1a3a5c"))))

        gasto_data = [["Concepto", "Importe", "Tipo"]]
        for g in gastos:
            gasto_data.append([g["concepto"], _fmt(g["importe"]), g.get("tipo", "")])
        gasto_data.append(["TOTAL", _fmt(total_gastos), ""])

        col_widths = [11 * cm, 4 * cm, 3 * cm]
        gasto_table = Table(gasto_data, colWidths=col_widths)
        gasto_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2e6da4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f0fe")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (0, -1), 5),
        ]))
        story.append(gasto_table)
        story.append(Spacer(1, 0.4 * cm))

        # ---- DATOS DE PAGO ----
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a3a5c")))
        story.append(Spacer(1, 0.2 * cm))

        pago_lines = [f"<b>VENCIMIENTO:</b> {fecha_venc}"]
        if alias:
            pago_lines.append(f"<b>Alias CBU:</b> {alias}")
        if titular:
            pago_lines.append(f"<b>Titular:</b> {titular}")
        if admin:
            pago_lines.append(f"<b>Administración:</b> {admin}")
        if telefono:
            pago_lines.append(f"<b>Tel:</b> {telefono}")
        if email:
            pago_lines.append(f"<b>Email:</b> {email}")
        if whatsapp:
            pago_lines.append(f"<b>WhatsApp:</b> {whatsapp}")

        pago_text = "  |  ".join(pago_lines)
        story.append(Paragraph(pago_text, ParagraphStyle(
            "pago", fontSize=8, fontName="Helvetica",
            alignment=TA_CENTER, spaceAfter=2)))

        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph(
            f"Estado: {'✓ PAGADO' if row.get('pagado') else 'PENDIENTE DE PAGO'}",
            ParagraphStyle("estado", fontSize=9, fontName="Helvetica-Bold",
                           alignment=TA_CENTER,
                           textColor=colors.HexColor("#006400") if row.get("pagado") else colors.HexColor("#c00000"))
        ))

        # Salto de página entre unidades (menos la última)
        if idx < len(liquidacion_rows) - 1:
            story.append(PageBreak())

    doc.build(story)
    return buffer.getvalue()


def generar_pdf_resumen_edificio(liquidacion_rows: list, gastos: list, config: dict,
                                  periodo: str, saldo_caja: float, fondo_reserva: float) -> bytes:
    """
    PDF único de resumen para el edificio:
    - Tabla de todas las unidades (UF, %, expensas, deuda, total, estado)
    - Detalle de gastos del mes
    - Saldo en caja y fondo de reserva
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=1.2*cm, leftMargin=1.2*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    c_azul = colors.HexColor("#1a3a5c")
    c_verde = colors.HexColor("#155724")
    c_rojo = colors.HexColor("#c00000")

    def st(name, **kw):
        return ParagraphStyle(name, **{"fontName": "Helvetica", "fontSize": 9, **kw})

    edificio = config.get("edificio_nombre", "EDIFICIO")
    mes_nombre = _mes_nombre(periodo).upper()
    total_gastos = sum(g["importe"] for g in gastos)
    total_a_cobrar = sum(r["total_a_pagar"] for r in liquidacion_rows)
    total_cobrado = sum(r.get("monto_pagado", 0) for r in liquidacion_rows)
    total_pendiente = sum(r["total_a_pagar"] for r in liquidacion_rows if not r["pagado"] and r.get("tipo_pago") != "PARCIAL") + \
                      sum(r.get("saldo_pendiente", 0) for r in liquidacion_rows if r.get("tipo_pago") == "PARCIAL")

    story = []

    # Encabezado
    story.append(Paragraph(edificio.upper(), st("tit", fontSize=14, fontName="Helvetica-Bold",
                                                 alignment=TA_CENTER, textColor=c_azul)))
    story.append(Paragraph(f"LIQUIDACIÓN DE EXPENSAS — {mes_nombre}",
                            st("sub", fontSize=10, fontName="Helvetica-Bold",
                               alignment=TA_CENTER, textColor=c_azul, spaceAfter=6)))
    story.append(HRFlowable(width="100%", thickness=2, color=c_azul))
    story.append(Spacer(1, 0.3*cm))

    # Resumen financiero en 4 cajas
    res_data = [
        ["TOTAL GASTOS", "TOTAL A COBRAR", "COBRADO", "PENDIENTE"],
        [_fmt(total_gastos), _fmt(total_a_cobrar), _fmt(total_cobrado), _fmt(total_pendiente)],
    ]
    res_t = Table(res_data, colWidths=[4.5*cm]*4)
    res_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), c_azul), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,0), 8),
        ("FONTNAME", (0,1), (-1,1), "Helvetica-Bold"), ("FONTSIZE", (0,1), (-1,1), 10),
        ("TEXTCOLOR", (3,1), (3,1), c_rojo),
        ("ALIGN", (0,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0,1), (-1,1), [colors.HexColor("#e8f0fe")]),
        ("GRID", (0,0), (-1,-1), 0.4, colors.grey),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(res_t)
    story.append(Spacer(1, 0.4*cm))

    # Tabla de unidades
    story.append(Paragraph("DETALLE POR UNIDAD FUNCIONAL",
                            st("h", fontSize=9, fontName="Helvetica-Bold", textColor=c_azul,
                               spaceAfter=4)))
    uf_header = ["UF", "Descripción", "Prop./Inquilino", "%", "Expensas", "Deuda", "Total", "Pagado", "Saldo"]
    uf_data = [uf_header]
    for r in liquidacion_rows:
        ocupante = r.get("inquilino") or r.get("propietario") or "—"
        tipo = r.get("tipo_pago", "PENDIENTE")
        if tipo == "TOTAL":
            est = "TOTAL"
            saldo_display = "—"
        elif tipo == "PARCIAL":
            est = "PARCIAL"
            saldo_display = _fmt(r.get("saldo_pendiente", 0))
        else:
            est = "—"
            saldo_display = _fmt(r["total_a_pagar"])  # aún no pagó nada → debe el total
        monto_p = r.get("monto_pagado", 0)
        uf_data.append([
            str(r["unidad"]),
            r["descripcion"][:18],
            ocupante[:20],
            f"{r['pct_aplicado']:.3f}%",
            _fmt(r["expensas"]),
            _fmt(r["deuda_anterior"]) if r["deuda_anterior"] else "—",
            _fmt(r["total_a_pagar"]),
            est,
            saldo_display,
        ])
    # Fila totales
    uf_data.append(["TOTAL", "", "", "100%",
                    _fmt(total_gastos), "", _fmt(total_a_cobrar),
                    _fmt(total_cobrado), _fmt(total_pendiente)])

    # A4 ancho útil = 21 - 2*1.2 = 18.6 cm → repartir entre 9 cols
    col_w = [0.9*cm, 2.8*cm, 2.8*cm, 1.5*cm, 2.0*cm, 1.8*cm, 2.0*cm, 1.8*cm, 1.9*cm]  # = 17.5 cm
    uf_t = Table(uf_data, colWidths=col_w, repeatRows=1)
    n = len(uf_data)
    uf_t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2e6da4")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7),
        ("FONTNAME", (0,n-1), (-1,n-1), "Helvetica-Bold"),
        ("BACKGROUND", (0,n-1), (-1,n-1), colors.HexColor("#dce8f8")),
        ("ROWBACKGROUNDS", (0,1), (-1,n-2), [colors.white, colors.HexColor("#f5f5f5")]),
        ("ALIGN", (3,0), (-1,-1), "RIGHT"), ("ALIGN", (7,0), (7,-1), "CENTER"),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(uf_t)
    story.append(Spacer(1, 0.5*cm))

    # Detalle de gastos + caja en dos columnas
    gasto_data = [["Concepto", "Tipo", "Importe"]]
    for g in gastos:
        gasto_data.append([g["concepto"], g.get("tipo",""), _fmt(g["importe"])])
    gasto_data.append(["TOTAL GASTOS", "", _fmt(total_gastos)])

    gt = Table(gasto_data, colWidths=[6.5*cm, 2.0*cm, 2.5*cm])  # = 11.0 cm
    ng = len(gasto_data)
    gt.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2e6da4")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
        ("FONTNAME", (0,ng-1), (-1,ng-1), "Helvetica-Bold"),
        ("BACKGROUND", (0,ng-1), (-1,ng-1), colors.HexColor("#e8f0fe")),
        ("ROWBACKGROUNDS", (0,1), (-1,ng-2), [colors.white, colors.HexColor("#f5f5f5")]),
        ("ALIGN", (2,0), (2,-1), "RIGHT"),
        ("GRID", (0,0), (-1,-1), 0.3, colors.grey),
        ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ("LEFTPADDING", (0,0), (-1,-1), 4),
    ]))

    caja_data = [
        ["ESTADO FINANCIERO"],
        ["Saldo en Caja", _fmt(saldo_caja)],
        ["Fondo de Reserva (*)", _fmt(fondo_reserva)],
        ["(*) pendiente de cobro", ""],
    ]
    ct = Table(caja_data, colWidths=[3.8*cm, 3.4*cm])  # = 7.2 cm
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), c_verde), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("SPAN", (0,0), (-1,0)), ("ALIGN", (0,0), (-1,0), "CENTER"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
        ("FONTNAME", (0,1), (-1,1), "Helvetica-Bold"),
        ("BACKGROUND", (0,1), (-1,1), colors.HexColor("#d4edda")),
        ("ROWBACKGROUNDS", (0,2), (-1,2), [colors.HexColor("#f0fff0")]),
        ("SPAN", (0,3), (1,3)), ("FONTSIZE", (0,3), (1,3), 6),
        ("TEXTCOLOR", (0,3), (1,3), colors.grey),
        ("ALIGN", (1,1), (1,2), "RIGHT"),
        ("GRID", (0,0), (-1,2), 0.3, colors.grey),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
    ]))

    combo = Table([[gt, ct]], colWidths=[11.1*cm, 7.4*cm])  # = 18.5 cm
    combo.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (1,0), (1,0), 8),
    ]))
    story.append(combo)

    doc.build(story)
    return buffer.getvalue()


def generar_recibo_pago(row: dict, config: dict, periodo: str) -> bytes:
    """Recibo de pago para una unidad: A5 apaisado (o mitad de A4)."""
    buffer = io.BytesIO()
    from reportlab.lib.pagesizes import A5
    W, H = A5
    doc = SimpleDocTemplate(buffer, pagesize=(W, H),
                            rightMargin=1*cm, leftMargin=1*cm,
                            topMargin=1*cm, bottomMargin=1*cm)

    c_azul = colors.HexColor("#1a3a5c")
    c_verde = colors.HexColor("#155724")
    c_rojo = colors.HexColor("#c00000")

    def st(name, **kw):
        return ParagraphStyle(name, **{"fontName": "Helvetica", "fontSize": 9, **kw})

    edificio = config.get("edificio_nombre", "EDIFICIO")
    mes_nombre = _mes_nombre(periodo).upper()
    ocupante = row.get("inquilino") or row.get("propietario") or "—"
    tipo_pago = row.get("tipo_pago", "TOTAL")
    monto = row.get("monto_pagado", row["total_a_pagar"])
    saldo = row.get("saldo_pendiente", 0)
    fecha_p = row.get("fecha_pago") or date.today().strftime("%Y-%m-%d")
    # Formatear fecha
    try:
        from datetime import datetime as _dt
        fd = _dt.strptime(str(fecha_p), "%Y-%m-%d")
        fecha_fmt = fd.strftime("%d/%m/%Y")
    except Exception:
        fecha_fmt = str(fecha_p)

    story = []
    story.append(Paragraph(edificio.upper(),
                            st("t", fontSize=12, fontName="Helvetica-Bold",
                               alignment=TA_CENTER, textColor=c_azul)))
    story.append(Paragraph(f"RECIBO DE PAGO — {mes_nombre}",
                            st("s", fontSize=9, fontName="Helvetica-Bold",
                               alignment=TA_CENTER, textColor=c_azul, spaceAfter=4)))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_azul))
    story.append(Spacer(1, 0.25*cm))

    detalle = [
        ["Unidad:", f"{row['unidad']} — {row['descripcion']}",
         "Fecha pago:", fecha_fmt],
        ["Prop./Inquilino:", ocupante, "Período:", mes_nombre],
    ]
    dt = Table(detalle, colWidths=[2.5*cm, 5.5*cm, 2.5*cm, 3*cm])
    dt.setStyle(TableStyle([
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("FONTNAME", (0,0), (0,-1), "Helvetica-Bold"),
        ("FONTNAME", (2,0), (2,-1), "Helvetica-Bold"),
        ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
    ]))
    story.append(dt)
    story.append(Spacer(1, 0.3*cm))

    # Importes
    imp_data = [
        ["Expensas del mes", "Deuda anterior", "Total a pagar", "MONTO ABONADO", "SALDO RESTANTE"],
        [_fmt(row["expensas"]),
         _fmt(row["deuda_anterior"]) if row["deuda_anterior"] else "—",
         _fmt(row["total_a_pagar"]),
         _fmt(monto),
         _fmt(saldo) if saldo > 0 else "—"],
    ]
    it = Table(imp_data, colWidths=[2.8*cm]*5)
    it.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), c_azul), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 8),
        ("FONTNAME", (3,1), (3,1), "Helvetica-Bold"), ("FONTSIZE", (3,1), (3,1), 10),
        ("TEXTCOLOR", (3,1), (3,1), c_verde),
        ("TEXTCOLOR", (4,1), (4,1), c_rojo if saldo > 0 else c_verde),
        ("FONTNAME", (4,1), (4,1), "Helvetica-Bold"),
        ("BACKGROUND", (3,1), (3,1), colors.HexColor("#d4edda")),
        ("BACKGROUND", (4,1), (4,1), colors.HexColor("#fff3cd") if saldo > 0 else colors.HexColor("#d4edda")),
        ("ROWBACKGROUNDS", (0,1), (2,1), [colors.HexColor("#e8f0fe")]),
        ("ALIGN", (0,0), (-1,-1), "CENTER"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("GRID", (0,0), (-1,-1), 0.4, colors.grey),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(it)
    story.append(Spacer(1, 0.25*cm))

    # Badge tipo pago
    color_badge = c_verde if tipo_pago == "TOTAL" else colors.HexColor("#856404")
    story.append(Paragraph(
        f"Pago: <b>{tipo_pago}</b>",
        st("tp", fontSize=10, fontName="Helvetica-Bold",
           alignment=TA_CENTER, textColor=color_badge)))

    # Datos de contacto
    story.append(Spacer(1, 0.25*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    partes = []
    admin = config.get("administrador")
    tel = config.get("telefono")
    email = config.get("email")
    if admin: partes.append(f"Admin: {admin}")
    if tel: partes.append(f"Tel: {tel}")
    if email: partes.append(f"Email: {email}")
    if partes:
        story.append(Paragraph("  |  ".join(partes),
                                st("ct", fontSize=7, alignment=TA_CENTER,
                                   textColor=colors.grey, spaceAfter=0)))

    doc.build(story)
    return buffer.getvalue()
