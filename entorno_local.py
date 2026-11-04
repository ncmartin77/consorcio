"""Carga variables desde .env.local (no versionado) para pruebas locales."""
import os

ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")


def cargar(obligatorias=()) -> None:
    """Lee .env.local (líneas CLAVE=valor; # comentarios) sin pisar variables ya definidas."""
    if not os.path.isfile(ARCHIVO):
        raise SystemExit(f"No existe {ARCHIVO}. Copiá .env.local.ejemplo como .env.local y completalo.")
    with open(ARCHIVO, encoding="utf-8-sig") as f:
        for n, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea or linea.startswith("#"):
                continue
            if "=" not in linea:
                raise SystemExit(f".env.local línea {n}: falta '='")
            clave, valor = linea.split("=", 1)
            clave, valor = clave.strip(), valor.strip()
            if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            os.environ.setdefault(clave, valor)
    faltan = [v for v in obligatorias if not os.environ.get(v, "").strip()]
    if faltan:
        raise SystemExit(f"Faltan en .env.local: {', '.join(faltan)}")
