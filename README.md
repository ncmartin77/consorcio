# App Consorcio — Administración de Edificio

Aplicación web local para gestionar expensas, liquidaciones, facturas y caja de un consorcio edilicio argentino. Corre en tu PC con Windows; se accede desde el navegador en `http://localhost:5000`.

---

## Requisitos previos

| Requisito | Versión mínima | Dónde conseguirlo |
|-----------|---------------|-------------------|
| Windows   | 10 / 11       | —                 |
| Python    | 3.8           | https://www.python.org/downloads/ |
| Conexión a internet | — | Solo para la instalación inicial |

> **Al instalar Python:** tildar la opción **"Add Python to PATH"** antes de hacer clic en *Install Now*.

---

## Instalación (primera vez)

1. Descomprimí el ZIP en la carpeta donde quieras tener la app (ej: `C:\Consorcio\`).
2. Abrí la carpeta y hacé doble clic en **`instalar.bat`**.
3. El instalador verifica Python, crea el entorno virtual e instala las dependencias automáticamente.
4. Al terminar, cerrá esa ventana.

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
