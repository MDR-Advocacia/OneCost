# robot/config.py
from pathlib import Path

# --- Configurações de Paths ---
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
SCRIPTS_DIR = BASE_DIR / "scripts"

# --- Configurações do Robô ---
URL_PORTAL_CUSTAS = "https://juridico.bb.com.br/paj/app/paj-custos/spas/custos/custos.app.html#/inicio/*"

# --- Configurações de Login (Vindas do antigo autologin.py) ---
CDP_ENDPOINT = "http://localhost:9222"
EXTENSION_URL = "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html"

# --- Configurações de Sessão (Vindas do antigo session.py) ---
SESSION_TIMEOUT_SECONDS = 30 * 60  # 30 minutos