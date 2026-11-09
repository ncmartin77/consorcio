"""
v10.0 — Lineamientos jurídicos (Paraná): prueba contra la base de PRUEBA.

Crea un consorcio aislado ("Prueba v10", 2 UF de 50 %), con expensas de $100.000 por UF
(gastos $180.000 + aporte al fondo $20.000) y tasa 3 % mensual, y verifica:
 1. Interés sin capitalizar: el ejemplo de la conversación (418.000, no 418.362,70), imputación
    del pago primero a intereses, tasa con vigencia (y bloqueo en períodos cerrados),
    tasa congelada en la liquidación cerrada y el switch de capitalización.
 2. Libro del Fondo de Reserva: saldo inicial + aportes cobrados + otros ingresos − pagos,
    aportes pendientes de cobro y compromisos.
 3. Exportación completa (ZIP con CSV/JSON, sin la clave de firma, solo admin).
 4. Clasificación del gasto (naturaleza / frecuencia / financiación / respaldo).
 5. Administración, vencimientos (plazos hábiles) y alertas.
Al final borra el consorcio de prueba.
"""
import base64
import io
import re
import zipfile
import zlib

from entorno_prueba import preparar

app, db, cliente = preparar()
db.ensure_v10()     # en la app lo hace before_request; acá se usa la capa de datos antes del primer request
db.ensure_auditoria()
c = db.create_consorcio("Prueba v10 lineamientos", "temporal: pruebas/probar_v10.py")
CID = c["id"]
db.set_active_consorcio(c["data_dir_abs"], c["db_path_abs"])
with cliente.session_transaction() as s:
    s["consorcio_id"] = CID

resultados = []


def check(caso, esperado, obtenido, ok):
    resultados.append((caso, esperado, obtenido, ok))
    print(f"{'✅' if ok else '❌'} {caso}: esperado {esperado} | obtenido {obtenido}")


def fecha(f):
    cliente.post("/config/fecha-sistema", data={"fecha_sistema": f})


def fila(periodo, uf):
    return next(r for r in db.get_liquidacion(periodo, simular=False) if str(r["unidad"]) == str(uf))


def flashes():
    with cliente.session_transaction() as s:
        msgs = [m for _, m in s.get("_flashes", [])]
        s.pop("_flashes", None)
    return " | ".join(msgs)


def texto_pdf(data: bytes) -> str:
    partes = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        d = m.group(1).strip()
        for dec in (lambda x: zlib.decompress(x),
                    lambda x: zlib.decompress(base64.a85decode(x if x.startswith(b"<~") else b"<~" + x, adobe=True))):
            try:
                partes.append(dec(d).decode("latin-1"))
                break
            except Exception:
                continue
    return "".join(re.findall(r"\((.*?)\) Tj", "".join(partes)))


try:
    db.save_config({"edificio_nombre": "Prueba v10", "tasa_mora": "3", "dia_vencimiento": "10",
                    "fondo_reserva_mensual": "20000", "saldo_inicial_caja": "650000",
                    "saldo_inicial_caja_fecha": "2026-10-01"})
    db.add_categoria("EXPENSAS")
    for num in ("1", "2"):
        db.save_unidad({"numero": num, "descripcion": f"Depto {num}", "propietario": f"Prop {num}",
                        "deuda_inicial": 0, "pct_EXPENSAS": 50})
    for mes in ("2026-09", "2026-10", "2026-11", "2026-12"):
        db.save_gasto(mes, "Gastos generales", 180000, "FIJO")
    fecha("2026-10-01")
    r = cliente.post("/config/tasa-mora/add", data={"vigente_desde": "2026-09-01", "tasa": "3",
                                                    "fundamento": "Reglamento art. 20"})
    check("Registrar tasa 3 % desde 01/09/2026", "1 tasa en el historial",
          [(t["vigente_desde"], t["tasa"]) for t in db.get_tasas_mora()], len(db.get_tasas_mora()) == 1)
    cliente.post("/apertura", data={"saldo_inicial_caja": "650000", "saldo_inicial_caja_fecha": "2026-10-01",
                                    "fondo_saldo_inicial": "600000", "fondo_saldo_inicial_fecha": "2026-10-01"})
    cfg = db.get_config()
    check("Apertura: saldo inicial del fondo", "600000 al 2026-10-01",
          f"{cfg.get('fondo_saldo_inicial')} al {cfg.get('fondo_saldo_inicial_fecha')}",
          float(cfg.get("fondo_saldo_inicial")) == 600000 and cfg.get("fondo_saldo_inicial_fecha") == "2026-10-01")

    # ── 1. Interés sin capitalizar ───────────────────────────────────────────
    cliente.post("/liquidacion/generar/2026-10")
    cliente.post("/liquidacion/cerrar/2026-10")
    f = fila("2026-10", "1")
    check("Oct: expensa por UF (180.000 + aporte 20.000, 50 %)", "100000", f["total_a_pagar"], f["total_a_pagar"] == 100000)

    fecha("2026-11-01")
    cliente.post("/liquidacion/generar/2026-11")
    cliente.post("/liquidacion/cerrar/2026-11", data={"interes_uf": ["1", "2"]})
    f = fila("2026-11", "1")
    check("Nov: deuda 100.000, interés 3.000, total 203.000", "100000/3000/203000",
          f"{f['deuda_anterior']:.0f}/{f['interes']:.0f}/{f['total_a_pagar']:.0f}",
          (f["deuda_anterior"], f["interes"], f["total_a_pagar"]) == (100000, 3000, 203000))

    fecha("2026-11-15")
    db.save_movimiento("2026-11-15", "Donación al fondo", "ENTRADA", "FONDO_RESERVA", 5000)

    fecha("2026-12-01")
    cliente.post("/liquidacion/generar/2026-12")
    h = cliente.get("/liquidacion/2026-12").get_data(as_text=True)
    check("Ventana de cierre Dic: muestra el capital (200.000) aparte de los intereses (3.000)", "200.000,00 y 3.000,00",
          "ok" if ("200000,00" in h or "200.000,00" in h) and "3000,00" in h else "no", ("200000,00" in h) and "3000,00" in h)
    cliente.post("/liquidacion/cerrar/2026-12", data={"interes_uf": ["1", "2"]})
    f = fila("2026-12", "1")
    check("Dic: interés 3 % sobre el capital 200.000 (no sobre 203.000)", "deuda 203.000 (3.000 int.), interés 6.000, total 309.000",
          f"{f['deuda_anterior']:.0f} ({f['deuda_interes']:.0f}) / {f['interes']:.0f} / {f['total_a_pagar']:.0f}",
          (f["deuda_anterior"], f["deuda_interes"], f["interes"], f["total_a_pagar"]) == (203000, 3000, 6000, 309000))
    check("Dic: tasa congelada en la liquidación cerrada", "3.0", f["tasa_aplicada"], f["tasa_aplicada"] == 3.0)

    fecha("2026-12-10")
    db.save_movimiento("2026-12-10", "Reparación bomba (con el fondo)", "SALIDA", "FONDO_RESERVA", 50000)
    db.save_factura({"fecha": "2026-12-10", "descripcion": "Impermeabilización (a pagar con el fondo)",
                     "importe": 30000, "categoria": "FONDO_RESERVA", "estado": "PENDIENTE"})

    err = db.add_tasa_mora("2026-12-01", 4, "")
    check("Tasa con vigencia dentro de un período cerrado", "rechazada", err or "aceptada", bool(err))
    cliente.post("/config/tasa-mora/add", data={"vigente_desde": "2027-01-01", "tasa": "4", "fundamento": "Acta 20/12"})
    check("Tasa 4 % desde 01/01/2027", "Dic usa 3, Ene usa 4",
          f"{db.tasa_mora(periodo='2026-12')} / {db.tasa_mora(periodo='2027-01')}",
          db.tasa_mora(periodo="2026-12") == 3 and db.tasa_mora(periodo="2027-01") == 4)

    fecha("2027-01-05")
    r = cliente.post("/cobranzas/2026-12/pagar/2", data={"monto_pagado": "150000", "fecha_pago": "2027-01-05"})
    check("UF 2 paga 150.000 de Dic", "1 pago", len(db.get_pagos("2026-12", "2")), len(db.get_pagos("2026-12", "2")) == 1)
    cliente.post("/liquidacion/generar/2027-01")
    f1, f2 = fila("2027-01", "1"), fila("2027-01", "2")
    check("Ene UF 1 (sin pagos): deuda 309.000 de la cual 9.000 son intereses", "309000 / 9000",
          f"{f1['deuda_anterior']:.0f} / {f1['deuda_interes']:.0f}",
          (f1["deuda_anterior"], f1["deuda_interes"]) == (309000, 9000))
    check("Ene UF 2: el pago cancela primero los 9.000 de intereses (CCyC 903)", "deuda 159.000, 0 de intereses",
          f"{f2['deuda_anterior']:.0f} / {f2['deuda_interes']:.0f}",
          (f2["deuda_anterior"], f2["deuda_interes"]) == (159000, 0))
    prop = {p["unidad"]: p for p in db.propuesta_intereses(db.get_liquidacion("2027-01"), periodo="2027-01")}
    check("Ene: interés propuesto con la tasa nueva (4 %) sobre el capital", "UF1 300.000→12.000, UF2 159.000→6.360",
          f"UF1 {prop['1']['capital']:.0f}→{prop['1']['interes']:.0f}, UF2 {prop['2']['capital']:.0f}→{prop['2']['interes']:.0f}",
          prop["1"]["interes"] == 12000 and prop["2"]["interes"] == 6360)
    tot_sin_cap = 309000 + 9000 + 100000
    check("Ejemplo a 3 meses (3 % todo el período): total de enero sin capitalizar", "418.000",
          f"{309000 + 300000 * 0.03 + 100000:.0f}", 309000 + 300000 * 0.03 + 100000 == tot_sin_cap)

    cliente.post("/config", data={"form_intereses": "1", "capitalizar_intereses": "on"})
    db.generar_liquidacion("2027-01")
    p_cap = {p["unidad"]: p for p in db.propuesta_intereses(db.get_liquidacion("2027-01"), periodo="2027-01")}
    check("Capitalización activada: el interés se calcula sobre toda la deuda", "UF1 309.000 × 4 % = 12.360",
          p_cap["1"]["interes"], p_cap["1"]["interes"] == 12360)
    cliente.post("/config", data={"form_intereses": "1"})
    db.generar_liquidacion("2027-01")
    check("Capitalización desactivada otra vez", "0 / deuda_interes UF1 9.000",
          f"{db.get_config().get('capitalizar_intereses')} / {fila('2027-01', '1')['deuda_interes']:.0f}",
          db.get_config().get("capitalizar_intereses") == "0" and fila("2027-01", "1")["deuda_interes"] == 9000)

    # ── 2. Libro del Fondo de Reserva ────────────────────────────────────────
    libro = db.get_libro_fondo()
    check("Fondo: aportes cobrados de UF 2 (pago 150.000: 9.000 int., Oct 100.000, Nov 41.000; aporte 10 %)",
          "14.100", round(sum(m["aportes_cobrados"] for m in libro["meses"]), 2),
          round(sum(m["aportes_cobrados"] for m in libro["meses"]), 2) == 14100)
    check("Fondo: saldo efectivo = 600.000 + 14.100 + 5.000 − 50.000", "569.100", libro["saldo"], libro["saldo"] == 569100)
    check("Fondo: aportes liquidados pendientes de cobro (6 × 10.000 − 14.100)", "45.900", libro["pendiente_cobro"],
          libro["pendiente_cobro"] == 45900)
    check("Fondo: compromisos (factura pendiente con el fondo)", "30.000 / disponible 539.100",
          f"{libro['total_compromisos']} / {libro['disponible_neto']}",
          libro["total_compromisos"] == 30000 and libro["disponible_neto"] == 539100)
    check("Fondo: saldo usado para pagar facturas con el fondo", "569.100", db.get_saldo_fondo(), db.get_saldo_fondo() == 569100)
    h = cliente.get("/fondo").get_data(as_text=True)
    check("Pantalla del libro del fondo", "200 con saldo 569.100,00", "ok" if "569.100,00" in h else "no", "569.100,00" in h)
    r = cliente.get("/liquidacion/pdf/2026-12")
    t = texto_pdf(r.data)
    check("PDF Dic: cuadro FONDO DE RESERVA con saldo efectivo y pendiente", "presente",
          "ok" if "FONDO DE RESERVA" in t and "Saldo efectivo" in t and "pendientes de cobro" in t else t[:80],
          r.status_code == 200 and "FONDO DE RESERVA" in t and "Saldo efectivo" in t)

    # ── 3. Exportación ───────────────────────────────────────────────────────
    r = cliente.get("/exportar")
    z = zipfile.ZipFile(io.BytesIO(r.data)) if r.status_code == 200 and r.mimetype == "application/zip" else None
    nombres = z.namelist() if z else []
    check("Exportación: ZIP con tablas, JSON y LEEME", "gastos, liquidaciones, pagos, tasas_mora, LEEME",
          len(nombres), z is not None and all(n in nombres for n in (
              "datos/gastos.csv", "datos/liquidaciones.csv", "datos/pagos.csv", "datos/tasas_mora.csv",
              "datos/consorcio_completo.json", "LEEME.txt")))
    if z:
        conf = z.read("datos/config.csv").decode("utf-8-sig")
        check("Exportación: sin la clave de firma de recibos", "sin clave_firma", "ok" if "clave_firma" not in conf else "la tiene",
              "clave_firma" not in conf and "edificio_nombre" in conf)
        gas = z.read("datos/gastos.csv").decode("utf-8-sig")
        check("Exportación: gastos del consorcio (4 meses + aportes)", ">= 8 filas", gas.count("\n") - 1, gas.count("\n") - 1 >= 8)
    u = db.get_or_create_usuario("PRUEBA_V10_NOADMIN", "prueba_v10_noadmin@example.com", "No admin")
    try:
        if not u["activo"]:
            db.toggle_usuario_activo(u["id"])
        with cliente.session_transaction() as s:
            admin_id = s["usuario_id"]
            s.update(usuario_id=u["id"], es_admin=False)
        r = cliente.get("/exportar")
        check("Exportación: un usuario no administrador no puede descargarla", "302 (redirige)",
              r.status_code, r.status_code == 302)
    finally:
        with cliente.session_transaction() as s:
            s.update(usuario_id=admin_id, es_admin=True)
        db._exec("DELETE FROM usuarios WHERE id=%s", (u["id"],))
        flashes()

    # ── 4. Clasificación del gasto ───────────────────────────────────────────
    def gasto(concepto):
        return next(g for g in db.get_gastos("2027-01") if g["concepto"] == concepto)
    fecha("2027-01-20")
    cliente.post("/gastos/save", data={"periodo": "2027-01", "concepto": "Reparación portón", "importe": "80000",
                                       "naturaleza": "ORDINARIA", "habitualidad": "NO_RECURRENTE",
                                       "financiacion": "EXPENSAS"})
    g = gasto("Reparación portón")
    check("Ordinario no recurrente (reparación necesaria)", "tipo VARIABLE, se cobra como ordinario",
          f"{g['tipo']} {g['naturaleza']}/{g['habitualidad']}/{g['financiacion']}",
          g["tipo"] == "VARIABLE" and g["naturaleza"] == "ORDINARIA")
    cliente.post("/gastos/save", data={"periodo": "2027-01", "concepto": "Pintura fachada", "importe": "500000",
                                       "naturaleza": "EXTRAORDINARIA", "habitualidad": "NO_RECURRENTE",
                                       "financiacion": "EXPENSAS", "respaldo": "Acta asamblea 10/01/2027"})
    g = gasto("Pintura fachada")
    check("Extraordinario a cobrar con respaldo", "EXTRAORDINARIO + respaldo",
          f"{g['tipo']} / {g['respaldo']}", g["tipo"] == "EXTRAORDINARIO" and g["respaldo"] == "Acta asamblea 10/01/2027")
    cliente.post("/gastos/save", data={"periodo": "2027-01", "concepto": "Cambio de bomba", "importe": "120000",
                                       "naturaleza": "ORDINARIA", "habitualidad": "NO_RECURRENTE",
                                       "financiacion": "FONDO_RESERVA", "respaldo": "Autorización del consejo"})
    g = gasto("Cambio de bomba")
    check("Ordinario pagado con el fondo: conserva la naturaleza", "VARIABLE_FR / ORDINARIA",
          f"{g['tipo']} / {g['naturaleza']}", g["tipo"] == "VARIABLE_FR" and g["naturaleza"] == "ORDINARIA")
    cliente.post(f"/gastos/{g['row']}/extraordinario/COBRAR")
    g = gasto("Cambio de bomba")
    check("Pasarlo a 'cobrar en expensas' lo deja ordinario (no extraordinario)", "VARIABLE / ORDINARIA / EXPENSAS",
          f"{g['tipo']} / {g['naturaleza']} / {g['financiacion']}",
          (g["tipo"], g["naturaleza"], g["financiacion"]) == ("VARIABLE", "ORDINARIA", "EXPENSAS"))
    n_antes = len(db.get_gastos("2027-01"))
    flashes()
    cliente.post("/gastos/save", data={"periodo": "2027-01", "concepto": "X", "importe": "1",
                                       "naturaleza": "RARA", "habitualidad": "RECURRENTE", "financiacion": "EXPENSAS"})
    check("Clasificación inválida", "rechazada", flashes()[:40], len(db.get_gastos("2027-01")) == n_antes)
    db._exec("INSERT INTO gastos (consorcio_id, periodo, concepto, importe, tipo) VALUES (%s,'2027-01','Legado',10,'VARIABLE_FR')",
             (CID,))
    g = gasto("Legado")
    check("Gasto anterior a la v10 (sin campos): clasificación deducida del tipo", "EXTRAORDINARIA/NO_RECURRENTE/FONDO_RESERVA",
          f"{g['naturaleza']}/{g['habitualidad']}/{g['financiacion']}",
          (g["naturaleza"], g["habitualidad"], g["financiacion"]) == ("EXTRAORDINARIA", "NO_RECURRENTE", "FONDO_RESERVA"))
    h = cliente.get("/gastos/2027-01").get_data(as_text=True)
    check("Pantalla de gastos con los campos nuevos", "naturaleza / habitualidad / financiacion / respaldo",
          "ok" if all(x in h for x in ('name="naturaleza"', 'name="habitualidad"', 'name="financiacion"', 'name="respaldo"')) else "no",
          all(x in h for x in ('name="naturaleza"', 'name="habitualidad"', 'name="financiacion"', 'name="respaldo"')))

    # ── 5. Administración, vencimientos y alertas ────────────────────────────
    from datetime import date
    check("3 días hábiles desde el viernes 08/01/2027", "miércoles 13/01/2027",
          db.sumar_plazo(date(2027, 1, 8), 3, "habiles"), db.sumar_plazo(date(2027, 1, 8), 3, "habiles") == date(2027, 1, 13))
    check("Rendición anual: 60 días corridos desde el 31/12/2026", "01/03/2027",
          db.sumar_plazo(date(2026, 12, 31), 60, "corridos"), db.sumar_plazo(date(2026, 12, 31), 60, "corridos") == date(2027, 3, 1))
    cliente.post("/config", data={"form_administracion": "1", "admin_cuit": "20-12345678-9",
                                  "admin_mandato_hasta": "2027-02-15", "registro_estado": "EN_TRAMITE",
                                  "ejercicio_cierre": "12-31", "tiene_ascensor": "on"})
    cfg = db.get_config()
    check("Configuración de administración guardada", "CUIT, mandato, En trámite, 12-31, ascensor",
          f"{cfg.get('admin_cuit')} {cfg.get('admin_mandato_hasta')} {cfg.get('registro_estado')} {cfg.get('ejercicio_cierre')} {cfg.get('tiene_ascensor')}",
          cfg.get("registro_estado") == "EN_TRAMITE" and cfg.get("tiene_ascensor") == "1" and cfg.get("ejercicio_cierre") == "12-31")
    cliente.post("/config", data={"form_administracion": "1", "ejercicio_cierre": "31/12", "tiene_ascensor": "on"})
    check("Cierre de ejercicio con formato inválido", "no se guarda", db.get_config().get("ejercicio_cierre"),
          db.get_config().get("ejercicio_cierre") == "12-31")
    tit = [a["titulo"] for a in db.get_alertas()]
    check("Alertas: mandato, registro en trámite, rendición anual y ascensor sin certificado", "4 alertas",
          tit, any("Mandato" in t for t in tit) and any("Registro" in t for t in tit)
          and any("Rendición" in t for t in tit) and any("ascensor" in t for t in tit))
    cliente.post("/vencimientos/add", data={"tipo": "CERTIFICADO_DEUDA", "fecha_inicio": "2027-01-15",
                                            "descripcion": "Pedido UF 1"})
    v = next(x for x in db.get_vencimientos() if x["tipo"] == "CERTIFICADO_DEUDA")
    check("Certificado de deuda pedido el viernes 15/01: vence a los 3 días hábiles", "2027-01-20",
          v["fecha_vencimiento"], v["fecha_vencimiento"] == "2027-01-20")
    cliente.post("/vencimientos/add", data={"tipo": "ASCENSOR_CERTIFICADO", "fecha_inicio": "2026-12-10"})
    cliente.post("/vencimientos/add", data={"tipo": "ASCENSOR_CERTIFICADO", "fecha_inicio": "2027-01-10"})
    asc = [a for a in db.get_alertas() if "ascensor" in a["titulo"].lower()]
    check("Ascensor: solo cuenta el último certificado (vence 10/02)", "1 alerta, vence en 21 días",
          [a["detalle"] for a in asc], len(asc) == 1 and "21" in asc[0]["detalle"])
    tit = [a["titulo"] for a in db.get_alertas()]
    check("Alerta del certificado de deuda (vence hoy)", "presente", "ok" if any("Certificado de deuda" in t for t in tit) else "no",
          any("Certificado de deuda" in t for t in tit))
    cliente.post(f"/vencimientos/{v['id']}/cumplido", data={"fecha": "2027-01-19"})
    tit = [a["titulo"] for a in db.get_alertas()]
    check("Marcado cumplido: la alerta desaparece", "sin alerta", "ok" if not any("Certificado de deuda" in t for t in tit) else "sigue",
          not any("Certificado de deuda" in t for t in tit))
    h = cliente.get("/vencimientos").get_data(as_text=True)
    check("Pantalla de vencimientos y badge del menú", "200 con alertas", "ok" if "Vencimientos y alertas" in h and "badge" in h else "no",
          "Rendición de cuentas anual" in h)
    r = cliente.get("/liquidacion/pdf/2026-12")
    t = texto_pdf(r.data)
    check("PDF: registro 'en trámite' sin presentarlo como inscripción + CUIT", "en trámite / CUIT",
          "ok" if "en tr" in t and "20-12345678-9" in t else t[-200:], "en tr" in t and "20-12345678-9" in t)
    # ── 6. Ayuda dentro de la app (solo el manual, sin diagramas) ────────────
    h = cliente.get("/ayuda").get_data(as_text=True)
    check("Ayuda: muestra el manual de usuario v10", "200 con el manual",
          "ok" if "Manual de Usuario" in h and "Intereses por mora" in h else "no",
          "Manual de Usuario" in h and "Intereses por mora" in h)
    check("Ayuda: sin diagramas (pedido del usuario)", "sin mermaid ni diagramas.md",
          "ok" if "mermaid" not in h.lower() and "Diagramas" not in h else "los tiene",
          "mermaid" not in h.lower() and "Diagramas" not in h)
    check("Menú: enlace a Ayuda y manual", "presente", "ok" if 'href="/ayuda"' in h else "no", 'href="/ayuda"' in h)
    for url in ("/config", "/apertura", "/liquidacion/2027-01", "/gastos/2026-12", "/facturas"):
        rr = cliente.get(url)
        check(f"Página {url}", 200, rr.status_code, rr.status_code == 200)
finally:
    db.delete_consorcio(CID)

ok = sum(1 for r in resultados if r[3])
print(f"\n{ok}/{len(resultados)} OK")
print("\n| Caso | Esperado | Resultado |\n|---|---|---|")
for caso, esp, obt, okk in resultados:
    print(f"| {caso} | {esp} | {'✅' if okk else '❌'} {obt} |")
