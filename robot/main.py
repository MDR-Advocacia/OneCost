# robot/main.py
# (Versão V8 - com logs dinâmicos e chamada focada)

import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PlaywrightError

# --- Bloco de segurança para garantir que o Python ache os módulos ---
try:
    robot_dir = Path(__file__).resolve().parent
    if str(robot_dir) not in sys.path:
        sys.path.insert(0, str(robot_dir))
except NameError:
    sys.path.insert(0, str(Path.cwd()))
# --- Fim do bloco de segurança ---


try:
    from config import URL_PORTAL_CUSTAS, LOG_DIR
    from core.browser_manager import realizar_login_automatico
    # Importa a função principal de extração
    from core.custos_manager import pesquisar_e_extrair_custas

except ModuleNotFoundError as e:
    print("="*80)
    print(f"ERRO DE IMPORTAÇÃO: {e}")
    print("Verifique se os arquivos 'config.py', 'core/browser_manager.py' e 'core/custos_manager.py' existem.")
    print("="*80)
    sys.exit(1)


# --- Configuração de Log Dinâmico ---
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
    logging.info(f"🤖 INICIANDO ROBO ONECOST (V8) | LOG: {log_filename} 🤖")
    logging.info("=" * 60)
    
    browser = None
    browser_process_ref = None

    try:
        with sync_playwright() as playwright:
            
            # --- FASE 1: LOGIN ---
            logging.info("FASE 1: Realizando login no portal...")
            browser, context, browser_process_ref, portal_page = realizar_login_automatico(playwright)
            logging.info("[SUCESSO] Login realizado.")

            # --- FASE 2: NAVEGAÇÃO PARA CUSTAS ---
            logging.info(f"FASE 2: Navegando para a página de Custas...")
            portal_page.goto(URL_PORTAL_CUSTAS)
            portal_page.wait_for_load_state("networkidle", timeout=60000)
            logging.info("[SUCESSO] Página de Custas carregada!")
            
            # --- FASE 3: PESQUISA E EXTRAÇÃO ---
            npj_para_buscar = "2023/0229740-000"
            logging.info(f"FASE 3: Iniciando extração de dados para o NPJ: {npj_para_buscar}...")
            
            resultados = pesquisar_e_extrair_custas(portal_page, npj_para_buscar)
            
            logging.info(f"Processamento concluído. Resultados para o NPJ {npj_para_buscar}:")
            # Imprime o resultado final de forma mais legível
            import json
            logging.info(json.dumps(resultados, indent=2, ensure_ascii=False))


    except PlaywrightError as e:
        logging.critical(f"Ocorreu um erro específico do Playwright: {e}", exc_info=True)
    except ConnectionError as e:
         logging.critical(f"Ocorreu um erro de conexão (no login): {e}", exc_info=True)
    except Exception as e:
        logging.critical(f"Ocorreu uma falha crítica e inesperada.", exc_info=True)
    
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

