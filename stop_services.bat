@echo off
echo --- Parando servicos Docker ---

REM Verifica se o Docker esta rodando
docker info > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Docker nao parece estar rodando.
    pause
    exit /b 1
)

docker-compose down

echo [OK] Servicos parados.
echo.
pause
