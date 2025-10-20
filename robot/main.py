# robot/main.py
# (Versão V4 - Final com imports centralizados)

import logging
import sys
import time
from pathlib import Path
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
    # Importa do config.py
    from config import URL_PORTAL_CUSTAS, LOG_DIR
    
    # Importa do core/browser_manager.py
    from core.browser_manager import realizar_login_automatico
    
    # Importa do core/session_manager.py (para uso futuro)
    # from core.session_manager import refresh_session_if_needed, SessionExpiredError

except ModuleNotFoundError as e:
    print("="*80)
    print(f"ERRO DE IMPORTAÇÃO: {e}")
    print("Verifique se os arquivos 'config.py' e 'core/browser_manager.py' existem dentro da pasta 'robot/'.")
    print("="*80)
    sys.exit(1)


# --- Configuração de Log ---
LOG_DIR.mkdir(exist_ok=True) # Garante que a pasta 'logs' (definida no config) exista

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "onecost_robot.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def main():
    logging.info("=" * 60)
    logging.info("🤖 INICIANDO TESTE RPA ONECOST (V4) 🤖")
    logging.info("=" * 60)
    
    browser = None
    browser_process_ref = None 

    try:
        with sync_playwright() as playwright:
            
            # --- FASE 1: LOGIN ---
            logging.info("FASE 1: Realizando login no portal...")
            browser, context, browser_process_ref, portal_page = realizar_login_automatico(playwright)
            logging.info("[SUCESSO] Login realizado. Estamos na página inicial do portal.")
            # session_start_time = time.time() # Guardar para o refresh

            # --- FASE 2: NAVEGAÇÃO PARA CUSTAS ---
            logging.info(f"FASE 2: Navegando para a página de Custas...")
            logging.info(f"URL Alvo: {URL_PORTAL_CUSTAS}")
            
            portal_page.goto(URL_PORTAL_CUSTAS)
            
            logging.info("Aguardando página de Custas carregar (networkidle)...")
            portal_page.wait_for_load_state("networkidle", timeout=60000)
            
            logging.info("[SUCESSO] Página de Custas carregada!")
            
            logging.info("Navegação concluída. Robô ficará aberto por 30 segundos...")
            time.sleep(30)

    except PlaywrightError as e:
        logging.critical(f"Ocorreu um erro específico do Playwright: {e}", exc_info=True)
    except ConnectionError as e:
         logging.critical(f"Ocorreu um erro de conexão (no login): {e}", exc_info=True)
    except Exception as e:
        logging.critical(f"Ocorreu uma falha crítica e inesperada.", exc_info=True)
    
    finally:
        # --- FASE 3: ENCERRAMENTO ---
        logging.info("Encerrando a sessão do navegador...")
        if browser and browser.is_connected():
            try:
                browser.close()
                logging.info("Browser do Playwright fechado.")
            except Exception as e:
                logging.warning(f"Erro ao fechar o browser: {e}")
        
        # O processo .bat/.sh é fechado pela função de login ou sessão
        # mas podemos adicionar uma garantia aqui se `browser_process_ref` for gerenciado
        
        logging.info("=" * 60)
        logging.info("RPA ONECOST (TESTE) FINALIZADO")
        logging.info("=" * 60)

if __name__ == "__main__":
    main()