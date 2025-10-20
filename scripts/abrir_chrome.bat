@echo off
REM --- ATENÇÃO: Verifique e ajuste este caminho se necessário ---
set "CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe"
set "PROFILE_PATH=%USERPROFILE%\chrome-dev-profile-onenotify"

echo [🌐] Abrindo Google Chrome com depuracao remota...
echo Usando perfil em: %PROFILE_PATH%

start "" "%CHROME_PATH%" --remote-debugging-port=9222 --user-data-dir="%PROFILE_PATH%"

echo [✔] Chrome aberto.

