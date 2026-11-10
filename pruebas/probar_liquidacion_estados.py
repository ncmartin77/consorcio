"""
La pantalla de Liquidación debe cargar en todos los estados del período (contra la base de PRUEBA):
abierta, cerrada y no generada, con y sin fecha del sistema fijada.
(En v6.2 fallaba con UnboundLocalError '_cal' si la liquidación estaba cerrada o no existía.)
Restaura el estado de la liquidación y la fecha al terminar.
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
app.config["PROPAGATE_EXCEPTIONS"] = True
cid = db._cid()
fecha0 = db.get_config().get("fecha_simulada", "")
ABIERTA = db.get_ultimo_periodo_liquidado()
SIN_GENERAR = db._next_periodo(db._next_periodo(ABIERTA))
estado0 = db._fetchone("SELECT estado FROM liquidaciones_estado WHERE consorcio_id=%s AND periodo=%s", (cid, ABIERTA))


def ver(etiqueta, periodo):
    try:
        r = cliente.get(f"/liquidacion/{periodo}")
        print(f"  {etiqueta:<28} /liquidacion/{periodo} -> {r.status_code}")
    except Exception as e:
        print(f"  {etiqueta:<28} /liquidacion/{periodo} -> ERROR {type(e).__name__}: {e}")


try:
    for fecha in ("", "2026-10-06"):
        cliente.post("/config/fecha-sistema", data=({"fecha_sistema": fecha} if fecha else {"accion": "quitar"}))
        print(f"Fecha del sistema: {fecha or 'real'}")
        ver("abierta", ABIERTA)
        ver("no generada", SIN_GENERAR)
        db.set_liq_estado(ABIERTA, "CERRADA")
        ver("cerrada", ABIERTA)
        db.set_liq_estado(ABIERTA, (estado0 or {}).get("estado", "ABIERTA"))
finally:
    db.set_liq_estado(ABIERTA, (estado0 or {}).get("estado", "ABIERTA"))
    cliente.post("/config/fecha-sistema", data=({"fecha_sistema": fecha0} if fecha0 else {"accion": "quitar"}))
    print("Restaurado: estado", ABIERTA, "=", db._fetchone(
        "SELECT estado FROM liquidaciones_estado WHERE consorcio_id=%s AND periodo=%s", (cid, ABIERTA))["estado"],
        "| fecha:", repr(db.get_config().get("fecha_simulada")))
