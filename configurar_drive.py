"""
configurar_drive.py — Setup interactivo de Google Drive.

Ejecutar UNA VEZ antes de usar la integración con Drive:

    python configurar_drive.py

Pasos que realiza:
  1. Verifica que credentials.json esté en la carpeta credentials/
  2. Abre el navegador para autorizar el acceso a Google Drive (OAuth2)
  3. Guarda el token en credentials/token.json
  4. Crea las carpetas ConsorcioApp/produccion/ y ConsorcioApp/pruebas/ en Drive
  5. Opcionalmente sube el Excel local actual a Drive (produccion)

Requisitos previos:
  - Tener una cuenta de Google
  - Haber creado un proyecto en Google Cloud Console con la Drive API habilitada
  - Haber descargado credentials.json (tipo "App de escritorio") y copiado
    a la carpeta credentials/ del proyecto

Guía paso a paso para obtener credentials.json:
  https://developers.google.com/drive/api/quickstart/python
  (Sección: "Authorize credentials for a desktop application")
"""

import os
import sys

_BASE_DIR = os.path.dirname(__file__)
_CREDS_DIR = os.path.join(_BASE_DIR, "credentials")
_CREDS_JSON = os.path.join(_CREDS_DIR, "credentials.json")
_TOKEN_JSON = os.path.join(_CREDS_DIR, "token.json")


def _separador(char="─", ancho=60):
    print(char * ancho)


def _titulo(texto):
    _separador("═")
    print(f"  {texto}")
    _separador("═")


def _paso(num, texto):
    print(f"\n[{num}] {texto}")


def _ok(texto):
    print(f"    ✓ {texto}")


def _error(texto):
    print(f"    ✗ {texto}")


def _info(texto):
    print(f"    → {texto}")


def verificar_dependencias():
    """Verifica que las librerías de Google estén instaladas."""
    _paso("A", "Verificando dependencias...")
    faltantes = []
    for pkg in ["google.oauth2", "google_auth_oauthlib", "googleapiclient"]:
        try:
            __import__(pkg.replace("-", "_"))
            _ok(pkg)
        except ImportError:
            _error(f"{pkg} — NO instalado")
            faltantes.append(pkg)

    if faltantes:
        print("\n  Instalá las dependencias primero:")
        print("    pip install google-api-python-client google-auth-oauthlib google-auth-httplib2")
        sys.exit(1)


def verificar_credentials_json():
    """Verifica que credentials.json exista."""
    _paso("B", "Verificando credentials.json...")

    os.makedirs(_CREDS_DIR, exist_ok=True)

    if os.path.exists(_CREDS_JSON):
        _ok(f"credentials.json encontrado en {_CREDS_DIR}/")
        return True

    _error("credentials.json NO encontrado.")
    print("""
  Para obtenerlo:

  1. Abrí https://console.cloud.google.com/
  2. Creá un proyecto nuevo (o seleccioná uno existente)
  3. Habilitá la API de Google Drive:
       APIs y servicios → Biblioteca → "Google Drive API" → Habilitar
  4. Creá credenciales OAuth 2.0:
       APIs y servicios → Credenciales → Crear credenciales
       → ID de cliente OAuth → Tipo: "App de escritorio"
  5. Descargá el JSON y copialo como:
       credentials/credentials.json
  (dentro de la carpeta del proyecto)

  Luego volvé a ejecutar este script.
""")
    return False


def ejecutar_oauth():
    """Corre el flujo OAuth2 y guarda token.json."""
    _paso("C", "Autorizando acceso a Google Drive...")

    if os.path.exists(_TOKEN_JSON):
        print("    token.json ya existe.")
        resp = input("    ¿Regenerar el token? (s/N): ").strip().lower()
        if resp != "s":
            _ok("Usando token existente.")
            return

    print("    Abriendo el navegador para autorizar...")
    print("    (Si no se abre automáticamente, copiá la URL que aparece en la consola)")
    print()

    from drive_sync import DriveSync
    DriveSync.run_oauth_flow()
    _ok(f"Token guardado en {_TOKEN_JSON}")


def crear_carpetas():
    """Crea la estructura de carpetas en Drive."""
    _paso("D", "Creando carpetas en Google Drive...")

    from drive_sync import DriveSync
    for env in ("produccion", "pruebas"):
        drive = DriveSync(env=env)
        try:
            drive._ensure_folders()
            _ok(f"ConsorcioApp/{env}/  y  ConsorcioApp/{env}/facturas/")
        except Exception as exc:
            _error(f"Error creando carpetas para '{env}': {exc}")
            raise


def subir_excel_local(env="produccion"):
    """Ofrece subir el Excel local actual a Drive."""
    _paso("E", "Subir Excel local a Drive...")

    db_path = os.path.join(_BASE_DIR, "data", "edificio_brasil.xlsx")
    if not os.path.exists(db_path):
        _info("No existe data/edificio_brasil.xlsx — nada que subir.")
        return

    tamanio_kb = os.path.getsize(db_path) // 1024
    print(f"    Archivo: {db_path} ({tamanio_kb} KB)")
    resp = input(f"    ¿Subir a ConsorcioApp/{env}/ en Drive? (S/n): ").strip().lower()
    if resp == "n":
        _info("Omitido. Podés subirlo más tarde iniciando la app normalmente.")
        return

    from drive_sync import DriveSync
    drive = DriveSync(env=env)
    print("    Subiendo...")
    drive.upload_excel(db_path)
    _ok("Excel subido correctamente.")


def mostrar_resumen():
    """Muestra el estado final de la configuración."""
    _separador()
    print()
    print("  CONFIGURACIÓN COMPLETADA")
    print()

    from drive_sync import DriveSync
    for env in ("produccion", "pruebas"):
        st = DriveSync(env=env).status()
        estado_excel = "✓ Excel en Drive" if st["excel_en_drive"] else "— Sin Excel (se sube al primer guardado)"
        print(f"  [{env:12s}]  {st['carpeta_drive']:35s}  {estado_excel}")

    print()
    _separador()
    print()
    print("  Próximos pasos:")
    print("    • Para iniciar en modo producción:  iniciar.bat")
    print("    • Para iniciar en modo pruebas:     iniciar_pruebas.bat")
    print()
    print("  El Excel se descargará de Drive automáticamente al iniciar la app.")
    print("  Cada guardado en la app sube el Excel a Drive en segundo plano.")
    print()
    _separador()


def main():
    _titulo("Configuración de Google Drive — Consorcio App")

    verificar_dependencias()

    if not verificar_credentials_json():
        sys.exit(1)

    ejecutar_oauth()
    crear_carpetas()
    subir_excel_local(env="produccion")
    mostrar_resumen()


if __name__ == "__main__":
    main()
