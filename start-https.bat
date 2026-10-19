@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" -Port 8443 -Cert "certs\server.pem" -Key "certs\server-key.pem" -AlsoHttp 8765 %*
pause
