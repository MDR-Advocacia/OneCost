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
    # Fallback se __file__ não estiver definido (menos comum)
    sys.path.insert(0, str(Path.cwd()))
# --- Fim do bloco ---

try:
    # Importações de configuração
    from config import (
        URL_PORTAL_CUSTAS, LOG_DIR, ROBOT_USERNAME, ROBOT_PASSWORD,
        API_BASE_URL, SESSION_TIMEOUT_SECONDS
    )
    # Importações dos módulos core
    from core.browser_manager import realizar_login_automatico
    from core.custos_manager import processar_solicitacao_especifica
    from core.session_manager import SessionExpiredError, refresh_session_if_needed
    # Importações do cliente da API
    from utils.api_client import (
        get_todas_solicitacoes_pendentes, # Busca todas as pendentes
        update_solicitacao_na_api,
        robot_login,
        resetar_solicitacoes_com_erro # Função de reset agora importada
    )
except ModuleNotFoundError as e:
    print("="*80); print(f"ERRO DE IMPORTAÇÃO (ModuleNotFoundError): {e}"); print(f"sys.path: {sys.path}"); print("="*80); sys.exit(1)
except ImportError as e:
    print("="*80); print(f"ERRO DE IMPORTAÇÃO ESPECÍFICO: {e}"); print("="*80); sys.exit(1)


# --- Configuração de Log Dinâmico ---
# Garante que o diretório de logs exista
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_filename = f"onecost_robot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
log_filepath = LOG_DIR / log_filename

# Formato do Log
log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')

# Configuração do Logger Raiz
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO) # Define o nível de log padrão

# Remove handlers existentes para evitar duplicação (importante em reexecuções)
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Handler para arquivo
file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
file_handler.setFormatter(log_formatter)
root_logger.addHandler(file_handler)

# Handler para console (stdout)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
root_logger.addHandler(stream_handler)

# Logger específico para este módulo
log = logging.getLogger(__name__)

log.info("Configuracao de logging concluida com sucesso.")

# --- Função Principal ---
def main():
    log.info("### Entrou na funcao main() ###")
    log.info("=" * 60)
    log.info(f"INICIANDO ROBO ONECOST | LOG: {log_filename}")
    log.info("=" * 60)

    # Código de saída geral do script (0 = sucesso, 1 = erro)
    general_exit_code = 0
    processed_count = 0 # Contador de solicitações processadas sem erro neste ciclo
    processed_with_error_count = 0 # Contador de solicitações processadas COM erro neste ciclo
    solicitacoes_para_processar = [] # Lista para armazenar as solicitações pendentes

    # Variáveis para gerenciar o navegador Playwright
    browser = None
    context = None
    page = None
    browser_process_ref = None # Referência ao processo do Chrome iniciado
    session_start_time = 0.0 # Timestamp do início da sessão atual do portal

    try:
        # FASE -1: Autenticar Robô na API Backend
        log.info("FASE -1: Autenticando robô na API...")
        if not robot_login(ROBOT_USERNAME, ROBOT_PASSWORD):
            # Se o login na API falhar, não adianta continuar
            log.critical("Falha ao autenticar robô na API. Encerrando.")
            sys.exit(1) # Sai com código de erro

        # FASE -0.5: Resetar Solicitações com Erro (Agora Ativo)
        log.info("FASE -0.5: Tentando resetar solicitações com status de erro...")
        if resetar_solicitacoes_com_erro():
             log.info("[SUCESSO] Solicitações com erro resetadas para 'Pendente' (se houveram).")
        else:
             # Apenas avisa, mas continua a execução. O erro específico já foi logado pelo api_client.
             log.warning("Falha ao resetar erros ou nenhuma solicitação com erro encontrada. Verifique os logs da API se a falha persistir.")

        # FASE 0: Buscar TODAS as Solicitações Pendentes na API
        log.info("FASE 0: Buscando TODAS as solicitações pendentes na API...")
        solicitacoes_para_processar = get_todas_solicitacoes_pendentes()

        # Se não houver solicitações, encerra o ciclo com sucesso
        if not solicitacoes_para_processar:
            log.info("Nenhuma solicitação pendente para processar. Encerrando ciclo.")
            sys.exit(0) # Sai com sucesso

        log.info(f"Encontradas {len(solicitacoes_para_processar)} solicitações pendentes para processar.")

        # Inicia o Playwright (gerenciador de contexto garante fechamento)
        with sync_playwright() as playwright:
            # FASE 1: Login no Portal (Apenas uma vez no início)
            log.info("FASE 1: Realizando login inicial no portal via CDP/Extensão...")
            # A função `realizar_login_automatico` retorna os objetos do browser, contexto, referência do processo e a página logada
            browser, context, browser_process_ref, page = realizar_login_automatico(playwright)
            session_start_time = time.time() # Marca o início da sessão do portal
            log.info("[SUCESSO] Login inicial realizado.")

            # FASE 2: Navegar para a Página de Custas (Apenas uma vez no início)
            log.info(f"FASE 2: Navegando para a página inicial de Custas: {URL_PORTAL_CUSTAS}")
            page.goto(URL_PORTAL_CUSTAS)
            log.info("Aguardando carregamento inicial da página de custos...")
            # Espera por elementos chave da página para garantir que carregou
            page.wait_for_selector("input#npj, button:has-text('Limpar')", timeout=60000)
            page.wait_for_load_state("domcontentloaded", timeout=60000) # Espera o DOM estar pronto
            log.info("[SUCESSO] Página de Custas carregada!")

            # Loop principal: Processa cada solicitação encontrada
            for solicitacao_atual in solicitacoes_para_processar:
                log.info("-" * 40)
                solicitacao_id = solicitacao_atual.get("id", "ID Desconhecido")
                solicitacao_npj = solicitacao_atual.get('npj', 'N/A') # Pega o NPJ para o log

                # --- Verificação/Renovação da Sessão ---
                try:
                    # Verifica se a sessão do portal expirou e tenta renovar se necessário
                    page, browser, context, browser_process_ref, session_start_time = refresh_session_if_needed(
                        playwright, page, browser, context, browser_process_ref, session_start_time, SESSION_TIMEOUT_SECONDS
                    )
                except SessionExpiredError as e_sess:
                     # Se a renovação falhar, é um erro crítico para o ciclo atual
                     log.critical(f"Erro CRÍTICO ao tentar renovar a sessão no meio do loop: {e_sess}", exc_info=True)
                     general_exit_code = 1 # Marca o ciclo geral como falha
                     break # Interrompe o loop FOR, não processa mais solicitações
                except Exception as e_refresh:
                    # Outro erro inesperado durante a renovação
                    log.critical(f"Erro inesperado durante a renovação da sessão: {e_refresh}", exc_info=True)
                    general_exit_code = 1
                    break # Interrompe o loop FOR

                # --- Processamento da Solicitação Individual ---
                log.info(f"Processando Solicitação ID {solicitacao_id} (NPJ: {solicitacao_npj})...")

                # Converte o valor para Decimal (necessário para comparações precisas)
                # Mantém uma cópia do valor original para o payload da API
                valor_original_api = solicitacao_atual.get('valor')
                try:
                    solicitacao_atual['valor_decimal_comparacao'] = Decimal(str(valor_original_api or '0.0'))
                except InvalidOperation:
                    log.error(f"Valor inválido na solicitação ID {solicitacao_id}. Usando 0.0 para comparação.")
                    solicitacao_atual['valor_decimal_comparacao'] = Decimal("0.0")

                # Bloco try/except para o processamento de UMA solicitação
                resultado_processamento = None # Reseta o resultado para esta iteração
                status_final_para_api = "Erro: Falha no processamento interno" # Default em caso de erro antes de chamar custos_manager
                try:
                    # Garante que a página do portal esteja em primeiro plano
                    page.bring_to_front()

                    # Verifica se a URL ainda é a da página de custos (pode ter redirecionado)
                    if "custos.app.html" not in page.url:
                        log.warning(f"URL atual ({page.url}) não é a esperada. Navegando novamente para Custas...")
                        page.goto(URL_PORTAL_CUSTAS)
                        # Re-espera pelos elementos chave
                        page.wait_for_selector("input#npj, button:has-text('Limpar')", timeout=45000)
                        page.wait_for_load_state("domcontentloaded", timeout=60000)
                        log.info("Página de Custas recarregada.")

                    # FASE 3: Chama a função que processa a custa específica
                    log.info(f"FASE 3 (ID {solicitacao_id}): Iniciando processamento da custa...")
                    # Passa o dicionário original, mas o valor foi convertido para Decimal internamente se necessário
                    resultado_processamento = processar_solicitacao_especifica(page, solicitacao_atual)

                    # Pega o status retornado pelo processamento
                    status_final_para_api = resultado_processamento.get('status_robo', 'Erro: Status não retornado')
                    log.info(f"Processamento da solicitação ID {solicitacao_id} concluído. Status retornado: '{status_final_para_api}'")

                    # Verifica se o processamento individual resultou em erro
                    if "erro" in status_final_para_api.lower():
                        processed_with_error_count += 1 # Conta como processada COM erro
                        # Não define general_exit_code = 1 aqui, pois o robô pode continuar
                    else:
                        processed_count += 1 # Incrementa contador de sucesso (sem erro)

                except (PlaywrightError, SessionExpiredError) as e:
                    # Erros específicos do Playwright ou de sessão durante o processamento
                    log.critical(f"Erro (Playwright/Sessão) ao processar ID {solicitacao_id}: {e}", exc_info=False)
                    log.debug("Stack trace completo do erro:", exc_info=True) # Log detalhado no modo debug
                    processed_with_error_count += 1
                    status_final_para_api = f"Erro Processamento: {type(e).__name__}" # Define status de erro
                    session_start_time = 0 # Força a verificação/renovação da sessão na próxima iteração
                except Exception as e:
                    # Captura qualquer outro erro inesperado durante o processamento
                    log.critical(f"Falha crítica inesperada ao processar ID {solicitacao_id}.", exc_info=True)
                    processed_with_error_count += 1
                    status_final_para_api = f"Erro Critico Inesperado: {type(e).__name__}" # Define status de erro
                finally:
                    # --- FASE 4: Atualiza o Status na API (SEMPRE tenta, mesmo em erro) ---
                    log.info(f"### Bloco finally para solicitação ID {solicitacao_id} ###")

                    # <<< CORREÇÃO AQUI >>>
                    # Monta o payload COM BASE NO resultado_processamento se ele existir,
                    # caso contrário, monta um payload de erro mínimo.
                    payload_api = {}
                    if resultado_processamento and isinstance(resultado_processamento, dict):
                        log.info(f"FASE 4 (ID {solicitacao_id}): Montando payload com resultado do processamento...")
                        payload_api = {
                            "status_robo": status_final_para_api, # Usa o status definido acima
                            "status_portal": resultado_processamento.get("status_portal"),
                            "comprovantes_path": resultado_processamento.get("comprovantes_path", []), # Pega a lista (ou vazia)
                            "numero_processo": resultado_processamento.get("numero_processo"), # Pega o CNJ
                            "especificacao": resultado_processamento.get("especificacao"), # Pega a especificação
                            "usuario_confirmacao_id": resultado_processamento.get("usuario_confirmacao_id")
                        }
                    else:
                        # Se resultado_processamento é None ou inválido (erro muito cedo)
                        log.error(f"FASE 4 (ID {solicitacao_id}): Não houve resultado válido do processamento. Enviando status de erro.")
                        payload_api = {
                            "status_robo": status_final_para_api, # Envia o status de erro definido no except
                            "status_portal": None,
                            "comprovantes_path": [],
                            "numero_processo": solicitacao_atual.get("numero_processo"), # Tenta manter o do BD se tiver
                            "especificacao": solicitacao_atual.get("especificacao"), # Tenta manter o do BD se tiver
                            "usuario_confirmacao_id": None
                        }

                    log.debug(f"Payload final para API (ID {solicitacao_id}): {json.dumps(payload_api, default=str)}")

                    # Chama a função do api_client para atualizar
                    if not update_solicitacao_na_api(solicitacao_id, payload_api):
                        log.error(f"[ERRO] Falha ao atualizar solicitação ID {solicitacao_id} na API.")
                        # Não define general_exit_code aqui para não parar o robô por falha de API
                    else:
                        log.info(f"[SUCESSO] Solicitação ID {solicitacao_id} atualizada na API.")
                    # <<< FIM DA CORREÇÃO >>>

                log.info(f"Fim do processamento da solicitação ID {solicitacao_id}.")
                time.sleep(1) # Pequena pausa entre o processamento de cada solicitação

            # Fim do loop FOR que itera sobre as solicitações
            total_processadas = processed_count + processed_with_error_count
            log.info(f"Fim do loop de processamento. {total_processadas}/{len(solicitacoes_para_processar)} solicitações tiveram tentativa de processamento ({processed_count} sem erro, {processed_with_error_count} com erro).")
            # Define o código de saída geral baseado se *alguma* solicitação teve erro no processamento
            if processed_with_error_count > 0:
                 general_exit_code = 1

    # Captura erros que podem ocorrer *antes* do loop principal (login, busca inicial)
    except (PlaywrightError, ConnectionError, FileNotFoundError, SessionExpiredError) as e:
        log.critical(f"Erro CRÍTICO durante inicialização/login do robô: {e}", exc_info=True)
        general_exit_code = 1
    except Exception as e:
        # Captura qualquer outro erro não previsto
        log.critical("Falha crítica inesperada GERAL.", exc_info=True)
        general_exit_code = 1
    finally:
        # --- FASE 5: Encerramento Final (SEMPRE executa) ---
        log.info("### Bloco finally GERAL ###")
        log.info("FASE 5: Encerrando a sessão final do navegador e processos...")

        # Tenta fechar a página, contexto e browser do Playwright de forma segura
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

        # Garante que o processo do Chrome iniciado seja finalizado
        proc = browser_process_ref.get('process') if browser_process_ref else None
        if proc and proc.poll() is None: # Verifica se o processo ainda está rodando
            log.info(f"Tentando finalizar processo final do Chrome (PID: {proc.pid})...")
            try:
                # Usa TASKKILL no Windows, terminate/kill em outros sistemas
                if sys.platform == "win32":
                    subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    proc.terminate(); time.sleep(0.5) # Tenta terminar gentilmente primeiro
                    if proc.poll() is None: proc.kill() # Força se ainda estiver rodando
                log.info("Processo final do Chrome finalizado.")
            except Exception as e_kill:
                log.warning(f"Não foi possível finalizar o processo final do Chrome (PID: {proc.pid}): {e_kill}")

        # Mensagem final indicando sucesso ou erro geral
        log.info("=" * 60)
        total_encontradas = len(solicitacoes_para_processar)
        if general_exit_code == 0:
            if total_encontradas > 0:
                 log.info(f"ROBO ONECOST FINALIZADO COM SUCESSO ({total_encontradas} solicitações encontradas, {processed_count} processadas sem erro neste ciclo)")
            else:
                 log.info("ROBO ONECOST FINALIZADO - Nenhuma solicitação pendente encontrada neste ciclo.")
        else:
             # Atualiza a mensagem de erro para refletir o novo contador
             log.error(f"ROBO ONECOST FINALIZADO COM ERRO (processou {processed_count}/{total_encontradas} sem erro, {processed_with_error_count} COM erro)")
        log.info("=" * 60)
        # Sai do script Python com o código de status apropriado
        sys.exit(general_exit_code)

# --- Ponto de Entrada Padrão do Script ---
if __name__ == "__main__":
    print("[main.py] Bloco __main__ iniciado. Chamando a funcao main()...")
    main()
