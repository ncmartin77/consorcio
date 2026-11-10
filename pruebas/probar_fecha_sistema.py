"""
Prueba de la Fecha del sistema (v5.7 / v5.8) contra la base de PRUEBA.

Verifica que:
- con una fecha fijada, los pagos posteriores no cuentan y el interés se calcula a esa fecha;
- todo es vista: lo guardado en la base no cambia;
- el switch funciona sobre los valores simulados;
- los recibos firmados salen con los datos reales;
- la franja de aviso aparece, el form principal de Configuración no borra la fecha,
  una fecha inválida se rechaza, y las pantallas y el PDF responden.
Al final vuelve a la fecha que hubiera antes.
Uso: probar_fecha_sistema.py [fecha_antes_del_pago] [fecha_despues_del_vencimiento]
     (por defecto 2026-10-06 y 2026-12-05, pensadas para los datos de oct-dic 2026)
"""
import sys
from collections import Counter

from entorno_prueba import preparar

app, db, cliente = preparar()
F1 = sys.argv[1] if len(sys.argv) > 1 else "2026-10-06"
F2 = sys.argv[2] if len(sys.argv) > 2 else "2026-12-05"
PERIODOS = sorted({r["periodo"] for r in db._fetchall(
    "SELECT DISTINCT periodo FROM liquidaciones WHERE consorcio_id=%s", (db._cid(),))})[-3:]


def guardado():
    return {(r["periodo"], str(r["unidad"])): (r["tipo_pago"], r["interes"], r["total_a_pagar"],
                                               r["monto_pagado"], r["fecha_pago"], r["sin_interes"])
            for p in PERIODOS for r in db.get_liquidacion(p, simular=False)}


def uf(p, n, simular=True):
    r = next(r for r in db.get_liquidacion(p, simular=simular) if str(r["unidad"]) == n)
    return {k: r[k] for k in ("tipo_pago", "interes", "total_a_pagar", "monto_pagado")}


fecha_original = db.get_config().get("fecha_simulada", "")
base = guardado()
print("Períodos:", PERIODOS)
for p in PERIODOS:
    print("  guardado", p, dict(Counter(v[0] for k, v in base.items() if k[0] == p)))

try:
    # --- Fecha anterior a los pagos ---
    r = cliente.post("/config/fecha-sistema", data={"fecha_sistema": F1}, follow_redirects=True)
    print(f"\n[{F1}] mensaje 'no se modifica':", "No se modifica ningún dato guardado" in r.get_data(as_text=True))
    p0 = F1[:7]
    html = cliente.get(f"/liquidacion/{p0}").get_data(as_text=True)
    pagados = html.count('badge bg-success">Pagado')
    pendientes = html.count('badge bg-danger">Pendiente')
    print(f"[{F1}] liquidación {p0}: Pagado={pagados} Pendiente={pendientes} "
          f"avisos 'pagó el'={html.count('pagó el ')}")
    print(f"[{F1}] franja de aviso:", "FECHA DEL SISTEMA FIJADA" in html)
    print(f"[{F1}] base sin cambios:", guardado() == base)
    pagada = next((r for r in db.get_liquidacion(p0, simular=False) if r["tipo_pago"] != "PENDIENTE"), None)
    if pagada:
        r = cliente.get(f"/liquidacion/recibo/{p0}/{pagada['unidad']}")
        print(f"[{F1}] recibo real UF {pagada['unidad']}:", r.status_code, r.mimetype)
    for ruta in ("/estado-cuenta", "/plano", "/unidades", "/caja", "/gastos", f"/liquidacion/pdf/{p0}"):
        print(f"[{F1}] {ruta}:", cliente.get(ruta).status_code)

    # --- Fecha posterior al vencimiento ---
    cliente.post("/config/fecha-sistema", data={"fecha_sistema": F2})
    p1 = PERIODOS[-2] if len(PERIODOS) > 1 else PERIODOS[0]
    n = str(db.get_liquidacion(p1, simular=False)[0]["unidad"])
    print(f"\n[{F2}] {p1} UF {n} vista:", uf(p1, n), "| guardado:", uf(p1, n, False))
    inicial = bool(next(r for r in db.get_liquidacion(p1, simular=False) if str(r["unidad"]) == n)["sin_interes"])
    for valor in (not inicial, inicial):
        j = cliente.post(f"/liquidacion/{p1}/sin-interes/{n}", json={"sin_interes": valor}).get_json()
        print(f"[{F2}] switch sin_interes={valor} ->", {k: j[k] for k in ("interes", "total_a_pagar", "tipo_pago")})
    from pdf_gen import _fecha_generacion
    print(f"[{F2}] marca de los PDF:", _fecha_generacion(db.get_config()))

    cfg = db.get_config()
    cliente.post("/config", data={k: cfg.get(k, "") for k in ("edificio_nombre", "edificio_direccion",
                                                              "administrador", "tasa_mora", "dia_vencimiento")})
    print(f"[{F2}] guardar form principal -> fecha sigue:", db.get_config().get("fecha_simulada"))
    r = cliente.post("/config/fecha-sistema", data={"fecha_sistema": "no-es-fecha"}, follow_redirects=True)
    print(f"[{F2}] fecha inválida rechazada:", "Fecha inválida" in r.get_data(as_text=True))
finally:
    if fecha_original:
        cliente.post("/config/fecha-sistema", data={"fecha_sistema": fecha_original})
    else:
        cliente.post("/config/fecha-sistema", data={"accion": "quitar"})
    print("\nFecha restaurada:", repr(db.get_config().get("fecha_simulada")),
          "| base igual al inicio:", guardado() == base)
