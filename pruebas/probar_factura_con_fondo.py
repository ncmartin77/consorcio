"""
Prueba de "Pagar factura con Fondo de Reserva" (v9.3) contra la base de PRUEBA.

Una factura pagada con el fondo:
  - queda PAGADA con categoría FONDO_RESERVA y sale de la Caja (categoría FONDO_RESERVA);
  - genera un gasto VARIABLE_FR, que NO entra en la liquidación (total de gastos sin cambios);
  - si es de un gasto recurrente (ya cargado al guardarla), ese gasto pasa a VARIABLE_FR sin duplicarse.
Control: la misma factura pagada sin el fondo sí suma al total de gastos.
Deja la base como estaba (borra facturas, caja y gastos de prueba y regenera la liquidación).
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
HOY = db.fecha_sistema().strftime("%Y-%m-%d")
MES = HOY[:7]
LIQ = db._next_periodo(MES)
TAG = "PRUEBA_FONDO_v93"
ok_total, fallas = 0, []


def chk(caso, esperado, real):
    global ok_total
    if esperado == real:
        ok_total += 1
        print(f"  OK  {caso}: {real}")
    else:
        fallas.append(caso)
        print(f"  MAL {caso}: esperado {esperado!r}, real {real!r}")


def nueva_factura(desc, importe):
    return db.save_factura({"fecha": HOY, "proveedor_nombre": TAG, "descripcion": desc,
                            "importe": importe, "categoria": "", "numero_factura": TAG})


def gastos_de(desc):
    return [g for g in db.get_gastos(MES) if g["concepto"] == desc]


def caja_de(fid):
    return db._fetchall("SELECT categoria, tipo, importe FROM caja WHERE consorcio_id=%s AND factura_id=%s",
                        (cid, fid))


print(f"Fecha del sistema {HOY} · gastos {MES} → liquidación {LIQ} "
      f"({'CERRADA' if db.liq_esta_cerrada(LIQ) else 'abierta'})")
total0 = db.get_total_gastos(MES)
facturas, gasto_rec_id = [], None
try:
    # 1) Pantalla
    html = cliente.get("/facturas").get_data(as_text=True)
    chk("Modal muestra el switch", True, "Pagar con Fondo de Reserva" in html)

    # 2) Factura común pagada con el fondo
    desc1 = f"{TAG} reparación bomba"
    f1 = nueva_factura(desc1, 12345.67); facturas.append(f1)
    r = cliente.post(f"/facturas/pagar/{f1}", data={"fecha_pago": HOY, "con_fondo": "1"})
    chk("Respuesta redirect", 302, r.status_code)
    fac = db.get_factura_by_id(f1)
    chk("Factura PAGADA", "PAGADA", fac["estado"])
    chk("Factura categoría", "FONDO_RESERVA", fac["categoria"])
    chk("Caja: salida con categoría FONDO_RESERVA",
        [("FONDO_RESERVA", "SALIDA", 12345.67)],
        [(c["categoria"], c["tipo"], float(c["importe"])) for c in caja_de(f1)])
    chk("Gasto creado VARIABLE_FR", ["VARIABLE_FR"], [g["tipo"] for g in gastos_de(desc1)])
    chk("Total de gastos de la liquidación sin cambios", total0, db.get_total_gastos(MES))
    chk("Desglose: aparece en 'con fondo'", True,
        any(g["concepto"] == desc1 for g in db.get_desglose_gastos(MES)["extra_fondo"]))

    # 3) Control: factura pagada sin el fondo suma al total
    desc2 = f"{TAG} control sin fondo"
    f2 = nueva_factura(desc2, 1000.00); facturas.append(f2)
    cliente.post(f"/facturas/pagar/{f2}", data={"fecha_pago": HOY})
    chk("Control: gasto ordinario", ["FIJO"], [g["tipo"] for g in gastos_de(desc2)])
    chk("Control: total sube 1000", round(total0 + 1000, 2), round(db.get_total_gastos(MES), 2))

    # 4) Gasto recurrente pagado con el fondo: no se duplica, pasa a VARIABLE_FR
    desc3 = f"{TAG} recurrente"
    gasto_rec_id = db._insert_returning(
        "INSERT INTO gastos_recurrentes (consorcio_id, concepto, categoria) VALUES (%s,%s,%s) RETURNING id",
        (cid, desc3, "FIJO"))
    f3 = nueva_factura(desc3, 500.00); facturas.append(f3)
    chk("Recurrente: gasto ordinario al guardar", ["FIJO"], [g["tipo"] for g in gastos_de(desc3)])
    cliente.post(f"/facturas/pagar/{f3}", data={"fecha_pago": HOY, "con_fondo": "1"})
    chk("Recurrente: un solo gasto, VARIABLE_FR", ["VARIABLE_FR"], [g["tipo"] for g in gastos_de(desc3)])
    chk("Total = inicial + control", round(total0 + 1000, 2), round(db.get_total_gastos(MES), 2))
finally:
    for fid in facturas:
        db._exec("DELETE FROM caja WHERE factura_id=%s AND consorcio_id=%s", (fid, cid))
        db._exec("DELETE FROM facturas WHERE id=%s AND consorcio_id=%s", (fid, cid))
    db._exec("DELETE FROM gastos WHERE consorcio_id=%s AND concepto LIKE %s", (cid, TAG + "%"))
    if gasto_rec_id:
        db._exec("DELETE FROM gastos_recurrentes WHERE id=%s AND consorcio_id=%s", (gasto_rec_id, cid))
    if not db.liq_esta_cerrada(LIQ):
        db.generar_liquidacion(LIQ)
    chk("Limpieza: total de gastos como al inicio", total0, db.get_total_gastos(MES))

print(f"\n{ok_total} OK, {len(fallas)} con falla" + (f": {fallas}" if fallas else ""))
