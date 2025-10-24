@echo off
REM Este script nao e mais usado diretamente pelo browser_manager.py
REM Mantido apenas como referencia ou para testes manuais.

REM --- Caminho original fornecido ---
set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
REM --- Perfil ---
set "PROFILE_PATH=%USERPROFILE%\chrome-dev-profile-onecost"

echo [MANUAL] Verificando caminho: %CHROME_PATH%
if not exist "%CHROME_PATH%" (
    echo [!] ERRO: Caminho nao encontrado. Verifique a variavel CHROME_PATH.
    pause
    exit /b 1
)

echo [MANUAL] Abrindo Chrome com debug na porta 9222 e perfil %PROFILE_PATH%...
start "" "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="%PROFILE_PATH%"

echo [MANUAL] Comando enviado.

