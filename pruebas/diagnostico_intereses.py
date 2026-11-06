"""
Diagnóstico de intereses (solo lectura) contra la base de PRUEBA.
Para cada período muestra lo guardado y el interés que daría la fórmula con el switch apagado,
para detectar diferencias (ej. deuda anterior desactualizada).
Uso: diagnostico_intereses.py [cantidad_de_unidades]   (por defecto 6)
"""
import sys

from entorno_prueba import preparar

app, db, cliente = preparar()
n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
cfg = db.get_config()
print("config:", {k: cfg.get(k) for k in ("tasa_mora", "dia_vencimiento", "fecha_simulada")})
print("estados:", [(r["periodo"], r["estado"]) for r in db._fetchall(
    "SELECT periodo, estado FROM liquidaciones_estado WHERE consorcio_id=%s ORDER BY periodo", (db._cid(),))])
periodos = [r["periodo"] for r in db._fetchall(
    "SELECT DISTINCT periodo FROM liquidaciones WHERE consorcio_id=%s ORDER BY periodo", (db._cid(),))]
for p in periodos:
    tasa, hoy, venc = db._params_interes(p, cfg)
    filas = db.get_liquidacion(p, simular=False)
    previas = {str(r["unidad"]) for r in db.get_liquidacion(db._prev_periodo(p), simular=False)}
    print(f"\n== {p}: tasa={tasa} hoy={hoy} vencimiento={venc} filas={len(filas)}")
    for r in filas[:n]:
        calc = db._calcular_interes(r["expensas"], r["deuda_anterior"], str(r["unidad"]) not in previas,
                                    r["monto_pagado"], False, tasa, hoy, venc)
        print(f"  UF {r['unidad']}: expensas={r['expensas']:.2f} deuda_ant={r['deuda_anterior']:.2f} "
              f"interés_guardado={r['interes']:.2f} sin_interes={r['sin_interes']} pagado={r['monto_pagado']:.2f} "
              f"fecha_pago={r['fecha_pago'] or '-'} -> interés con switch apagado={calc:.2f}")
