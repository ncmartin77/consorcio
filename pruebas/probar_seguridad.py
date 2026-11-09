"""
Prueba de los arreglos de seguridad (v9.8) contra la base de PRUEBA.

1. Cuenta nueva de Google: queda INACTIVA (no entra hasta que un admin la habilite).
2. Usuario NO admin (aunque su sesión diga es_admin=True): no puede eliminar ni crear consorcios
   ni resetear datos; el rol se toma de la base en cada pedido.
3. CSRF: un POST con Origin/Referer de otro sitio se rechaza (403); el mismo sitio pasa.
4. Validaciones del servidor: importes "nan"/"inf"/negativos, tipo de caja inválido, pago con monto
   "nan", apertura con texto; gastos de una liquidación CERRADA (si la base de prueba tiene una).
5. SECRET_KEY obligatoria en el servidor (RENDER=true sin SECRET_KEY → la app no arranca).
Deja la base como estaba (borra el usuario de prueba).
"""
import os
import subprocess
import sys

from entorno_prueba import preparar, RAIZ

app, db, cliente = preparar()
cid = db._cid()
MES = db.fecha_sistema().strftime("%Y-%m")
TAG = "PRUEBA_SEG_v98"
ok_total, fallas = 0, []


def chk(caso, esperado, real):
    global ok_total
    if esperado == real:
        ok_total += 1
        print(f"  OK  {caso}: {real}")
    else:
        fallas.append(caso)
        print(f"  MAL {caso}: esperado {esperado!r}, real {real!r}")


def n(sql, params=()):
    return db._fetchone(sql, params)["n"]


uid_prueba = None
estado_restaurar = None
try:
    # 1) Cuenta nueva inactiva
    print("[1] Cuenta nueva")
    u = db.get_or_create_usuario(google_id=TAG, email=f"{TAG.lower()}@example.com", nombre=TAG)
    uid_prueba = u["id"]
    chk("Cuenta nueva queda inactiva", False, bool(u["activo"]))
    chk("Cuenta nueva no es admin", False, bool(u["es_admin"]))
    c_nuevo = app.test_client()
    with c_nuevo.session_transaction() as s:
        s.update(usuario_id=uid_prueba, usuario_email=u["email"], es_admin=False)
    r = c_nuevo.get("/consorcios")
    chk("Inactiva: la manda al login", True, r.status_code == 302 and "/login" in r.headers["Location"])

    # 2) Usuario activo NO admin, con sesión que dice es_admin=True (rol viejo en la sesión)
    print("[2] Usuario no admin")
    db._exec("UPDATE usuarios SET activo=TRUE, es_admin=FALSE WHERE id=%s", (uid_prueba,))
    db._exec("INSERT INTO permisos_consorcio (usuario_id, consorcio_id) VALUES (%s,%s)", (uid_prueba, cid))
    c_user = app.test_client()
    with c_user.session_transaction() as s:
        s.update(usuario_id=uid_prueba, usuario_email=u["email"], es_admin=True, consorcio_id=cid)
    n_cons = n("SELECT count(*) n FROM consorcios")
    c_user.post(f"/consorcios/{cid}/eliminar")
    chk("No puede eliminar el consorcio", True, db.get_consorcio(cid) is not None)
    c_user.post("/consorcios/nuevo", data={"nombre": TAG})
    chk("No puede crear consorcios", n_cons, n("SELECT count(*) n FROM consorcios"))
    n_gastos = n("SELECT count(*) n FROM gastos WHERE consorcio_id=%s", (cid,))
    c_user.post("/config/reset")
    chk("No puede resetear datos", n_gastos, n("SELECT count(*) n FROM gastos WHERE consorcio_id=%s", (cid,)))
    with c_user.session_transaction() as s:
        chk("El rol se refresca desde la base", False, s.get("es_admin"))
    r = c_user.get("/admin/usuarios")
    chk("No entra a administración de usuarios", True, r.status_code == 302)

    # 3) CSRF
    print("[3] CSRF")
    r = cliente.post("/tareas/add", data={"descripcion": TAG}, headers={"Origin": "https://sitio-malo.example"})
    chk("POST con Origin de otro sitio → 403", 403, r.status_code)
    r = cliente.post("/tareas/add", data={"descripcion": TAG}, headers={"Referer": "https://sitio-malo.example/x"})
    chk("POST con Referer de otro sitio → 403", 403, r.status_code)
    r = cliente.post("/tareas/add", data={"descripcion": TAG}, headers={"Origin": "http://localhost"})
    chk("POST del mismo sitio pasa", 200, r.status_code)
    db._exec("DELETE FROM tareas WHERE consorcio_id=%s AND descripcion=%s", (cid, TAG))

    # 4) Validaciones del servidor
    print("[4] Validaciones")
    for valor in ("nan", "inf", "-50", "abc"):
        cliente.post("/gastos/save", data={"periodo": MES, "concepto": TAG, "importe": valor, "tipo": "FIJO"})
    chk("Gasto con importe nan/inf/negativo/texto: rechazado", 0,
        n("SELECT count(*) n FROM gastos WHERE consorcio_id=%s AND concepto=%s", (cid, TAG)))
    cliente.post("/gastos/save", data={"periodo": MES, "concepto": TAG, "importe": "10", "tipo": "FONDO_RESERVA"})
    chk("Gasto nuevo tipo FONDO_RESERVA a mano: rechazado", 0,
        n("SELECT count(*) n FROM gastos WHERE consorcio_id=%s AND concepto=%s", (cid, TAG)))
    hoy = db.fecha_sistema().strftime("%Y-%m-%d")
    cliente.post("/caja/save", data={"periodo": MES, "fecha": hoy, "descripcion": TAG, "tipo": "OTRO", "importe": "10"})
    cliente.post("/caja/save", data={"periodo": MES, "fecha": hoy, "descripcion": TAG, "tipo": "ENTRADA", "importe": "inf"})
    chk("Caja con tipo inválido o importe inf: rechazado", 0,
        n("SELECT count(*) n FROM caja WHERE consorcio_id=%s AND descripcion=%s", (cid, TAG)))
    cliente.post("/facturas/save", data={"fecha": hoy, "descripcion": TAG, "importe": "-5", "proveedor_nombre": TAG})
    chk("Factura con importe negativo: rechazada", 0,
        n("SELECT count(*) n FROM facturas WHERE consorcio_id=%s AND descripcion=%s", (cid, TAG)))
    # Factura pagada: no se puede "despagar" reenviándola con su id
    cliente.post("/facturas/save", data={"fecha": hoy, "descripcion": TAG, "importe": "100", "proveedor_nombre": TAG})
    fid = db._fetchone("SELECT id FROM facturas WHERE consorcio_id=%s AND descripcion=%s", (cid, TAG))["id"]
    cliente.post(f"/facturas/pagar/{fid}", data={"fecha_pago": hoy})
    cliente.post("/facturas/save", data={"id": fid, "fecha": hoy, "descripcion": TAG, "importe": "999",
                                         "proveedor_nombre": TAG})
    fac = db.get_factura_by_id(fid)
    chk("Factura pagada reenviada con su id: sigue PAGADA y sin cambios", ("PAGADA", 100.0),
        (fac["estado"], fac["importe"]))
    cliente.post(f"/facturas/pagar/{fid}", data={"fecha_pago": hoy})
    chk("Pagar dos veces la misma factura: una sola salida en Caja", 1,
        n("SELECT count(*) n FROM caja WHERE consorcio_id=%s AND factura_id=%s", (cid, fid)))
    db._exec("DELETE FROM caja WHERE consorcio_id=%s AND factura_id=%s", (cid, fid))
    db._exec("DELETE FROM gastos WHERE consorcio_id=%s AND factura_id=%s", (cid, fid))
    db._exec("DELETE FROM facturas WHERE id=%s", (fid,))
    if not db.liq_esta_cerrada(db._next_periodo(MES)):
        db.generar_liquidacion(db._next_periodo(MES))

    cfg0 = db.get_config().get("saldo_inicial_caja")
    cliente.post("/apertura", data={"saldo_inicial_caja": "nan"})
    chk("Apertura con saldo nan: rechazada (sin cambios)", cfg0, db.get_config().get("saldo_inicial_caja"))
    # Si la base de prueba no tiene ninguna liquidación cerrada, se cierra la primera SOLO durante
    # la prueba (se restaura en el finally) para probar pagos y gastos de período cerrado.
    if not db.get_ultima_liq_cerrada():
        primera = db._fetchone("SELECT periodo, estado FROM liquidaciones_estado WHERE consorcio_id=%s "
                               "ORDER BY periodo LIMIT 1", (cid,))
        if primera:
            estado_restaurar = (primera["periodo"], primera["estado"])
            db._exec("UPDATE liquidaciones_estado SET estado='CERRADA' WHERE consorcio_id=%s AND periodo=%s",
                     (cid, primera["periodo"]))
            print(f"  --  liquidación {primera['periodo']} cerrada temporalmente para la prueba")
    pc = db.periodo_cobranza()
    if pc:
        uf = str(db.get_liquidacion(pc)[0]["unidad"])
        n_pagos = n("SELECT count(*) n FROM pagos WHERE consorcio_id=%s", (cid,))
        cliente.post(f"/cobranzas/{pc}/pagar/{uf}", data={"monto_pagado": "nan", "fecha_pago": hoy})
        chk("Pago de expensas con monto nan: rechazado", n_pagos, n("SELECT count(*) n FROM pagos WHERE consorcio_id=%s", (cid,)))
    else:
        print("  --  (sin liquidación cerrada en la base de prueba: no se prueba el pago con nan)")
    cerrada = db.get_ultima_liq_cerrada()
    if cerrada:
        mes_c = db._prev_periodo(cerrada)
        g = db._fetchone("SELECT id, importe FROM gastos WHERE consorcio_id=%s AND trim(periodo)=%s "
                         "AND tipo <> 'FONDO_RESERVA' LIMIT 1", (cid, mes_c))
        cliente.post("/gastos/save", data={"periodo": mes_c, "concepto": TAG, "importe": "10", "tipo": "FIJO"})
        chk(f"Gasto nuevo en {mes_c} (liquidación cerrada): rechazado", 0,
            n("SELECT count(*) n FROM gastos WHERE consorcio_id=%s AND concepto=%s", (cid, TAG)))
        if g:
            cliente.post(f"/gastos/delete/{g['id']}/{mes_c}")
            chk(f"Borrar gasto de {mes_c} (cerrada): rechazado", 1,
                n("SELECT count(*) n FROM gastos WHERE id=%s", (g["id"],)))
    else:
        print("  --  (sin liquidación cerrada en la base de prueba: no se prueban gastos de período cerrado)")

    # 5) SECRET_KEY obligatoria en el servidor
    print("[5] SECRET_KEY")
    env = {k: v for k, v in os.environ.items() if k != "SECRET_KEY"}
    env["RENDER"] = "true"
    p = subprocess.run([sys.executable, "-c", "import app"], cwd=RAIZ, env=env, capture_output=True, text=True)
    chk("En el servidor sin SECRET_KEY no arranca", True, p.returncode != 0 and "SECRET_KEY" in p.stderr)
finally:
    if estado_restaurar:
        db._exec("UPDATE liquidaciones_estado SET estado=%s WHERE consorcio_id=%s AND periodo=%s",
                 (estado_restaurar[1], cid, estado_restaurar[0]))
        chk("Limpieza: estado de la liquidación restaurado", estado_restaurar[1],
            db.get_liq_estado(estado_restaurar[0]))
    db._exec("DELETE FROM gastos WHERE consorcio_id=%s AND concepto=%s", (cid, TAG))
    db._exec("DELETE FROM caja WHERE consorcio_id=%s AND descripcion=%s", (cid, TAG))
    db._exec("DELETE FROM facturas WHERE consorcio_id=%s AND descripcion=%s", (cid, TAG))
    db._exec("DELETE FROM tareas WHERE consorcio_id=%s AND descripcion=%s", (cid, TAG))
    db._exec("DELETE FROM consorcios WHERE nombre=%s", (TAG,))
    if uid_prueba:
        db._exec("DELETE FROM permisos_consorcio WHERE usuario_id=%s", (uid_prueba,))
        db._exec("DELETE FROM usuarios WHERE id=%s", (uid_prueba,))
    chk("Limpieza: usuario de prueba borrado", 0, n("SELECT count(*) n FROM usuarios WHERE google_id=%s", (TAG,)))

print(f"\n{ok_total} OK, {len(fallas)} con falla" + (f": {fallas}" if fallas else ""))
