@echo off
setlocal enabledelayedexpansion

REM --- Configuracoes ---
set "SCRIPT_DIR=%~dp0"
REM Assume que o script esta na raiz do projeto 'OneCost-acd180...'
set "LOG_DIR=%SCRIPT_DIR%robot\logs"
set "VENV_DIR=%SCRIPT_DIR%venv"
set "REQUIREMENTS_FILE=%SCRIPT_DIR%requirements.txt"
set "SCRIPT_PRINCIPAL=%SCRIPT_DIR%robot\main.py"
set "PAUSA_SUCESSO_SEGUNDOS=600"
set "PAUSA_FALHA_SEGUNDOS=120"

REM --- Criação da pasta de logs ---
if not exist "%LOG_DIR%" (
    echo [SUPERVISOR] Criando pasta de logs em: %LOG_DIR%
    mkdir "%LOG_DIR%"
)

:SETUP
cls
echo [SUPERVISOR] Iniciando configuracao do ambiente...

REM --- Verifica/Cria Ambiente Virtual (venv) ---
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [SUPERVISOR] Ambiente virtual '%VENV_DIR%' nao encontrado. Criando...
    python -m venv "%VENV_DIR%"
    if %ERRORLEVEL% NEQ 0 (
        echo [SUPERVISOR] ERRO: Falha ao criar ambiente virtual. Verifique se o Python esta no PATH.
        pause
        exit /b 1
    )
    echo [SUPERVISOR] Ambiente virtual criado.
) else (
    echo [SUPERVISOR] Ambiente virtual encontrado em '%VENV_DIR%'.
)

REM --- Ativa o Ambiente Virtual ---
echo [SUPERVISOR] Ativando ambiente virtual para setup...
call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% NEQ 0 (
    echo [SUPERVISOR] ERRO: Falha ao ativar ambiente virtual no setup.
    pause
    exit /b 1
)

REM --- Instala/Atualiza Dependencias ---
if not exist "%REQUIREMENTS_FILE%" (
    echo [SUPERVISOR] ERRO: Arquivo '%REQUIREMENTS_FILE%' nao encontrado.
    pause
    exit /b 1
)
echo [SUPERVISOR] Instalando/Atualizando dependencias de '%REQUIREMENTS_FILE%'...
pip install -r "%REQUIREMENTS_FILE%"
if %ERRORLEVEL% NEQ 0 (
    echo [SUPERVISOR] ERRO: Falha ao instalar dependencias do Python.
    pause
    exit /b 1
)

REM --- Instala Navegadores do Playwright ---
echo [SUPERVISOR] Verificando/Instalando navegadores do Playwright (isso pode levar um tempo)...
playwright install chromium
REM Adicione 'firefox' ou 'webkit' se precisar deles: playwright install firefox webkit
if %ERRORLEVEL% NEQ 0 (
    echo [SUPERVISOR] ERRO: Falha ao instalar navegadores do Playwright.
    pause
    exit /b 1
)

echo [SUPERVISOR] Configuracao do ambiente concluida.

:LOOP
cls
echo [SUPERVISOR] Iniciando novo ciclo...

REM --- Geração de timestamp robusto via WMIC ---
echo [SUPERVISOR] Gerando timestamp...
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /format:list') do set "datetime=%%I"
set "YYYY=!datetime:~0,4!"
set "MM=!datetime:~4,2!"
set "DD=!datetime:~6,2!"
set "HH=!datetime:~8,2!"
set "MIN=!datetime:~10,2!"
set "SEC=!datetime:~12,2!"
set "TIMESTAMP=!YYYY!-!MM!-!DD!_!HH!-!MIN!-!SEC!"
set "LOG_CICLO=%LOG_DIR%\supervisor_ciclo_!TIMESTAMP!.log"
echo [SUPERVISOR] Log deste ciclo sera salvo em: %LOG_CICLO%

REM --- Tenta criar/escrever no arquivo de log imediatamente ---
echo [SUPERVISOR] Criando/Abrindo arquivo de log do ciclo...
echo ---------------------------------------------------------------- >> "%LOG_CICLO%" 2> nul
if %ERRORLEVEL% NEQ 0 (
    echo [SUPERVISOR] ERRO CRITICO: Nao foi possivel escrever no arquivo de log '%LOG_CICLO%'. Verifique as permissoes.
    pause
    exit /b 1
)
echo [SUPERVISOR] Arquivo de log acessivel.

echo [SUPERVISOR] Iniciando ciclo de RPA em %date% %time% >> "%LOG_CICLO%"
echo ---------------------------------------------------------------- >> "%LOG_CICLO%"

REM --- Validação de Caminhos Essenciais ---
echo [SUPERVISOR] Verificando caminho do script principal... >> "%LOG_CICLO%"
echo [SUPERVISOR] Verificando caminho do script principal...
if not exist "%SCRIPT_PRINCIPAL%" (
    echo [SUPERVISOR] ERRO CRITICO: Script principal '%SCRIPT_PRINCIPAL%' nao encontrado. Script abortado. >> "%LOG_CICLO%"
    echo [SUPERVISOR] ERRO CRITICO: Script principal '%SCRIPT_PRINCIPAL%' nao encontrado.
    pause
    exit /b 1
)
echo [SUPERVISOR] Script principal encontrado. >> "%LOG_CICLO%"
echo [SUPERVISOR] Script principal encontrado.

REM --- Encerrar Processos Residuais ---
echo [SUPERVISOR] Tentando encerrar processos residuais do Chrome... >> "%LOG_CICLO%"
echo [SUPERVISOR] Tentando encerrar processos residuais do Chrome...
taskkill /F /IM chrome.exe /T >> "%LOG_CICLO%" 2>&1
echo [SUPERVISOR] Comando taskkill executado (erros sao normais se o Chrome nao estiver aberto). >> "%LOG_CICLO%"
echo [SUPERVISOR] Comando taskkill executado.

REM --- Ativa Venv (Novamente, para garantir dentro do loop) ---
echo [SUPERVISOR] Ativando ambiente virtual para execucao... >> "%LOG_CICLO%"
echo [SUPERVISOR] Ativando ambiente virtual para execucao...
call "%VENV_DIR%\Scripts\activate.bat"
if %ERRORLEVEL% NEQ 0 (
    echo [SUPERVISOR] ERRO: Falha ao reativar ambiente virtual no loop. >> "%LOG_CICLO%"
    echo [SUPERVISOR] ERRO: Falha ao reativar ambiente virtual no loop.
    goto :HANDLE_FAILURE
)
echo [SUPERVISOR] Ambiente virtual ativado. >> "%LOG_CICLO%"
echo [SUPERVISOR] Ambiente virtual ativado.

echo [SUPERVISOR] Executando: python "%SCRIPT_PRINCIPAL%" >> "%LOG_CICLO%" 2>&1
echo [SUPERVISOR] Executando o script principal da RPA agora...

REM --- Executa o Script Python ---
python "%SCRIPT_PRINCIPAL%" >> "%LOG_CICLO%" 2>&1
set SCRIPT_EXIT_CODE=%ERRORLEVEL%

echo [SUPERVISOR] Script Python finalizado com Exit Code: %SCRIPT_EXIT_CODE%. >> "%LOG_CICLO%"
echo [SUPERVISOR] Script Python finalizado com Exit Code: %SCRIPT_EXIT_CODE%.

if %SCRIPT_EXIT_CODE% NEQ 0 (
    goto :HANDLE_FAILURE
) else (
    goto :HANDLE_SUCCESS
)

REM --- SUB-ROTINA DE SUCESSO ---
:HANDLE_SUCCESS
echo.
echo [SUPERVISOR] Tarefas do ciclo concluidas com sucesso.
echo [SUPERVISOR] Pressione CTRL+C para interromper o loop.
echo [SUPERVISOR] Ciclo de RPA finalizado com SUCESSO. >> "%LOG_CICLO%"

echo [SUPERVISOR] Aguardando %PAUSA_SUCESSO_SEGUNDOS% segundos para o proximo ciclo...
powershell -Command "$curTop = [System.Console]::CursorTop; for ($i = %PAUSA_SUCESSO_SEGUNDOS%; $i -ge 1; $i--) { [System.Console]::SetCursorPosition(0, $curTop); $min = [int]($i/60); $sec = $i%%60; Write-Host -NoNewline ('[PAUSA] Proximo ciclo em: {0}m {1:00}s...' -f $min, $sec).PadRight([System.Console]::WindowWidth - 1); Start-Sleep -Seconds 1 }"
echo.
goto :LOOP

REM --- SUB-ROTINA DE FALHA ---
:HANDLE_FAILURE
echo.
echo !!!!!!!!!! FALHA DETECTADA NO CICLO !!!!!!!!!!
echo [SUPERVISOR] O script Python encerrou com erro (Exit Code: %SCRIPT_EXIT_CODE%). Verifique o log '%LOG_CICLO%' para detalhes.
echo [SUPERVISOR] O supervisor vai reiniciar o ciclo em breve. Pressione CTRL+C para cancelar.
echo [SUPERVISOR] !!!!!!!!!! FALHA DETECTADA (Exit Code: %SCRIPT_EXIT_CODE%) em %date% %time% !!!!!!!!!! >> "%LOG_CICLO%"

echo [SUPERVISOR] Aguardando %PAUSA_FALHA_SEGUNDOS% segundos antes de reiniciar...
powershell -Command "$curTop = [System.Console]::CursorTop; for ($i = %PAUSA_FALHA_SEGUNDOS%; $i -ge 1; $i--) { [System.Console]::SetCursorPosition(0, $curTop); Write-Host -NoNewline ('[REINICIANDO] Em: {0}s...' -f $i).PadRight([System.Console]::WindowWidth - 1); Start-Sleep -Seconds 1 }"
echo.
goto :LOOP

:END
endlocal
echo [SUPERVISOR] Script finalizado.
pause

