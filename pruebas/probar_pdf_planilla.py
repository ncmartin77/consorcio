"""
Prueba de la planilla de liquidación (PDF resumen, v9.6) contra la base de PRUEBA.
Descarga el PDF de cada liquidación y verifica: hoja horizontal, columnas "Liquidado mes ant." y
"Pago anterior", y que el cuadro de totales venga después de la tabla de unidades.
Uso: probar_pdf_planilla.py [carpeta_salida]   (guarda los PDF para revisarlos)
"""
import io
import os
import sys

from entorno_prueba import preparar

app, db, cliente = preparar()
salida = sys.argv[1] if len(sys.argv) > 1 else None
ok_total, fallas = 0, []


def chk(caso, esperado, real):
    global ok_total
    if esperado == real:
        ok_total += 1
        print(f"  OK  {caso}: {real}")
    else:
        fallas.append(caso)
        print(f"  MAL {caso}: esperado {esperado!r}, real {real!r}")


import base64  # noqa: E402
import re  # noqa: E402
import zlib  # noqa: E402

periodos = [r["periodo"] for r in db._fetchall(
    "SELECT DISTINCT periodo FROM liquidaciones WHERE consorcio_id=%s ORDER BY periodo", (db._cid(),))]
for p in periodos:
    print(f"\nLiquidación {p}")
    r = cliente.get(f"/liquidacion/pdf/{p}")
    chk("Respuesta 200 PDF", (200, "application/pdf"), (r.status_code, r.mimetype))
    # Sin librerías de PDF: MediaBox de los bytes y texto de los streams (descomprimidos con zlib)
    crudo = r.data.decode("latin-1")
    caja = re.search(r"/MediaBox \[\s*0 0 ([\d.]+) ([\d.]+)", crudo)
    chk("Hoja horizontal", True, bool(caja) and float(caja.group(1)) > float(caja.group(2)))
    partes = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", r.data, re.S):
        datos = m.group(1).strip()
        for dec in (lambda d: zlib.decompress(d),
                    lambda d: zlib.decompress(base64.a85decode(d if d.startswith(b"<~") else b"<~" + d,
                                                               adobe=True))):
            try:
                partes.append(dec(datos).decode("latin-1"))
                break
            except Exception:
                continue
    texto = "".join(re.findall(r"\((.*?)\) Tj", "".join(partes)))
    chk("Columna Liquidado mes ant.", True, "Liquidado mes ant." in texto)
    chk("Columna Pago anterior", True, "Pago anterior" in texto)
    chk("Totales debajo de la tabla de UF", True,
        texto.find("DETALLE POR UNIDAD FUNCIONAL") < texto.find("TOTAL A COBRAR"))
    if salida:
        with open(os.path.join(salida, f"planilla_{p}.pdf"), "wb") as fh:
            fh.write(r.data)

print(f"\n{ok_total} OK, {len(fallas)} con falla" + (f": {fallas}" if fallas else ""))
