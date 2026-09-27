# App Consorcio — Administración de Edificio

Aplicación web local para gestionar expensas, liquidaciones, facturas y caja de un consorcio edilicio argentino. Corre en tu PC con Windows; se accede desde el navegador en `http://localhost:5000`.

---

## Requisitos previos

| Requisito | Mínimo | Notas |
|-----------|--------|-------|
| Windows   | 10 (build 19041) / 11 | — |
| Conexión a internet | — | Solo para la instalación inicial |
| Python 3.8+ | opcional | El instalador lo descarga si falta |

> No necesitás instalar nada manualmente. El instalador lo hace todo solo.

---

## Instalación (primera vez)

1. Descomprimí el ZIP en la carpeta donde quieras tener la app (ej: `C:\Consorcio\`).
2. Hacé doble clic en **`instalar.bat`** — no requiere ninguna intervención.
3. El instalador:
   - Se auto-eleva a administrador
   - Detecta si Python está instalado; si no, lo descarga e instala en silencio
   - Si no hay conexión o Python falla, instala WSL con Debian automáticamente
   - Si WSL requiere reinicio, lo programa y reinicia solo — al volver, continúa automáticamente
   - Crea el entorno virtual e instala todas las dependencias
   - Genera un log detallado en `instalacion.log`
4. Al finalizar, ejecutá `iniciar.bat`.

---

## Uso diario

Hacé doble clic en **`iniciar.bat`**.

Se abre una ventana de consola y el navegador en `http://localhost:5000`.  
Para cerrar la app, cerrá esa ventana de consola (o presioná `Ctrl+C`).

---

## Estructura de archivos

```
app.py                  ← Servidor web (Flask)
excel_db.py             ← Toda la lógica de datos
pdf_gen.py              ← Generación de PDFs
requirements.txt        ← Dependencias Python
instalar.bat            ← Instalador (ejecutar una vez)
iniciar.bat             ← Inicio diario
data/
  edificio_brasil.xlsx  ← BASE DE DATOS (¡hacer backup!)
templates/              ← Pantallas HTML
static/                 ← Estilos e imágenes
```

> **Importante:** todo está guardado en `data/edificio_brasil.xlsx`. Hacé copias de seguridad de ese archivo periódicamente.

---

## Backup

Copiá el archivo `data/edificio_brasil.xlsx` a un pendrive, Google Drive o donde prefieras. Ese archivo es toda la base de datos.

---

## Solución de problemas

| Problema | Solución |
|----------|----------|
| "Python no está instalado" | Instalá Python desde python.org y asegurate de tildar "Add to PATH" |
| La app no abre el navegador | Abrí manualmente `http://localhost:5000` |
| Error al instalar dependencias | Verificá la conexión a internet y volvé a ejecutar `instalar.bat` |
| "Port 5000 already in use" | Cerrá otras instancias de la app o reiniciá la PC |

---

## Actualización

Si recibís una nueva versión en ZIP:

1. Hacé backup de `data/edificio_brasil.xlsx`.
2. Descomprimí el nuevo ZIP **sobre** la carpeta actual (sobreescribí los archivos).
3. Ejecutá `instalar.bat` de nuevo para actualizar dependencias.
4. Iniciá con `iniciar.bat`.

---

*Generado con Claude Code.*
