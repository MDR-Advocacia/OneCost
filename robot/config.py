import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# --- Configuração de Logging Inicial ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
log = logging.getLogger(__name__)

# --- Carregar Variáveis de Ambiente ---
try:
    dotenv_path = Path(__file__).resolve().parent.parent / '.env'
    log.info(f"Tentando carregar .env de: {dotenv_path}")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)
        log.info("Arquivo .env carregado com sucesso.")
    else:
        log.warning(f"Arquivo .env não encontrado em {dotenv_path}. Usando variáveis de ambiente do sistema.")
except Exception as e:
    log.error(f"Erro ao carregar .env: {e}")

# --- Constantes de Configuração ---

# Diretórios
BASE_DIR = Path(__file__).resolve().parent.parent
ROBOT_DIR = BASE_DIR / "robot"
COMPROVANTES_DIR = BASE_DIR / "comprovantes"
SCRIPTS_DIR = BASE_DIR / "scripts"
LOG_DIR = ROBOT_DIR / "logs"

# Cria os diretórios se não existirem
try:
    COMPROVANTES_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    log.error(f"Erro ao criar diretórios: {e}")

# URL do portal de custas
URL_PORTAL_CUSTAS = os.getenv("URL_PORTAL_CUSTAS", "https://juridico.bb.com.br/paj/app/paj-custos/spas/custos/custos.app.html#/inicio/*")

# Credenciais do robô
ROBOT_USERNAME = os.getenv("ROBOT_USERNAME", "robot")
ROBOT_PASSWORD = os.getenv("ROBOT_PASSWORD", "default_password")

# Credenciais do robô para o AD / OneLog
ONELOG_USERNAME = os.getenv("ONELOG_USERNAME", "robo.onecost")
ONELOG_PASSWORD = os.getenv("ONELOG_PASSWORD", "senha_ad")

# Timeout para esperar por downloads (em milissegundos)
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT_MS", "60000")) 

# URLs das APIs
API_BASE_URL = os.getenv("API_BASE_URL", "http://backend:8000")
ONELOG_API_URL = os.getenv("ONELOG_API_URL", "http://api-onelog.mdradvocacia.com")

# Tempo limite da sessão do portal em segundos
SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))