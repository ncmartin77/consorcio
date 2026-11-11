"""
Saldo a favor (v7.0; con Cobranzas de la v9.0 y el interés de la v10.0; actualizada en la v10.3).

Escenario: octubre cerrado (100.000 por UF).
1. Pago de más en octubre: la UF 1 paga 250.000 → queda pagada con saldo −150.000 y Caja
   registra el cobro completo.
2. Noviembre: deuda anterior −150.000 (a favor); el total queda en −50.000, o sea que la UF
   queda pagada sin abonar y le sigue sobrando 50.000.
3. El saldo a favor nunca genera interés.
4. Diciembre: arrastra el saldo a favor que sobró (−50.000).
5. Pantallas.
"""
from escenario import Escenario

with Escenario("Prueba saldo a favor") as e:
    e.fecha("2026-10-01"); e.generar("2026-10"); e.cerrar("2026-10")
    e.fecha("2026-10-05"); e.pagar("2026-10", "1", 250000, "2026-10-05")
    f = e.fila("2026-10", "1")
    e.check("Oct: pago de más → TOTAL con saldo −150.000", ("TOTAL", -150000), (f["tipo_pago"], f["saldo_pendiente"]))
    e.check("Oct: Caja registra el cobro completo", 250000.0, e.caja_expensas("2026-10")[0][2])

    e.fecha("2026-11-01"); e.generar("2026-11")
    f = e.fila("2026-11", "1")
    e.check("Nov: deuda anterior −150.000 (a favor)", -150000, f["deuda_anterior"])
    e.check("Nov: total −50.000 y pagada sin abonar", (-50000, "TOTAL"), (f["total_a_pagar"], f["tipo_pago"]))
    prop = {p["unidad"] for p in e.db.propuesta_intereses(e.db.get_liquidacion("2026-11", simular=False), periodo="2026-11")}
    e.check("Nov: el saldo a favor no tiene interés propuesto (la UF 2 sí)", {"2"}, prop)
    e.cerrar("2026-11", interes_uf=["1", "2"])
    e.check("Nov cerrada con interés a todas: la UF 1 igual queda en 0", 0, e.fila("2026-11", "1")["interes"])

    e.fecha("2026-12-01"); e.generar("2026-12")
    f = e.fila("2026-12", "1")
    e.check("Dic: arrastra el saldo a favor que sobró", -50000, f["deuda_anterior"])
    e.check("Dic: total 50.000 (100.000 − 50.000)", 50000, f["total_a_pagar"])

    for ruta in ("/cobranzas/2026-11", "/liquidacion/2026-12", "/estado-cuenta", "/plano"):
        e.check(f"Pantalla {ruta}", 200, e.cliente.get(ruta).status_code)
