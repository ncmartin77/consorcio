"""
Prueba de "Anular pago" y de la fecha de pago con fecha del sistema (v6.4) contra la base de PRUEBA.

1. Con fecha fijada, los formularios proponen la fecha del sistema.
2. Anular el pago de una unidad: la fila queda sin pago y se borra su entrada en Caja.
3. Anular todos los pagos del período.
4. Pagar con fecha fijada: el pago queda con esa fecha (fila y Caja) y cuenta en la vista.
5. Restaurar: se revierten todas las operaciones desde el Log de Movimientos (prueba que
   la anulación se puede deshacer) y se compara con el estado inicial.
Uso: probar_anular_pagos.py [periodo] [fecha]   (por defecto 2026-10 y 2026-10-06)
"""
import sys

from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
PERIODO = sys.argv[1] if len(sys.argv) > 1 else "2026-10"
FECHA = sys.argv[2] if len(sys.argv) > 2 else "2026-10-06"
admin_email = db.get_usuario(1)["email"]


def filas():
    return {str(r["unidad"]): (r["tipo_pago"], r["monto_pagado"], r["fecha_pago"], r["interes"], r["total_a_pagar"])
            for r in db.get_liquidacion(PERIODO, simular=False)}


def caja_expensas():
    return sorted((str(r["fecha"]), r["descripcion"], float(r["importe"])) for r in db._fetchall(
        "SELECT fecha, descripcion, importe FROM caja WHERE consorcio_id=%s AND categoria='Expensas' "
        "AND descripcion LIKE %s", (cid, f"Expensas {PERIODO} - %")))


fecha0 = db.get_config().get("fecha_simulada", "")
inicio_audit = db._fetchone("SELECT COALESCE(MAX(id),0) AS m FROM audit_log")["m"]
f0, c0 = filas(), caja_expensas()
con_pago = [u for u, v in f0.items() if (v[1] or 0) > 0]
print(f"{PERIODO}: {len(con_pago)} unidades con pago, {len(c0)} entradas de Caja 'Expensas {PERIODO}'")
assert con_pago, "No hay pagos para probar"
u1 = con_pago[0]

try:
    cliente.post("/config/fecha-sistema", data={"fecha_sistema": FECHA})
    h = cliente.get(f"/liquidacion/{PERIODO}").get_data(as_text=True)
    print(f"\n[1] Fecha fijada {FECHA}: formularios proponen esa fecha:", f"'{FECHA}'" in h,
          "| botón 'Anular todos los pagos':", "Anular todos los pagos" in h,
          "| botones por unidad:", h.count("Anular pago (solo admin)"))
    h2 = cliente.get("/caja").get_data(as_text=True)
    print("    Caja propone la fecha fijada:", f"'{FECHA}'" in h2)

    r = cliente.post(f"/liquidacion/{PERIODO}/anular-pagos", data={"unidad": u1}, follow_redirects=True)
    f1, c1 = filas(), caja_expensas()
    print(f"\n[2] Anular UF {u1}: fila {f0[u1][:3]} → {f1[u1][:3]} | Caja {len(c0)} → {len(c1)} | "
          f"otras unidades intactas: {all(f1[u] == f0[u] for u in f0 if u != u1)}")

    cliente.post(f"/liquidacion/{PERIODO}/anular-pagos", follow_redirects=True)
    f2, c2 = filas(), caja_expensas()
    print(f"[3] Anular todos: unidades con pago {sum(1 for v in f2.values() if (v[1] or 0) > 0)} | Caja {len(c2)}")

    total = f2[u1][4]
    cliente.post(f"/liquidacion/pagar/{PERIODO}/{u1}", data={"monto_pagado": str(total)})  # sin fecha: usa la del sistema
    f3, c3 = filas(), caja_expensas()
    vista = next(r for r in db.get_liquidacion(PERIODO) if str(r["unidad"]) == u1)
    print(f"[4] Pagar UF {u1} sin indicar fecha: fecha_pago={f3[u1][2]} | Caja: {c3} | en la vista: {vista['tipo_pago']}")
finally:
    cliente.post("/config/fecha-sistema", data=({"fecha_sistema": fecha0} if fecha0 else {"accion": "quitar"}))
    ops = db._fetchall("SELECT op_id, MAX(id) AS ult FROM audit_log WHERE id > %s AND consorcio_id=%s "
                       "AND revertida_en IS NULL AND (descripcion LIKE 'Liquidación:%%') "
                       "GROUP BY op_id ORDER BY ult DESC", (inicio_audit, cid))
    for o in ops:
        ok, msg = db.revertir_operacion(o["op_id"], admin_email)
        print("  revertir:", ok, msg)
    print(f"\n[5] Restaurado desde el Log de Movimientos: liquidación igual al inicio: {filas() == f0} | "
          f"Caja igual: {caja_expensas() == c0} | fecha: {db.get_config().get('fecha_simulada')!r}")
