"""
Levanta la app en esta PC (http://127.0.0.1:5000) contra una base LOCAL, para usarla en el
navegador sin Supabase ni Google.

    pruebas/correr_en_docker.sh pruebas/servidor_local.py
    → abrir http://127.0.0.1:5000/__login_local          (entra como el usuario 1, admin)
       o   http://127.0.0.1:5000/__login_local?uid=2     (otro usuario de la base)

- Toma la base de `.env.local`, como las pruebas, pero acá SOLO acepta una base local
  (127.0.0.1 / localhost): nunca consorcio-tst ni producción.
- El login con Google no funciona en local (Google no tiene registrada esta dirección), así
  que este lanzador agrega la ruta `/__login_local`, que abre una sesión con un usuario de la
  base. Solo responde a pedidos desde esta misma PC.
- Este archivo NO es parte de la app: Render arranca `app.py` con gunicorn y nunca lo carga.
  La ruta de ingreso de prueba existe solo mientras corre este lanzador.
- Puerto: variable PUERTO (por defecto 5000).
"""
import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import entorno_prueba as ep  # noqa: E402

ep._cargar_env()
host_db = (urlsplit(os.environ.get("DATABASE_URL", "")).hostname or "").lower()
if host_db not in ("127.0.0.1", "localhost", "::1"):
    sys.exit("servidor_local.py solo corre contra una base LOCAL (127.0.0.1 / localhost).")

sys.path.insert(0, ep.RAIZ)
os.chdir(ep.RAIZ)
import app as modulo_app  # noqa: E402
import pg_db as db  # noqa: E402
from flask import abort, redirect, request, session  # noqa: E402

app = modulo_app.app
LOCALES = ("127.0.0.1", "::1")


@app.route("/__login_local")
def __login_local():
    if request.remote_addr not in LOCALES or request.headers.get("X-Forwarded-For"):
        abort(404)
    try:
        u = db.get_usuario(int(request.args.get("uid", "1")))
    except ValueError:
        u = None
    if not u or not u["activo"]:
        return "Usuario inexistente o inactivo en la base local.", 404
    session.clear()
    session.update(usuario_id=u["id"], usuario_email=u["email"],
                   usuario_nombre=u.get("nombre") or "Local", es_admin=bool(u["es_admin"]))
    return redirect("/consorcios")


modulo_app._PUBLIC_ENDPOINTS.add("__login_local")

if __name__ == "__main__":
    puerto = int(os.environ.get("PUERTO", "5000"))
    print(f"App {open('version.txt').read().strip()} en http://127.0.0.1:{puerto}  "
          f"(base: {host_db}{urlsplit(os.environ['DATABASE_URL']).path})")
    print(f"Entrar: http://127.0.0.1:{puerto}/__login_local")
    app.run(host="127.0.0.1", port=puerto, debug=False, use_reloader=False)
