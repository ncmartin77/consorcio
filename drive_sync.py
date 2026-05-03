"""
drive_sync.py — Sincronización con Google Drive.

Gestiona carga y descarga del Excel principal y los comprobantes PDF
de facturas hacia/desde Google Drive.

Estructura en Drive:
    ConsorcioApp/
    ├── produccion/
    │   ├── edificio_brasil.xlsx
    │   └── facturas/
    │       └── {proveedor}/
    │           └── {timestamp}.pdf
    └── pruebas/
        ├── edificio_brasil.xlsx
        └── facturas/
            └── {proveedor}/
                └── {timestamp}.pdf

Uso típico (en excel_db.py):
    from drive_sync import DriveSync
    drive = DriveSync(env="produccion")
    drive.download_excel(local_path)   # al arrancar
    drive.upload_excel_async(local_path)  # en cada _save_wb()
"""

import os
import threading
import logging

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(__file__)
_CREDENTIALS_DIR = os.path.join(_BASE_DIR, "credentials")
_SCOPES = ["https://www.googleapis.com/auth/drive"]

# Nombre de la carpeta raíz en Mi Drive
DRIVE_ROOT_FOLDER = "ConsorcioApp"


class DriveSync:
    """
    Sincroniza archivos del proyecto con Google Drive via la API v3.

    Los uploads pesados (Excel, PDF) se ofrecen en versión asíncrona
    (_async) para no bloquear las respuestas HTTP de Flask.
    """

    def __init__(self, env: str = "produccion"):
        if env not in ("produccion", "pruebas"):
            raise ValueError(f"env debe ser 'produccion' o 'pruebas', recibido: {env!r}")
        self.env = env
        self._service = None
        self._env_folder_id: str | None = None
        self._facturas_folder_id: str | None = None
        self._excel_file_id: str | None = None
        self._lock = threading.Lock()

    # ── Verificación de estado ─────────────────────────────────────────────────

    @classmethod
    def is_configured(cls) -> bool:
        """
        True si token.json existe (el flujo OAuth ya fue completado).
        La app sólo intenta usar Drive cuando esto es True.
        """
        return os.path.exists(os.path.join(_CREDENTIALS_DIR, "token.json"))

    @classmethod
    def has_client_secrets(cls) -> bool:
        """
        True si credentials.json existe (descargado de Google Cloud Console).
        Requerido para correr el flujo OAuth por primera vez.
        """
        return os.path.exists(os.path.join(_CREDENTIALS_DIR, "credentials.json"))

    # ── Autenticación OAuth2 ───────────────────────────────────────────────────

    def _authenticate(self):
        """
        Carga el token guardado y lo refresca si venció.
        No abre el navegador — eso lo hace configurar_drive.py.
        Lanza RuntimeError si token.json no existe.
        """
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_path = os.path.join(_CREDENTIALS_DIR, "token.json")
        if not os.path.exists(token_path):
            raise RuntimeError(
                "token.json no encontrado. Ejecuta: python configurar_drive.py"
            )

        creds = Credentials.from_authorized_user_file(token_path, _SCOPES)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                # Guardar token refrescado
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
                logger.info("[Drive] Token refrescado automáticamente.")
            else:
                raise RuntimeError(
                    "El token de Drive venció y no puede refrescarse. "
                    "Ejecuta: python configurar_drive.py"
                )

        self._service = build("drive", "v3", credentials=creds)

    @classmethod
    def run_oauth_flow(cls):
        """
        Ejecuta el flujo OAuth interactivo (abre el navegador).
        Solo debe llamarse desde configurar_drive.py, nunca desde Flask.
        Requiere que credentials.json exista en credentials/.
        """
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        client_secrets = os.path.join(_CREDENTIALS_DIR, "credentials.json")
        if not os.path.exists(client_secrets):
            raise FileNotFoundError(
                f"No se encontró credentials.json en {_CREDENTIALS_DIR}/\n"
                "Descárgalo desde Google Cloud Console y copialo ahí."
            )

        flow = InstalledAppFlow.from_client_secrets_file(client_secrets, _SCOPES)
        creds = flow.run_local_server(port=0)

        os.makedirs(_CREDENTIALS_DIR, exist_ok=True)
        token_path = os.path.join(_CREDENTIALS_DIR, "token.json")
        with open(token_path, "w") as f:
            f.write(creds.to_json())

        logger.info(f"[Drive] token.json guardado en {token_path}")
        return build("drive", "v3", credentials=creds)

    def _svc(self):
        """Devuelve el servicio Drive, autenticando si es la primera vez."""
        if self._service is None:
            self._authenticate()
        return self._service

    # ── Gestión de carpetas ────────────────────────────────────────────────────

    def _get_or_create_folder(self, name: str, parent_id: str | None = None) -> str:
        """Busca una carpeta por nombre en Drive. Si no existe, la crea. Devuelve su ID."""
        query = (
            f"mimeType='application/vnd.google-apps.folder'"
            f" and name='{name}'"
            f" and trashed=false"
        )
        if parent_id:
            query += f" and '{parent_id}' in parents"

        results = self._svc().files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]

        metadata: dict = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]

        folder = self._svc().files().create(body=metadata, fields="id").execute()
        logger.info(f"[Drive] Carpeta creada: {name}")
        return folder["id"]

    def _ensure_folders(self):
        """
        Garantiza que existan en Drive:
            ConsorcioApp/{env}/
            ConsorcioApp/{env}/facturas/
        Cachea los IDs para no repetir llamadas a la API.
        """
        if self._env_folder_id:
            return
        with self._lock:
            if self._env_folder_id:  # double-check tras adquirir el lock
                return
            root_id = self._get_or_create_folder(DRIVE_ROOT_FOLDER)
            env_id = self._get_or_create_folder(self.env, parent_id=root_id)
            facturas_id = self._get_or_create_folder("facturas", parent_id=env_id)
            self._env_folder_id = env_id
            self._facturas_folder_id = facturas_id

    def _find_file(self, name: str, parent_id: str) -> str | None:
        """Busca un archivo por nombre dentro de una carpeta. Devuelve ID o None."""
        query = f"name='{name}' and '{parent_id}' in parents and trashed=false"
        results = self._svc().files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        return files[0]["id"] if files else None

    # ── Excel principal ────────────────────────────────────────────────────────

    def download_excel(self, local_path: str) -> bool:
        """
        Descarga edificio_brasil.xlsx desde Drive hacia local_path.
        Devuelve True si el archivo existía en Drive y fue descargado.
        Devuelve False si no existe en Drive (primera vez) o hay error de red.
        """
        from googleapiclient.http import MediaIoBaseDownload

        try:
            self._ensure_folders()
            file_id = self._find_file("edificio_brasil.xlsx", self._env_folder_id)
            if not file_id:
                logger.info("[Drive] edificio_brasil.xlsx no encontrado en Drive.")
                return False

            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            request = self._svc().files().get_media(fileId=file_id)
            with open(local_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            self._excel_file_id = file_id
            logger.info(f"[Drive] Excel descargado → {local_path}")
            return True

        except Exception as exc:
            logger.error(f"[Drive] Error al descargar Excel: {exc}")
            return False

    def upload_excel(self, local_path: str):
        """
        Sube el Excel local a Drive.
        Si ya existe en Drive, lo actualiza (PUT). Si no, lo crea (POST).
        """
        from googleapiclient.http import MediaFileUpload

        try:
            self._ensure_folders()
            media = MediaFileUpload(
                local_path,
                mimetype=(
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"
                ),
                resumable=False,
            )

            # Buscar ID si no lo tenemos cacheado
            if not self._excel_file_id:
                self._excel_file_id = self._find_file(
                    "edificio_brasil.xlsx", self._env_folder_id
                )

            if self._excel_file_id:
                # Actualizar archivo existente
                self._svc().files().update(
                    fileId=self._excel_file_id,
                    media_body=media,
                ).execute()
            else:
                # Crear archivo nuevo
                metadata = {
                    "name": "edificio_brasil.xlsx",
                    "parents": [self._env_folder_id],
                }
                result = (
                    self._svc()
                    .files()
                    .create(body=metadata, media_body=media, fields="id")
                    .execute()
                )
                self._excel_file_id = result["id"]

            logger.info(f"[Drive] Excel subido ({self.env}).")

        except Exception as exc:
            logger.error(f"[Drive] Error al subir Excel: {exc}")

    def upload_excel_async(self, local_path: str):
        """
        Sube el Excel en un thread daemon para no bloquear la respuesta HTTP.
        Si ya hay un upload en curso, el nuevo lo sobreescribirá en Drive al
        terminar (el último en escribir gana, lo cual es correcto para un
        sistema de un solo usuario).
        """
        threading.Thread(
            target=self.upload_excel,
            args=(local_path,),
            daemon=True,
        ).start()

    # ── Comprobantes PDF ───────────────────────────────────────────────────────

    def upload_factura(self, local_path: str, relative_path: str):
        """
        Sube un comprobante PDF de factura a Drive.

        Args:
            local_path:     Ruta absoluta al PDF en disco local.
            relative_path:  Ruta relativa desde DATA_DIR, ej:
                            'facturas/proveedor_sa/2026-04-11_143022.pdf'
        """
        from googleapiclient.http import MediaFileUpload

        try:
            self._ensure_folders()

            # Parsear ruta: facturas/{proveedor}/{archivo.pdf}
            parts = relative_path.replace("\\", "/").split("/")
            if len(parts) < 3:
                logger.warning(
                    f"[Drive] Ruta de factura con formato inesperado: {relative_path}"
                )
                return

            proveedor_dir = parts[1]
            filename = parts[2]

            sub_folder_id = self._get_or_create_folder(
                proveedor_dir, parent_id=self._facturas_folder_id
            )
            media = MediaFileUpload(local_path, mimetype="application/pdf", resumable=False)
            metadata = {"name": filename, "parents": [sub_folder_id]}
            self._svc().files().create(
                body=metadata, media_body=media, fields="id"
            ).execute()
            logger.info(f"[Drive] Factura subida: {relative_path}")

        except Exception as exc:
            logger.error(f"[Drive] Error al subir factura {relative_path}: {exc}")

    def upload_factura_async(self, local_path: str, relative_path: str):
        """Sube un PDF de factura en un thread daemon."""
        threading.Thread(
            target=self.upload_factura,
            args=(local_path, relative_path),
            daemon=True,
        ).start()

    # ── Utilidad de diagnóstico ────────────────────────────────────────────────

    def status(self) -> dict:
        """
        Devuelve un dict con el estado actual de la sincronización.
        Útil para diagnóstico desde configurar_drive.py.
        """
        configured = self.is_configured()
        excel_in_drive = False
        if configured:
            try:
                self._ensure_folders()
                excel_in_drive = bool(
                    self._find_file("edificio_brasil.xlsx", self._env_folder_id)
                )
            except Exception:
                pass

        return {
            "configurado": configured,
            "env": self.env,
            "excel_en_drive": excel_in_drive,
            "carpeta_drive": f"{DRIVE_ROOT_FOLDER}/{self.env}/",
        }
