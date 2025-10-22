from pathlib import Path
import os
from datetime import datetime

# --- Caminhos Base ---
# Aponta para a raiz do projeto (a pasta que contém 'robot', 'backend', etc.)
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
SCRIPTS_DIR = BASE_DIR / "scripts"
# NOVO: Diretório para salvar os comprovantes
COMPROVANTES_DIR = BASE_DIR / "comprovantes"


# --- Configurações do Robô ---
# URL de custas com o '*' no final, como solicitado
URL_PORTAL_CUSTAS = "https://juridico.bb.com.br/paj/app/paj-custos/spas/custos/custos.app.html#/inicio/*"


# --- Configurações de Login (Restauradas para o seu browser_manager) ---
CDP_ENDPOINT = "http://localhost:9222"
# CORREÇÃO: ID da extensão corrigido, sem o "/page"
EXTENSION_URL = "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html"

# --- Configurações da API Interna ---
# Para rodar localmente fora do Docker, use "http://localhost:8001"
# Para rodar o robô dentro do Docker (no futuro), usaríamos "http://backend:8000"
API_BASE_URL = "http://localhost:8001" 
API_USERNAME = "admin"
API_PASSWORD = "admin"
