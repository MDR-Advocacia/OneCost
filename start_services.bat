@echo off
echo --- Iniciando servicos Docker (DB, Backend, Dashboard) ---

REM Verifica se o Docker esta rodando
docker info > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Docker nao parece estar rodando. Inicie o Docker Desktop.
    pause
    exit /b 1
)

echo [1/2] Construindo e subindo os containers em modo detached...
docker-compose up --build -d

echo.
echo [2/2] Verificando status dos containers...
docker-compose ps

echo.
echo [OK] Servicos iniciados! Dashboard deve estar acessivel em http://localhost:3001
echo Para parar, execute: stop_services.bat
echo.
pause
