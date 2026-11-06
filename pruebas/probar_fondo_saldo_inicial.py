"""
Saldo inicial del fondo cargado al mismo mes que un aporte (v6.6), contra la base de PRUEBA.
Un aporte entra al fondo cuando se COBRA (liquidación siguiente a su mes): con saldo inicial al
mes P, el aporte de P (que se cobra en P+1) SÍ debe sumar. Un gasto pagado con el fondo en P,
en cambio, ya está incluido en el saldo inicial y NO resta.
Restaura la configuración del fondo al terminar.
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
cfg0 = {k: db.get_config().get(k, "") for k in ("fondo_saldo_inicial", "fondo_saldo_inicial_periodo")}
f = lambda v: f"$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

aportes = {r["periodo"]: float(r["t"]) for r in db._fetchall(
    "SELECT periodo, SUM(importe) t FROM gastos WHERE consorcio_id=%s AND tipo='FONDO_RESERVA' GROUP BY 1", (cid,))}
usos = {r["periodo"]: float(r["t"]) for r in db._fetchall(
    "SELECT periodo, SUM(importe) t FROM gastos WHERE consorcio_id=%s AND tipo='VARIABLE_FR' GROUP BY 1", (cid,))}
liq = {r["periodo"] for r in db._fetchall("SELECT DISTINCT periodo FROM liquidaciones WHERE consorcio_id=%s", (cid,))}
# Mes con aporte, uso con el fondo y liquidación siguiente generada (en la base de prueba: 2026-10)
P = next(p for p in sorted(aportes) if p in usos and db._next_periodo(p) in liq)
print(f"Mes de prueba {P}: aporte {f(aportes[P])} (se cobra en {db._next_periodo(P)}, generada), "
      f"pagado con el fondo {f(usos[P])}")
try:
    for ini in (0, 80000):
        db.save_config({"fondo_saldo_inicial": str(ini), "fondo_saldo_inicial_periodo": P})
        r = db.get_resumen_fondo(P)
        esperado = ini + aportes[P]   # el uso de P ya está dentro del saldo inicial
        print(f"  Saldo inicial {f(ini)} al {P}: anterior {f(r['saldo_anterior'])} + aporte "
              f"{f(r['aporte'])} ({'cuenta' if r['aporte_liquidado'] else 'NO cuenta'}) − usos {f(r['usos'])} "
              f"= {f(r['saldo'])} | esperado {f(esperado)} → {'✅' if round(r['saldo'], 2) == round(esperado, 2) else '❌'}")
    Pm1 = db._prev_periodo(P)
    db.save_config({"fondo_saldo_inicial": "0", "fondo_saldo_inicial_periodo": Pm1})
    r = db.get_resumen_fondo(P)
    esperado = aportes.get(P, 0) - usos.get(P, 0) + (aportes.get(Pm1, 0) if P in liq else 0)
    print(f"  Saldo inicial $ 0 al {Pm1}: saldo {f(r['saldo'])} (aporte de {Pm1} cobrado en {P}: "
          f"{'sí' if P in liq else 'no'}; uso de {P} resta) | esperado {f(esperado)} → "
          f"{'✅' if round(r['saldo'], 2) == round(esperado, 2) else '❌'}")
finally:
    db.save_config(cfg0)
    print("Config del fondo restaurada:", cfg0)
