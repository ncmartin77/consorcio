"""
Reproduce "Liquidar" (POST /liquidacion/generar/<periodo>) con una fecha del sistema fijada,
contra la base de PRUEBA, mostrando el traceback si falla. Restaura la fecha y la liquidación.
Uso: reproducir_error_liquidar.py [periodo] [fecha]   (por defecto 2026-10 y 2026-10-06)
"""
import sys
import traceback

from entorno_prueba import preparar

app, db, cliente = preparar()
app.config["PROPAGATE_EXCEPTIONS"] = True
PERIODO = sys.argv[1] if len(sys.argv) > 1 else "2026-10"
FECHA = sys.argv[2] if len(sys.argv) > 2 else "2026-10-06"
cid = db._cid()

fecha0 = db.get_config().get("fecha_simulada", "")
filas0 = db._fetchall("SELECT * FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s ORDER BY id", (cid, PERIODO))
print(f"Liquidación {PERIODO}: {len(filas0)} filas guardadas antes")
try:
    cliente.post("/config/fecha-sistema", data={"fecha_sistema": FECHA})
    for ruta in (f"/liquidacion/{PERIODO}", f"/liquidacion/generar/{PERIODO}"):
        try:
            r = cliente.post(ruta) if "generar" in ruta else cliente.get(ruta)
            print(ruta, "->", r.status_code, r.headers.get("Location", ""))
        except Exception:
            print(ruta, "-> EXCEPCIÓN")
            traceback.print_exc()
finally:
    cliente.post("/config/fecha-sistema", data=({"fecha_sistema": fecha0} if fecha0 else {"accion": "quitar"}))
    filas1 = db._fetchall("SELECT * FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s ORDER BY id",
                          (cid, PERIODO))
    print(f"Fecha restaurada: {db.get_config().get('fecha_simulada')!r} | filas después: {len(filas1)}")
