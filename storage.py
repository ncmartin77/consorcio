"""
Almacenamiento de archivos (comprobantes de facturas, adjuntos de notificaciones).

- Si están configuradas SUPABASE_URL y SUPABASE_SERVICE_KEY → Supabase Storage
  (bucket privado; el navegador nunca accede directo: la app descarga y sirve el archivo).
- Si no → disco local bajo LOCAL_ROOT (instalaciones locales / desarrollo).

Las claves de archivo son rutas tipo "<consorcio_id>/facturas/<proveedor>/<timestamp>.pdf".
Usa solo la biblioteca estándar (urllib) para no agregar dependencias.
"""
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request

_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
BUCKET = os.environ.get("SUPABASE_BUCKET", "comprobantes").strip() or "comprobantes"
_TIMEOUT = 30

# Raíz para el modo local; app.py la fija al DATA_DIR del entorno.
LOCAL_ROOT = os.path.join(os.path.dirname(__file__), "data", "archivos")

_bucket_ok = False
_bucket_lock = threading.Lock()


class StorageError(Exception):
    pass


def usa_supabase() -> bool:
    return bool(_URL and _KEY)


def descripcion() -> str:
    return f"Supabase Storage (bucket '{BUCKET}')" if usa_supabase() else f"disco local ({LOCAL_ROOT})"


# ── Supabase ──────────────────────────────────────────────────────────────────

def _headers(extra: dict | None = None) -> dict:
    h = {"apikey": _KEY}
    # Clave legacy service_role (JWT) → también va en Authorization.
    # Las claves nuevas sb_secret_* van solo en apikey (no son JWT).
    if _KEY.startswith("eyJ"):
        h["Authorization"] = f"Bearer {_KEY}"
    if extra:
        h.update(extra)
    return h


def _request(method: str, path: str, data: bytes | None = None, headers: dict | None = None):
    """Devuelve (status, body_bytes). No lanza por códigos HTTP de error."""
    req = urllib.request.Request(f"{_URL}{path}", data=data, method=method, headers=_headers(headers))
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise StorageError(f"No se pudo conectar con Supabase Storage: {e.reason}") from e


def _obj_path(clave: str) -> str:
    return f"/storage/v1/object/{urllib.parse.quote(BUCKET)}/{urllib.parse.quote(clave, safe='/')}"


def _ensure_bucket():
    """Crea el bucket privado si no existe. Una vez por proceso."""
    global _bucket_ok
    if _bucket_ok:
        return
    with _bucket_lock:
        if _bucket_ok:
            return
        status, body = _request("GET", f"/storage/v1/bucket/{urllib.parse.quote(BUCKET)}")
        if status != 200:
            payload = json.dumps({"id": BUCKET, "name": BUCKET, "public": False}).encode()
            status, body = _request("POST", "/storage/v1/bucket", payload,
                                    {"Content-Type": "application/json"})
            texto = body.decode("utf-8", "replace")
            if status not in (200, 201) and "already exists" not in texto.lower() \
                    and "duplicate" not in texto.lower():
                raise StorageError(f"No se pudo crear el bucket '{BUCKET}' ({status}): {texto[:200]}")
        _bucket_ok = True


# ── Local ─────────────────────────────────────────────────────────────────────

def _local_path(clave: str) -> str:
    root = os.path.realpath(LOCAL_ROOT)
    path = os.path.realpath(os.path.join(root, *clave.split("/")))
    if not path.startswith(root + os.sep):
        raise StorageError("Ruta de archivo inválida")
    return path


def _validar(clave: str):
    if not clave or clave.startswith("/") or ".." in clave.split("/") or "\\" in clave:
        raise StorageError("Ruta de archivo inválida")


# ── API pública ───────────────────────────────────────────────────────────────

def guardar(clave: str, datos: bytes, content_type: str = "application/octet-stream"):
    """Guarda (o reemplaza) el archivo. Lanza StorageError si falla."""
    _validar(clave)
    if usa_supabase():
        _ensure_bucket()
        status, body = _request("POST", _obj_path(clave), datos,
                                {"Content-Type": content_type, "x-upsert": "true"})
        if status not in (200, 201):
            raise StorageError(f"Error al subir el archivo ({status}): {body.decode('utf-8', 'replace')[:200]}")
        return
    path = _local_path(clave)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(datos)


def leer(clave: str) -> bytes | None:
    """Devuelve el contenido, o None si el archivo no existe."""
    _validar(clave)
    if usa_supabase():
        status, body = _request("GET", _obj_path(clave))
        if status == 200:
            return body
        texto = body.decode("utf-8", "replace").lower()
        if status in (400, 404) and ("not found" in texto or "not_found" in texto or status == 404):
            return None
        raise StorageError(f"Error al leer el archivo ({status}): {texto[:200]}")
    path = _local_path(clave)
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def borrar(clave: str):
    """Elimina el archivo si existe (no falla si no existe)."""
    _validar(clave)
    if usa_supabase():
        payload = json.dumps({"prefixes": [clave]}).encode()
        status, body = _request("DELETE", f"/storage/v1/object/{urllib.parse.quote(BUCKET)}", payload,
                                {"Content-Type": "application/json"})
        if status not in (200, 204, 404):
            raise StorageError(f"Error al borrar el archivo ({status}): {body.decode('utf-8', 'replace')[:200]}")
        return
    path = _local_path(clave)
    if os.path.isfile(path):
        os.remove(path)
