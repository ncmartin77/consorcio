"""
Diagnóstico (solo lectura) de facturas, sus pagos en Caja y gastos relacionados, contra la base de PRUEBA.
Uso: diagnostico_factura_caja.py "texto a buscar" ["otro texto" ...]
"""
import sys

from entorno_prueba import preparar

app, db, cliente = preparar()
cid = db._cid()
for texto in sys.argv[1:] or ["ENERSA", "RG Ingenieria"]:
    like = f"%{texto}%"
    print(f"\n===== '{texto}' =====")
    for f in db._fetchall("SELECT id, fecha, fecha_pago, estado, importe, categoria, numero_factura, descripcion, "
                          "proveedor_nombre FROM facturas WHERE consorcio_id=%s AND (descripcion ILIKE %s OR "
                          "proveedor_nombre ILIKE %s) ORDER BY fecha", (cid, like, like)):
        bloq = db.factura_en_liquidacion(f["id"])
        print(f"  FACTURA #{f['id']} fecha={f['fecha']} pago={f['fecha_pago']} {f['estado']} {float(f['importe']):,.2f} "
              f"cat={f['categoria']!r} nro={f['numero_factura']!r} | bloqueada por liquidación cerrada: {bloq}")
        for c in db._fetchall("SELECT id, fecha, tipo, categoria, importe, factura_id, descripcion FROM caja "
                              "WHERE consorcio_id=%s AND factura_id=%s", (cid, f["id"])):
            print(f"     caja vinculada #{c['id']} {c['fecha']} {c['tipo']} {float(c['importe']):,.2f} {c['descripcion']}")
    for c in db._fetchall("SELECT id, fecha, tipo, categoria, importe, factura_id, descripcion FROM caja "
                          "WHERE consorcio_id=%s AND descripcion ILIKE %s ORDER BY fecha", (cid, like)):
        mes = str(c["fecha"])[:7]
        print(f"  CAJA #{c['id']} {c['fecha']} {c['tipo']} {c['categoria']} {float(c['importe']):,.2f} "
              f"factura_id={c['factura_id']} | mes {mes} cerrado: {db.liq_esta_cerrada(mes)} | {c['descripcion']}")
    for g in db._fetchall("SELECT id, periodo, tipo, importe, concepto FROM gastos WHERE consorcio_id=%s "
                          "AND concepto ILIKE %s ORDER BY periodo", (cid, like)):
        print(f"  GASTO #{g['id']} {g['periodo']} {g['tipo']} {float(g['importe']):,.2f} {g['concepto']} | "
              f"liquidación {db._next_periodo(g['periodo'])} cerrada: {db.liq_esta_cerrada(db._next_periodo(g['periodo']))}")
print("\nEstados:", [(r["periodo"], r["estado"]) for r in db._fetchall(
    "SELECT periodo, estado FROM liquidaciones_estado WHERE consorcio_id=%s ORDER BY periodo", (cid,))])
