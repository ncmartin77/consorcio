@echo off
:: Punto de entrada del instalador.
:: Lanza instalar.ps1 con permisos de administrador y politica de ejecucion libre.
:: No requiere ninguna intervencion del usuario.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0instalar.ps1""' -Wait"
