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
        log.warning(f"Arquivo .env não encontrado em {dotenv_path}. Usando valores padrão/variáveis de ambiente existentes.")
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
    log.info(f"Diretório de comprovantes: {COMPROVANTES_DIR}")
    log.info(f"Diretório de logs: {LOG_DIR}")
except Exception as e:
    log.error(f"Erro ao criar diretórios: {e}")

# URL do portal de custas
URL_PORTAL_CUSTAS = os.getenv("URL_PORTAL_CUSTAS", "https://juridico.bb.com.br/paj/app/paj-custos/spas/custos/custos.app.html#/inicio/*")

# Credenciais do robô para login na API do backend
ROBOT_USERNAME = os.getenv("ROBOT_USERNAME", "robot")
ROBOT_PASSWORD = os.getenv("ROBOT_PASSWORD", "default_password")

# Timeout para esperar por downloads (em milissegundos)
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT_MS", "60000")) # 60 segundos por padrão
log.info(f"Usando DOWNLOAD_TIMEOUT de {DOWNLOAD_TIMEOUT}ms")

# Configurações de Login via Extensão/CDP
CDP_ENDPOINT = os.getenv("CDP_ENDPOINT", "http://localhost:9222")
EXTENSION_URL = os.getenv("EXTENSION_URL", "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html")
# Ajuste o CHROME_USER_DATA_DIR se necessário para sua máquina
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR", str(Path.home() / "chrome-dev-profile-onecost"))
log.info(f"Usando CHROME_USER_DATA_DIR: {CHROME_USER_DATA_DIR}")

# URL base da API do backend
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001") # Corresponde ao docker-compose
log.info(f"Usando API_BASE_URL: {API_BASE_URL}")

# *** NOVO: Tempo limite da sessão do portal em segundos ***
# Define quanto tempo a sessão do portal deve durar antes de forçar um novo login.
# Exemplo: 30 minutos = 1800 segundos. Ajuste conforme necessário.
SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT_SECONDS", "1800")) # Padrão 30 minutos
log.info(f"Usando SESSION_TIMEOUT_SECONDS: {SESSION_TIMEOUT_SECONDS}s")


# Verifica se os diretórios essenciais foram criados (apenas loga)
if not LOG_DIR.exists():
     log.error(f"Falha ao verificar/criar diretório de logs: {LOG_DIR}")
if not SCRIPTS_DIR.exists():
     log.warning(f"Diretório de scripts não encontrado: {SCRIPTS_DIR}")
