import logging
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
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
        API_BASE_URL, SESSION_TIMEOUT_SECONDS
    )
    from core.browser_manager import realizar_login_automatico
    from core.custos_manager import processar_solicitacao_especifica
    from utils.api_client import (
        get_todas_solicitacoes_pendentes, # <-- MUDANÇA: Busca todas
        update_solicitacao_na_api,
        robot_login
    )
    from core.session_manager import SessionExpiredError, refresh_session_if_needed
except ModuleNotFoundError as e:
    print("="*80); print(f"ERRO DE IMPORTAÇÃO (ModuleNotFoundError): {e}"); print(f"sys.path: {sys.path}"); print("="*80); sys.exit(1)
except ImportError as e:
    print("="*80); print(f"ERRO DE IMPORTAÇÃO ESPECÍFICO: {e}"); print("="*80); sys.exit(1)


# --- Configuração de Log Dinâmico ---
log_filename = f"onecost_robot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
log_filepath = LOG_DIR / log_filename
LOG_DIR.mkdir(parents=True, exist_ok=True)
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

log.info("Configuracao de logging concluida com sucesso.")

# --- Função Principal ---
def main():
    log.info("### Entrou na funcao main() ###")
    log.info("=" * 60)
    log.info(f"INICIANDO ROBO ONECOST | LOG: {log_filename}")
    log.info("=" * 60)

    general_exit_code = 0
    processed_count = 0
    solicitacoes_para_processar = [] # Lista de solicitações
    
    # Variáveis do Navegador
    browser = None
    context = None
    page = None
    browser_process_ref = None
    session_start_time = 0.0

    try:
        # FASE -1: Autenticar Robô na API
        log.info("FASE -1: Autenticando robô na API...")
        if not robot_login(ROBOT_USERNAME, ROBOT_PASSWORD):
            log.critical("Falha ao autenticar robô na API. Encerrando.")
            sys.exit(1)

        # FASE -0.5: Resetar Erros (Comentado)
        log.info("FASE -0.5: Verificando reset de erros (desativado temporariamente)...")
        log.warning("Reset de erros desativado. Usuário 'robot' precisa de permissão de admin para esta função.")
        
        # FASE 0: Buscar TODAS as Solicitações Pendentes
        log.info("FASE 0: Buscando TODAS as solicitações pendentes na API...")
        solicitacoes_para_processar = get_todas_solicitacoes_pendentes()

        if not solicitacoes_para_processar:
            log.info("Nenhuma solicitação pendente para processar. Encerrando ciclo.")
            sys.exit(0) # Sai com sucesso

        log.info(f"Encontradas {len(solicitacoes_para_processar)} solicitações pendentes para processar.")

        # Inicia o Playwright UMA VEZ
        with sync_playwright() as playwright:
            # FASE 1: Login no Portal UMA VEZ
            log.info("FASE 1: Realizando login inicial no portal via CDP/Extensão...")
            browser, context, browser_process_ref, page = realizar_login_automatico(playwright)
            session_start_time = time.time()
            log.info("[SUCESSO] Login inicial realizado.")

            # FASE 2: Navegar para a Página de Custas UMA VEZ
            log.info(f"FASE 2: Navegando para a página inicial de Custas: {URL_PORTAL_CUSTAS}")
            page.goto(URL_PORTAL_CUSTAS)
            log.info("Aguardando carregamento inicial da página de custos...")
            page.wait_for_selector("input#npj, button:has-text('Limpar')", timeout=60000)
            page.wait_for_load_state("domcontentloaded", timeout=60000)
            log.info("[SUCESSO] Página de Custas carregada!")

            # MUDANÇA: Loop FOR em vez de WHILE TRUE
            for solicitacao_atual in solicitacoes_para_processar:
                log.info("-" * 40)
                solicitacao_id = solicitacao_atual.get("id", "ID Desconhecido")
                
                # Verifica a sessão ANTES de processar
                try:
                    page, browser, context, browser_process_ref, session_start_time = refresh_session_if_needed(
                        playwright, page, browser, context, browser_process_ref, session_start_time, SESSION_TIMEOUT_SECONDS
                    )
                except SessionExpiredError as e_sess:
                     log.critical(f"Erro CRÍTICO ao tentar renovar a sessão no meio do loop: {e_sess}", exc_info=True)
                     general_exit_code = 1
                     break # Sai do loop FOR
                except Exception as e_refresh:
                    log.critical(f"Erro inesperado durante a renovação da sessão: {e_refresh}", exc_info=True)
                    general_exit_code = 1
                    break # Sai do loop FOR

                log.info(f"Processando Solicitação ID {solicitacao_id} (NPJ: {solicitacao_atual.get('npj', 'N/A')})...")
                try:
                    solicitacao_atual['valor'] = Decimal(str(solicitacao_atual.get('valor', '0.0')))
                except InvalidOperation:
                    log.error(f"Valor inválido na solicitação ID {solicitacao_id}. Usando 0.0.")
                    solicitacao_atual['valor'] = Decimal("0.0")

                # --- Bloco de Processamento de Uma Solicitação ---
                resultado_processamento = None
                try:
                    # Garante que a página esteja visível
                    page.bring_to_front()
                    if "custos.app.html" not in page.url:
                        log.warning(f"URL atual ({page.url}) não é a esperada. Navegando novamente para Custas...")
                        page.goto(URL_PORTAL_CUSTAS)
                        page.wait_for_selector("input#npj, button:has-text('Limpar')", timeout=45000)
                        page.wait_for_load_state("domcontentloaded", timeout=60000)
                        log.info("Página de Custas recarregada.")

                    # FASE 3: Processar a Custa Específica
                    log.info(f"FASE 3 (ID {solicitacao_id}): Iniciando processamento da custa...")
                    resultado_processamento = processar_solicitacao_especifica(page, solicitacao_atual)
                    log.info(f"Processamento da solicitação ID {solicitacao_id} concluído com status: {resultado_processamento.get('status_robo_final', 'Desconhecido')}")
                    
                    if "erro" in resultado_processamento.get("status_robo_final", "").lower():
                        general_exit_code = 1 # Se qualquer item falhar, o ciclo geral é de erro
                    else:
                        processed_count += 1

                except (PlaywrightError, SessionExpiredError) as e:
                    log.critical(f"Erro (Playwright/Sessão) ao processar ID {solicitacao_id}: {e}", exc_info=False)
                    log.debug("Stack trace completo do erro:", exc_info=True)
                    general_exit_code = 1
                    if not resultado_processamento:
                         resultado_processamento = {"solicitacao_id": solicitacao_id, "status_robo_final": f"Erro Processamento: {type(e).__name__}"}
                    session_start_time = 0 # Força renovação na próxima iteração
                except Exception as e:
                    log.critical(f"Falha crítica inesperada ao processar ID {solicitacao_id}.", exc_info=True)
                    general_exit_code = 1
                    if not resultado_processamento:
                         resultado_processamento = {"solicitacao_id": solicitacao_id, "status_robo_final": f"Erro Critico Inesperado: {type(e).__name__}"}
                finally:
                    log.info(f"### Bloco finally para solicitação ID {solicitacao_id} ###")
                    # FASE 4: Atualizar Status na API
                    if resultado_processamento and "solicitacao_id" in resultado_processamento:
                        sol_id = resultado_processamento["solicitacao_id"]
                        log.info(f"FASE 4 (ID {sol_id}): Tentando atualizar status na API...")
                        payload_api = {
                            "status_robo": resultado_processamento.get("status_robo_final", "Erro: Status Desconhecido"),
                            "status_portal": resultado_processamento.get("status_portal_encontrado"),
                            "comprovantes_path": [str(p) for p in resultado_processamento.get("lista_arquivos_baixados", []) if p],
                            "numero_processo": resultado_processamento.get("numero_processo_completo")
                        }
                        if resultado_processamento.get("usuario_confirmacao_id"):
                            payload_api["usuario_confirmacao_id"] = resultado_processamento["usuario_confirmacao_id"]

                        log.debug(f"Payload para API (ID {sol_id}): {json.dumps(payload_api, default=str)}")
                        if not update_solicitacao_na_api(sol_id, payload_api):
                            log.error(f"[ERRO] Falha ao atualizar solicitação ID {sol_id} na API.")
                            general_exit_code = 1
                        else:
                            log.info(f"[SUCESSO] Solicitação ID {sol_id} atualizada na API.")
                    else:
                        log.error(f"Não houve resultado do processamento para ID {solicitacao_id}. Não foi possível atualizar a API.")
                        general_exit_code = 1
                
                log.info(f"Fim do processamento da solicitação ID {solicitacao_id}.")
                time.sleep(1) # Pausa entre solicitações
            
            # Fim do loop FOR
            log.info(f"Fim do loop de processamento. {processed_count}/{len(solicitacoes_para_processar)} processadas sem erro.")

    # Captura erros que podem ocorrer fora do loop (login inicial, busca inicial)
    except (PlaywrightError, ConnectionError, FileNotFoundError, SessionExpiredError) as e:
        log.critical(f"Erro CRÍTICO durante inicialização/login: {e}", exc_info=True)
        general_exit_code = 1
        # Se falhou, não há solicitações para marcar como erro
    except Exception as e:
        log.critical("Falha crítica inesperada GERAL.", exc_info=True)
        general_exit_code = 1
    finally:
        log.info("### Bloco finally GERAL ###")
        # FASE 5: Encerramento FINAL do Navegador
        log.info("FASE 5: Encerrando a sessão final do navegador e processos...")
        
        if 'page' in locals() and page and not page.is_closed():
            try: page.close()
            except Exception as e_close_page: log.warning(f"Erro ao fechar página final: {e_close_page}")
        if 'context' in locals() and context:
            try: context.close()
            except Exception as e_close_context: log.warning(f"Erro ao fechar contexto final: {e_close_context}")
        if 'browser' in locals() and browser and browser.is_connected():
            try:
                browser.close()
                log.info("Browser final do Playwright fechado.")
            except Exception as e_br: log.warning(f"Erro ao fechar o browser final: {e_br}")

        # Garante que o processo do Chrome seja finalizado
        proc = browser_process_ref.get('process') if browser_process_ref else None
        if proc and proc.poll() is None:
            log.info(f"Tentando finalizar processo final do Chrome (PID: {proc.pid})...")
            try:
                if sys.platform == "win32":
                    subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    proc.terminate(); time.sleep(0.5)
                    if proc.poll() is None: proc.kill()
                log.info("Processo final do Chrome finalizado.")
            except Exception as e_kill:
                log.warning(f"Não foi possível finalizar o processo final do Chrome (PID: {proc.pid}): {e_kill}")

        log.info("=" * 60)
        total_encontradas = len(solicitacoes_para_processar)
        if general_exit_code == 0:
            if total_encontradas > 0:
                 log.info(f"ROBO ONECOST FINALIZADO COM SUCESSO ({total_encontradas} solicitações encontradas, {processed_count} processadas sem erro neste ciclo)")
            else:
                 log.info("ROBO ONECOST FINALIZADO - Nenhuma solicitação pendente encontrada neste ciclo.")
        else:
            log.error(f"ROBO ONECOST FINALIZADO COM ERRO (processou {processed_count}/{total_encontradas} solicitações, mas houve falha)")
        log.info("=" * 60)
        sys.exit(general_exit_code)

# --- Ponto de Entrada ---
if __name__ == "__main__":
    print("[main.py] Bloco __main__ iniciado. Chamando a funcao main()...")
    main()

