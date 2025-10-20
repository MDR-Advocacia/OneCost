#!/bin/bash
# run_robot.sh

# Para o script se qualquer comando falhar
set -e

echo "--- Script de Inicialização do OneCost Robot (macOS) ---"

# 1. Verifica/Cria o Ambiente Virtual (venv)
if [ ! -d "venv" ]; then
    echo "[INFO] Ambiente 'venv' não encontrado. Criando..."
    python3 -m venv venv
else
    echo "[INFO] Ambiente 'venv' já existe."
fi

# 2. Ativa o Ambiente Virtual
echo "[INFO] Ativando venv..."
source venv/bin/activate

# 3. Instala/Atualiza as Dependências
echo "[INFO] Instalando dependências do requirements.txt..."
pip install -r requirements.txt

# 4. Instala os Navegadores do Playwright (só instala se faltar)
echo "[INFO] Instalando/Verificando navegadores do Playwright..."
playwright install

# 5. Executa o Robô!
echo "[INFO] 🤖 Iniciando execução do main.py..."
python robot/main.py

echo "--- Execução finalizada. ---"

# (O venv permanece ativo no seu terminal após o script,
#  você pode desativar digitando 'deactivate')