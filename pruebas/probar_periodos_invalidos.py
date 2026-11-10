"""
Robustez ante gastos con período mal cargado (contra la base de PRUEBA).
Inserta temporalmente gastos de fondo con períodos inválidos (vacío y "2026-9") y
verifica que Gastos, Liquidación, Liquidar, Plano y el PDF no den error. Los borra al final.
"""
import traceback

from entorno_prueba import preparar

app, db, cliente = preparar()
app.config["PROPAGATE_EXCEPTIONS"] = True
cid = db._cid()
MALOS = ["2026-9", ""]  # periodo es NOT NULL en la tabla
ids = []
try:
    for p in MALOS:
        ids.append(db._insert_returning(
            "INSERT INTO gastos (consorcio_id, periodo, concepto, importe, tipo) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (cid, p, "PRUEBA periodo invalido", 1000, "FONDO_RESERVA")))
    print("Insertados gastos con períodos inválidos:", MALOS)
    for metodo, ruta in (("GET", "/gastos/2026-11"), ("GET", "/liquidacion/2026-10"),
                         ("POST", "/liquidacion/generar/2026-10"), ("GET", "/plano"),
                         ("GET", "/liquidacion/pdf/2026-12")):
        try:
            r = cliente.post(ruta) if metodo == "POST" else cliente.get(ruta)
            print(f"  {metodo} {ruta} -> {r.status_code}")
        except Exception as e:
            print(f"  {metodo} {ruta} -> ERROR {type(e).__name__}: {e}")
            print("    " + traceback.format_exc().strip().splitlines()[-3])
finally:
    for i in ids:
        db._exec("DELETE FROM gastos WHERE id=%s AND consorcio_id=%s", (i, cid))
    print("Gastos de prueba borrados.")
