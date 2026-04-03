@echo off
:: Lanza instalar.ps1 directamente.
:: La elevacion a administrador la maneja el propio PS1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
