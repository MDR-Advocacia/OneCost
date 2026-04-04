# robot/utils/onelog_client.py
import time
import requests
import logging
from typing import Dict, Any, Optional

_ultimo_marcapasso = 0
_setor_atual = None  # NOVO: Vai guardar o setor exato retornado pelo OneLog
INTERVALO_MARCAPASSO = 15 * 60  # Reduzido para 15 min (O OneLog desativa aos 19/20)

try:
    from config import ONELOG_API_URL, ONELOG_USERNAME, ONELOG_PASSWORD
except ImportError:
    import os
    ONELOG_API_URL = os.getenv("ONELOG_API_URL", "http://api-onelog.mdradvocacia.com")
    ONELOG_USERNAME = os.getenv("ONELOG_USERNAME")
    ONELOG_PASSWORD = os.getenv("ONELOG_PASSWORD")

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def obter_sessao_onelog() -> Dict[str, Any]:
    global _setor_atual
    log.info("--- INICIANDO INTEGRAÇÃO COM ONELOG ---")
    if not ONELOG_USERNAME or not ONELOG_PASSWORD:
        raise ValueError("Credenciais do OneLog (ONELOG_USERNAME/ONELOG_PASSWORD) não configuradas no .env.")

    payload_login = {
        "username": ONELOG_USERNAME,
        "password": ONELOG_PASSWORD,
        "user_agent": DEFAULT_USER_AGENT
    }

    try:
        log.info(f"Solicitando acesso ao Portal via OneLog ({ONELOG_API_URL})...")
        res_login = requests.post(f"{ONELOG_API_URL}/api/zerocore/login", json=payload_login, timeout=15)
        
        if res_login.status_code in [401, 403]:
            raise PermissionError(f"Acesso Negado no AD do OneLog: {res_login.json().get('mensagem', 'Erro desconhecido')}")
        res_login.raise_for_status()
        
        data_login = res_login.json()
        setor = data_login.get("setor")
        _setor_atual = setor # SALVA O NOME CORRETO (Ex: "ROBOS") PARA USAR NO MARCAPASSO
        log.info(f"✅ Setor identificado pelo OneLog: {_setor_atual}")
        
        if data_login.get("status") == "sucesso":
            log.info("Sessão já estava ativa e pronta no OneLog!")
            return {"cookies": data_login.get("cookies", []), "user_agent": DEFAULT_USER_AGENT}

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
                
                payload_sessao = {"username": ONELOG_USERNAME, "password": ONELOG_PASSWORD, "setor": setor}
                res_sessao = requests.post(f"{ONELOG_API_URL}/api/zerocore/session", json=payload_sessao, timeout=15)
                res_sessao.raise_for_status()
                session_data = res_sessao.json()
                
                if session_data.get("status") == "sucesso":
                    log.info("Cookies resgatados com sucesso do OneLog.")
                    return {
                        "cookies": session_data.get("cookies", []),
                        "user_agent": session_data.get("user_agent", DEFAULT_USER_AGENT) 
                    }
                else:
                    raise Exception("Erro ao resgatar sessão final do OneLog.")

        raise TimeoutError("Tempo limite esgotado aguardando o OneLog.")

    except Exception as e:
        log.error(f"Falha crítica na integração com OneLog: {e}", exc_info=True)
        raise


def renovar_sessao_onelog() -> bool:
    global _ultimo_marcapasso, _setor_atual
    agora = time.time()
    
    if agora - _ultimo_marcapasso < INTERVALO_MARCAPASSO:
        return True

    if not _setor_atual:
        log.warning("Marcapasso ignorado: O robô ainda não fez login para descobrir o setor.")
        return False

    try:
        log.info(f"Enviando marcapasso para o OneLog no setor: '{_setor_atual}'...")
        
        # Envia no JSON para bater certinho com o novo api.py do OneLog
        payload_renew = {
            "username": ONELOG_USERNAME,
            "password": ONELOG_PASSWORD,
            "setor": _setor_atual,
            "user_agent": DEFAULT_USER_AGENT
        }
        
        res = requests.post(f"{ONELOG_API_URL}/api/zerocore/renew", json=payload_renew, timeout=10)
        res.raise_for_status()
        log.info("Marcapasso recebido com sucesso pelo OneLog.")
        
        _ultimo_marcapasso = agora
        return True
    except Exception as e:
        log.warning(f"Falha ao enviar marcapasso para o OneLog: {e}")
        return False