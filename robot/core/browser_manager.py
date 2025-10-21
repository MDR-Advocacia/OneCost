# robot/core/browser_manager.py
import logging
import time
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import Playwright, Browser, BrowserContext, Page, Error
from typing import Tuple

# Importa as configurações do config.py
try:
    # Adiciona o diretório 'robot' ao sys.path para garantir que 'config' seja encontrado
    robot_dir = Path(__file__).resolve().parent.parent
    if str(robot_dir) not in sys.path:
        sys.path.insert(0, str(robot_dir))
    from config import CDP_ENDPOINT, EXTENSION_URL, SCRIPTS_DIR
except ModuleNotFoundError:
    # Fallback caso a estrutura mude
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from config import CDP_ENDPOINT, EXTENSION_URL, SCRIPTS_DIR


# --- CONFIGURAÇÕES DO MÓDULO ---
BAT_FILE_NAME = "abrir_chrome.sh" if sys.platform != "win32" else "abrir_chrome.bat"
BAT_FILE_PATH = SCRIPTS_DIR / BAT_FILE_NAME


def realizar_login_automatico(playwright: Playwright) -> Tuple[Browser, BrowserContext, dict, Page]:
    """
    Executa o login abrindo uma instância específica do Chrome com a extensão,
    conecta-se a ela via CDP e gerencia a navegação.
    """
    logging.info("--- MÓDULO DE LOGIN AUTOMÁTICO (CDP + EXTENSÃO) ---")
    
    popen_args = {"shell": True}
    if sys.platform == "win32":
        popen_args['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

    logging.info(f"Garantindo que o Chrome está em execução via: {BAT_FILE_PATH}")
    browser_process = subprocess.Popen(str(BAT_FILE_PATH), **popen_args)
    
    browser = None
    # Tenta conectar ao navegador por até 50 segundos
    for attempt in range(25): 
        time.sleep(2)
        logging.info(f"Tentativa de conexão nº {attempt + 1}...")
        try:
            browser = playwright.chromium.connect_over_cdp(CDP_ENDPOINT)
            logging.info("Conectado com sucesso ao navegador!")
            break 
        except Error:
            if attempt == 24:
                raise ConnectionError("Falha ao conectar. Verifique se o Chrome está rodando em modo de depuração.")
            continue
    
    if not browser:
        raise ConnectionError("Não foi possível conectar ao navegador.")

    context = browser.contexts[0]
    # Limpa páginas antigas para começar com um ambiente limpo
    for page in context.pages:
        if not page.is_closed():
            page.close()
    
    browser_process_ref = {'process': browser_process}

    try:
        # ETAPA 1: Abrir a extensão
        logging.info(f"Abrindo a página da extensão: {EXTENSION_URL}")
        extension_page = context.new_page()
        extension_page.goto(EXTENSION_URL)
        search_input = extension_page.get_by_placeholder("Digite ou selecione um sistema pra acessar")
        search_input.wait_for(state="visible", timeout=15000)
        
        # ETAPA 2: Preencher e clicar nos itens da extensão
        search_input.fill("banco do")
        extension_page.locator('div[role="menuitem"]:not([disabled])', has_text="Banco do Brasil - Intranet").first.click()
        
        # ETAPA 3: Esperar pelo evento de nova página
        logging.info("Ativando 'escutador' para a página do portal...")
        with context.expect_page(timeout=90000) as new_page_info:
            logging.info("Clicando em ACESSAR...")
            extension_page.get_by_role("button", name="ACESSAR").click()

        # ETAPA 4: Capturar a página correta e aguardar
        portal_page = new_page_info.value
        logging.info(f"Nova página do portal capturada! URL: {portal_page.url}")
        
        portal_page.wait_for_load_state("domcontentloaded", timeout=60000)

        # ETAPA 5: Esperar pelo elemento de confirmação na página correta
        logging.info("Aguardando o elemento de confirmação ('#aPaginaInicial') na página capturada...")
        portal_page.locator("#aPaginaInicial").wait_for(state="visible", timeout=90000)
        
        logging.info("Elemento encontrado. Aguardando a página se estabilizar completamente...")
        portal_page.wait_for_load_state("networkidle", timeout=45000)

        logging.info("Login 100% automatizado concluído com sucesso!")
        
        if not extension_page.is_closed():
            extension_page.close()
            
        return browser, context, browser_process_ref, portal_page

    except Exception as e:
        logging.error("Falha grave durante o processo de login automatizado.", exc_info=True)
        
        proc = browser_process_ref.get('process')
        if proc and proc.poll() is None:
            logging.warning("Tentando encerrar o processo do Chrome...")
            if sys.platform == "win32":
                subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, capture_output=True)
            else:
                proc.kill()
        raise

