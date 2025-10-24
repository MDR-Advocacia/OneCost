# robot/core/session_manager.py
import time
import logging
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import Page, Browser, BrowserContext, Playwright

# --- CORREÇÃO DE IMPORT ---
# Importa o login do browser_manager
try:
    from core.browser_manager import realizar_login_automatico
    # SESSION_TIMEOUT_SECONDS é passado como argumento agora
except ModuleNotFoundError:
    robot_dir = Path(__file__).resolve().parent.parent
    if str(robot_dir) not in sys.path:
        sys.path.insert(0, str(robot_dir))
    from core.browser_manager import realizar_login_automatico

# Definição de uma exceção customizada
class SessionExpiredError(Exception):
    """Exceção para quando a sessão do portal expira."""
    pass

def close_browser_safely(browser: Browser, browser_process_ref: dict):
    """Fecha o navegador e o processo associado de forma segura."""
    if browser and browser.is_connected():
        try:
            browser.close()
            logging.info("Browser do Playwright fechado.")
        except Exception as e:
            logging.warning(f"Erro não crítico ao fechar o browser: {e}")

    proc = browser_process_ref.get('process')
    if proc and proc.poll() is None:
        logging.info(f"Tentando finalizar processo do Chrome (PID: {proc.pid})...")
        try:
            if sys.platform == "win32":
                subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                proc.terminate(); time.sleep(0.5)
                if proc.poll() is None: proc.kill()
            logging.info("Processo do Chrome finalizado.")
        except Exception as e:
            logging.warning(f"Não foi possível finalizar o processo do Chrome (PID: {proc.pid}): {e}")

def refresh_session_if_needed(
    playwright: Playwright,
    page: Page,
    browser: Browser,
    context: BrowserContext,
    browser_process_ref: dict,
    session_start_time: float,
    session_timeout_seconds: int # Recebe o timeout como parâmetro
) -> tuple[Page, Browser, BrowserContext, dict, float]:
    """
    Verifica se a sessão expirou com base no tempo. Se sim, fecha o navegador
    atual, inicia uma nova instância e realiza o login novamente.
    """
    elapsed_time = time.time() - session_start_time
    if elapsed_time < session_timeout_seconds:
        # Se o tempo não foi atingido, retorna os objetos atuais
        # Adiciona verificação se a página ainda está conectada
        try:
            # Tenta uma ação simples para verificar se a conexão está ativa
            _ = page.title() # ou page.url
            if not browser.is_connected():
                 raise Exception("Browser desconectado inesperadamente.")
            logging.debug(f"Sessão ainda válida (tempo decorrido: {elapsed_time:.0f}s < {session_timeout_seconds}s)")
            return page, browser, context, browser_process_ref, session_start_time
        except Exception as e_check:
             logging.warning(f"Erro ao verificar estado da página/browser ({e}). Forçando renovação de sessão...")
             # Continua para a lógica de renovação

    logging.warning("="*60)
    logging.warning(f"TEMPO DE SESSÃO ATINGIDO OU CONEXÃO PERDIDA ({elapsed_time:.0f}s). INICIANDO RENOVAÇÃO.")
    logging.warning("="*60)

    # --- LÓGICA DE REINÍCIO ROBUSTA ---
    logging.info("Fechando a instância atual do navegador...")
    close_browser_safely(browser, browser_process_ref)

    logging.info("Aguardando 3 segundos antes de tentar novo login...")
    time.sleep(3)

    # 4. Inicia uma nova sessão completa
    logging.info("Iniciando uma nova sessão com login automático...")
    try:
        new_browser, new_context, new_browser_process_ref, new_page = realizar_login_automatico(playwright)
        new_session_start_time = time.time()
        logging.info("="*60)
        logging.info("RENOVAÇÃO DE SESSÃO CONCLUÍDA COM SUCESSO.")
        logging.info("="*60)
        return new_page, new_browser, new_context, new_browser_process_ref, new_session_start_time
    except Exception as e:
        logging.critical(f"Falha CRÍTICA durante a tentativa de renovar a sessão: {e}", exc_info=True)
        # Tenta fechar o novo browser/processo se ele chegou a ser criado no erro
        if 'new_browser' in locals() or 'new_browser_process_ref' in locals():
            logging.warning("Tentando limpar recursos após falha na renovação...")
            close_browser_safely(locals().get('new_browser'), locals().get('new_browser_process_ref', {}))
        raise SessionExpiredError(f"Não foi possível renovar a sessão após expirar. Erro original: {e}") from e
