# Deploy a Firebase / Cloud Run

## Decisión arquitectónica

**Opción elegida: Cloud Run + Cloud Storage (Opción A)**

Los Excel viven en un bucket de Google Cloud Storage (GCS). Cada request descarga
el Excel del bucket, opera sobre él, y lo sube de vuelta. Es el mismo patrón que
ya usa `drive_sync.py` con Google Drive, pero con GCS.

```
Firebase Hosting  (dominio + HTTPS + CDN)
      ↓ proxy rewrite
Cloud Run         (Flask app en contenedor Docker)
      ↓ lee/escribe
Cloud Storage     (Excel + facturas, organizados por consorcio)
      gs://consorcio-app-data/
          consorcios/<cid>/base.xlsx
          consorcios/<cid>/facturas/<proveedor>/<timestamp>.pdf
          _consorcios.json
```

**Por qué no las otras opciones:**
- Opción B (Cloud SQL / PostgreSQL): requiere reescribir toda la capa de datos.
- Opción C (Firestore): el modelo relacional del Excel no mapea bien a documentos NoSQL.

---

## Prerequisitos (instalar antes)

```bash
# 1. gcloud CLI
#    https://cloud.google.com/sdk/docs/install
gcloud --version   # verificar

# 2. Firebase CLI
npm install -g firebase-tools
firebase --version  # verificar

# 3. Docker Desktop (Windows)
#    https://www.docker.com/products/docker-desktop/
docker --version   # verificar
```

---

## Paso 1 — Crear proyecto Firebase / GCP

```bash
firebase login
firebase projects:create consorcio-app-XXXX   # nombre único global

# Vincular con gcloud
gcloud config set project consorcio-app-XXXX

# Habilitar APIs necesarias
gcloud services enable \
  run.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com
```

> Requiere billing habilitado en la cuenta Google (tarjeta de crédito).
> Cloud Run tiene free tier generoso (2M requests/mes gratis).

---

## Paso 2 — Crear bucket de Cloud Storage

```bash
gsutil mb -l us-central1 gs://consorcio-app-data
gsutil versioning set on gs://consorcio-app-data   # opcional pero recomendable
```

Estructura del bucket:
```
gs://consorcio-app-data/
    _consorcios.json
    consorcios/f7d67313/base.xlsx
    consorcios/f7d67313/facturas/proveedor_sa/2026-10-09_143022.pdf
    consorcios/2def0e2f/base.xlsx
    ...
```

Subir datos iniciales desde la instalación local:
```bash
# Subir el índice
gsutil cp _consorcios.json gs://consorcio-app-data/

# Subir cada consorcio
gsutil -m cp -r data/f7d67313/ gs://consorcio-app-data/consorcios/f7d67313/
gsutil -m cp -r data/2def0e2f/ gs://consorcio-app-data/consorcios/2def0e2f/
gsutil -m cp -r data/331e1bb3/ gs://consorcio-app-data/consorcios/331e1bb3/
```

---

## Paso 3 — Crear `gcs_sync.py`

Nuevo módulo que reemplaza el acceso al filesystem local por GCS.
Mismo patrón que `drive_sync.py`.

```python
# gcs_sync.py
"""
Capa de acceso a Google Cloud Storage para datos de consorcios.
Reemplaza el filesystem local en el deploy de Cloud Run.
"""
import os
import tempfile
from google.cloud import storage

_BUCKET_NAME = os.environ.get("GCS_BUCKET", "consorcio-app-data")
_client = None

def _get_client():
    global _client
    if not _client:
        _client = storage.Client()
    return _client

def _bucket():
    return _get_client().bucket(_BUCKET_NAME)

def download_to_temp(gcs_path: str) -> str:
    """Descarga blob GCS a un archivo temporal. Retorna la ruta local."""
    blob = _bucket().blob(gcs_path)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    blob.download_to_filename(tmp.name)
    return tmp.name

def upload_from_file(local_path: str, gcs_path: str):
    """Sube un archivo local a GCS."""
    blob = _bucket().blob(gcs_path)
    blob.upload_from_filename(local_path)

def read_json(gcs_path: str) -> bytes:
    """Lee un JSON de GCS como bytes."""
    return _bucket().blob(gcs_path).download_as_bytes()

def write_json(gcs_path: str, data: bytes):
    """Escribe bytes JSON a GCS."""
    _bucket().blob(gcs_path).upload_from_string(data, content_type="application/json")

def list_blobs(prefix: str):
    return list(_get_client().list_blobs(_BUCKET_NAME, prefix=prefix))
```

---

## Paso 4 — Adaptar `excel_db.py` para GCS

### Estrategia

Agregar una variable de entorno `USE_GCS=true`. Cuando está activa:
- `_get_wb()` descarga el Excel de GCS a un archivo temporal antes de abrirlo
- `_save_wb()` sube el archivo temporal de vuelta a GCS después de guardarlo
- `_read_index()` / `_write_index()` usan GCS en lugar del filesystem

### Cambios en `_get_wb()` y `_save_wb()`

```python
# Al inicio de excel_db.py, agregar:
_USE_GCS = os.environ.get("USE_GCS", "").lower() in ("1", "true", "yes")

def _gcs_path_for_db() -> str:
    """Retorna el path GCS relativo del Excel activo."""
    # data_dir es algo como /app/data/f7d67313 en local,
    # pero en GCS usamos consorcios/<cid>/base.xlsx
    cid = os.path.basename(get_data_dir())
    return f"consorcios/{cid}/base.xlsx"

def _get_wb():
    if _USE_GCS:
        from gcs_sync import download_to_temp
        tmp_path = download_to_temp(_gcs_path_for_db())
        # Guardar ruta temporal en thread-local para que _save_wb la use
        _tls.gcs_tmp_path = tmp_path
        return load_workbook(tmp_path)
    # comportamiento original...
    db_path = get_db_path()
    if not os.path.exists(db_path):
        _init_db()
    return load_workbook(db_path)

def _save_wb(wb):
    if _USE_GCS:
        from gcs_sync import upload_from_file
        tmp_path = getattr(_tls, "gcs_tmp_path", None)
        if not tmp_path:
            import tempfile
            tmp_path = tempfile.mktemp(suffix=".xlsx")
        wb.save(tmp_path)
        upload_from_file(tmp_path, _gcs_path_for_db())
        return
    # comportamiento original...
    db_path = get_db_path()
    wb.save(db_path)
```

### Cambios en `_read_index()` / `_write_index()`

```python
def _read_index() -> dict:
    if _USE_GCS:
        from gcs_sync import read_json
        import json as _json
        try:
            return _json.loads(read_json("_consorcios.json"))
        except Exception:
            return {"consorcios": []}
    # comportamiento original...

def _write_index(idx: dict):
    if _USE_GCS:
        from gcs_sync import write_json
        import json as _json
        write_json("_consorcios.json", _json.dumps(idx, ensure_ascii=False, indent=2).encode())
        return
    # comportamiento original...
```

### Cambio en checkpoint

```python
def crear_checkpoint(descripcion: str = "") -> dict:
    if _USE_GCS:
        from gcs_sync import download_to_temp, upload_from_file
        tmp = download_to_temp(_gcs_path_for_db())
        cid = os.path.basename(get_data_dir())
        upload_from_file(tmp, f"consorcios/{cid}/_checkpoint.xlsx")
        # guardar metadata en GCS también
        ...
    # comportamiento original...
```

---

## Paso 5 — Crear `Dockerfile`

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema (para Pillow y ReportLab)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir google-cloud-storage

COPY . .

# Cloud Run provee PORT
ENV PORT=8080
ENV APP_HOST=0.0.0.0
ENV USE_GCS=true

CMD ["python", "app.py"]
```

### `.dockerignore`

```
venv/
venv_wsl/
__pycache__/
*.pyc
data/
credentials/
*.bat
*.ps1
*.log
.git/
FIREBASE.md
```

---

## Paso 6 — Actualizar `requirements.txt`

Agregar:
```
google-cloud-storage>=2.10.0
```

---

## Paso 7 — Actualizar `app.py` para Cloud Run

Cloud Run usa la variable `PORT`. Cambiar el bloque `if __name__ == "__main__"`:

```python
if __name__ == "__main__":
    if not os.environ.get("USE_GCS"):
        db.sync_from_drive()
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host=host, port=port)
```

> `debug=False` en producción (Cloud Run).

---

## Paso 8 — Build y push de la imagen

```bash
# Crear repositorio en Artifact Registry
gcloud artifacts repositories create consorcio \
  --repository-format=docker \
  --location=us-central1

# Configurar Docker para autenticar con GCP
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build
docker build -t us-central1-docker.pkg.dev/consorcio-app-XXXX/consorcio/app:latest .

# Push
docker push us-central1-docker.pkg.dev/consorcio-app-XXXX/consorcio/app:latest
```

---

## Paso 9 — Deploy en Cloud Run

```bash
gcloud run deploy consorcio \
  --image us-central1-docker.pkg.dev/consorcio-app-XXXX/consorcio/app:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars USE_GCS=true,GCS_BUCKET=consorcio-app-data \
  --memory 512Mi \
  --timeout 60
```

Anotar la URL que devuelve (`https://consorcio-XXXXXX.run.app`).

---

## Paso 10 — Configurar Firebase Hosting

```bash
firebase init hosting
# Responder:
#   Use existing project → consorcio-app-XXXX
#   Public directory → public   (crear carpeta vacía)
#   Single-page app → No
#   GitHub deploys → No
```

Editar `firebase.json`:

```json
{
  "hosting": {
    "public": "public",
    "ignore": ["firebase.json", "**/.*"],
    "rewrites": [
      {
        "source": "/**",
        "run": {
          "serviceId": "consorcio",
          "region": "us-central1"
        }
      }
    ]
  }
}
```

Crear carpeta `public/` con un `index.html` vacío (requerido por Firebase Hosting):
```bash
mkdir public && echo "" > public/index.html
```

```bash
firebase deploy --only hosting
```

La app queda en `https://consorcio-app-XXXX.web.app`.

---

## Paso 11 — Dominio personalizado (opcional)

```bash
firebase hosting:channel:deploy produccion
# O agregar dominio propio en Firebase Console → Hosting → Add custom domain
```

---

## Paso 12 — Proteger el acceso (recomendado)

Agregar login básico. Opciones:

**A. HTTP Basic Auth en Cloud Run** (más simple):
```python
# En app.py, agregar middleware de autenticación básica
import base64

USERS = {os.environ.get("APP_USER", "admin"): os.environ.get("APP_PASSWORD", "")}

@app.before_request
def require_auth():
    if request.endpoint == "static":
        return
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            user, pwd = base64.b64decode(auth[6:]).decode().split(":", 1)
            if USERS.get(user) == pwd and pwd:
                return
        except Exception:
            pass
    return Response("Acceso restringido", 401,
                    {"WWW-Authenticate": 'Basic realm="Consorcio"'})
```

Setear en Cloud Run:
```bash
gcloud run services update consorcio \
  --set-env-vars APP_USER=admin,APP_PASSWORD=mipassword123
```

**B. Firebase Authentication** (más complejo, requiere cambios en frontend):
Integrar Firebase Auth SDK en `base.html` y verificar tokens en el backend.

---

## Variables de entorno en Cloud Run

| Variable | Valor | Descripción |
|---|---|---|
| `USE_GCS` | `true` | Activa backend de Cloud Storage |
| `GCS_BUCKET` | `consorcio-app-data` | Nombre del bucket |
| `APP_HOST` | `0.0.0.0` | Flask bind address |
| `PORT` | (auto) | Seteado por Cloud Run |
| `APP_USER` | `admin` | Usuario para HTTP Basic Auth |
| `APP_PASSWORD` | `***` | Contraseña para HTTP Basic Auth |

---

## Costo estimado

Con uso normal (1-2 usuarios, operaciones administrativas):
- Cloud Run: **gratis** (free tier: 2M requests/mes, 360K GB-segundos)
- Cloud Storage: **~$0.02/mes** (< 1 GB de datos)
- Firebase Hosting: **gratis** (10 GB/mes transferencia)
- **Total esperado: $0 o centavos por mes**

Billing se activa solo si se supera el free tier.

---

## Problemas conocidos a resolver antes de implementar

1. **Concurrencia**: si dos usuarios guardan al mismo tiempo, el segundo sobreescribe al primero. Mitigación: Cloud Run con `--concurrency 1` (una request a la vez por instancia) + `--min-instances 1`.

2. **Cold start**: primera request tras inactividad puede tardar 2-5 segundos mientras el contenedor arranca. Mitigación: `--min-instances 1` (costo: ~$5/mes).

3. **Checkpoint en GCS**: la función `crear_checkpoint` actual usa `shutil.copy2()` en el filesystem. En modo GCS necesita copiar entre blobs de GCS (`bucket.copy_blob()`).

4. **Secret management**: la `clave_firma` de HMAC y contraseñas deben ir en **Secret Manager** de GCP, no en variables de entorno planas.

```bash
echo -n "mipassword" | gcloud secrets create app-password --data-file=-
# En Cloud Run:
gcloud run services update consorcio \
  --set-secrets APP_PASSWORD=app-password:latest
```
