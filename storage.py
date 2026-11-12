"""
Almacenamiento de archivos: comprobantes de facturas y adjuntos de notificaciones (v11.0).

Dónde se guardan:
- Si están las variables STORAGE_S3_* → en un bucket S3 privado. En producción es
  Supabase Storage (Storage → S3 Connection); en pruebas puede ser el proyecto consorcio-tst
  o un S3 local (SeaweedFS del Docker de plataforma/).
- Si no están → en el disco, bajo LOCAL_ROOT (instalaciones de escritorio y pruebas sin red).

Por qué: en Render el disco se borra con cada deploy, así que los archivos subidos se perdían.

El navegador nunca entra directo al bucket: la app lee el archivo y lo sirve, después de
controlar la sesión. Las claves son rutas como "<consorcio_id>/facturas/<proveedor>/<fecha>.pdf".

Variables:
    STORAGE_S3_ENDPOINT          p. ej. https://<proyecto>.supabase.co/storage/v1/s3
    STORAGE_S3_REGION            la que muestra Supabase (p. ej. us-east-1)
    STORAGE_S3_BUCKET            por defecto "comprobantes" (se crea solo si no existe)
    STORAGE_S3_ACCESS_KEY_ID
    STORAGE_S3_SECRET_ACCESS_KEY
"""
import os
import re
import threading

_ENDPOINT = os.environ.get("STORAGE_S3_ENDPOINT", "").strip().rstrip("/")
_REGION = os.environ.get("STORAGE_S3_REGION", "").strip() or "us-east-1"
BUCKET = os.environ.get("STORAGE_S3_BUCKET", "").strip() or "comprobantes"
_KEY_ID = os.environ.get("STORAGE_S3_ACCESS_KEY_ID", "").strip()
_SECRET = os.environ.get("STORAGE_S3_SECRET_ACCESS_KEY", "").strip()

# Raíz para el modo disco; app.py la fija dentro de DATA_DIR.
LOCAL_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "archivos")

_cliente = None
_bucket_ok = False
_lock = threading.Lock()


class StorageError(Exception):
    """El almacenamiento no respondió o rechazó la operación (no es "archivo inexistente")."""


def usa_s3() -> bool:
    return bool(_ENDPOINT and _KEY_ID and _SECRET)


def endpoint() -> str:
    return _ENDPOINT


def descripcion() -> str:
    if usa_s3():
        return f"S3 {_ENDPOINT} (bucket '{BUCKET}')"
    return f"disco ({LOCAL_ROOT})"


# ── Claves ────────────────────────────────────────────────────────────────────

_CLAVE_OK = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$")


def _validar(clave: str):
    partes = (clave or "").split("/")
    if not clave or not _CLAVE_OK.match(clave) or any(p in (".", "..") for p in partes):
        raise StorageError("Ruta de archivo inválida")


# ── S3 ────────────────────────────────────────────────────────────────────────

def _s3():
    """Cliente S3 (uno por proceso). Crea el bucket privado la primera vez si falta."""
    global _cliente, _bucket_ok
    if _cliente is not None and _bucket_ok:
        return _cliente
    with _lock:
        if _cliente is None:
            import boto3
            from botocore.config import Config
            _cliente = boto3.client(
                "s3",
                endpoint_url=_ENDPOINT,
                region_name=_REGION,
                aws_access_key_id=_KEY_ID,
                aws_secret_access_key=_SECRET,
                config=Config(
                    s3={"addressing_style": "path"},          # Supabase y SeaweedFS
                    signature_version="s3v4",
                    request_checksum_calculation="when_required",
                    response_checksum_validation="when_required",
                    connect_timeout=10, read_timeout=30,
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        if not _bucket_ok:
            from botocore.exceptions import BotoCoreError, ClientError
            try:
                _cliente.head_bucket(Bucket=BUCKET)
            except ClientError as e:
                codigo = str(e.response.get("Error", {}).get("Code", ""))
                if codigo not in ("404", "NoSuchBucket", "NotFound"):
                    raise StorageError(f"No se pudo acceder al bucket '{BUCKET}': {codigo}") from e
                try:
                    _cliente.create_bucket(Bucket=BUCKET)   # privado: sin ACL pública
                except ClientError as e2:
                    c2 = str(e2.response.get("Error", {}).get("Code", ""))
                    if c2 not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                        raise StorageError(f"No se pudo crear el bucket '{BUCKET}': {c2}") from e2
            except BotoCoreError as e:
                raise StorageError(f"No se pudo conectar con el almacenamiento: {e}") from e
            _bucket_ok = True
    return _cliente


def _no_existe(e) -> bool:
    codigo = str(e.response.get("Error", {}).get("Code", ""))
    return codigo in ("404", "NoSuchKey", "NotFound")


# ── Disco ─────────────────────────────────────────────────────────────────────

def _ruta_local(clave: str) -> str:
    raiz = os.path.realpath(LOCAL_ROOT)
    ruta = os.path.realpath(os.path.join(raiz, *clave.split("/")))
    if not ruta.startswith(raiz + os.sep):
        raise StorageError("Ruta de archivo inválida")
    return ruta


# ── API ───────────────────────────────────────────────────────────────────────

def guardar(clave: str, datos: bytes, content_type: str = "application/octet-stream"):
    """Guarda (o reemplaza) el archivo. Lanza StorageError si falla."""
    _validar(clave)
    if usa_s3():
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            _s3().put_object(Bucket=BUCKET, Key=clave, Body=datos, ContentType=content_type)
        except (BotoCoreError, ClientError) as e:
            raise StorageError(f"Error al subir el archivo: {e}") from e
        return
    ruta = _ruta_local(clave)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "wb") as f:
        f.write(datos)


def leer(clave: str) -> bytes | None:
    """Devuelve el contenido, o None si el archivo no existe. Lanza StorageError si falla."""
    _validar(clave)
    if usa_s3():
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            r = _s3().get_object(Bucket=BUCKET, Key=clave)
            return r["Body"].read()
        except ClientError as e:
            if _no_existe(e):
                return None
            raise StorageError(f"Error al leer el archivo: {e}") from e
        except BotoCoreError as e:
            raise StorageError(f"Error al leer el archivo: {e}") from e
    ruta = _ruta_local(clave)
    if not os.path.isfile(ruta):
        return None
    with open(ruta, "rb") as f:
        return f.read()


def borrar(clave: str):
    """Elimina el archivo si existe (no falla si no existe)."""
    _validar(clave)
    if usa_s3():
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            _s3().delete_object(Bucket=BUCKET, Key=clave)
        except ClientError as e:
            if not _no_existe(e):
                raise StorageError(f"Error al borrar el archivo: {e}") from e
        except BotoCoreError as e:
            raise StorageError(f"Error al borrar el archivo: {e}") from e
        return
    ruta = _ruta_local(clave)
    if os.path.isfile(ruta):
        os.remove(ruta)


def borrar_prefijo(prefijo: str) -> int:
    """Borra todos los archivos bajo `prefijo` (debe terminar en "/"). Devuelve cuántos."""
    if not prefijo.endswith("/") or prefijo.strip("/") == "":
        raise StorageError("Prefijo inválido")
    claves = listar(prefijo)
    for c in claves:
        borrar(c)
    return len(claves)


def listar(prefijo: str) -> list[str]:
    """Claves que empiezan con `prefijo` (p. ej. "<cid>/facturas/")."""
    if usa_s3():
        from botocore.exceptions import BotoCoreError, ClientError
        claves = []
        try:
            pag = _s3().get_paginator("list_objects_v2")
            for pagina in pag.paginate(Bucket=BUCKET, Prefix=prefijo):
                claves += [o["Key"] for o in pagina.get("Contents", [])]
        except (BotoCoreError, ClientError) as e:
            raise StorageError(f"Error al listar archivos: {e}") from e
        return claves
    raiz = os.path.realpath(LOCAL_ROOT)
    base = os.path.join(raiz, *[p for p in prefijo.split("/") if p])
    if not os.path.isdir(base):
        return []
    claves = []
    for dirpath, _dirs, files in os.walk(base):
        for f in files:
            claves.append(os.path.relpath(os.path.join(dirpath, f), raiz).replace(os.sep, "/"))
    return sorted(claves)
