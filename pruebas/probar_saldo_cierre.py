"""
Saldo de caja a la fecha de cierre de la liquidación (v8.1), contra la base de PRUEBA.
- Abierta: saldo a la fecha del sistema.
- Cerrada: saldo a la fecha en que se cerró (se guarda al cerrar; al reabrir se borra).
- Cerrada antes de que existiera la fecha de cierre: fin de mes.
Restaura estados y fecha del sistema.
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
P = db.get_ultimo_periodo_liquidado()
fecha0 = db.get_config().get("fecha_simulada", "")
estado0 = db.get_liq_estado(P) or "ABIERTA"
ok = lambda b: "✅" if b else "❌"
try:
    cliente.post("/config/fecha-sistema", data={"fecha_sistema": f"{P}-10"})
    r = db.get_resumen_caja_periodo(P)
    print(f"Abierta, fecha del sistema {P}-10: saldo al {r['fecha_final']} {ok(r['fecha_final'] == f'{P}-10')}")
    h = cliente.get(f"/liquidacion/{P}").get_data(as_text=True)
    print(f"  Pantalla SALDO EN CAJA al {P}-10: {ok(f'value=\"{P}-10\"' in h)}")
    cliente.post("/config/fecha-sistema", data={"fecha_sistema": f"{db._next_periodo(P)}-05"})
    db.set_liq_estado(P, "CERRADA")
    cliente.post("/config/fecha-sistema", data={"fecha_sistema": f"{db._next_periodo(P)}-20"})
    r = db.get_resumen_caja_periodo(P)
    esperado = f"{db._next_periodo(P)}-05"
    print(f"Cerrada el {esperado} (hoy {db._next_periodo(P)}-20): saldo al {r['fecha_final']} {ok(r['fecha_final'] == esperado)}")
    pdf = cliente.get(f"/liquidacion/pdf/{P}")
    print(f"  PDF: {pdf.status_code}")
    db._exec("UPDATE liquidaciones_estado SET fecha_cierre=NULL WHERE consorcio_id=%s AND periodo=%s", (cid, P))
    r = db.get_resumen_caja_periodo(P)
    print(f"Cerrada sin fecha guardada: saldo al {r['fecha_final']} (fin de mes) {ok(r['fecha_final'].endswith(('-30', '-31', '-28', '-29')))}")
    db.set_liq_estado(P, "ABIERTA")
    fc = db._fetchone("SELECT fecha_cierre FROM liquidaciones_estado WHERE consorcio_id=%s AND periodo=%s", (cid, P))["fecha_cierre"]
    print(f"Reabierta: fecha de cierre borrada {ok(fc is None)}")
finally:
    db.set_liq_estado(P, estado0)
    cliente.post("/config/fecha-sistema", data=({"fecha_sistema": fecha0} if fecha0 else {"accion": "quitar"}))
    print("Restaurado:", P, db.get_liq_estado(P), "| fecha:", repr(db.get_config().get("fecha_simulada")))
