"""
Prueba de la página de error 500 (contra la base de PRUEBA): fuerza un error en una ruta
temporal y verifica que el admin ve el detalle técnico y un usuario común no.
"""
from entorno_prueba import preparar

app, db, cliente = preparar()
app.config["PROPAGATE_EXCEPTIONS"] = False


@app.route("/__prueba_error")
def __prueba_error():
    return {}["clave_que_no_existe"]


r = cliente.get("/__prueba_error")
h = r.get_data(as_text=True)
print("Admin  ->", r.status_code, "| detalle:", "KeyError" in h and "Traceback" in h,
      "| versión:", "Versión:" in h)

with cliente.session_transaction() as s:
    s["es_admin"] = False
r = cliente.get("/__prueba_error")
h = r.get_data(as_text=True)
print("Común  ->", r.status_code, "| sin detalle:", "Traceback" not in h and "KeyError" not in h)
