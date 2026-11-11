"""
Página de error 500 (v6.2, actualizada en la v10.3): fuerza un error en una ruta temporal y
verifica que un administrador ve el detalle técnico y un usuario NO administrador no.

Desde la v9.8 el rol se lee de la base en cada pedido: la prueba usa un usuario no
administrador real (creado y borrado acá); cambiar `es_admin` en la sesión no alcanza.
"""
from entorno_prueba import preparar
from escenario import Escenario

# La ruta temporal se registra ANTES del primer pedido (Flask no acepta rutas nuevas después).
app, _, _ = preparar()
app.config["PROPAGATE_EXCEPTIONS"] = False


@app.route("/__prueba_error")
def __prueba_error():
    return {}["clave_que_no_existe"]


with Escenario("Prueba página de error") as e:
    r = e.cliente.get("/__prueba_error")
    h = r.get_data(as_text=True)
    e.check("Admin: error 500", 500, r.status_code)
    e.check("Admin: ve el detalle técnico y la versión", True, "Traceback" in h and "KeyError" in h and "Versión:" in h)

    with e.como_usuario_no_admin():
        r = e.cliente.get("/__prueba_error")
        h = r.get_data(as_text=True)
        e.check("No admin (aunque la sesión diga es_admin=True): error 500", 500, r.status_code)
        e.check("No admin: NO ve el detalle técnico", True, "Traceback" not in h and "KeyError" not in h)
        e.check("No admin: ve el mensaje simple", True, "Avisá al administrador" in h)
