"""
Anular pagos (v6.4; desde la v9.0 en Cobranzas; actualizada en la v10.3).

Escenario propio: octubre cerrado y cobrado. Verifica:
1. Anular UN pago (pago_id): desaparece ese pago y su entrada en Caja; lo demás no cambia.
2. Un usuario NO administrador no puede anular.
3. Anular los pagos de una unidad.
4. Con pagos no se puede reabrir la liquidación; sin pagos, sí.
5. Anular TODOS los pagos del período.
6. Pagar sin indicar fecha usa la fecha del sistema (fila y Caja).
"""
from escenario import Escenario

P = "2026-10"
with Escenario("Prueba anular pagos") as e:
    e.fecha("2026-10-01"); e.generar(P); e.cerrar(P)
    e.fecha("2026-10-08")
    e.pagar(P, "1", 100000, "2026-10-05")
    e.pagar(P, "2", 30000, "2026-10-06")
    e.pagar(P, "2", 20000, "2026-10-08")
    e.check("Inicio: 3 pagos y 3 entradas de Caja", (3, 3), (len(e.pagos(P)), len(e.caja_expensas(P))))
    e.check("Inicio: UF 2 parcial con saldo 50.000", ("PARCIAL", 50000),
            (e.fila(P, "2")["tipo_pago"], e.fila(P, "2")["saldo_pendiente"]))

    # 1. Anular un pago
    p20 = next(p for p in e.pagos(P, "2") if p["monto"] == 20000)
    e.cliente.post(f"/cobranzas/{P}/anular", data={"pago_id": p20["id"]})
    e.check("Anular el pago de 20.000: UF 2 queda con un pago de 30.000", [30000],
            [p["monto"] for p in e.pagos(P, "2")])
    e.check("Anular el pago de 20.000: su entrada de Caja se borra", 2, len(e.caja_expensas(P)))
    e.check("Anular el pago de 20.000: UF 1 intacta", ("TOTAL", 1), (e.fila(P, "1")["tipo_pago"], len(e.pagos(P, "1"))))

    # 2. No administrador
    with e.como_usuario_no_admin():
        e.cliente.post(f"/cobranzas/{P}/anular", data={"unidad": "1"})
    e.check("Un usuario no administrador no puede anular", 1, len(e.pagos(P, "1")))

    # 3 y 4. Anular una unidad; reabrir con y sin pagos
    e.check("Con pagos no se puede reabrir", True, bool(e.db.error_reapertura(P)))
    e.cliente.post(f"/cobranzas/{P}/anular", data={"unidad": "1"})
    e.check("Anular la UF 1: sin pagos y PENDIENTE", (0, "PENDIENTE"),
            (len(e.pagos(P, "1")), e.fila(P, "1")["tipo_pago"]))

    # 5. Anular todos
    e.cliente.post(f"/cobranzas/{P}/anular")
    e.check("Anular todos: sin pagos ni entradas de Caja", (0, 0), (len(e.pagos(P)), len(e.caja_expensas(P))))
    e.check("Sin pagos se puede reabrir", None, e.db.error_reapertura(P))

    # 6. Pago sin fecha → fecha del sistema
    e.fecha("2026-10-09")
    e.pagar(P, "1", 100000)
    pago = e.pagos(P, "1")[0]
    e.check("Pago sin fecha: toma la fecha del sistema", "2026-10-09", str(pago["fecha"]))
    e.check("Pago sin fecha: Caja con la fecha del sistema", "2026-10-09", e.caja_expensas(P)[0][0])
