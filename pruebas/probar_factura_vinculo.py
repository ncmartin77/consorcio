"""
Prueba del vínculo gasto ↔ factura y de la observación del pago (v9.4) contra la base de PRUEBA.

1. Pagar una factura crea su gasto vinculado (gastos.factura_id) y guarda la observación.
2. Borrar la factura deja el gasto sin vínculo y Gastos Mensuales ofrece emitir su factura.
3. Emitir la factura desde ese gasto la vincula; pagarla NO duplica el gasto.
4. Borrar el pago en Caja (factura vuelve a PENDIENTE) y volver a pagar NO duplica el gasto.
5. Recurrente: borrar la factura y emitirla de nuevo reutiliza el gasto que quedó.
Deja la base como estaba.
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
HOY = db.fecha_sistema().strftime("%Y-%m-%d")
MES = HOY[:7]
LIQ = db._next_periodo(MES)
TAG = "PRUEBA_VINCULO_v94"
ok_total, fallas = 0, []


def chk(caso, esperado, real):
    global ok_total
    if esperado == real:
        ok_total += 1
        print(f"  OK  {caso}: {real}")
    else:
        fallas.append(caso)
        print(f"  MAL {caso}: esperado {esperado!r}, real {real!r}")


def gastos_de(desc):
    return [g for g in db.get_gastos(MES) if g["concepto"] == desc]


def factura_por_desc(desc):
    r = db._fetchone("SELECT id FROM facturas WHERE consorcio_id=%s AND descripcion=%s ORDER BY id DESC LIMIT 1",
                     (cid, desc))
    return r["id"] if r else None


print(f"Fecha del sistema {HOY} · gastos {MES} → liquidación {LIQ} "
      f"({'CERRADA' if db.liq_esta_cerrada(LIQ) else 'abierta'})")
cliente.get("/facturas")  # before_request: columnas nuevas + vínculo de gastos viejos
total0 = db.get_total_gastos(MES)
gasto_rec_id = None
try:
    # 1) Pagar crea el gasto vinculado + observación
    desc = f"{TAG} ascensor"
    cliente.post("/facturas/save", data={"fecha": HOY, "proveedor_nombre": TAG, "descripcion": desc,
                                         "importe": "2500", "numero_factura": TAG})
    f1 = factura_por_desc(desc)
    cliente.post(f"/facturas/pagar/{f1}", data={"fecha_pago": HOY, "observacion": "Transferencia op. 123"})
    g = gastos_de(desc)
    chk("Pago: un gasto vinculado a la factura", [(f1, "PAGADA")], [(x["factura_id"], x["factura_estado"]) for x in g])
    chk("Observación guardada", "Transferencia op. 123", db.get_factura_by_id(f1)["observacion"])
    chk("Observación visible en Facturas", True, "Transferencia op. 123" in cliente.get("/facturas").get_data(as_text=True))
    chk("Total sube 2500", round(total0 + 2500, 2), round(db.get_total_gastos(MES), 2))

    # 2) Borrar la factura: el gasto queda sin vínculo y se puede emitir de nuevo
    cliente.post(f"/facturas/delete/{f1}")
    g = gastos_de(desc)
    chk("Borrada: queda el gasto, sin factura", [None], [x["factura_id"] for x in g])
    html = cliente.get(f"/gastos/{MES}").get_data(as_text=True)
    chk("Gastos Mensuales ofrece emitir factura", True,
        f'"row": {g[0]["row"]}' in html and "Emitir factura de este gasto" in html)

    # 3) Emitir desde el gasto y pagar: no se duplica
    cliente.post("/facturas/save", data={"fecha": HOY, "proveedor_nombre": TAG, "descripcion": desc,
                                         "importe": "2500", "numero_factura": TAG, "gasto_id": g[0]["row"]})
    f2 = factura_por_desc(desc)
    chk("Factura nueva vinculada al gasto", [f2], [x["factura_id"] for x in gastos_de(desc)])
    cliente.post(f"/facturas/pagar/{f2}", data={"fecha_pago": HOY})
    chk("Pagada: sigue un solo gasto", 1, len(gastos_de(desc)))
    chk("Total sin duplicar (+2500)", round(total0 + 2500, 2), round(db.get_total_gastos(MES), 2))

    # 4) Borrar el pago en Caja y volver a pagar: no se duplica
    caja = db._fetchone("SELECT id FROM caja WHERE consorcio_id=%s AND factura_id=%s", (cid, f2))
    cliente.post(f"/caja/delete/{caja['id']}/{MES}")
    chk("Pago borrado: factura PENDIENTE", "PENDIENTE", db.get_factura_by_id(f2)["estado"])
    cliente.post(f"/facturas/pagar/{f2}", data={"fecha_pago": HOY})
    chk("Repagada: sigue un solo gasto", 1, len(gastos_de(desc)))
    chk("Total sin duplicar (+2500) tras repagar", round(total0 + 2500, 2), round(db.get_total_gastos(MES), 2))

    # 5) Recurrente: borrar y volver a emitir reutiliza el gasto
    desc_r = f"{TAG} recurrente"
    gasto_rec_id = db._insert_returning(
        "INSERT INTO gastos_recurrentes (consorcio_id, concepto, categoria) VALUES (%s,%s,%s) RETURNING id",
        (cid, desc_r, "FIJO"))
    cliente.post("/facturas/save", data={"fecha": HOY, "proveedor_nombre": TAG, "descripcion": desc_r,
                                         "importe": "700", "numero_factura": TAG})
    f3 = factura_por_desc(desc_r)
    chk("Recurrente: gasto vinculado al guardar", [f3], [x["factura_id"] for x in gastos_de(desc_r)])
    cliente.post(f"/facturas/delete/{f3}")
    cliente.post("/facturas/save", data={"fecha": HOY, "proveedor_nombre": TAG, "descripcion": desc_r,
                                         "importe": "700", "numero_factura": TAG})
    f4 = factura_por_desc(desc_r)
    chk("Recurrente re-emitida: reutiliza el gasto", [f4], [x["factura_id"] for x in gastos_de(desc_r)])
    cliente.post(f"/facturas/pagar/{f4}", data={"fecha_pago": HOY})
    chk("Recurrente pagada: un solo gasto", 1, len(gastos_de(desc_r)))
finally:
    ids = [r["id"] for r in db._fetchall("SELECT id FROM facturas WHERE consorcio_id=%s AND numero_factura=%s",
                                         (cid, TAG))]
    for fid in ids:
        db._exec("DELETE FROM caja WHERE factura_id=%s AND consorcio_id=%s", (fid, cid))
        db._exec("DELETE FROM facturas WHERE id=%s AND consorcio_id=%s", (fid, cid))
    db._exec("DELETE FROM gastos WHERE consorcio_id=%s AND concepto LIKE %s", (cid, TAG + "%"))
    if gasto_rec_id:
        db._exec("DELETE FROM gastos_recurrentes WHERE id=%s AND consorcio_id=%s", (gasto_rec_id, cid))
    if not db.liq_esta_cerrada(LIQ):
        db.generar_liquidacion(LIQ)
    chk("Limpieza: total de gastos como al inicio", total0, db.get_total_gastos(MES))

print(f"\n{ok_total} OK, {len(fallas)} con falla" + (f": {fallas}" if fallas else ""))
