"""
v9.0/v9.1 — Cobranzas separada de Liquidación, contra la base de PRUEBA.
v9.2: el interés se decide al CERRAR la liquidación, con un switch por unidad
(tasa × deuda anterior); mientras está abierta y en Cobranzas no hay interés.

Crea un consorcio de prueba aislado ("Prueba v9 cobranzas", 3 UF) y recorre el ciclo:
liquidación abierta → cierre (desde el 1° del mes) → cobro sobre la última cerrada →
deuda anterior / interés al vencimiento en la siguiente → fecha del sistema fijada →
anulaciones, bloqueo de Caja, reapertura, recibos, PDF, Log de Movimientos y migración de
pagos viejos. Al final borra el consorcio de prueba.
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
c = db.create_consorcio("Prueba v9 cobranzas", "temporal: pruebas/probar_cobranzas.py")
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


def fila(periodo, uf, simular=True):
    return next(r for r in db.get_liquidacion(periodo, simular=simular) if str(r["unidad"]) == str(uf))


def pagar(periodo, uf, monto, f, **extra):
    r = cliente.post(f"/cobranzas/{periodo}/pagar/{uf}", data={"monto_pagado": monto, "fecha_pago": f, **extra})
    return r


def flashes():
    with cliente.session_transaction() as s:
        msgs = [m for _, m in s.get("_flashes", [])]
        s.pop("_flashes", None)
    return " | ".join(msgs)


try:
    db.save_config({"edificio_nombre": "Prueba v9", "tasa_mora": "10", "dia_vencimiento": "10",
                    "fondo_reserva_mensual": "0"})
    db.add_categoria("EXPENSAS")
    for num, pct, deuda in (("1", 50, 100), ("2", 30, 0), ("3", 20, -50)):
        db.save_unidad({"numero": num, "descripcion": f"Depto {num}", "propietario": f"Prop {num}",
                        "deuda_inicial": deuda, "pct_EXPENSAS": pct})
    db.save_gasto("2026-07", "Limpieza", 1000, "FIJO")
    db.save_gasto("2026-08", "Limpieza", 2000, "FIJO")

    # ── 1. Liquidación abierta ───────────────────────────────────────────────
    fecha("2026-07-20")
    cliente.post("/liquidacion/generar/2026-08")
    tot = {str(r["unidad"]): r["total_a_pagar"] for r in db.get_liquidacion("2026-08")}
    check("L08 generada (deuda de apertura, sin interés el 1er mes)", "{1: 600, 2: 300, 3: 150}",
          tot, tot == {"1": 600.0, "2": 300.0, "3": 150.0})
    r = db.registrar_pago("2026-08", "1", 100, "2026-07-20")
    check("Pagar sobre liquidación ABIERTA", "rechazado", r.get("error", "aceptado"), "abierta" in r.get("error", ""))
    cliente.post("/liquidacion/cerrar/2026-08")
    check("Cerrar L08 con fecha 20/07 (no cambió el mes)", "sigue ABIERTA",
          db.get_liq_estado("2026-08") + " — " + flashes(), db.get_liq_estado("2026-08") == "ABIERTA")
    h = cliente.get("/liquidacion/2026-08").get_data(as_text=True)
    check("Pantalla Liquidación sin botones de pago", "sin modalPago / Pago Completo",
          "ok" if "modalPago" not in h and "Pago Completo" not in h else "tiene", "modalPago" not in h)

    # ── 2. Cierre y cobro ────────────────────────────────────────────────────
    fecha("2026-08-01")
    h = cliente.get("/liquidacion/2026-08").get_data(as_text=True)
    check("Ventana de cierre L08: unidades con deuda anterior", "solo UF 1 (deuda 100, interés 10)",
          h.count('name="interes_uf"'), h.count('name="interes_uf"') == 1 and 'data-interes="10.0"' in h)
    cliente.post("/liquidacion/cerrar/2026-08", data={"interes_uf": ["1"]})
    fc = db._fetchone("SELECT fecha_cierre FROM liquidaciones_estado WHERE consorcio_id=%s AND periodo='2026-08'",
                      (CID,))["fecha_cierre"]
    check("Cerrar L08 con fecha 01/08", "CERRADA, fecha de cierre 01/08",
          f"{db.get_liq_estado('2026-08')} {fc}", db.get_liq_estado("2026-08") == "CERRADA" and str(fc) == "2026-08-01")
    check("Periodo en cobro", "2026-08", db.periodo_cobranza(), db.periodo_cobranza() == "2026-08")
    f1 = fila("2026-08", "1")
    check("Cerrar con interés para UF 1", "interés 10 % × 100 = 10, total 610", f"{f1['interes']} / {f1['total_a_pagar']}",
          f1["interes"] == 10 and f1["total_a_pagar"] == 610)
    r = db.registrar_pago("2026-08", "1", 600, "2026-08-05")
    check("Pago con fecha posterior a la fecha del sistema (05/08 con hoy 01/08)", "rechazado",
          r.get("error", "aceptado")[:60], "posterior a la fecha del sistema" in r.get("error", ""))
    fecha("2026-08-05"); pagar("2026-08", "1", 610, "2026-08-05"); flashes()
    fecha("2026-08-08"); pagar("2026-08", "2", 100, "2026-08-08"); flashes()
    fecha("2026-08-20"); pagar("2026-08", "2", 200, "2026-08-20", bonificacion="5", bonif_motivo="redondeo"); flashes()
    fecha("2026-08-25"); pagar("2026-08", "1", 50, "2026-08-25"); flashes()
    ip = sum(p["interes"] for u in "123" for p in db.get_pagos("2026-08", u))
    check("Pagar después del vencimiento (UF 2, 20/08)", "Cobranzas no cobra interés", ip, ip == 0)
    est = {u: (fila("2026-08", u)["tipo_pago"], fila("2026-08", u)["monto_pagado"]) for u in "123"}
    check("Estado de L08 tras los pagos", "1 TOTAL 660 / 2 TOTAL 300 / 3 PENDIENTE 0",
          est, est == {"1": ("TOTAL", 660.0), "2": ("TOTAL", 300.0), "3": ("PENDIENTE", 0.0)})
    check("UF 1 pagó de más", "saldo a favor 50", -fila("2026-08", "1")["saldo_pendiente"],
          fila("2026-08", "1")["saldo_pendiente"] == -50)
    n_pagos = len(db.get_pagos("2026-08"))
    caja = db._fetchall("SELECT tipo, categoria, importe FROM caja WHERE consorcio_id=%s ORDER BY id", (CID,))
    cats = [x["categoria"] for x in caja]
    check("Pagos y Caja", "4 pagos, 4 entradas Expensas + 1 bonificación, sin Intereses",
          f"{n_pagos} pagos, {cats.count('Expensas')} entradas, {cats.count('BONIFICACION')} bonif., "
          f"{cats.count('Intereses')} interés",
          n_pagos == 4 and cats.count("Expensas") == 4 and cats.count("BONIFICACION") == 1 and cats.count("Intereses") == 0)
    r = db.registrar_pago("2026-08", "3", 10, "2026-07-31")
    check("Pago con fecha en una Caja cerrada (julio, L08 cerrada)", "rechazado",
          r.get("error", "aceptado")[:60], "Caja de 2026-07" in r.get("error", ""))

    # ── 3. Liquidación siguiente: deuda anterior, sin interés (v9.1) ─────────
    cliente.post("/liquidacion/generar/2026-09")
    l9 = {u: (fila("2026-09", u)["deuda_anterior"], fila("2026-09", u)["interes"], fila("2026-09", u)["total_a_pagar"])
          for u in "123"}
    esperado = {"1": (-50.0, 0.0, 950.0), "2": (0.0, 0.0, 600.0), "3": (150.0, 0.0, 550.0)}
    check("L09 abierta: deuda / interés / total (abierta: sin interés)", esperado, l9, l9 == esperado)
    h = cliente.get("/liquidacion/2026-09").get_data(as_text=True)
    check("Pantalla Liquidación sin columna ni switch de interés", "sin chk-sin-interes / toggleTodosInteres",
          "ok" if "chk-sin-interes" not in h and "toggleTodosInteres" not in h else "tiene",
          "chk-sin-interes" not in h and "toggleTodosInteres" not in h)
    r = db.registrar_pago("2026-09", "1", 10, "2026-08-25")
    check("Pagar sobre L09 abierta", "rechazado", r.get("error", "aceptado")[:50], bool(r.get("error")))

    # ── 4. Fecha del sistema fijada antes de algunos pagos ───────────────────
    fecha("2026-08-15")
    f2 = fila("2026-08", "2")
    check("Fecha 15/08: L08 UF 2 no cuenta el pago del 20/08", "PARCIAL 100, pagó el 20/08",
          f"{f2['tipo_pago']} {f2['monto_pagado']} {f2.get('pago_posterior')}",
          f2["tipo_pago"] == "PARCIAL" and f2["monto_pagado"] == 100 and f2.get("pago_posterior", {}).get("fecha") == "2026-08-20")
    l9s = {u: (fila("2026-09", u)["deuda_anterior"], fila("2026-09", u)["interes"]) for u in "12"}
    check("Fecha 15/08: L09 se recalcula a esa fecha", "UF1 deuda 0 / UF2 deuda 200, sin interés",
          l9s, l9s == {"1": (0.0, 0.0), "2": (200.0, 0.0)})
    h = cliente.get("/cobranzas").get_data(as_text=True)
    check("Cobranzas: fecha por defecto = fecha del sistema", 'value="2026-08-15"', "ok" if 'value="2026-08-15"' in h else "no",
          'value="2026-08-15"' in h)
    fecha("2026-08-25")
    check("Vuelta a 25/08: L09 UF 2", "deuda 0, total 600", fila("2026-09", "2")["total_a_pagar"],
          fila("2026-09", "2")["total_a_pagar"] == 600)
    h = cliente.get("/cobranzas").get_data(as_text=True)
    check("Cobranzas sin interés (ni switch ni columna)", "sin cobrar_interes / si paga hoy",
          "ok" if "cobrar_interes" not in h and "si paga hoy" not in h else "tiene",
          "cobrar_interes" not in h and "si paga hoy" not in h)

    # ── 5. Anular un pago (admin) ────────────────────────────────────────────
    p_20 = next(p for p in db.get_pagos("2026-08", "2") if p["fecha"] == "2026-08-20")
    cliente.post("/cobranzas/2026-08/anular", data={"pago_id": p_20["id"]}); flashes()
    queda = db._fetchone("SELECT COUNT(*) AS n FROM caja WHERE consorcio_id=%s AND id = ANY(%s)",
                         (CID, [p_20["caja_id"], p_20["bonif_caja_id"], p_20["interes_caja_id"]]))["n"]
    check("Anular el pago del 20/08 de UF 2", "se borra pago + entrada + bonificación + interés; L09 UF2 deuda 200",
          f"caja restante {queda}, deuda {fila('2026-09', '2')['deuda_anterior']}",
          queda == 0 and fila("2026-09", "2")["deuda_anterior"] == 200)
    pagar("2026-08", "2", 200, "2026-08-20"); flashes()

    # ── 6. Log de Movimientos: revertir el registro de un pago ───────────────
    op = db._fetchone("SELECT op_id FROM audit_log WHERE tabla='pagos' AND accion='INSERT' "
                      "AND datos_despues->>'consorcio_id'=%s ORDER BY id DESC LIMIT 1", (CID,))["op_id"]
    db.revertir_operacion(op, "pruebas")
    check("Revertir desde el Log el último pago", "UF 2 vuelve a deber 200 en L09",
          fila("2026-09", "2")["deuda_anterior"], fila("2026-09", "2")["deuda_anterior"] == 200)
    pagar("2026-08", "2", 200, "2026-08-20"); flashes()

    # ── 7. Cierre de L09 y cambio de liquidación en cobro ────────────────────
    cliente.post("/liquidacion/cerrar/2026-09")
    check("Cerrar L09 el 25/08", "rechazado (desde el 01/09)", db.get_liq_estado("2026-09"),
          db.get_liq_estado("2026-09") == "ABIERTA")
    flashes()
    fecha("2026-09-02")
    prop = [(p["unidad"], p["deuda"], p["interes"]) for p in db.propuesta_intereses(db.get_liquidacion("2026-09"))]
    check("Propuesta de interés al cerrar L09", "solo UF 3: deuda 150, interés 15 (UF 1 a favor, UF 2 sin deuda)",
          prop, prop == [("3", 150.0, 15.0)])
    cliente.post("/liquidacion/cerrar/2026-09", data={"interes_uf": ["3"]}); flashes()
    l9c = {u: (fila("2026-09", u)["interes"], fila("2026-09", u)["total_a_pagar"]) for u in "123"}
    check("L09 cerrada con interés para UF 3", "UF3 15 → total 565; UF1/UF2 sin interés",
          l9c, l9c == {"1": (0.0, 950.0), "2": (0.0, 600.0), "3": (15.0, 565.0)})
    h = cliente.get("/liquidacion/2026-09").get_data(as_text=True)
    check("Liquidación cerrada muestra la columna Interés", "columna con $ 15,00",
          "ok" if ">Interés</th>" in h and "15,00" in h else "no", ">Interés</th>" in h and "15,00" in h)
    check("Cerrar L09 el 02/09", "CERRADA, en cobro 2026-09", f"{db.get_liq_estado('2026-09')} {db.periodo_cobranza()}",
          db.get_liq_estado("2026-09") == "CERRADA" and db.periodo_cobranza() == "2026-09")
    fecha("2026-09-05")
    r = db.registrar_pago("2026-08", "3", 10, "2026-09-02")
    check("Pagar sobre L08 (ya no es la última cerrada)", "rechazado", r.get("error", "aceptado")[:60], bool(r.get("error")))
    r = db.registrar_pago("2026-09", "3", 100, "2026-08-31")
    check("Pago a L09 con fecha de agosto (Caja de agosto cerrada)", "rechazado", r.get("error", "aceptado")[:50],
          "Caja de 2026-08" in r.get("error", ""))
    pagar("2026-09", "3", 565, "2026-09-03"); flashes()
    check("Pago a L09 el 03/09", "UF 3 TOTAL", fila("2026-09", "3")["tipo_pago"], fila("2026-09", "3")["tipo_pago"] == "TOTAL")

    # ── 8. Reapertura ────────────────────────────────────────────────────────
    cliente.post("/liquidacion/reabrir/2026-09")
    check("Reabrir L09 con pagos", "rechazado", db.get_liq_estado("2026-09") + " — " + flashes(),
          db.get_liq_estado("2026-09") == "CERRADA")
    cliente.post("/liquidacion/reabrir/2026-08")
    check("Reabrir L08 con L09 cerrada", "rechazado", db.get_liq_estado("2026-08"), db.get_liq_estado("2026-08") == "CERRADA")
    flashes()

    # ── 9. Caja: editar / borrar el cobro de un pago ─────────────────────────
    p3 = db.get_pagos("2026-09", "3")[0]
    cliente.post("/caja/save", data={"periodo": "2026-09", "row_num": p3["caja_id"], "fecha": "2026-09-04",
                                     "descripcion": "Expensas 2026-09 - Prop 3 - UF 3", "tipo": "ENTRADA",
                                     "categoria": "Expensas", "importe": "500"}); flashes()
    p3b = db.get_pagos("2026-09", "3")[0]
    check("Editar en Caja el cobro de UF 3 (500, 04/09)", "el pago acompaña: 500 el 04/09, PARCIAL",
          f"{p3b['monto']} {p3b['fecha']} {fila('2026-09', '3')['tipo_pago']}",
          p3b["monto"] == 500 and p3b["fecha"] == "2026-09-04" and fila("2026-09", "3")["tipo_pago"] == "PARCIAL")
    cliente.post(f"/caja/delete/{p3['caja_id']}/2026-09"); flashes()
    check("Borrar en Caja el cobro de UF 3", "se borra el pago", len(db.get_pagos("2026-09", "3")),
          len(db.get_pagos("2026-09", "3")) == 0)
    p8 = db.get_pagos("2026-08", "1")[0]
    ok = db.delete_movimiento(p8["caja_id"])
    check("Borrar en Caja un cobro de agosto (Caja cerrada)", "bloqueado", ok, ok is False)

    # ── 10. Pago completo, libre deuda, pantallas y PDFs ─────────────────────
    cliente.post("/cobranzas/2026-09/pagar-todo", data={"fecha_pago": "2026-09-05"}); flashes()
    cob = {u: fila("2026-09", u)["monto_pagado"] for u in "123"}
    check("Pago completo de L09 cobra el total (con el interés de UF 3)", "950 / 600 / 565",
          cob, cob == {"1": 950.0, "2": 600.0, "3": 565.0})
    est = {u: fila("2026-09", u)["tipo_pago"] for u in "123"}
    check("Pago completo de L09", "todas TOTAL", est, set(est.values()) == {"TOTAL"})
    ld = db.get_estado_libre_deuda()
    check("Libre deuda según la última cerrada (L09)", "las 3 libres, período 2026-09",
          {u: (v["libre"], v["periodo"]) for u, v in ld.items()},
          all(v["libre"] and v["periodo"] == "2026-09" for v in ld.values()))
    codigos = {
        "/cobranzas": cliente.get("/cobranzas").status_code,
        "/cobranzas/2026-08 (consulta)": cliente.get("/cobranzas/2026-08").status_code,
        "/liquidacion/2026-09": cliente.get("/liquidacion/2026-09").status_code,
        "/caja/2026-09": cliente.get("/caja/2026-09").status_code,
        "recibo UF 1": cliente.get("/liquidacion/recibo/2026-09/1").status_code,
        "recibo UF 3 (con interés)": cliente.get("/liquidacion/recibo/2026-09/3").status_code,
        "PDF resumen L08 (con interés)": cliente.get("/liquidacion/pdf/2026-08").status_code,
        "PDF resumen": cliente.get("/liquidacion/pdf/2026-09").status_code,
        "/plano/2026-09": cliente.get("/plano/2026-09").status_code,
        "/unidades": cliente.get("/unidades").status_code,
    }
    check("Pantallas y PDFs", "200 en todas", codigos, set(codigos.values()) == {200})
    h = cliente.get("/cobranzas/2026-08").get_data(as_text=True)
    check("Cobranzas de L08 (no es la última)", "solo consulta, sin botón de pago",
          "ok" if "Solo consulta" in h and "abrirModalPago({" not in h else "no",
          "Solo consulta" in h and "abrirModalPago({" not in h)

    # ── 11. Migración de pagos viejos (filas de liquidaciones → tabla pagos) ─
    db._exec("""INSERT INTO liquidaciones (consorcio_id, periodo, unidad, expensas, deuda_anterior, interes,
                total_a_pagar, pagado, monto_pagado, tipo_pago, saldo_pendiente, fecha_pago)
                VALUES (%s,'2026-05','1',300,0,0,300,TRUE,300,'TOTAL',0,'2026-05-07')""", (CID,))
    db.save_movimiento("2026-05-03", "Expensas 2026-05 - Prop 1 - UF 1 (PARCIAL)", "ENTRADA", "Expensas", 200)
    db.save_movimiento("2026-05-07", "Bonificación UF 1 2026-05 - viejo", "SALIDA", "BONIFICACION", 10)
    db.save_config({"pagos_migrados": ""})
    db._pagos_migrados.discard(CID)
    n = db.migrar_pagos_legacy()
    pm = db.get_pagos("2026-05", "1")
    check("Migración de un pago viejo (200 en Caja + 100 sin entrada, bonificación)",
          "2 pagos: 200 vinculado a Caja + 100; bonificación 10 en el primero",
          [(p["monto"], bool(p["caja_id"]), p["bonificacion"]) for p in pm],
          n == 2 and [(p["monto"], bool(p["caja_id"]), p["bonificacion"]) for p in pm] == [(200.0, True, 10.0), (100.0, False, 0.0)])
    n2 = db.migrar_pagos_legacy()
    check("Migración idempotente", "0 la segunda vez", n2, n2 == 0)
finally:
    db.delete_consorcio(CID)
    print("Consorcio de prueba borrado:", CID)

print()
print("| Caso | Esperado | Resultado |")
print("|---|---|---|")
for caso, esperado, obtenido, ok in resultados:
    print(f"| {caso} | {esperado} | {'✅' if ok else '❌ ' + str(obtenido)} |")
print(f"\n{sum(1 for r in resultados if r[3])}/{len(resultados)} OK")
