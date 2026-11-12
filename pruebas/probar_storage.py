"""
Prueba de archivos en el almacenamiento (v11.0): comprobantes de facturas y adjuntos de
notificaciones.

Corre contra lo que diga .env.local:
- con STORAGE_S3_* → el bucket S3 (consorcio-tst o un S3 local);
- sin esas variables → el disco (data/archivos/).

    pruebas/correr_en_docker.sh pruebas/probar_storage.py

Arma un consorcio temporal, sube un PDF y una imagen como comprobantes, los vuelve a leer por
la app, revisa el backup y la exportación, sube y lee un adjunto de notificación, y controla
que un consorcio no vea los archivos de otro. Al final borra los archivos del consorcio
temporal y el consorcio.
"""
import io
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from escenario import Escenario  # noqa: E402

PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGBA", (40, 20), (200, 30, 30, 255)).save(buf, "PNG")
    return buf.getvalue()


with Escenario("Prueba storage v11") as e:
    import storage
    db, cli = e.db, e.cliente
    print("Almacenamiento:", storage.descripcion())

    try:
        f1 = db.save_factura({"fecha": "2026-10-05", "proveedor_nombre": "Ascensores Ñandú S.A.",
                              "descripcion": "Abono", "importe": 1000, "categoria": "EXPENSAS"})
        f2 = db.save_factura({"fecha": "2026-10-06", "proveedor_nombre": "Limpieza",
                              "descripcion": "Insumos", "importe": 500, "categoria": "EXPENSAS"})

        # 1. Subir un PDF
        r = cli.post(f"/facturas/{f1}/upload", data={"comprobante": (io.BytesIO(PDF), "factura.pdf")},
                     content_type="multipart/form-data")
        ruta1 = db.get_factura_by_id(f1).get("archivo_pdf")
        e.check("PDF: redirige", 302, r.status_code)
        e.check("PDF: ruta guardada en la factura", True,
                bool(ruta1) and ruta1.startswith("facturas/ascensores_nandu_sa/"), None)
        e.check("PDF: está en el almacenamiento", PDF, storage.leer(f"{e.cid}/{ruta1}"))
        e.check("PDF: no quedó en el disco del consorcio", False,
                os.path.exists(os.path.join(db.get_data_dir(), ruta1)))

        # 2. Verlo por la app
        r = cli.get(f"/facturas/{f1}/comprobante")
        e.check("PDF: la app lo sirve", (200, "application/pdf", PDF),
                (r.status_code, r.mimetype, r.data))

        # 3. Subir una imagen: se convierte a PDF
        r = cli.post(f"/facturas/{f2}/upload", data={"comprobante": (io.BytesIO(_png()), "foto.png")},
                     content_type="multipart/form-data")
        r = cli.get(f"/facturas/{f2}/comprobante")
        e.check("Imagen: se sirve convertida a PDF", (200, True),
                (r.status_code, r.data.startswith(b"%PDF")))

        # 4. Imagen rota: mensaje claro, sin error 500
        r = cli.post(f"/facturas/{f2}/upload", data={"comprobante": (io.BytesIO(b"no es imagen"), "x.jpg")},
                     content_type="multipart/form-data")
        e.check("Imagen rota: no rompe (302)", 302, r.status_code)
        e.check("Imagen rota: avisa", True, "No se pudo leer la imagen" in e.flashes(), None)

        # 5. Comprobante viejo en disco: se sigue viendo
        f3 = db.save_factura({"fecha": "2026-10-07", "proveedor_nombre": "Viejo",
                              "descripcion": "De antes", "importe": 1, "categoria": "EXPENSAS"})
        viejo = os.path.join(db.get_data_dir(), "facturas", "viejo", "2020-01-01_000000.pdf")
        os.makedirs(os.path.dirname(viejo), exist_ok=True)
        with open(viejo, "wb") as fh:
            fh.write(PDF)
        db.set_factura_archivo_pdf(f3, "facturas/viejo/2020-01-01_000000.pdf")
        r = cli.get(f"/facturas/{f3}/comprobante")
        e.check("Archivo viejo en disco: se ve", (200, PDF), (r.status_code, r.data))

        # 6. Comprobante registrado pero inexistente
        f4 = db.save_factura({"fecha": "2026-10-08", "proveedor_nombre": "Perdido",
                              "descripcion": "Sin archivo", "importe": 1, "categoria": "EXPENSAS"})
        db.set_factura_archivo_pdf(f4, "facturas/perdido/2020-01-01_000000.pdf")
        r = cli.get(f"/facturas/{f4}/comprobante")
        e.check("Inexistente: redirige con aviso", (302, True),
                (r.status_code, "no se encontró" in e.flashes()))

        # 7. Backup y exportación incluyen los comprobantes
        r = cli.get("/backup")
        z = zipfile.ZipFile(io.BytesIO(r.data))
        e.check("Backup: incluye el PDF subido", PDF, z.read(ruta1) if ruta1 in z.namelist() else None)
        e.check("Backup: incluye el archivo viejo", True,
                "facturas/viejo/2020-01-01_000000.pdf" in z.namelist(), None)
        r = cli.get("/exportar")
        z = zipfile.ZipFile(io.BytesIO(r.data))
        nombres = z.namelist()
        leeme = z.read("LEEME.txt").decode("utf-8-sig")
        e.check("Exportación: 3 comprobantes", 3, sum(n.startswith("comprobantes/") for n in nombres))
        e.check("Exportación: avisa el que falta", True,
                "no se encontraron" in leeme and "facturas/perdido/" in leeme, None)

        # 8. Adjunto de notificación
        r = cli.post("/notificaciones/upload", data={"archivo": (io.BytesIO(PDF), "aviso.pdf")},
                     content_type="multipart/form-data")
        url = (r.get_json() or {}).get("url", "")
        nombre = url.rsplit("/", 1)[-1]
        e.check("Notificación: sube", (200, True), (r.status_code, nombre.endswith(".pdf")))
        r = cli.get(f"/notificaciones/ver/{nombre}")
        e.check("Notificación: se ve", (200, PDF), (r.status_code, r.data))
        r = cli.post("/notificaciones/upload", data={"archivo": (io.BytesIO(b"x"), "x.exe")},
                     content_type="multipart/form-data")
        e.check("Notificación: rechaza .exe", 400, r.status_code)
        e.check("Notificación: nombre raro → 404", 404, cli.get("/notificaciones/ver/..%2Fx.pdf").status_code)

        # 9. Otro consorcio no ve los archivos de este
        otro = db.create_consorcio("Prueba storage v11 (otro)", "temporal")
        try:
            with cli.session_transaction() as s:
                s["consorcio_id"] = otro["id"]
            e.check("Otro consorcio: no ve la notificación", 404,
                    cli.get(f"/notificaciones/ver/{nombre}").status_code)
            e.check("Otro consorcio: no ve la factura", 302, cli.get(f"/facturas/{f1}/comprobante").status_code)
        finally:
            db.delete_consorcio(otro["id"])
            with cli.session_transaction() as s:
                s["consorcio_id"] = e.cid
            db.set_active_consorcio(*[db.get_consorcio(e.cid)[k] for k in ("data_dir_abs", "db_path_abs")])

        # 10. Claves con trucos: rechazadas
        for mala in ("../x", "a//b", "a/../b", "", "a/./b"):
            try:
                storage.leer(mala)
                ok = False
            except storage.StorageError:
                ok = True
            e.check(f"Clave inválida rechazada: {mala!r}", True, ok, None)

        # 11. Quitar, reemplazar y borrar (v11.1)
        def subir(fid, datos=PDF):
            cli.post(f"/facturas/{fid}/upload", data={"comprobante": (io.BytesIO(datos), "c.pdf")},
                     content_type="multipart/form-data")
            return db.get_factura_by_id(fid).get("archivo_pdf")

        def existe(ruta):
            return storage.leer(f"{e.cid}/{ruta}") is not None

        import time
        f5 = db.save_factura({"fecha": "2026-10-09", "proveedor_nombre": "Quitar",
                              "descripcion": "Quitar", "importe": 1, "categoria": "EXPENSAS"})
        r5 = subir(f5)
        e.flashes()
        r = cli.post(f"/facturas/{f5}/comprobante/quitar")
        e.check("Quitar: la factura queda sin comprobante", (302, ""),
                (r.status_code, db.get_factura_by_id(f5).get("archivo_pdf")))
        e.check("Quitar: el archivo se borró", False, existe(r5))
        e.check("Quitar: avisa", True, "Comprobante quitado" in e.flashes(), None)
        e.check("Quitar sin comprobante: avisa", (302, True),
                (cli.post(f"/facturas/{f5}/comprobante/quitar").status_code, "no tiene comprobante" in e.flashes()))

        viejo_ruta = subir(f5)
        time.sleep(1.1)                      # el nombre del archivo lleva la hora con segundos
        nuevo_ruta = subir(f5, PDF + b"%v2")
        e.check("Reemplazar: el archivo anterior se borró", (False, True),
                (existe(viejo_ruta), existe(nuevo_ruta)))

        r = cli.post(f"/facturas/delete/{f5}")
        e.check("Eliminar factura: se borra su comprobante", False, existe(nuevo_ruta))

        f6 = db.save_factura({"fecha": "2026-10-10", "proveedor_nombre": "Compartido",
                              "descripcion": "A", "importe": 1, "categoria": "EXPENSAS"})
        f7 = db.save_factura({"fecha": "2026-10-10", "proveedor_nombre": "Compartido",
                              "descripcion": "B", "importe": 1, "categoria": "EXPENSAS"})
        r6 = subir(f6)
        db.set_factura_archivo_pdf(f7, r6)
        cli.post(f"/facturas/{f6}/comprobante/quitar")
        e.check("Archivo compartido por dos facturas: no se borra", True, existe(r6), None)
        cli.post(f"/facturas/{f7}/comprobante/quitar")
        e.check("Archivo compartido: se borra al quitarlo de la última", False, existe(r6))

        cli.post(f"/facturas/{f3}/comprobante/quitar")
        e.check("Quitar archivo viejo en disco: se borra del disco", False, os.path.exists(viejo))

        # 12. Eliminar un consorcio borra todos sus archivos
        otro = db.create_consorcio("Prueba storage v11 (eliminar)", "temporal")
        try:
            with cli.session_transaction() as s:
                s["consorcio_id"] = otro["id"]
            fo = None
            cli.get("/facturas")                 # activa el otro consorcio en la capa de datos
            fo = db.save_factura({"fecha": "2026-10-11", "proveedor_nombre": "Otro",
                                  "descripcion": "x", "importe": 1, "categoria": "EXPENSAS"})
            subir(fo)
            cli.post("/notificaciones/upload", data={"archivo": (io.BytesIO(PDF), "a.pdf")},
                     content_type="multipart/form-data")
            antes = len(storage.listar(f"{otro['id']}/"))
            r = cli.post(f"/consorcios/{otro['id']}/eliminar")
            e.check("Eliminar consorcio: tenía 2 archivos y no queda ninguno", (2, []),
                    (antes, storage.listar(f"{otro['id']}/")))
            e.check("Eliminar consorcio: no tocó los archivos de los demás", True,
                    existe(ruta1), None)
        finally:
            if db.get_consorcio(otro["id"]):
                db.delete_consorcio(otro["id"])
            storage.borrar_prefijo(f"{otro['id']}/")
            with cli.session_transaction() as s:
                s["consorcio_id"] = e.cid
            db.set_active_consorcio(*[db.get_consorcio(e.cid)[k] for k in ("data_dir_abs", "db_path_abs")])

    finally:
        import shutil
        shutil.rmtree(os.path.join(db.get_data_dir(), "facturas", "viejo"), ignore_errors=True)
        n = storage.borrar_prefijo(f"{e.cid}/")
        print(f"Archivos del consorcio temporal borrados del almacenamiento: {n}")
        e.check("Limpieza: no quedan archivos", [], storage.listar(f"{e.cid}/"))
