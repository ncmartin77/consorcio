"""
Entorno común de las pruebas: SOLO contra una base de PRUEBA.

- Lee `.env.local` (no versionado) y carga sus variables, salvo `ORIGEN_*` (producción).
- Acepta dos bases: el proyecto de prueba de Supabase (`consorcio-tst`) o una base LOCAL
  (host 127.0.0.1 / localhost / ::1), por ejemplo la `consorcio_pruebas` del Postgres de
  Docker de `plataforma/` (copia restaurada con `scripts/restaurar_legado.sh`). Útil donde la
  red no llega a Supabase.
- Aborta con cualquier otra base y, siempre, si aparece el proyecto de producción.
- Devuelve la app Flask, el módulo de datos y un cliente de pruebas con sesión de admin
  (no hace falta el login de Google).

Uso desde la raíz del repo (venv de Windows):
    C:\\Users\\Maria\\.venvs\\consorcio\\Scripts\\python.exe pruebas\\probar_libre_deuda.py
"""
import os
import sys
from urllib.parse import urlsplit

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROYECTO_PRUEBA = "rbwjkgqvfaxxvcwaywtj"      # consorcio-tst
PROYECTO_PRODUCCION = "eboskxnitazzwfobwkiq"
CID = os.environ.get("PRUEBA_CID", "28693516")  # Edificio Perú 376


def _cargar_env():
    ruta = os.path.join(RAIZ, ".env.local")
    if not os.path.exists(ruta):
        sys.exit("Falta .env.local (ver .env.local.ejemplo): las pruebas necesitan la base de PRUEBA.")
    for linea in open(ruta, encoding="utf-8"):
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        if not k.startswith("ORIGEN_"):
            os.environ[k] = v
    url = os.environ.get("DATABASE_URL", "")
    if PROYECTO_PRODUCCION in url:
        sys.exit("DATABASE_URL apunta a PRODUCCIÓN: no se corre nada.")
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        host = ""
    if PROYECTO_PRUEBA not in url and host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit("DATABASE_URL no apunta a la base de PRUEBA (consorcio-tst o una base local): no se corre nada.")


def preparar(cid: str = CID):
    """Devuelve (app, db, cliente) con el consorcio `cid` activo y sesión de admin."""
    _cargar_env()
    sys.path.insert(0, RAIZ)
    os.chdir(RAIZ)
    from app import app
    import pg_db as db

    c = db.get_consorcio(cid)
    if not c:
        sys.exit(f"No existe el consorcio {cid} en la base de prueba.")
    db.set_active_consorcio(c["data_dir_abs"], c["db_path_abs"])
    admin = db.get_usuario(1)
    cliente = app.test_client()
    with cliente.session_transaction() as s:
        s.update(usuario_id=admin["id"], usuario_email=admin["email"], usuario_nombre="Pruebas",
                 es_admin=True, consorcio_id=cid)
    return app, db, cliente
