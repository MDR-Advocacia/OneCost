# robot/core/browser_manager.py
import logging
from playwright.sync_api import Playwright, Browser, BrowserContext, Page
from typing import Tuple

from config import URL_PORTAL_CUSTAS
from utils.onelog_client import obter_sessao_onelog

log = logging.getLogger(__name__)

def realizar_login_automatico(playwright: Playwright) -> Tuple[Browser, BrowserContext, dict, Page]:
    """
    Substitui a automação visual/extensão pela injeção direta de cookies da API do OneLog.
    Roda nativamente em modo Headless no Docker.
    """
    log.info("--- MÓDULO DE LOGIN: INJEÇÃO DE SESSÃO ONELOG (HEADLESS) ---")

    # 1. Busca os cookies e o User-Agent autorizados no OneLog
    dados_sessao = obter_sessao_onelog()
    cookies_onelog = dados_sessao.get("cookies", [])
    user_agent_onelog = dados_sessao.get("user_agent")

    # 2. Inicia o navegador do Playwright (Com interface gráfica renderizada no Xvfb)
    log.info("Iniciando Chromium com Tela Virtual (Headless=False)...")
    browser = playwright.chromium.launch(
        headless=False,
        args=[
            "--disable-dev-shm-usage", 
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars"
        ]
    )

    # 3. Cria um contexto clonando a impressão digital do OneLog para evitar o Cloudflare
    log.info(f"Criando contexto blindado com User-Agent: {user_agent_onelog}")
    context = browser.new_context(
        user_agent=user_agent_onelog,
        viewport={'width': 1920, 'height': 1080},
        locale='pt-BR',
        timezone_id='America/Sao_Paulo'
    )

    # 4. Injeta os cookies
    log.info(f"Injetando {len(cookies_onelog)} cookies na sessão...")
    
    # Formata os cookies do OneLog para o padrão exigido pelo Playwright
    cookies_formatados = []
    for cookie in cookies_onelog:
        c = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie["domain"],
            "path": cookie["path"],
            "secure": cookie.get("secure", True)
        }
        cookies_formatados.append(c)
        
    context.add_cookies(cookies_formatados)

    # 5. Navega direto para a página de custas
    log.info(f"Navegando diretamente para o portal de custas: {URL_PORTAL_CUSTAS}")
    page = context.new_page()
    page.goto(URL_PORTAL_CUSTAS)
    
    # Aguarda a página estabilizar
    page.wait_for_load_state("domcontentloaded", timeout=60000)
    
    # Referência vazia para manter compatibilidade com o main.py antigo que esperava um subprocesso
    browser_process_ref = {} 
    
    log.info("[SUCESSO] Portal carregado via injeção de sessão do OneLog!")
    
    return browser, context, browser_process_ref, page