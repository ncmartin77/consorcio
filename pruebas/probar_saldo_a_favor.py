"""
Saldo a favor (v7.0) contra la base de PRUEBA.
1. Reglas de interés: saldo a favor sin interés; mora solo sobre lo no cubierto.
2. Pago de más en el mes P: queda pagado, saldo -excedente, Caja con el monto completo.
3. Mes P+1: deuda anterior negativa (a favor) y total reducido.
4. Saldo a favor que cubre todo P+1: queda pagado sin abonar y el resto sigue a favor.
5. Pantallas y recibo.
Restaura liquidaciones y Caja al terminar.
Uso: probar_saldo_a_favor.py [P] [P+1]   (por defecto 2026-11 y 2026-12)
"""
import sys
from datetime import date

from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
P = sys.argv[1] if len(sys.argv) > 1 else "2026-11"
P1 = sys.argv[2] if len(sys.argv) > 2 else db._next_periodo(P)
CAMPOS = ("pagado", "monto_pagado", "tipo_pago", "saldo_pendiente", "fecha_pago", "deuda_anterior", "interes",
          "total_a_pagar", "expensas")
f = lambda v: f"$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def foto(periodo):
    return {str(r["unidad"]): tuple(r[c] for c in CAMPOS) for r in db._fetchall(
        f"SELECT unidad, {', '.join(CAMPOS)} FROM liquidaciones WHERE consorcio_id=%s AND periodo=%s", (cid, periodo))}


def fila(periodo, u):
    return next(r for r in db.get_liquidacion(periodo, simular=False) if str(r["unidad"]) == u)


ok = lambda b: "✅" if b else "❌"
print("[1] Reglas de interés (tasa 5 %, vencido, sin pagos):")
ven = date(2026, 1, 10)
hoy = date(2026, 2, 1)
casos = [("deuda +10.000, expensas 20.000", 10000, 20000, 500 + 1000),
         ("a favor −5.000, expensas 20.000", -5000, 20000, 750),
         ("a favor −25.000, expensas 20.000", -25000, 20000, 0)]
for nombre, deuda, exp, esperado in casos:
    i = db._calcular_interes(exp, deuda, False, 0, False, 0.05, hoy, ven)
    print(f"    {nombre}: interés {f(i)} (esperado {f(esperado)}) {ok(round(i, 2) == esperado)}")

caja_max = db._fetchone("SELECT COALESCE(MAX(id),0) m FROM caja WHERE consorcio_id=%s", (cid,))["m"]
f0, f1 = foto(P), foto(P1)
fecha0 = db.get_config().get("fecha_simulada", "")
estado0 = db.get_liq_estado(P)
try:
    if fecha0:
        cliente.post("/config/fecha-sistema", data={"accion": "quitar"})
    if estado0 == "CERRADA":
        db.set_liq_estado(P, "ABIERTA")
    pendientes = [u for u, v in f0.items() if not v[0] and (v[1] or 0) == 0]
    u1, u2 = pendientes[0], pendientes[1]

    # 2) Pago de más
    t1 = fila(P, u1)["total_a_pagar"]
    r = cliente.post(f"/liquidacion/pagar/{P}/{u1}", data={"monto_pagado": str(round(t1 + 5000, 2))},
                     follow_redirects=True)
    x = fila(P, u1)
    caja = db._fetchone("SELECT importe FROM caja WHERE consorcio_id=%s AND id>%s ORDER BY id DESC LIMIT 1",
                        (cid, caja_max))
    print(f"\n[2] UF {u1} {P}: total {f(t1)}, paga {f(t1 + 5000)} → {x['tipo_pago']}, saldo {f(x['saldo_pendiente'])} "
          f"{ok(x['tipo_pago'] == 'TOTAL' and round(x['saldo_pendiente'], 2) == -5000)} | Caja {f(float(caja['importe']))} "
          f"{ok(round(float(caja['importe']), 2) == round(t1 + 5000, 2))} | aviso: "
          f"{ok('saldo a favor de $ 5,000.00' in r.get_data(as_text=True))}")

    # 3) Mes siguiente
    db.generar_liquidacion(P1)
    y = fila(P1, u1)
    print(f"[3] UF {u1} {P1}: deuda anterior {f(y['deuda_anterior'])} {ok(round(y['deuda_anterior'], 2) == -5000)} | "
          f"interés {f(y['interes'])} | total {f(y['total_a_pagar'])} = expensas {f(y['expensas'])} − 5.000 "
          f"{ok(round(y['total_a_pagar'], 2) == round(y['expensas'] - 5000 + y['interes'], 2))}")

    # 4) Saldo a favor que cubre todo el mes siguiente
    t2 = fila(P, u2)["total_a_pagar"]
    exp2 = fila(P1, u2)["expensas"]
    extra = round(exp2 + 1000, 2)
    cliente.post(f"/liquidacion/pagar/{P}/{u2}", data={"monto_pagado": str(round(t2 + extra, 2))})
    db.generar_liquidacion(P1)
    z = fila(P1, u2)
    sig = db._deuda_desde_mes_anterior(z)
    print(f"[4] UF {u2}: a favor {f(extra)} vs expensas {P1} {f(exp2)} → total {f(z['total_a_pagar'])}, "
          f"{z['tipo_pago']} sin abonar {ok(z['tipo_pago'] == 'TOTAL' and z['pagado'] == 1)} | pasa al mes siguiente "
          f"{f(sig)} {ok(round(sig, 2) == -1000)}")

    # 5) Pantallas y recibo
    h = cliente.get(f"/liquidacion/{P1}").get_data(as_text=True)
    h0 = cliente.get(f"/liquidacion/{P}").get_data(as_text=True)
    print(f"\n[5] Liquidación {P1} muestra 'a favor': {ok('a favor' in h)} | {P} muestra 'a favor próx. mes': "
          f"{ok('a favor próx. mes' in h0)} | formulario sin máximo: {ok('input.max' not in h0)}")
    rr = cliente.get(f"/liquidacion/recibo/{P}/{u1}")
    print(f"    Recibo UF {u1} {P}: {rr.status_code} {rr.mimetype} | Unidades: {cliente.get('/unidades').status_code}")
finally:
    db._exec("DELETE FROM caja WHERE consorcio_id=%s AND id>%s", (cid, caja_max))
    for periodo, foto0 in ((P, f0), (P1, f1)):
        for u, v in foto0.items():
            db._exec(f"UPDATE liquidaciones SET {', '.join(c + '=%s' for c in CAMPOS)} "
                     "WHERE consorcio_id=%s AND periodo=%s AND unidad=%s", (*v, cid, periodo, u))
    if estado0 == "CERRADA":
        db.set_liq_estado(P, "CERRADA")
    if fecha0:
        cliente.post("/config/fecha-sistema", data={"fecha_sistema": fecha0})
    print(f"\nRestaurado: {P} igual {ok(foto(P) == f0)} | {P1} igual {ok(foto(P1) == f1)} | Caja sin movimientos nuevos "
          f"{ok(db._fetchone('SELECT COUNT(*) n FROM caja WHERE consorcio_id=%s AND id>%s', (cid, caja_max))['n'] == 0)}")
