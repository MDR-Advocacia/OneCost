# robot/core/session_manager.py
import time
import logging
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import Page, Browser, BrowserContext, Playwright

# --- CORREÇÃO DE IMPORT ---
# Importa o login do nosso novo módulo e as configs do config.py
try:
    from core.browser_manager import realizar_login_automatico
    from config import SESSION_TIMEOUT_SECONDS
except ModuleNotFoundError:
    # Adiciona o diretório 'robot' ao sys.path se não encontrar
    robot_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(robot_dir))
    from core.browser_manager import realizar_login_automatico
    from config import SESSION_TIMEOUT_SECONDS


# Definição de uma exceção customizada para ser mais explícita
class SessionExpiredError(Exception):
    """Exceção para quando a sessão do portal expira."""
    pass


def refresh_session_if_needed(
    playwright: Playwright,
    page: Page,
    browser: Browser,
    context: BrowserContext,
    browser_process_ref: dict,
    session_start_time: float
) -> tuple[Page, Browser, BrowserContext, dict, float]:
    """
    Verifica se a sessão expirou com base no tempo. Se sim, fecha o navegador
    atual, inicia uma nova instância e realiza o login novamente de forma robusta.
    """
    elapsed_time = time.time() - session_start_time
    if elapsed_time < SESSION_TIMEOUT_SECONDS:
        # Se o tempo não foi atingido, retorna os objetos atuais sem alteração
        return page, browser, context, browser_process_ref, session_start_time

    logging.warning("="*60)
    logging.warning(f"TEMPO DE SESSÃO ATINGIDO ({elapsed_time:.0f}s). INICIANDO RENOVAÇÃO FORÇADA.")
    logging.warning("="*60)

    # --- LÓGICA DE REINÍCIO ROBUSTA ---
    logging.info("Fechando a instância atual do navegador e seus processos...")
    
    # 1. Desconecta o Playwright do navegador
    if browser and browser.is_connected():
        try:
            browser.close()
        except Exception as e:
            logging.warning(f"Erro não crítico ao fechar o browser (pode já estar fechado): {e}")

    # 2. Finaliza o processo do chrome.exe
    proc = browser_process_ref.get('process')
    if proc and proc.poll() is None:
        try:
            if sys.platform == "win32":
                subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, capture_output=True, check=False)
            else:
                proc.kill()
            logging.info(f"Processo do navegador (PID: {proc.pid}) finalizado com sucesso.")
        except Exception as e:
            logging.warning(f"Não foi possível finalizar o processo do navegador: {e}")

    logging.info("Aguardando 5 segundos para garantir a liberação de recursos do sistema...")
    time.sleep(5)

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
        raise SessionExpiredError(f"Não foi possível renovar a sessão após expirar. Erro original: {e}") from e