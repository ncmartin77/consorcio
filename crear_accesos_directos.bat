@echo off
:: Crea dos accesos directos en el Escritorio:
::   "Consorcio Brasil" -> iniciar.bat (solo localhost)
::   "Consorcio Brasil - Red Local" -> iniciar_red.bat (acceso desde la red)

set APPDIR=%~dp0
set DESKTOP=%USERPROFILE%\Desktop

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut('%DESKTOP%\Consorcio Brasil.lnk'); " ^
  "$s.TargetPath = '%APPDIR%iniciar.bat'; " ^
  "$s.WorkingDirectory = '%APPDIR%'; " ^
  "$s.Description = 'App Consorcio (solo esta PC)'; " ^
  "$s.Save()"

powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$s = $ws.CreateShortcut('%DESKTOP%\Consorcio Brasil - Red Local.lnk'); " ^
  "$s.TargetPath = '%APPDIR%iniciar_red.bat'; " ^
  "$s.WorkingDirectory = '%APPDIR%'; " ^
  "$s.Description = 'App Consorcio (accesible desde la red local)'; " ^
  "$s.Save()"

echo.
echo Accesos directos creados en el Escritorio:
echo   - Consorcio Brasil
echo   - Consorcio Brasil - Red Local
echo.
pause
