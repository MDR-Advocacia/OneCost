# robot/core/browser_manager.py
import time
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import Playwright, Browser, BrowserContext, Page, Error

# Importa as configurações do config.py
try:
    from config import CDP_ENDPOINT, EXTENSION_URL, SCRIPTS_DIR
except ModuleNotFoundError:
    # Adiciona o diretório 'robot' ao sys.path se não encontrar
    robot_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(robot_dir))
    from config import CDP_ENDPOINT, EXTENSION_URL, SCRIPTS_DIR


# --- CONFIGURAÇÕES DO MÓDULO ---
BAT_FILE_NAME = "abrir_chrome.sh" if sys.platform != "win32" else "abrir_chrome.bat"
BAT_FILE_PATH = SCRIPTS_DIR / BAT_FILE_NAME # Caminho corrigido usando config


def realizar_login_automatico(playwright: Playwright) -> tuple[Browser, BrowserContext, dict, Page]:
    """
    Executa o login de forma 100% automatizada, implementando a lógica robusta de
    capturar a nova aba e aguardar pela sua estabilização.
    """
    print("--- MÓDULO DE LOGIN AUTOMÁTICO (SOLUÇÃO DEFINITIVA V2) ---")
    
    popen_args = {"shell": True}
    if sys.platform == "win32":
        popen_args['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP

    print(f"[>>] Garantindo que o Chrome está em execução via: {BAT_FILE_PATH}")
    browser_process = subprocess.Popen(str(BAT_FILE_PATH), **popen_args)
    
    browser = None
    for attempt in range(25): 
        time.sleep(2)
        print(f"    Tentativa de conexão nº {attempt + 1}...")
        try:
            browser = playwright.chromium.connect_over_cdp(CDP_ENDPOINT)
            print("[OK] Conectado com sucesso ao navegador!")
            break 
        except Error:
            if attempt == 24:
                raise ConnectionError("Falha ao conectar. Verifique se o Chrome está rodando em modo de depuração.")
            continue
    
    if not browser:
        raise ConnectionError("Não foi possível conectar ao navegador.")

    context = browser.contexts[0]
    for page in context.pages:
        if not page.is_closed():
            page.close()
    
    browser_process_ref = {'process': browser_process}

    try:
        # ETAPA 1: Abrir a extensão
        print("[INFO] Abrindo a página da extensão...")
        extension_page = context.new_page()
        extension_page.goto(EXTENSION_URL)
        search_input = extension_page.get_by_placeholder("Digite ou selecione um sistema pra acessar")
        search_input.wait_for(state="visible", timeout=15000)
        
        # ETAPA 2: Preencher e clicar nos itens da extensão
        search_input.fill("banco do")
        extension_page.locator('div[role="menuitem"]:not([disabled])', has_text="Banco do Brasil - Intranet").first.click()
        
        # ETAPA 3: A MUDANÇA CRÍTICA - Esperar pelo evento de nova página
        print("[INFO] Ativando 'escutador' para a página do portal...")
        with context.expect_page(timeout=90000) as new_page_info:
            print("[INFO] Clicando em ACESSAR...")
            extension_page.get_by_role("button", name="ACESSAR").click()

        # ETAPA 4: Capturar a página correta e aguardar
        portal_page = new_page_info.value
        print(f"[OK] Nova página do portal capturada! URL: {portal_page.url}")
        
        portal_page.wait_for_load_state("domcontentloaded", timeout=60000)

        # ETAPA 5: Agora sim, esperamos pelo elemento de confirmação na página correta
        print("[INFO] Aguardando o elemento de confirmação ('#aPaginaInicial') na página capturada...")
        portal_page.locator("#aPaginaInicial").wait_for(state="visible", timeout=90000)
        
        print("[INFO] Elemento encontrado. Aguardando a página se estabilizar completamente...")
        portal_page.wait_for_load_state("networkidle", timeout=45000)

        print("[SUCESSO] Login 100% automatizado concluído com sucesso!")
        
        if not extension_page.is_closed():
            extension_page.close()
            
        return browser, context, browser_process_ref, portal_page

    except Exception as e:
        print("\n" + "="*60)
        print("[ERRO CRÍTICO] Falha grave durante o processo de login automatizado.")
        print(f"Detalhes do erro: {e}")
        print("="*60 + "\n")
        
        proc = browser_process_ref.get('process')
        if proc and proc.poll() is None:
            if sys.platform == "win32":
                subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, capture_output=True)
            else:
                proc.kill()
        raise