import logging
import sys
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PlaywrightError

# Bloco de segurança para garantir que o Python ache os módulos
try:
    robot_dir = Path(__file__).resolve().parent
    if str(robot_dir) not in sys.path:
        sys.path.insert(0, str(robot_dir))
except NameError:
    sys.path.insert(0, str(Path.cwd()))

try:
    from config import URL_PORTAL_CUSTAS, LOG_DIR, API_BASE_URL, API_USERNAME, API_PASSWORD
    from core.browser_manager import realizar_login_automatico
    from core.custos_manager import processar_solicitacao_especifica
    from utils.api_client import ApiClient
except ModuleNotFoundError as e:
    print(f"ERRO DE IMPORTAÇÃO: {e}")
    sys.exit(1)

# Configuração de Log Dinâmico
LOG_DIR.mkdir(exist_ok=True)
log_filename = f"onecost_robot_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
log_filepath = LOG_DIR / log_filename

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler(log_filepath, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    logging.info("=" * 60)
    logging.info(f"🤖 INICIANDO ROBO ONECOST | LOG: {log_filename} 🤖")
    logging.info("=" * 60)
    
    api_client = ApiClient(API_BASE_URL, API_USERNAME, API_PASSWORD)
    if not api_client.token:
        logging.critical("Falha na autenticação com a API. Abortando execução.")
        return

    # Busca todas as solicitações que NÃO estão com status de 'Finalizado com Sucesso'
    solicitacoes_para_processar = api_client.get_solicitacoes(status_ne="Finalizado com Sucesso")
    
    if not solicitacoes_para_processar:
        logging.info("Nenhuma solicitação a ser processada. Encerrando.")
        return

    logging.info(f"Total de {len(solicitacoes_para_processar)} solicitações a serem processadas.")

    browser = None
    try:
        with sync_playwright() as playwright:
            # --- FASE 1: LOGIN NO PORTAL DO BANCO ---
            logging.info("FASE 1: Realizando login no portal do banco...")
            browser, context, browser_process_ref, portal_page = realizar_login_automatico(playwright)
            logging.info("[SUCESSO] Login no portal realizado.")

            # --- FASE 2: NAVEGAÇÃO PARA CUSTAS ---
            logging.info("FASE 2: Navegando para a página de Custas...")
            portal_page.goto(URL_PORTAL_CUSTAS)
            portal_page.wait_for_load_state("networkidle", timeout=60000)
            
            # ADIÇÃO: Espera o loader principal da página de custas desaparecer
            logging.info("Aguardando o carregamento completo da interface de custas...")
            portal_page.locator("div.loader.is-loading").wait_for(state="hidden", timeout=30000)
            
            logging.info("[SUCESSO] Página de Custas carregada!")
            
            # --- FASE 3: PROCESSAMENTO DA FILA ---
            logging.info("FASE 3: Iniciando processamento da fila de solicitações...")
            for solicitacao in solicitacoes_para_processar:
                solicitacao_id = solicitacao['id']
                
                # Atualiza o status para "Em Processamento" na API
                api_client.update_solicitacao(solicitacao_id, {"status_robo": "Em Processamento"})

                # Chama a função de processamento individual
                resultado = processar_solicitacao_especifica(portal_page, solicitacao)
                
                # Envia o resultado final para a API
                if resultado:
                    api_client.update_solicitacao(solicitacao_id, resultado)
                else:
                    api_client.update_solicitacao(solicitacao_id, {"status_robo": "Erro: Falha desconhecida no robô"})

    except (PlaywrightError, ConnectionError) as e:
        logging.critical(f"Ocorreu um erro de automação/conexão: {e}", exc_info=True)
    except Exception as e:
        logging.critical("Ocorreu uma falha crítica e inesperada no fluxo principal.", exc_info=True)
    
    finally:
        # --- FASE 4: ENCERRAMENTO ---
        logging.info("Encerrando a sessão do navegador...")
        if browser and browser.is_connected():
            try:
                browser.close()
                logging.info("Browser do Playwright fechado.")
            except Exception as e:
                logging.warning(f"Erro ao fechar o browser: {e}")
        
        logging.info("=" * 60)
        logging.info("ROBO ONECOST FINALIZADO")
        logging.info("=" * 60)

if __name__ == "__main__":
    main()

