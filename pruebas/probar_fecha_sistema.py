"""
Fecha del sistema (v5.7 / v5.8; desde la v9.0 también para pagos y cierres; actualizada en
la v10.3 con escenario propio).

Escenario: octubre cerrado; la UF 1 paga el 20/10. Verifica:
- con una fecha anterior al pago, la VISTA no cuenta el pago (pendiente) y la base no cambia;
- sin fecha fijada (o con una posterior), el pago cuenta;
- la franja de aviso; el formulario principal de Configuración no borra la fecha;
- una fecha inválida se rechaza; pantallas y PDF responden con la fecha fijada.
"""
from escenario import Escenario

P = "2026-10"
with Escenario("Prueba fecha del sistema") as e:
    e.fecha("2026-10-01"); e.generar(P); e.cerrar(P)
    e.fecha("2026-10-20"); e.pagar(P, "1", 100000, "2026-10-20")
    guardado = e.fila(P, "1")

    r = e.cliente.post("/config/fecha-sistema", data={"fecha_sistema": "2026-10-15"}, follow_redirects=True)
    e.check("Fijar 15/10: aviso de que no se modifica nada", True,
            "No se modifica ningún dato guardado" in r.get_data(as_text=True) or "como si hoy fuera 15/10/2026" in r.get_data(as_text=True))
    e.check("15/10 (antes del pago): la vista muestra la UF 1 pendiente", "PENDIENTE", e.fila(P, "1", simular=True)["tipo_pago"])
    e.check("15/10: lo guardado sigue pagado", "TOTAL", e.fila(P, "1")["tipo_pago"])
    e.check("15/10: la base no cambió", guardado, e.fila(P, "1"))
    h = e.cliente.get(f"/cobranzas/{P}").get_data(as_text=True)
    e.check("15/10: franja de aviso de fecha fijada", True, "FECHA DEL SISTEMA FIJADA" in h)
    for ruta in ("/estado-cuenta", "/plano", "/unidades", "/caja", "/gastos", f"/liquidacion/pdf/{P}", f"/cobranzas/{P}"):
        e.check(f"15/10: {ruta}", 200, e.cliente.get(ruta).status_code)

    e.fecha("2026-10-25")
    e.check("25/10 (después del pago): la vista la muestra pagada", "TOTAL", e.fila(P, "1", simular=True)["tipo_pago"])

    cfg = e.db.get_config()
    e.cliente.post("/config", data={k: cfg.get(k, "") for k in ("edificio_nombre", "edificio_direccion",
                                                               "administrador", "tasa_mora", "dia_vencimiento")})
    e.check("Guardar el formulario principal no borra la fecha", "2026-10-25", e.db.get_config().get("fecha_simulada"))
    r = e.cliente.post("/config/fecha-sistema", data={"fecha_sistema": "no-es-fecha"}, follow_redirects=True)
    e.check("Fecha inválida rechazada", True, "Fecha inválida" in r.get_data(as_text=True))
    e.check("Fecha inválida: queda la anterior", "2026-10-25", e.db.get_config().get("fecha_simulada"))

    e.fecha(None)
    e.check("Sin fecha fijada: el pago cuenta", "TOTAL", e.fila(P, "1", simular=True)["tipo_pago"])
