"""
Diagnóstico del fondo de reserva y gastos extraordinarios (solo lectura) contra la base de PRUEBA.
Muestra gastos por tipo y período, facturas extraordinarias / de fondo y movimientos de caja del fondo.
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
cfg = db.get_config()
print("fondo_reserva_mensual:", cfg.get("fondo_reserva_mensual"))
print("\nGastos por período y tipo:")
for r in db._fetchall("SELECT periodo, tipo, COUNT(*) n, SUM(importe) total FROM gastos WHERE consorcio_id=%s "
                      "GROUP BY 1,2 ORDER BY 1,2", (cid,)):
    print(f"  {r['periodo']} {r['tipo']:<14} n={r['n']:<3} total={float(r['total']):>12,.2f}")
print("\nFacturas extraordinarias o de categoría FONDO_RESERVA:")
for r in db._fetchall("SELECT id, fecha, fecha_pago, descripcion, importe, estado, categoria, extraordinario "
                      "FROM facturas WHERE consorcio_id=%s AND (extraordinario OR upper(categoria)='FONDO_RESERVA') "
                      "ORDER BY fecha", (cid,)):
    print(f"  #{r['id']} {r['fecha']} pago={r['fecha_pago']} {r['estado']:<9} cat={r['categoria']!r} "
          f"ext={r['extraordinario']} {float(r['importe']):>11,.2f} {r['descripcion']}")
print("\nCategorías de facturas:", [(r["categoria"], r["n"]) for r in db._fetchall(
    "SELECT categoria, COUNT(*) n FROM facturas WHERE consorcio_id=%s GROUP BY 1", (cid,))])
print("\nCaja con categoría FONDO_RESERVA:")
for r in db._fetchall("SELECT fecha, tipo, categoria, importe, descripcion FROM caja WHERE consorcio_id=%s "
                      "AND upper(categoria) LIKE 'FONDO%%' ORDER BY fecha", (cid,)):
    print(f"  {r['fecha']} {r['tipo']} {float(r['importe']):>11,.2f} {r['descripcion']}")
print("\nget_fondo_reserva() (suma de aportes):", db.get_fondo_reserva())
print("Configuración relacionada:", {k: v for k, v in cfg.items() if "fondo" in k.lower() or "saldo_inicial" in k})
