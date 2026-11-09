"""
Prueba del fondo de reserva y gastos extraordinarios (v6.0) contra la base de PRUEBA.

1. Migración: gastos ordinarios cuya factura se pagó con el fondo pasan a "pagado con fondo"
   y se recalcula la liquidación que los cobraba.
2. Libro del fondo (v10.0): saldo inicial + aportes cobrados + otros ingresos − pagos con el fondo.
3. Extraordinario "pendiente": se cobra en las expensas siguientes.
4. Extraordinario "con el fondo": no se cobra (sale de la caja cuando se paga).
5. Pantallas y PDF.
Deja la base como estaba (salvo la migración, que es el cambio buscado).
Uso: probar_fondo_reserva.py [mes_gastos]   (por defecto el anterior al último liquidado)
"""
import sys

from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
ultimo_liq = db.get_ultimo_periodo_liquidado()
MES = sys.argv[1] if len(sys.argv) > 1 else db._prev_periodo(ultimo_liq)   # gastos que cobra la última liq
LIQ = db._next_periodo(MES)
f = lambda v: f"$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def suma_expensas(periodo):
    return round(sum(r["expensas"] for r in db.get_liquidacion(periodo, simular=False)), 2)


def tipos_fondo():
    return {r["id"]: r["tipo"] for r in db._fetchall(
        "SELECT g.id, g.tipo FROM gastos g JOIN facturas fa ON fa.consorcio_id=g.consorcio_id "
        "AND upper(coalesce(fa.categoria,''))='FONDO_RESERVA' AND fa.importe=g.importe "
        "AND to_char(coalesce(fa.fecha_pago,fa.fecha),'YYYY-MM')=g.periodo WHERE g.consorcio_id=%s", (cid,))}


cfg0 = db.get_config()
cfg_fondo0 = {k: cfg0.get(k, "") for k in ("fondo_saldo_inicial", "fondo_saldo_inicial_periodo")}
print(f"Mes de gastos {MES} → liquidación {LIQ}")

# 1) Migración (corre en el primer request)
antes_tipos = tipos_fondo()
periodos_liq = sorted({r["periodo"] for r in db._fetchall(
    "SELECT DISTINCT periodo FROM liquidaciones WHERE consorcio_id=%s", (cid,))})
antes_exp = {p: suma_expensas(p) for p in periodos_liq}
cliente.get(f"/gastos/{MES}")
despues_tipos = tipos_fondo()
print("\n[1] Migración — gastos con factura pagada con el fondo:")
for gid in antes_tipos:
    print(f"    gasto #{gid}: {antes_tipos[gid]} → {despues_tipos[gid]}")
for p in periodos_liq:
    d = suma_expensas(p)
    if d != antes_exp[p]:
        print(f"    liquidación {p}: expensas {f(antes_exp[p])} → {f(d)} (diferencia {f(d - antes_exp[p])})")

try:
    # 2) v10.0: libro del fondo = saldo inicial + aportes cobrados + otros ingresos − pagos con el fondo
    #    (reemplaza la regla v8.0 "fondo = saldo de caja")
    print("\n[2] Libro del Fondo de Reserva (v10.0):")
    for m in (db._prev_periodo(MES), MES):
        r = db.get_resumen_fondo(m)
        libro = db.get_libro_fondo(hasta=db.datetime.strptime(r["fecha"], "%Y-%m-%d").date())
        cuenta = round(libro["saldo_inicial"] + sum(x["aportes_cobrados"] + x["otros_ingresos"] - x["pagos"]
                                                    for x in libro["meses"]), 2)
        print(f"    liquidación {db._next_periodo(m)}: fondo {f(r['saldo'])} | inicial + movimientos {f(cuenta)} "
              f"{'✅' if cuenta == r['saldo'] else '❌'} | pendiente de cobro {f(r['pendiente_cobro'])} | "
              f"aporte {f(r['aporte'])} | pagado con fondo {f(r['usos'])}")
    base = db.get_resumen_fondo(MES)
    exp_base = suma_expensas(LIQ)
    d0 = db.get_desglose_gastos(MES)
    print(f"    desglose {MES}: ordinarios {f(d0['total_ordinarios'])} + aporte {f(d0['total_aporte'])} "
          f"+ extra a cobrar {f(d0['total_extra_cobrar'])} = {f(d0['total_expensas'])} | expensas {LIQ}: {f(exp_base)}")

    # 3) Extraordinario pendiente (a cobrar)
    cliente.post("/gastos/save", data={"periodo": MES, "concepto": "PRUEBA Pintura hall", "importe": "100000",
                                       "tipo": "EXTRAORDINARIO", "modo_extraordinario": "COBRAR"})
    g = db._fetchone("SELECT id, tipo FROM gastos WHERE consorcio_id=%s AND periodo=%s AND concepto=%s",
                     (cid, MES, "PRUEBA Pintura hall"))
    r = db.get_resumen_fondo(MES)
    print(f"\n[3] Extraordinario {f(100000)} PENDIENTE (tipo {g['tipo']}): expensas {LIQ} {f(exp_base)} → "
          f"{f(suma_expensas(LIQ))} | fondo {f(base['saldo'])} → {f(r['saldo'])}")

    # 4) Pasarlo a "pagado con el fondo"
    cliente.post(f"/gastos/{g['id']}/extraordinario/FONDO")
    tipo = db._fetchone("SELECT tipo FROM gastos WHERE id=%s", (g["id"],))["tipo"]
    r = db.get_resumen_fondo(MES)
    print(f"[4] Mismo gasto CON EL FONDO (tipo {tipo}): expensas {LIQ} → {f(suma_expensas(LIQ))} | "
          f"fondo {f(base['saldo'])} → {f(r['saldo'])}")

    # 5) Pantallas y PDF
    print("\n[5] Pantallas:")
    h = cliente.get(f"/gastos/{MES}").get_data(as_text=True)
    print("    /gastos:", "Gastos extraordinarios" in h, "| 'Con el fondo':", "Con el fondo" in h,
          "| total a repartir:", "Total a repartir" in h)
    h = cliente.get(f"/liquidacion/{LIQ}").get_data(as_text=True)
    print("    /liquidacion:", "saldo efectivo al" in h, "| aporte del período:", "Aporte del período" in h)
    r = cliente.get(f"/liquidacion/pdf/{LIQ}")
    print("    PDF resumen:", r.status_code, r.mimetype, len(r.data))
    print("    /plano:", cliente.get("/plano").status_code, "| /config:", cliente.get("/config").status_code)
finally:
    db._exec("DELETE FROM gastos WHERE consorcio_id=%s AND concepto=%s", (cid, "PRUEBA Pintura hall"))
    if db.liquidacion_existe(LIQ) and not db.liq_esta_cerrada(LIQ):
        db.generar_liquidacion(LIQ)
    db.save_config(cfg_fondo0)
    print(f"\nLimpieza: gasto de prueba borrado, {LIQ} recalculada ({f(suma_expensas(LIQ))}), "
          f"config del fondo restaurada {cfg_fondo0}")
