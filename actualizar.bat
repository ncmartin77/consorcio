@echo off
:: actualizar.bat
:: Actualiza el codigo sin tocar la base de datos (data/).
:: Ejecutar DESPUES de descomprimir el nuevo ZIP encima de la carpeta actual.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0actualizar.ps1"
