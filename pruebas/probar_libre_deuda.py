"""
Prueba del certificado de libre deuda (v5.6) contra la base de PRUEBA.

Cubre: bloqueo por deuda, emisión y numeración, PDF, verificación pública
(válido / código falso / inexistente / anulado), anulación y auditoría.
Si ninguna unidad está libre de deuda, simula el pago total de la primera unidad
y lo restaura al final. Con --limpiar borra los certificados de prueba emitidos.
"""
import os
import re
import sys
import tempfile

from entorno_prueba import preparar, CID

app, db, cliente = preparar()
db.ensure_libres_deuda()
db.ensure_auditoria()

estado = db.get_estado_libre_deuda()
libres = [n for n, e in estado.items() if e["libre"]]
deudores = [n for n, e in estado.items() if not e["libre"]]
print("Último período liquidado:", db.get_ultimo_periodo_liquidado())
print("Libres:", libres, "| con deuda:", len(deudores), "(ej.:", estado[deudores[0]]["motivo"] if deudores else "-", ")")

r = cliente.get("/unidades")
assert r.status_code == 200
print("GET /unidades:", r.status_code)

if deudores:
    r = cliente.post(f"/unidades/{deudores[0]}/libre-deuda", data={"solicitante": "x"}, follow_redirects=True)
    print("Emitir a unidad con deuda -> bloqueado:", b"No se puede emitir" in r.data)

original, periodo = None, db.get_ultimo_periodo_liquidado()
if libres:
    u = libres[0]
else:
    u = deudores[0]
    original = db._fetchone("SELECT pagado, monto_pagado, tipo_pago, saldo_pendiente, fecha_pago FROM liquidaciones "
                            "WHERE consorcio_id=%s AND periodo=%s AND unidad=%s", (CID, periodo, u))
    db._exec("UPDATE liquidaciones SET pagado=TRUE, monto_pagado=total_a_pagar, tipo_pago='TOTAL', "
             "saldo_pendiente=0, fecha_pago=CURRENT_DATE WHERE consorcio_id=%s AND periodo=%s AND unidad=%s",
             (CID, periodo, u))
    print(f"(pago simulado de la unidad {u} en {periodo})")

try:
    r = cliente.post(f"/unidades/{u}/libre-deuda",
                     data={"solicitante": "Juan <Pérez> & Cía", "destino": "Escribanía García", "validez_dias": "30"})
    num = int(re.search(r"ld=(\d+)", r.headers["Location"]).group(1))
    cert = db.get_libre_deuda(num)
    print("Emitido:", {k: cert[k] for k in ("numero", "unidad", "periodo_hasta", "fecha_emision", "vence")})

    r = cliente.get(f"/libre-deuda/{num}/pdf")
    destino = os.path.join(tempfile.gettempdir(), f"libre_deuda_prueba_{num:04d}.pdf")
    open(destino, "wb").write(r.data)
    print("PDF:", r.status_code, r.mimetype, len(r.data), "bytes ->", destino)

    publico = app.test_client()  # sin sesión
    url = f"/libre-deuda/verificar/{CID}/{num}/{cert['codigo']}"
    print("Verificar válido:", "auténtico y vigente" in publico.get(url).get_data(as_text=True))
    print("Verificar código falso:", "Verificación fallida" in publico.get(
        f"/libre-deuda/verificar/{CID}/{num}/{'0' * 32}").get_data(as_text=True))
    print("Verificar inexistente:", "no encontrado" in publico.get(
        f"/libre-deuda/verificar/{CID}/99999/{cert['codigo']}").get_data(as_text=True))

    cliente.post(f"/libre-deuda/{num}/anular")
    print("Verificar anulado:", "ANULADO" in publico.get(url).get_data(as_text=True))
    ops = db._fetchall("SELECT accion, descripcion FROM audit_log WHERE tabla='libres_deuda' ORDER BY id DESC LIMIT 2")
    print("Auditoría:", [(o["accion"], o["descripcion"]) for o in ops])
finally:
    if original is not None:
        db._exec("UPDATE liquidaciones SET pagado=%s, monto_pagado=%s, tipo_pago=%s, saldo_pendiente=%s, fecha_pago=%s "
                 "WHERE consorcio_id=%s AND periodo=%s AND unidad=%s",
                 (original["pagado"], original["monto_pagado"], original["tipo_pago"], original["saldo_pendiente"],
                  original["fecha_pago"], CID, periodo, u))
        print(f"(pago de la unidad {u} restaurado)")
    if "--limpiar" in sys.argv:
        db._exec("DELETE FROM libres_deuda WHERE consorcio_id=%s", (CID,))
        print("Certificados de prueba borrados.")
