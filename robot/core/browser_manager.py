# robot/core/browser_manager.py
import logging
import time
import subprocess
import sys
import os # Import os module
from pathlib import Path
from playwright.sync_api import Playwright, Browser, BrowserContext, Page, Error
from typing import Tuple, Optional # Import Optional

# Importa as configurações do config.py
try:
    robot_dir = Path(__file__).resolve().parent.parent
    if str(robot_dir) not in sys.path:
        sys.path.insert(0, str(robot_dir))
    # Usa CHROME_USER_DATA_DIR de config.py para consistencia
    from config import CDP_ENDPOINT, EXTENSION_URL, CHROME_USER_DATA_DIR
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import CDP_ENDPOINT, EXTENSION_URL, CHROME_USER_DATA_DIR
except ImportError as e:
    # Handle potential import errors more gracefully during initialization
    print(f"Erro ao importar configuracoes: {e}")
    # Define fallbacks if config import fails, though this shouldn't normally happen
    CDP_ENDPOINT = "http://localhost:9222"
    EXTENSION_URL = "chrome-extension://lnidijeaekolpfeckelhkomndglcglhh/index.html"
    CHROME_USER_DATA_DIR = str(Path.home() / "chrome-dev-profile-onecost")


# --- Função para encontrar o Chrome (Windows) ---
def find_chrome_executable() -> Optional[str]:
    """Tenta encontrar o executável do Chrome em locais comuns no Windows."""
    possible_paths = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LocalAppData", "")) / "Google" / "Chrome" / "Application" / "chrome.exe"
    ]
    for path in possible_paths:
        if path.is_file(): # Check if it's a file specifically
            logging.info(f"Executável do Chrome encontrado em: {path}")
            return str(path)
    logging.error("Não foi possível encontrar o executável do Chrome nos caminhos padrão.")
    return None

# --- Função Principal de Login ---
def realizar_login_automatico(playwright: Playwright) -> Tuple[Browser, BrowserContext, dict, Page]:
    """
    Executa o login chamando o chrome.exe diretamente com os parâmetros necessários,
    conecta-se a ele via CDP e gerencia a navegação.
    Timings otimizados.
    """
    logging.info("--- MÓDULO DE LOGIN AUTOMÁTICO (Chamada Direta + CDP + EXTENSÃO V3) ---")

    chrome_exec_path: Optional[str] = None
    browser_process = None # Inicializa como None

    # Encontrar ou definir o caminho do Chrome
    if sys.platform == "win32":
        chrome_exec_path = find_chrome_executable()
        if not chrome_exec_path:
            raise FileNotFoundError("Executável do Chrome não encontrado automaticamente. Verifique a instalação ou ajuste a função find_chrome_executable.")
    elif sys.platform == "darwin": # macOS
        chrome_exec_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if not Path(chrome_exec_path).exists():
             raise FileNotFoundError(f"Executável do Chrome não encontrado em {chrome_exec_path} (macOS).")
    else: # Linux (pode precisar de ajuste)
        chrome_exec_path = "/usr/bin/google-chrome" # Ou similar
        if not Path(chrome_exec_path).exists():
            logging.warning(f"Executável do Chrome não encontrado em {chrome_exec_path} (Linux). Tentando 'chromium-browser'...")
            chrome_exec_path = "/usr/bin/chromium-browser"
            if not Path(chrome_exec_path).exists():
                raise FileNotFoundError("Executável do Chrome/Chromium não encontrado (Linux).")

    profile_path = str(Path(CHROME_USER_DATA_DIR).resolve())
    logging.info(f"Usando perfil de usuário em: {profile_path}")

    # Argumentos para iniciar o Chrome (COM --user-data-dir)
    chrome_args = [
        chrome_exec_path,
        f"--remote-debugging-port={CDP_ENDPOINT.split(':')[-1]}",
        f"--user-data-dir={profile_path}"
    ]

    popen_args = {}
    if sys.platform == "win32":
        # Mantem CREATE_NO_WINDOW para evitar janela piscando
        popen_args['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    try:
        logging.info(f"Iniciando Chrome diretamente: {' '.join(chrome_args)}")
        browser_process = subprocess.Popen(chrome_args, **popen_args)
        logging.info(f"Processo do Chrome iniciado (PID: {browser_process.pid}). Aguardando um pouco...")
        # *** REDUZIDO TEMPO DE ESPERA INICIAL ***
        time.sleep(1.5) # Espera 1.5 segundos (era 3)
        process_status = browser_process.poll()
        if process_status is not None:
            logging.error(f"O processo do Chrome terminou inesperadamente logo após iniciar (Exit Code: {process_status}).")
            raise ConnectionError(f"Chrome encerrou prematuramente (Exit Code: {process_status}). Verifique logs do sistema ou conflitos.")
        logging.info("Processo do Chrome ainda está rodando após espera inicial. Continuando para conexão CDP...")
    except Exception as e_popen:
        logging.error(f"Falha ao iniciar ou verificar o processo do Chrome: {e_popen}", exc_info=True)
        if browser_process and browser_process.poll() is None:
             try: browser_process.kill()
             except: pass
        raise ConnectionError(f"Não foi possível iniciar o Chrome. Erro: {e_popen}") from e_popen


    browser = None
    max_attempts = 15 # Reduzido (era 25)
    wait_interval = 2 # Reduzido (era 3)

    # Tempo total de espera: 1.5 + (14 * 2) = ~29.5 segundos (era ~77s)
    logging.info(f"Aguardando até ~30 segundos para conectar ao Chrome em {CDP_ENDPOINT}...")

    # Tenta conectar
    for attempt in range(max_attempts):
        # Pequena pausa antes da primeira tentativa real após a verificação
        if attempt == 0:
            time.sleep(0.5)
        else:
            time.sleep(wait_interval)

        logging.info(f"Tentativa de conexão nº {attempt + 1}/{max_attempts}...")
        try:
            browser = playwright.chromium.connect_over_cdp(CDP_ENDPOINT)
            logging.info("Conectado com sucesso ao navegador!")
            # *** REMOVIDA PAUSA EXTRA APÓS CONECTAR ***
            # logging.info("Aguardando 3 segundos extras após conectar...")
            # time.sleep(3)
            break # Sai do loop se conectar
        except Error as e_connect:
            logging.warning(f"Falha na tentativa {attempt + 1}: {e_connect}")
            if attempt == max_attempts - 1:
                logging.error(f"Falha ao conectar após {max_attempts} tentativas.")
                # Tenta matar o processo do Chrome
                if browser_process and browser_process.poll() is None:
                    logging.warning("Tentando encerrar processo do Chrome...")
                    try:
                        if sys.platform == "win32":
                            subprocess.run(f"TASKKILL /F /PID {browser_process.pid} /T", shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            browser_process.kill()
                        logging.info("Processo do Chrome finalizado.")
                    except Exception as e_kill_direct:
                        logging.error(f"Erro ao tentar finalizar processo do Chrome: {e_kill_direct}")
                raise ConnectionError(f"Falha ao conectar ao Chrome em {CDP_ENDPOINT}.")

    if not browser:
        raise ConnectionError("Não foi possível conectar ao navegador.")

    context = browser.contexts[0]
    logging.info("Limpando páginas existentes no contexto do navegador...")
    initial_pages = list(context.pages)
    for page in initial_pages:
        if not page.is_closed():
            if len(initial_pages) > 1 and EXTENSION_URL not in page.url and "about:blank" not in page.url:
                try: page.close()
                except Exception as e_close: logging.warning(f"Não foi possível fechar uma página pré-existente ({page.url}): {e_close}")
            else:
                logging.info(f"Mantendo página inicial: {page.url}")
    logging.info("Páginas limpas (ou mantida a inicial).")

    browser_process_ref = {'process': browser_process}

    try:
        # ETAPA 1: Abrir a extensão
        logging.info(f"Abrindo a página da extensão: {EXTENSION_URL}")
        # Aumenta um pouco o timeout default para new_page pode ajudar
        # context.set_default_timeout(10000) # Exemplo: 10 segundos
        extension_page = context.new_page()
        extension_page.goto(EXTENSION_URL)
        search_input = extension_page.get_by_placeholder("Digite ou selecione um sistema pra acessar")
        search_input.wait_for(state="visible", timeout=15000)

        # ETAPAS 2 a 5
        logging.info("Interagindo com a extensão...")
        search_input.fill("banco do")
        extension_page.locator('div[role="menuitem"]:not([disabled])', has_text="Banco do Brasil - Intranet").first.click()

        logging.info("Ativando 'escutador' para a página do portal...")
        with context.expect_page(timeout=90000) as new_page_info:
            logging.info("Clicando em ACESSAR...")
            extension_page.get_by_role("button", name="ACESSAR").click()

        portal_page = new_page_info.value
        logging.info(f"Nova página do portal capturada! URL: {portal_page.url}")

        portal_page.wait_for_load_state("domcontentloaded", timeout=60000)
        logging.info("Aguardando o elemento de confirmação ('#aPaginaInicial') na página capturada...")
        portal_page.locator("#aPaginaInicial").wait_for(state="visible", timeout=90000)
        logging.info("Elemento encontrado. Aguardando a página se estabilizar completamente...")
        portal_page.wait_for_load_state("networkidle", timeout=45000)
        logging.info("Login 100% automatizado concluído com sucesso!")

        if not extension_page.is_closed():
            try: extension_page.close()
            except Exception as e_close_ext: logging.warning(f"Não foi possível fechar a página da extensão: {e_close_ext}")

        return browser, context, browser_process_ref, portal_page

    except Exception as e:
        logging.error(f"Falha grave durante o processo de login automatizado: {type(e).__name__} - {e}", exc_info=True)
        proc = browser_process_ref.get('process')
        if proc and proc.poll() is None:
            logging.warning("Tentando encerrar o processo do Chrome devido a erro...")
            try:
                if sys.platform == "win32":
                    subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    proc.terminate(); time.sleep(1)
                    if proc.poll() is None: proc.kill()
                logging.info(f"Processo do navegador (PID: {proc.pid}) finalizado.")
            except Exception as e_kill:
                logging.error(f"Erro ao tentar finalizar o processo do navegador: {e_kill}")
        raise

