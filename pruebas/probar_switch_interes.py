"""
Prueba del switch "sin interés" (por unidad y "Todos") contra la base de PRUEBA.
Cada cambio se hace y se deshace: los datos quedan como estaban.
Uso: probar_switch_interes.py [periodo] [unidad]   (por defecto: último período, primera unidad)
"""
import sys

from entorno_prueba import preparar

app, db, cliente = preparar()
periodo = sys.argv[1] if len(sys.argv) > 1 else db.get_ultimo_periodo_liquidado()
filas = db.get_liquidacion(periodo, simular=False)
unidad = sys.argv[2] if len(sys.argv) > 2 else str(filas[0]["unidad"])
fila = next(r for r in filas if str(r["unidad"]) == unidad)
inicial = bool(fila["sin_interes"])
print(f"{periodo} UF {unidad}: interés guardado {fila['interes']:.2f}, sin_interes={inicial}")

for valor in (not inicial, inicial):
    j = cliente.post(f"/liquidacion/{periodo}/sin-interes/{unidad}", json={"sin_interes": valor}).get_json()
    print(f"  switch sin_interes={valor}:", {k: j.get(k) for k in ("ok", "interes", "total_a_pagar", "tipo_pago")})

flags = {str(r["unidad"]): bool(r["sin_interes"]) for r in filas}
for valor in (True, False):
    j = cliente.post(f"/liquidacion/{periodo}/sin-interes-todos", json={"sin_interes": valor}).get_json()
    print(f"  Todos sin_interes={valor}: UF {unidad} ->", j["rows"][unidad], "| total período", j["total_periodo"])
# Restaurar el switch original de cada unidad
for u, v in flags.items():
    db.aplicar_sin_interes(periodo, v, unidad=u)
print("Switch de cada unidad restaurado.")
