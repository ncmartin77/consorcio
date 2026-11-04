"""
Levanta la app en esta PC para pruebas, con la base y el Storage de PRUEBA (.env.local).

    python correr_local.py      → http://localhost:5000

Se niega a arrancar si DATABASE_URL apunta al proyecto de producción.
"""
import os
import re

import entorno_local

entorno_local.cargar(obligatorias=("DATABASE_URL", "SECRET_KEY"))

# Protección: nunca correr las pruebas contra producción
_prod_ref = os.environ.get("PRODUCCION_REF", "eboskmenitazzwfobwkiq").lower()
for var in ("DATABASE_URL", "SUPABASE_URL"):
    if _prod_ref and _prod_ref in os.environ.get(var, "").lower():
        raise SystemExit(f"ABORTADO: {var} apunta al proyecto de PRODUCCIÓN ({_prod_ref}). "
                         "Usá los datos del proyecto de prueba en .env.local.")

os.environ.setdefault("APP_HOST", "127.0.0.1")

from app import app, storage  # noqa: E402  (importar después de cargar el entorno)

_ref = re.findall(r"[a-z]{20,}", os.environ["DATABASE_URL"].lower())
print("=" * 60)
print(" PRUEBA LOCAL")
print(f"  Base de datos : proyecto {_ref[0] if _ref else '?'}")
print(f"  Archivos      : {storage.descripcion()}")
print(f"  Login prueba  : {os.environ.get('DEV_LOGIN_EMAIL') or '(desactivado: solo Google)'}")
print("  Abrir         : http://localhost:5000")
print("=" * 60)

app.run(debug=True, host=os.environ["APP_HOST"], port=5000, use_reloader=False)
