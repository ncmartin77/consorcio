"""
Certificado de libre deuda (v5.6; desde la v9.0 según la última liquidación CERRADA;
actualizada en la v10.3 con escenario propio).

Escenario: octubre cerrado; la UF 1 paga todo y la UF 2 no. Verifica bloqueo por deuda,
emisión y numeración, PDF, verificación pública (válido / código falso / inexistente /
anulado), anulación y auditoría.
"""
from escenario import Escenario

P = "2026-10"
with Escenario("Prueba libre deuda") as e:
    e.fecha("2026-10-01"); e.generar(P); e.cerrar(P)
    e.fecha("2026-10-05"); e.pagar(P, "1", 100000, "2026-10-05")
    estado = e.db.get_estado_libre_deuda()
    e.check("UF 1 libre de deuda, UF 2 con deuda", (True, False), (estado["1"]["libre"], estado["2"]["libre"]))
    e.check("GET /unidades", 200, e.cliente.get("/unidades").status_code)

    r = e.cliente.post("/unidades/2/libre-deuda", data={"solicitante": "x"}, follow_redirects=True)
    e.check("Emitir a la UF 2 (con deuda): bloqueado", True, "No se puede emitir" in r.get_data(as_text=True))
    e.check("Emitir a la UF 2: no se creó ningún certificado", 0, len(e.db.get_libres_deuda()))

    r = e.cliente.post("/unidades/1/libre-deuda",
                       data={"solicitante": "Juan <Pérez> & Cía", "destino": "Escribanía García", "validez_dias": "30"})
    certs = e.db.get_libres_deuda()
    e.check("Emitir a la UF 1: certificado número 1", [1], [c["numero"] for c in certs])
    cert = e.db.get_libre_deuda(1)
    e.check("Datos: UF 1, sin deuda hasta 2026-10, vence a los 30 días", ("1", "2026-10", "2026-11-04"),
            (str(cert["unidad"]), cert["periodo_hasta"], str(cert["vence"])))

    r = e.cliente.get("/libre-deuda/1/pdf")
    e.check("PDF del certificado", (200, "application/pdf"), (r.status_code, r.mimetype))

    publico = e.app.test_client()  # sin sesión
    url = f"/libre-deuda/verificar/{e.cid}/1/{cert['codigo']}"
    e.check("Verificación pública: válido", True, "auténtico y vigente" in publico.get(url).get_data(as_text=True))
    e.check("Verificación pública: código falso", True, "Verificación fallida" in publico.get(
        f"/libre-deuda/verificar/{e.cid}/1/{'0' * 32}").get_data(as_text=True))
    e.check("Verificación pública: inexistente", True, "no encontrado" in publico.get(
        f"/libre-deuda/verificar/{e.cid}/99999/{cert['codigo']}").get_data(as_text=True))

    e.cliente.post("/libre-deuda/1/anular")
    e.check("Verificación pública: anulado", True, "ANULADO" in publico.get(url).get_data(as_text=True))
    ops = e.db._fetchall("SELECT accion FROM audit_log WHERE tabla='libres_deuda' AND consorcio_id=%s ORDER BY id",
                         (e.cid,))
    e.check("Auditoría: emisión y anulación", ["INSERT", "UPDATE"], [o["accion"] for o in ops])
