import logging
# import logging_loki  # <-- ADIÇÃO LOKI (DESATIVADO)
import sys
import time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PlaywrightError
import json
from decimal import Decimal, InvalidOperation
import subprocess
# --- ADIÇÃO PROMETHEUS (DESATIVADO) ---
# from prometheus_client import CollectorRegistry, Gauge, Summary, push_to_gateway

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
        SESSION_TIMEOUT_SECONDS, SESSION_RENEW_BEFORE_SECONDS
    )
    # Importações dos módulos core
    from core.browser_manager import realizar_login_automatico
    from core.custos_manager import processar_solicitacao_especifica
    from core.session_manager import SessionExpiredError, refresh_session_if_needed
    # Importações do cliente da API
    from utils.api_client import (
        get_todas_solicitacoes_pendentes,  # Busca todas as pendentes
        update_solicitacao_na_api,
        robot_login,
        resetar_solicitacoes_com_erro  # Função de reset agora importada
    )
except ModuleNotFoundError as e:
    print("=" * 80); print(f"ERRO DE IMPORTAÇÃO (ModuleNotFoundError): {e}"); print(f"sys.path: {sys.path}"); print("=" * 80); sys.exit(1)
except ImportError as e:
    print("=" * 80); print(f"ERRO DE IMPORTAÇÃO ESPECÍFICO: {e}"); print("=" * 80); sys.exit(1)


# --- Configuração de Log Dinâmico ---
# Garante que o diretório de logs exista
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_filename = f"onecost_robot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
log_filepath = LOG_DIR / log_filename

# Formato do Log
log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s')

# Configuração do Logger Raiz
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)  # Define o nível de log padrão

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

# --- ADIÇÃO DO HANDLER DO LOKI (DESATIVADO) ---
# try:
#     # Tags que serão enviadas ao Loki com cada log
#     loki_tags = {
#         "application": "onecost-robot",
#         "ambiente": "producao", # Mude para "teste" se quiser
#         "host_ip": "192.168.0.52" # IP da máquina que roda o robô
#     }
#     loki_handler = logging_loki.LokiHandler(
#         url="http://192.168.0.30:3100/loki/api/v1/push",  # IP do servidor de monitoramento
#         tags=loki_tags,
#         version="1"
#     )
#     root_logger.addHandler(loki_handler)
#     root_logger.info("Handler do Loki configurado com sucesso.")
# except Exception as e_loki:
#     root_logger.error(f"Falha ao configurar handler do Loki: {e_loki}")
# --- FIM DO BLOCO LOKI ---

# Logger específico para este módulo
log = logging.getLogger(__name__)

log.info("Configuracao de logging concluida com sucesso.")

# --- Função Principal ---
def main():
    log.info("### Entrou na funcao main() ###")
    log.info("=" * 60)
    log.info(f"INICIANDO ROBO ONECOST | LOG: {log_filename}")
    log.info("=" * 60)
    run_started_at = time.time()

    # --- DEFINIÇÃO DAS MÉTRICAS (PROMETHEUS - DESATIVADO) ---
    # registry = CollectorRegistry()
    
    # # (Gauge) Um valor que pode subir ou descer (1 para sucesso, 0 para falha)
    # g_robot_run_success = Gauge(
    #     "robot_run_success", 
    #     "Status da execução do robô (1 = sucesso, 0 = falha)", 
    #     registry=registry
    # )
    # # (Gauge) Um contador de itens
    # g_solicitacoes_processadas = Gauge(
    #     "robot_solicitacoes_processadas", 
    #     "Total de solicitações processadas com sucesso", 
    #     registry=registry
    # )
    # # (Summary) Mede o tempo de duração
    # s_robot_run_duration = Summary(
    #     "robot_run_duration_seconds", 
    #     "Tempo de duração da execução do robô", 
    #     registry=registry
    # )
    
    # start_time = time.time()  # Marca o tempo de início
    # g_robot_run_success.set(0)  # Assume falha até que termine com sucesso
    # g_solicitacoes_processadas.set(0)  # Zera o contador
    # --- FIM DO BLOCO (MÉTRICAS) ---

    # Código de saída geral do script (0 = sucesso, 1 = erro)
    general_exit_code = 0
    processed_count = 0  # Contador de solicitações processadas com sucesso
    solicitacoes_para_processar = []  # Lista para armazenar as solicitações pendentes

    # Variáveis para gerenciar o navegador Playwright
    browser = None
    context = None
    page = None
    browser_process_ref = None  # Referência ao processo do Chrome iniciado
    session_start_time = 0.0  # Timestamp do início da sessão atual do portal

    try:
        # FASE -1: Autenticar Robô na API Backend
        log.info("FASE -1: Autenticando robô na API...")
        if not robot_login(ROBOT_USERNAME, ROBOT_PASSWORD):
            # Se o login na API falhar, não adianta continuar
            log.critical("Falha ao autenticar robô na API. Encerrando.")
            general_exit_code = 1
            return general_exit_code

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
            return general_exit_code

        log.info(f"Encontradas {len(solicitacoes_para_processar)} solicitações pendentes para processar.")

        # Inicia o Playwright (gerenciador de contexto garante fechamento)
        with sync_playwright() as playwright:
            # FASE 1: Login no Portal (Apenas uma vez no início)
            log.info("FASE 1: Realizando login inicial no portal via CDP/Extensão...")
            # A função `realizar_login_automatico` retorna os objetos do browser, contexto, referência do processo e a página logada
            browser, context, browser_process_ref, page = realizar_login_automatico(playwright)
            session_start_time = time.time()  # Marca o início da sessão do portal
            log.info("[SUCESSO] Login inicial realizado.")

            # FASE 2: Navegar para a Página de Custas (Apenas uma vez no início)
            log.info(f"FASE 2: Navegando para a página inicial de Custas: {URL_PORTAL_CUSTAS}")
            page.goto(URL_PORTAL_CUSTAS)
            log.info("Aguardando carregamento inicial da página de custos...")
            # Espera por elementos chave da página para garantir que carregou
            #page.wait_for_selector("input#npj, button:has-text('Limpar')", timeout=60000)

            try:
                log.info("Aguardando formulário NPJ carregar...")
                page.wait_for_selector("input#npj, button:has-text('Limpar')", timeout=60000)
            except Exception as e:
                log.error("Timeout ao carregar a página. Tirando foto para debug...")
                # Salva um print e o HTML diretamente na pasta mapeada do seu Mac
                page.screenshot(path="/app/comprovantes/debug_tela_banco.png")
                with open("/app/comprovantes/debug_banco.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                raise e
        
            page.wait_for_load_state("domcontentloaded", timeout=60000) # Espera o DOM estar pronto
            log.info("[SUCESSO] Página de Custas carregada!")

            # Loop principal: Processa cada solicitação encontrada
            for solicitacao_atual in solicitacoes_para_processar:
                log.info("-" * 40)
                solicitacao_id = solicitacao_atual.get("id", "ID Desconhecido")

                # --- Verificação/Renovação da Sessão ---
                try:
                    # Verifica se a sessão do portal expirou e tenta renovar se necessário
                    page, browser, context, browser_process_ref, session_start_time = refresh_session_if_needed(
                        playwright,
                        page,
                        browser,
                        context,
                        browser_process_ref,
                        session_start_time,
                        SESSION_TIMEOUT_SECONDS,
                        SESSION_RENEW_BEFORE_SECONDS,
                    )
                except SessionExpiredError as e_sess:
                     # Se a renovação falhar, é um erro crítico para o ciclo atual
                     log.critical(f"Erro CRÍTICO ao tentar renovar a sessão no meio do loop: {e_sess}", exc_info=True)
                     general_exit_code = 1  # Marca o ciclo geral como falha
                     break  # Interrompe o loop FOR, não processa mais solicitações
                except Exception as e_refresh:
                    # Outro erro inesperado durante a renovação
                    log.critical(f"Erro inesperado durante a renovação da sessão: {e_refresh}", exc_info=True)
                    general_exit_code = 1
                    break  # Interrompe o loop FOR

                # --- Processamento da Solicitação Individual ---
                log.info(f"Processando Solicitação ID {solicitacao_id} (NPJ: {solicitacao_atual.get('npj', 'N/A')})...")

                # Converte o valor para Decimal (necessário para comparações precisas)
                try:
                    solicitacao_atual['valor'] = Decimal(str(solicitacao_atual.get('valor', '0.0')))
                except InvalidOperation:
                    log.error(f"Valor inválido na solicitação ID {solicitacao_id}. Usando 0.0.")
                    solicitacao_atual['valor'] = Decimal("0.0")

                # Bloco try/except para o processamento de UMA solicitação
                resultado_processamento = None  # Reseta o resultado para esta iteração
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
                    resultado_processamento = processar_solicitacao_especifica(page, solicitacao_atual)
                    
                    # --- CORREÇÃO 1 (main.py) ---
                    # Usa 'status_robo' ao invés de 'status_robo_final'
                    status_final = resultado_processamento.get('status_robo', 'Desconhecido') 
                    # ----------------------------

                    log.info(f"Processamento da solicitação ID {solicitacao_id} concluído com status: {status_final}")

                    # Verifica se o processamento individual resultou em erro
                    if "erro" in status_final.lower():
                        general_exit_code = 1  # Marca o ciclo geral como erro
                    else:
                        processed_count += 1  # Incrementa contador de sucesso

                except SessionExpiredError as e:
                    log.warning(f"Sessão do portal expirada ao processar ID {solicitacao_id}: {e}")
                    log.debug("Stack trace completo da expiração de sessão:", exc_info=True)
                    if not resultado_processamento:
                         resultado_processamento = {
                             "solicitacao_id": solicitacao_id,
                             "status_robo": "Pendente",
                             "monitoramento_ativo": True,
                             "motivo_encerramento": "Sessão do portal expirada; nova tentativa agendada",
                         }
                    session_start_time = 0  # Força a renovação da sessão na próxima iteração
                except PlaywrightError as e:
                    # Erros específicos do Playwright durante o processamento
                    log.critical(f"Erro Playwright ao processar ID {solicitacao_id}: {e}", exc_info=False)
                    log.debug("Stack trace completo do erro:", exc_info=True)  # Log detalhado no modo debug
                    general_exit_code = 1
                    if not resultado_processamento:
                         resultado_processamento = {"solicitacao_id": solicitacao_id, "status_robo": f"Erro Processamento: {type(e).__name__}"}
                    session_start_time = 0  # Força a verificação/renovação da sessão na próxima iteração
                except Exception as e:
                    # Captura qualquer outro erro inesperado durante o processamento
                    log.critical(f"Falha crítica inesperada ao processar ID {solicitacao_id}.", exc_info=True)
                    general_exit_code = 1
                    if not resultado_processamento:
                         resultado_processamento = {"solicitacao_id": solicitacao_id, "status_robo": f"Erro Critico Inesperado: {type(e).__name__}"}
                finally:
                    # --- FASE 4: Atualiza o Status na API (SEMPRE tenta, mesmo em erro) ---
                    log.info(f"### Bloco finally para solicitação ID {solicitacao_id} ###")
                    if resultado_processamento and "solicitacao_id" in resultado_processamento:
                        sol_id_final = resultado_processamento["solicitacao_id"]
                        log.info(f"FASE 4 (ID {sol_id_final}): Tentando atualizar status na API...")
                        
                        # --- CORREÇÃO 2 (main.py) ---
                        # Usa 'status_robo' ao invés de 'status_robo_final'
                        payload_api = {
                            "status_robo": resultado_processamento.get("status_robo", "Erro: Status Desconhecido"), 
                            # ----------------------------
                            "status_portal": resultado_processamento.get("status_portal"),
                            "especificacao": resultado_processamento.get("especificacao"),
                            "comprovantes_path": [str(p) for p in resultado_processamento.get("comprovantes_path", []) if p],  # Garante strings e remove vazios (Nome da chave corrigido no custos_manager)
                            "numero_processo": resultado_processamento.get("numero_processo"),
                            "usuario_confirmacao_id": resultado_processamento.get("usuario_confirmacao_id"),  # Inclui ID se o robô confirmou
                            "monitoramento_ativo": resultado_processamento.get("monitoramento_ativo"),
                            "motivo_encerramento": resultado_processamento.get("motivo_encerramento"),
                            "proxima_verificacao_em": resultado_processamento.get("proxima_verificacao_em"),
                            "alerta_enviado_em": resultado_processamento.get("alerta_enviado_em"),
                        }

                        log.debug(f"Payload para API (ID {sol_id_final}): {json.dumps(payload_api, default=str)}")
                        # Chama a função do api_client para atualizar
                        if not update_solicitacao_na_api(sol_id_final, payload_api):
                            log.error(f"[ERRO] Falha ao atualizar solicitação ID {sol_id_final} na API.")
                            general_exit_code = 1  # Marca erro se a atualização falhar
                        else:
                            log.info(f"[SUCESSO] Solicitação ID {sol_id_final} atualizada na API.")
                    else:
                        # Caso não haja resultado (erro muito inicial no processamento)
                        log.error(f"Não houve resultado do processamento para ID {solicitacao_id}. Não foi possível atualizar a API.")
                        general_exit_code = 1

                log.info(f"Fim do processamento da solicitação ID {solicitacao_id}.")
                time.sleep(1)  # Pequena pausa entre o processamento de cada solicitação

            # Fim do loop FOR que itera sobre as solicitações
            log.info(f"Fim do loop de processamento. {processed_count}/{len(solicitacoes_para_processar)} processadas sem erro neste ciclo.")

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

        # --- CORREÇÃO 3 (main.py) ---
        # O 'with sync_playwright()' já cuida de fechar page, context e browser.
        # Remover chamadas manuais para evitar os avisos "Event loop is closed!".
        
        # if 'page' in locals() and page and not page.is_closed():
        #     try: page.close()
        #     except Exception as e_close_page: log.warning(f"Erro ao fechar página final: {e_close_page}")
        # if 'context' in locals() and context:
        #     try: context.close()
        #     except Exception as e_close_context: log.warning(f"Erro ao fechar contexto final: {e_close_context}")
        # if 'browser' in locals() and browser and browser.is_connected():
        #     try:
        #         browser.close()
        #         log.info("Browser final do Playwright fechado.")
        #     except Exception as e_br: log.warning(f"Erro ao fechar o browser final: {e_br}")
        # ----------------------------

        # Garante que o processo do Chrome iniciado seja finalizado
        proc = browser_process_ref.get('process') if browser_process_ref else None
        if proc and proc.poll() is None:  # Verifica se o processo ainda está rodando
            log.info(f"Tentando finalizar processo final do Chrome (PID: {proc.pid})...")
            try:
                # Usa TASKKILL no Windows, terminate/kill em outros sistemas
                if sys.platform == "win32":
                    subprocess.run(f"TASKKILL /F /PID {proc.pid} /T", shell=True, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    proc.terminate(); time.sleep(0.5)  # Tenta terminar gentilmente primeiro
                    if proc.poll() is None: proc.kill()  # Força se ainda estiver rodando
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
            # g_robot_run_success.set(1)  # <-- MARCA SUCESSO (DESATIVADO)
        else:
            log.error(f"ROBO ONECOST FINALIZADO COM ERRO (processou {processed_count}/{total_encontradas} solicitações, mas houve falha)")
            # g_robot_run_success.set(0)  # <-- MARCA FALHA (DESATIVADO)
        log.info("=" * 60)
        
        duration = time.time() - run_started_at
        log.info(f"Duracao total deste ciclo: {duration:.2f}s")

    return general_exit_code

# --- Ponto de Entrada Padrão do Script ---
if __name__ == "__main__":
    print("[main.py] Bloco __main__ iniciado. Chamando a funcao main()...")
    sys.exit(main())
