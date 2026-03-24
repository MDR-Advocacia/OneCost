# robot/utils/onelog_client.py
import time
import requests
import logging
from typing import Dict, Any, Optional

_ultimo_marcapasso = 0
INTERVALO_MARCAPASSO = 20 * 60  # 20 minutos em segundos

try:
    from config import ONELOG_API_URL, ONELOG_USERNAME, ONELOG_PASSWORD
except ImportError:
    import os
    ONELOG_API_URL = os.getenv("ONELOG_API_URL", "http://api-onelog.mdradvocacia.com")
    ONELOG_USERNAME = os.getenv("ONELOG_USERNAME")
    ONELOG_PASSWORD = os.getenv("ONELOG_PASSWORD")

log = logging.getLogger(__name__)

# Definimos um User-Agent padrão (Windows) caso a API do OneLog não devolva um
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def obter_sessao_onelog() -> Dict[str, Any]:
    """Faz o fluxo completo de login no OneLog e retorna os cookies e User-Agent."""
    log.info("--- INICIANDO INTEGRAÇÃO COM ONELOG ---")
    if not ONELOG_USERNAME or not ONELOG_PASSWORD:
        raise ValueError("Credenciais do OneLog (ONELOG_USERNAME/ONELOG_PASSWORD) não configuradas no .env.")

    payload_login = {
        "username": ONELOG_USERNAME,
        "password": ONELOG_PASSWORD,
        "user_agent": DEFAULT_USER_AGENT
    }

    try:
        # 1. Solicita Login
        log.info(f"Solicitando acesso ao Portal via OneLog ({ONELOG_API_URL})...")
        res_login = requests.post(f"{ONELOG_API_URL}/api/zerocore/login", json=payload_login, timeout=15)
        
        if res_login.status_code in [401, 403]:
            raise PermissionError(f"Acesso Negado no AD do OneLog: {res_login.json().get('mensagem', 'Erro desconhecido')}")
        res_login.raise_for_status()
        
        data_login = res_login.json()
        setor = data_login.get("setor")
        
        # Se for sucesso instantâneo (sessão já existia)
        if data_login.get("status") == "sucesso":
            log.info("Sessão já estava ativa e pronta no OneLog!")
            return {"cookies": data_login.get("cookies", []), "user_agent": DEFAULT_USER_AGENT}

        # 2. Polling (Aguardando o robô do OneLog fazer o login real)
        log.info("Login enfileirado no OneLog. Aguardando processamento...")
        tentativas = 0
        while tentativas < 150:  # Timeout de ~5 minutos
            time.sleep(2)
            tentativas += 1
            
            res_status = requests.get(f"{ONELOG_API_URL}/api/zerocore/status?setor={setor}", timeout=10)
            data_status = res_status.json()
            
            if data_status.get("mensagem"):
                log.info(f"[OneLog Status] {data_status['mensagem']}")
                
            if data_status.get("erro"):
                raise Exception("Falha no worker do OneLog ao tentar logar no Banco.")
                
            if data_status.get("concluido"):
                log.info("OneLog finalizou o login! Resgatando cookies...")
                
                # 3. Pegar os cookies finais
                payload_sessao = {"username": ONELOG_USERNAME, "password": ONELOG_PASSWORD, "setor": setor}
                res_sessao = requests.post(f"{ONELOG_API_URL}/api/zerocore/session", json=payload_sessao, timeout=15)
                res_sessao.raise_for_status()
                session_data = res_sessao.json()
                
                if session_data.get("status") == "sucesso":
                    log.info("Cookies resgatados com sucesso do OneLog.")
                    return {
                        "cookies": session_data.get("cookies", []),
                        # Pega o User-Agent que o OneLog usou (se ele devolver), senão usa o padrão
                        "user_agent": session_data.get("user_agent", DEFAULT_USER_AGENT) 
                    }
                else:
                    raise Exception("Erro ao resgatar sessão final do OneLog.")

        raise TimeoutError("Tempo limite esgotado aguardando o OneLog.")

    except Exception as e:
        log.error(f"Falha crítica na integração com OneLog: {e}", exc_info=True)
        raise


def renovar_sessao_onelog() -> bool:
    """Aciona a rota de heartbeat/renew do OneLog (Marcapasso) a cada 20 minutos."""
    global _ultimo_marcapasso
    agora = time.time()
    
    # Se passaram menos de 20 minutos desde a última vez, o robô ignora o envio e segue a vida
    if agora - _ultimo_marcapasso < INTERVALO_MARCAPASSO:
        return True

    try:
        log.info("O tempo passou! Enviando sinal de marcapasso (renew) para o OneLog...")
        # Lembre-se de manter a alteração do payload ou do ?setor=BB_Robos que resolveu o erro 400
        res = requests.post(f"{ONELOG_API_URL}/api/zerocore/renew?setor=BB_Robos", timeout=10)
        res.raise_for_status()
        log.info("Marcapasso recebido com sucesso pelo OneLog.")
        
        # Só atualiza o relógio se o OneLog confirmar o recebimento
        _ultimo_marcapasso = agora
        return True
    except Exception as e:
        log.warning(f"Falha ao enviar marcapasso para o OneLog: {e}")
        return False