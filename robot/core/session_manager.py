# robot/core/session_manager.py
import logging
import time
from playwright.sync_api import Playwright, Browser, BrowserContext, Page
from typing import Tuple, Dict, Any

from core.browser_manager import realizar_login_automatico
from utils.onelog_client import renovar_sessao_onelog

log = logging.getLogger(__name__)

class SessionExpiredError(Exception):
    """Exceção levantada quando a sessão do portal expira irreversivelmente."""
    pass


def _pagina_indica_login_bb(page: Page) -> bool:
    """Reconhece a tela de autenticação do BB mesmo quando a URL não muda claramente."""
    verificacoes = [
        "text=/Bem-vindo à Intranet BB/i",
        "text=/Código do Usuário/i",
        "button:has-text('AUTENTICAR')",
    ]
    for seletor in verificacoes:
        try:
            if page.locator(seletor).is_visible(timeout=750):
                return True
        except Exception:
            pass
    return False

def refresh_session_if_needed(
    playwright: Playwright, 
    page: Page, 
    browser: Browser, 
    context: BrowserContext, 
    browser_process_ref: Dict[str, Any], 
    session_start_time: float, 
    timeout_seconds: int,
    renew_before_seconds: int,
) -> Tuple[Page, Browser, BrowserContext, Dict[str, Any], float]:
    """
    1. Verifica se a página ainda está logada.
    2. Aciona o marcapasso (renew) do OneLog para garantir a imunidade do cookie.
    3. Se o limite de tempo estourar ou a sessão cair, recria o contexto do zero.
    """
    current_time = time.time()
    elapsed_time = current_time - session_start_time

    # Dispara o marcapasso para o backend do OneLog a cada X tempo, ou sempre que passar por aqui
    renovar_sessao_onelog()

    # Verifica se há elementos que indicam que fomos deslogados.
    is_logged_out = _pagina_indica_login_bb(page)
    if not is_logged_out:
        try:
            if page.locator("text=/Sessão Expirada|Faça Login/i").is_visible(timeout=1000):
                is_logged_out = True
        except Exception:
            pass
    if is_logged_out:
        log.warning("Detectada tela de login/sessão expirada no portal.")

    atingiu_janela_preventiva = elapsed_time > renew_before_seconds

    # Força a renovação se entrou na janela preventiva, se o tempo esgotou ou se deslogou
    if atingiu_janela_preventiva or elapsed_time > timeout_seconds or is_logged_out or session_start_time == 0:
        if is_logged_out:
            log.warning("Renovando sessão por queda de login...")
        elif session_start_time == 0:
            log.warning("Renovando sessão por erro anterior no loop...")
        elif atingiu_janela_preventiva:
            log.info(
                "Sessão atingiu a janela preventiva de renovação (%ss > %ss). Reciclando contexto com novos cookies...",
                int(elapsed_time),
                renew_before_seconds,
            )
        else:
            log.info(f"Sessão atingiu o limite de tempo ({elapsed_time:.0f}s > {timeout_seconds}s). Reciclando contexto...")

        # Fecha contexto atual limpamente
        try:
            if page and not page.is_closed(): page.close()
            if context: context.close()
            if browser and browser.is_connected(): browser.close()
        except Exception as e:
            log.warning(f"Erro ao limpar contexto antigo: {e}")

        # Recria do zero usando o novo fluxo Headless + OneLog
        try:
            novo_browser, novo_context, novo_ref, nova_page = realizar_login_automatico(playwright)
            novo_session_start_time = time.time()
            log.info("Sessão renovada com sucesso via OneLog.")
            return nova_page, novo_browser, novo_context, novo_ref, novo_session_start_time
        except Exception as e:
            log.critical(f"Falha crítica ao tentar renovar a sessão via OneLog: {e}")
            raise SessionExpiredError(f"Não foi possível renovar a sessão: {e}")

    # Se estiver tudo bem, devolve as mesmas variáveis
    return page, browser, context, browser_process_ref, session_start_time
