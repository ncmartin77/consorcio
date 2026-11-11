"""
Interés al cerrar la liquidación (v9.2; reemplaza al switch "sin interés" de la pantalla
Liquidación; con la regla de la v10.0: tasa vigente × capital). Actualizada en la v10.3.

Escenario: octubre cerrado y sin pagos. Verifica que:
- mientras noviembre está ABIERTA no lleva interés;
- la propuesta de cierre muestra 3 % sobre el capital de cada UF con deuda;
- al cerrar con interés solo para la UF 1: UF 1 con 3.000 y total 203.000; UF 2 sin interés;
- la tasa queda congelada en la liquidación cerrada;
- una UF que pagó todo antes del cierre no tiene interés propuesto.
"""
from escenario import Escenario

with Escenario("Prueba interés al cerrar") as e:
    e.fecha("2026-10-01"); e.generar("2026-10"); e.cerrar("2026-10")
    e.fecha("2026-11-01"); e.generar("2026-11")
    f1 = e.fila("2026-11", "1")
    e.check("Nov abierta: deuda anterior 100.000 y sin interés", (100000, 0), (f1["deuda_anterior"], f1["interes"]))
    prop = {p["unidad"]: p for p in e.db.propuesta_intereses(e.db.get_liquidacion("2026-11", simular=False), periodo="2026-11")}
    e.check("Propuesta de cierre: 3 % sobre el capital de cada UF", {"1": 3000, "2": 3000},
            {u: p["interes"] for u, p in prop.items()})

    e.cerrar("2026-11", interes_uf=["1"])
    f1, f2 = e.fila("2026-11", "1"), e.fila("2026-11", "2")
    e.check("Cierre: UF 1 con interés 3.000 y total 203.000", (3000, 203000), (f1["interes"], f1["total_a_pagar"]))
    e.check("Cierre: UF 2 sin interés (switch apagado) y total 200.000", (0, True, 200000),
            (f2["interes"], bool(f2["sin_interes"]), f2["total_a_pagar"]))
    e.check("Tasa congelada en la liquidación", 3.0, f1["tasa_aplicada"])

    # Una UF que pagó todo antes de cerrar diciembre no tiene interés propuesto
    e.fecha("2026-11-20"); e.pagar("2026-11", "2", 200000, "2026-11-20")
    e.fecha("2026-12-01"); e.generar("2026-12")
    prop = {p["unidad"]: p["interes"] for p in e.db.propuesta_intereses(e.db.get_liquidacion("2026-12", simular=False), periodo="2026-12")}
    e.check("Dic: la UF 2 (pagó todo) no tiene interés propuesto", False, "2" in prop)
    e.check("Dic: la UF 1 paga interés sobre el capital 200.000 (no sobre 203.000)", 6000, prop.get("1"))
