"""
Escenario de prueba aislado (v10.3): un consorcio TEMPORAL armado desde cero, para que las
pruebas no dependan de los datos que tenga la base de prueba.

    from escenario import Escenario
    with Escenario("Prueba anular pagos") as e:
        e.fecha("2026-10-01"); e.generar("2026-10"); e.cerrar("2026-10")
        e.pagar("2026-10", "1", 100000, "2026-11-05")
        e.check("UF 1 pagada", "TOTAL", e.fila("2026-10", "1")["tipo_pago"])
    # al salir: borra el consorcio (y en cascada sus liquidaciones, pagos, Caja, certificados)
    # y termina el script con código 1 si algún control falló.

El consorcio: 2 UF ("1" y "2") al 50 % en la categoría EXPENSAS, gastos fijos de $200.000 por
mes (sep a dic 2026) → expensa de $100.000 por UF, sin fondo de reserva, tasa de mora 3 %
mensual desde 01/09/2026 y vencimiento el día 10.
"""
import sys
from contextlib import contextmanager

from entorno_prueba import preparar

MESES_GASTOS = ("2026-09", "2026-10", "2026-11", "2026-12")


class Escenario:
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.resultados = []

    # ── armado y limpieza ────────────────────────────────────────────────────
    def __enter__(self):
        self.app, self.db, self.cliente = preparar()
        db = self.db
        db.ensure_v10()          # en la app lo hace before_request; acá se usa la capa de datos antes
        db.ensure_auditoria()
        db.ensure_libres_deuda()
        c = db.create_consorcio(self.nombre, f"temporal: {sys.argv[0]}")
        self.cid = c["id"]
        db.set_active_consorcio(c["data_dir_abs"], c["db_path_abs"])
        with self.cliente.session_transaction() as s:
            s["consorcio_id"] = self.cid
        db.save_config({"edificio_nombre": self.nombre, "tasa_mora": "3", "dia_vencimiento": "10",
                        "fondo_reserva_mensual": "0", "saldo_inicial_caja": "0",
                        "saldo_inicial_caja_fecha": "2026-09-01"})
        db.add_categoria("EXPENSAS")
        for num in ("1", "2"):
            db.save_unidad({"numero": num, "descripcion": f"Depto {num}", "propietario": f"Prop {num}",
                            "deuda_inicial": 0, "pct_EXPENSAS": 50})
        for mes in MESES_GASTOS:
            db.save_gasto(mes, "Gastos generales", 200000, "FIJO")
        self.fecha("2026-09-01")
        self.cliente.post("/config/tasa-mora/add", data={"vigente_desde": "2026-09-01", "tasa": "3",
                                                         "fundamento": "Prueba"})
        print(f"Consorcio temporal '{self.nombre}' ({self.cid}) creado.")
        return self

    def __exit__(self, tipo, valor, tb):
        try:
            self.db.delete_consorcio(self.cid)
            print(f"Consorcio temporal {self.cid} borrado.")
        except Exception as ex:  # que la limpieza no tape el error original
            print(f"⚠️ No se pudo borrar el consorcio temporal {self.cid}: {ex}")
        if tipo is not None:
            return False         # muestra el error de la prueba
        ok = sum(1 for r in self.resultados if r[3])
        print(f"\nResultado: {ok}/{len(self.resultados)} OK")
        sys.exit(0 if ok == len(self.resultados) else 1)

    # ── acciones ─────────────────────────────────────────────────────────────
    def fecha(self, f: str):
        """Fija la fecha del sistema ('' o None la quita)."""
        data = {"fecha_sistema": f} if f else {"accion": "quitar"}
        self.cliente.post("/config/fecha-sistema", data=data)

    def generar(self, periodo: str):
        return self.cliente.post(f"/liquidacion/generar/{periodo}")

    def cerrar(self, periodo: str, interes_uf=()):
        """Cierra la liquidación; `interes_uf` son las UF a las que se les cobra el interés."""
        return self.cliente.post(f"/liquidacion/cerrar/{periodo}", data={"interes_uf": list(interes_uf)})

    def pagar(self, periodo: str, uf: str, monto: float, fecha_pago: str = None, bonificacion: float = 0):
        data = {"monto_pagado": str(monto), "bonificacion": str(bonificacion)}
        if fecha_pago:
            data["fecha_pago"] = fecha_pago
        return self.cliente.post(f"/cobranzas/{periodo}/pagar/{uf}", data=data)

    # ── lecturas ─────────────────────────────────────────────────────────────
    def fila(self, periodo: str, uf: str, simular: bool = False) -> dict:
        return next(r for r in self.db.get_liquidacion(periodo, simular=simular) if str(r["unidad"]) == str(uf))

    def pagos(self, periodo: str, uf: str = None) -> list:
        return self.db.get_pagos(periodo, uf)

    def caja_expensas(self, periodo: str) -> list:
        return sorted((str(r["fecha"]), r["descripcion"], float(r["importe"])) for r in self.db._fetchall(
            "SELECT fecha, descripcion, importe FROM caja WHERE consorcio_id=%s AND categoria='Expensas' "
            "AND descripcion LIKE %s", (self.cid, f"Expensas {periodo} - %")))

    def flashes(self) -> str:
        with self.cliente.session_transaction() as s:
            msgs = [m for _, m in s.get("_flashes", [])]
            s.pop("_flashes", None)
        return " | ".join(msgs)

    # ── controles ────────────────────────────────────────────────────────────
    def check(self, caso, esperado, obtenido, ok=None):
        """Registra un control. Sin `ok`, compara obtenido == esperado."""
        if ok is None:
            ok = obtenido == esperado
        self.resultados.append((caso, esperado, obtenido, bool(ok)))
        print(f"{'✅' if ok else '❌'} {caso}: esperado {esperado} | obtenido {obtenido}")
        return ok

    @contextmanager
    def como_usuario_no_admin(self):
        """Sesión de un usuario NO administrador real (activo, creado y borrado acá). El rol se
        lee de la base en cada pedido (v9.8): cambiar es_admin en la sesión no alcanza."""
        db = self.db
        uid = db._fetchone("""INSERT INTO usuarios (google_id, email, nombre, activo, es_admin)
                              VALUES (%s, %s, 'Prueba no admin', TRUE, FALSE) RETURNING id""",
                           (f"prueba-no-admin-{self.cid}", f"no-admin-{self.cid}@prueba.local"))["id"]
        with self.cliente.session_transaction() as s:
            anterior = dict(s)
            s["usuario_id"] = uid
            s["es_admin"] = True  # a propósito: no tiene que servir
        try:
            yield uid
        finally:
            with self.cliente.session_transaction() as s:
                s.clear()
                s.update(anterior)
            db._exec("DELETE FROM usuarios WHERE id=%s", (uid,))
