import os
import random
import logging
from pathlib import Path
from urllib.parse import urlparse, urlunparse
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


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "sim", "on"}

# URLs das APIs
def _normalize_internal_api_base_url(url: str) -> str:
    """Migra automaticamente o hostname legado 'backend' para o serviço atual."""
    normalized_url = (url or "http://onecost-backend:8000").rstrip("/")
    try:
        parsed = urlparse(normalized_url)
        if parsed.hostname != "backend":
            return normalized_url

        host = "onecost-backend"
        if parsed.port:
            host = f"{host}:{parsed.port}"

        return urlunparse(parsed._replace(netloc=host)).rstrip("/")
    except Exception:
        return normalized_url


raw_api_base_url = os.getenv("API_BASE_URL", "http://onecost-backend:8000")
API_BASE_URL = _normalize_internal_api_base_url(raw_api_base_url)
if API_BASE_URL != raw_api_base_url.rstrip("/"):
    log.warning(
        "API_BASE_URL legado detectado (%s). Usando %s no lugar.",
        raw_api_base_url,
        API_BASE_URL,
    )

ONELOG_API_URL = os.getenv("ONELOG_API_URL", "http://api-onelog.mdradvocacia.com")

# Tempo limite da sessão do portal em segundos
SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))
# Janela preventiva para reciclar cookies/contexto antes da expiração habitual (~30 min)
SESSION_RENEW_BEFORE_SECONDS = int(os.getenv("SESSION_RENEW_BEFORE_SECONDS", "1320"))

# Fila e cadência do robô
ROBOT_QUEUE_STATUSES = os.getenv(
    "ROBOT_QUEUE_STATUSES",
    "Pendente,Monitorando retorno do banco",
)
ROBOT_MAX_ITEMS_PER_CYCLE = int(os.getenv("ROBOT_MAX_ITEMS_PER_CYCLE", "20"))
ROBOT_RECENT_PENDING_DAYS = int(os.getenv("ROBOT_RECENT_PENDING_DAYS", "10"))
ROBOT_MONITORING_LOOKBACK_DAYS = int(os.getenv("ROBOT_MONITORING_LOOKBACK_DAYS", "10"))
ROBOT_MONITORING_RECHECK_MINUTES = int(os.getenv("ROBOT_MONITORING_RECHECK_MINUTES", "30"))
ROBOT_RESET_ERRORS_ON_START = _env_bool("ROBOT_RESET_ERRORS_ON_START", "false")

# Proxy opcional para o navegador que acessa o portal BB.
# Espelha o OneLog: aceita uma lista em PROXY_LIST/BB_BROWSER_PROXY_LIST e escolhe
# um endpoint no momento de abrir o Chromium.
_proxy_env = (
    os.getenv("BB_BROWSER_PROXY_LIST")
    or os.getenv("PROXY_LIST")
    or os.getenv("BB_BROWSER_PROXY_SERVER", "")
)
BB_BROWSER_PROXY_SERVERS = [p.strip() for p in _proxy_env.split(",") if p.strip()]
BB_BROWSER_PROXY_SERVER = BB_BROWSER_PROXY_SERVERS[0] if BB_BROWSER_PROXY_SERVERS else ""
BB_BROWSER_PROXY_USERNAME = os.getenv("BB_BROWSER_PROXY_USERNAME", "").strip()
BB_BROWSER_PROXY_PASSWORD = os.getenv("BB_BROWSER_PROXY_PASSWORD", "").strip()


def escolher_bb_browser_proxy() -> dict | None:
    if not BB_BROWSER_PROXY_SERVERS:
        return None

    proxy_config = {"server": random.choice(BB_BROWSER_PROXY_SERVERS)}
    if BB_BROWSER_PROXY_USERNAME:
        proxy_config["username"] = BB_BROWSER_PROXY_USERNAME
    if BB_BROWSER_PROXY_PASSWORD:
        proxy_config["password"] = BB_BROWSER_PROXY_PASSWORD
    return proxy_config
