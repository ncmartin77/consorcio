"""
v9.0 — Ensayo de la migración de pagos (filas de liquidaciones → tabla pagos) sobre el
consorcio de prueba (Perú 376 en la base de PRUEBA). Compara, por liquidación y unidad, lo
pagado antes (monto_pagado de la fila) con la suma de los pagos migrados, y cuántos quedaron
vinculados a su entrada de Caja. Muestra también el estado de cada liquidación.
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
antes = {(r["periodo"], str(r["unidad"])): float(r["monto_pagado"]) for r in db._fetchall(
    "SELECT periodo, unidad, monto_pagado FROM liquidaciones WHERE consorcio_id=%s AND COALESCE(monto_pagado,0) > 0",
    (cid,))}
ya = db._fetchone("SELECT COUNT(*) AS n FROM pagos WHERE consorcio_id=%s", (cid,))["n"]
print(f"Consorcio {cid}: {len(antes)} filas con pago (sistema viejo); pagos ya migrados: {ya}")

r = cliente.get("/cobranzas")          # dispara la migración en before_request
print("GET /cobranzas:", r.status_code)

despues: dict = {}
vinculados = sueltos = 0
for p in db._fetchall("SELECT periodo, unidad, monto, caja_id FROM pagos WHERE consorcio_id=%s", (cid,)):
    k = (p["periodo"], str(p["unidad"]))
    despues[k] = round(despues.get(k, 0.0) + float(p["monto"]), 2)
    if p["caja_id"]:
        vinculados += 1
    else:
        sueltos += 1
dif = {k: (antes.get(k, 0.0), despues.get(k, 0.0)) for k in set(antes) | set(despues)
       if round(antes.get(k, 0.0) - despues.get(k, 0.0), 2) != 0}
print(f"Pagos en la tabla: {vinculados + sueltos} ({vinculados} vinculados a Caja, {sueltos} sin entrada en Caja)")
print("Diferencias por liquidación/unidad:", dif or "ninguna ✅")
print("Total antes $", round(sum(antes.values()), 2), "| después $", round(sum(despues.values()), 2))
for e in db._fetchall("SELECT periodo, estado, fecha_cierre FROM liquidaciones_estado WHERE consorcio_id=%s "
                      "ORDER BY periodo", (cid,)):
    print(f"  {e['periodo']}: {e['estado']} {e['fecha_cierre'] or ''}")
print("En cobro:", db.periodo_cobranza() or "(ninguna cerrada)")
