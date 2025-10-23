import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PlaywrightError
import json
from decimal import Decimal, InvalidOperation
import subprocess

# --- Bloco de segurança ---
try:
    robot_dir = Path(__file__).resolve().parent
    if str(robot_dir) not in sys.path:
        sys.path.insert(0, str(robot_dir))
except NameError:
    sys.path.insert(0, str(Path.cwd()))
# --- Fim do bloco ---

try:
    from config import (
        URL_PORTAL_CUSTAS, LOG_DIR, ROBOT_USERNAME, ROBOT_PASSWORD,
        API_BASE_URL, CDP_ENDPOINT, EXTENSION_URL
    )
    from core.browser_manager import realizar_login_automatico
    from core.custos_manager import processar_solicitacao_especifica
    # Importa as funções do api_client (não mais uma classe)
    from utils.api_client import (
        get_proxima_solicitacao_pendente,
        update_solicitacao_na_api,
        robot_login,
        resetar_solicitacoes_com_erro # Importa a nova função
    )
except ModuleNotFoundError as e:
    print("="*80); print(f"ERRO DE IMPORTAÇÃO (ModuleNotFoundError): {e}"); print(f"sys.path: {sys.path}"); print("="*80); sys.exit(1)
except ImportError as e:
    print("="*80); print(f"ERRO DE IMPORTAÇÃO ESPECÍFICO: {e}"); print("="*80); sys.exit(1)

# --- Configuração de Log Dinâmico ---
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_filename = f"onecost_robot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
log_filepath = LOG_DIR / log_filename
log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
for handler in root_logger.handlers[:]: root_logger.removeHandler(handler)
file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
root_logger.addHandler(stream_handler)
log = logging.getLogger(__name__)

# --- Função Principal ---
def main():
    log.info("=" * 60); log.info(f"🤖 INICIANDO ROBO ONECOST | LOG: {log_filename} 🤖"); log.info("=" * 60)

    browser = None; context = None; page = None; browser_process_ref = None
    solicitacao_atual = None; resultado_processamento = None

    try:
        # FASE -1: Autenticar Robô na API
        log.info("FASE -1: Autenticando robô na API...")
        if not robot_login(ROBOT_USERNAME, ROBOT_PASSWORD):
            log.critical("Falha ao autenticar robô na API. Encerrando.")
            return

        # FASE -0.5: Resetar Erros
        log.info("FASE -0.5: Resetando solicitações com status de erro...")
        if not resetar_solicitacoes_com_erro():
            log.warning("Não foi possível resetar os status de erro na API. Continuando...")
        else:
            log.info("Status de erro resetados (se houveram).")

        # FASE 0: Buscar Solicitação Pendente
        log.info("FASE 0: Buscando solicitação pendente na API...")
        solicitacao_atual = get_proxima_solicitacao_pendente()

        if not solicitacao_atual:
            log.info("Nenhuma solicitação pendente para processar. Encerrando.")
            return

        log.info(f"Solicitação ID {solicitacao_atual['id']} (NPJ: {solicitacao_atual['npj']}) será processada.")
        try:
            solicitacao_atual['valor'] = Decimal(str(solicitacao_atual.get('valor', '0.0')))
        except InvalidOperation:
            log.error(f"Valor inválido na solicitação ID {solicitacao_atual['id']}: {solicitacao_atual.get('valor')}. Usando 0.0.")
            solicitacao_atual['valor'] = Decimal("0.0")

        # Inicia o Playwright
        with sync_playwright() as playwright:
            # FASE 1: Login no Portal
            log.info("FASE 1: Realizando login no portal via CDP/Extensão...")
            browser, context, browser_process_ref, page = realizar_login_automatico(playwright)
            log.info("[SUCESSO] Login realizado.")

            # FASE 2: Navegar para a Página de Custas
            log.info(f"FASE 2: Navegando para a página de Custas: {URL_PORTAL_CUSTAS}")
            page.goto(URL_PORTAL_CUSTAS)
            log.info("Aguardando carregamento inicial da página de custos...")
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_selector("input[placeholder='Informe o NPJ'], button:has-text('Limpar')", timeout=30000)
            log.info("[SUCESSO] Página de Custas carregada!")

            # FASE 3: Processar a Custa Específica
            log.info(f"FASE 3: Iniciando processamento da custa ID {solicitacao_atual['id']}...")
            resultado_processamento = processar_solicitacao_especifica(page, solicitacao_atual)

    except PlaywrightError as e:
        log.critical(f"Erro Playwright: {e}", exc_info=True)
        if solicitacao_atual and not resultado_processamento:
            resultado_processamento = {"solicitacao_id": solicitacao_atual['id'], "status_robo_final": "Erro: Falha Playwright"}
    except ConnectionError as e:
         log.critical(f"Erro Conexão CDP: {e}", exc_info=True)
         if solicitacao_atual and not resultado_processamento:
             resultado_processamento = {"solicitacao_id": solicitacao_atual['id'], "status_robo_final": "Erro: Falha Conexão CDP"}
    except Exception as e:
        log.critical(f"Falha crítica inesperada.", exc_info=True)
        if solicitacao_atual and not resultado_processamento:
             resultado_processamento = {"solicitacao_id": solicitacao_atual['id'], "status_robo_final": f"Erro Crítico: {type(e).__name__}"}

    finally:
        # FASE 4: Atualizar Status na API
        if resultado_processamento and "solicitacao_id" in resultado_processamento:
            sol_id = resultado_processamento["solicitacao_id"]
            log.info(f"FASE 4: Tentando atualizar status da solicitação ID {sol_id} na API...")
            payload_api = {
                "status_robo": resultado_processamento.get("status_robo_final", "Erro: Status Desconhecido"),
                "status_portal": resultado_processamento.get("status_portal_encontrado"),
                "comprovantes_path": [str(p) for p in resultado_processamento.get("lista_arquivos_baixados", [])],
                "numero_processo": resultado_processamento.get("numero_processo_completo")
            }
            log.debug(f"Payload para API (ID {sol_id}): {json.dumps(payload_api, default=str)}")
            if not update_solicitacao_na_api(sol_id, payload_api): log.error(f"[ERRO] Falha ao atualizar solicitação ID {sol_id} na API.")
            else: log.info(f"[SUCESSO] Solicitação ID {sol_id} atualizada na API.")
        elif solicitacao_atual:
             sol_id = solicitacao_atual.get("id")
             log.warning(f"FASE 4: Tentando marcar solicitação ID {sol_id} como erro na API devido à falha anterior...")
             payload_api = {"status_robo": resultado_processamento.get("status_robo_final") if resultado_processamento else "Erro: Falha na Inicialização"}
             if not update_solicitacao_na_api(sol_id, payload_api): log.error(f"[ERRO] Falha ao atualizar solicitação ID {sol_id} como erro na API.")

        # FASE 5: Encerramento
        log.info("FASE 5: Encerrando a sessão do navegador...")
        if page and not page.is_closed():
            try: page.close()
            except Exception as e_close_page: log.warning(f"Erro ao fechar página: {e_close_page}")
        if context:
            try:
                for p in context.pages:
                     if not p.is_closed():
                          try: p.close()
                          except Exception: pass
            except Exception as e_close_context_pages: log.warning(f"Erro ao fechar páginas restantes do contexto: {e_close_context_pages}")
        if browser and browser.is_connected():
            try:
                browser.close()
                log.info("Browser do Playwright fechado.")
            except Exception as e: log.warning(f"Erro ao fechar o browser: {e}")
        if browser_process_ref and 'process' in browser_process_ref:
            proc = browser_process_ref.get('process')
            if proc and proc.poll() is None:
                log.info(f"Tentando finalizar processo do Chrome (PID: {proc.pid})...")
                try:
                    if sys.platform == "win32": subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, check=False, capture_output=True)
                    else: proc.terminate(); time.sleep(1); proc.kill()
                    log.info("Processo do Chrome finalizado.")
                except Exception as e_kill: log.warning(f"Não foi possível finalizar o processo do Chrome: {e_kill}")

        log.info("=" * 60); log.info("ROBO ONECOST FINALIZADO"); log.info("=" * 60)

if __name__ == "__main__":
    main()

