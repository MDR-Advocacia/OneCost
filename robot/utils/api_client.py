import os
import requests
import logging
from typing import Optional, Dict, List, Any
import json
from decimal import Decimal # Para tratar o valor corretamente no payload

# Importar configs
try:
    # Tenta importar ROBOT_USERNAME também, para log de erro 403
    from config import API_BASE_URL, ROBOT_USERNAME, ROBOT_PASSWORD
except ImportError:
    # Fallback se executado de forma isolada
    API_BASE_URL = os.getenv("API_BASE_URL", "http://onecost-backend:8000")
    ROBOT_USERNAME = "robô_desconhecido" # Define um fallback
    ROBOT_PASSWORD = os.getenv("ROBOT_PASSWORD", "default_password")


log = logging.getLogger(__name__) # Logger específico

# Variáveis globais para armazenar o token JWT e o ID do usuário robô
_api_token: Optional[str] = None
_robot_user_id: Optional[int] = None
_robot_login_username: Optional[str] = ROBOT_USERNAME
_robot_login_password: Optional[str] = ROBOT_PASSWORD

# --- Funções Auxiliares ---

def _get_auth_headers() -> Dict[str, str]:
    """Retorna o cabeçalho de autorização se o token existir."""
    headers = {'Accept': 'application/json'}
    if _api_token:
        headers['Authorization'] = f'Bearer {_api_token}'
    return headers


def _build_headers(extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Monta headers preservando content-type e atualizando o bearer token atual."""
    headers = _get_auth_headers()
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _reauthenticate_robot() -> bool:
    """Tenta renovar o token do robô usando as credenciais já conhecidas."""
    if not _robot_login_username or _robot_login_password is None:
        log.error("Não é possível reautenticar o robô: credenciais não disponíveis.")
        return False

    log.warning("Token da API expirado ou rejeitado. Tentando novo login do robô...")
    return robot_login(_robot_login_username, _robot_login_password)


def _request_with_reauth(method: str, url: str, *, retry_on_401: bool = True, **kwargs) -> requests.Response:
    """Executa requisições autenticadas e refaz login uma vez em caso de 401."""
    response = requests.request(method, url, **kwargs)

    if response.status_code != 401 or not retry_on_401:
        return response

    log.warning("API retornou 401 em %s %s. Renovando token e repetindo a requisição...", method.upper(), url)
    if not _reauthenticate_robot():
        return response

    retry_kwargs = dict(kwargs)
    retry_kwargs['headers'] = _build_headers(kwargs.get('headers'))
    return requests.request(method, url, **retry_kwargs)

def _fetch_robot_user_id() -> Optional[int]:
    """Busca o ID do usuário robô logado usando o endpoint /users/me."""
    if not _api_token:
        log.error("Não é possível buscar ID do robô: Robô não autenticado.")
        return None

    me_url = f"{API_BASE_URL}/users/me"
    headers = _get_auth_headers()
    log.info(f"Buscando informações do usuário robô em {me_url}...")
    try:
        response = requests.get(me_url, headers=headers, timeout=10)
        response.raise_for_status() # Lança erro para status >= 400
        user_data = response.json()
        user_id = user_data.get('id')
        username = user_data.get('username') # Pega username para log
        if isinstance(user_id, int):
            log.info(f"ID do usuário robô '{username}' obtido com sucesso: {user_id}")
            return user_id
        else:
            log.error(f"ID do usuário robô não encontrado ou inválido na resposta de {me_url}: {user_data}")
            return None
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao buscar informações do usuário robô ({me_url}): {e}")
        if e.response is not None:
             try:
                 error_detail = e.response.json()
                 log.error(f"Detalhes do erro da API (status {e.response.status_code}): {error_detail}")
             except json.JSONDecodeError:
                  log.error(f"Não foi possível decodificar a resposta de erro da API (status {e.response.status_code}): {e.response.text}")
        return None
    except Exception as e:
        log.error(f"Erro inesperado ao buscar ID do usuário robô: {e}", exc_info=True)
        return None


# --- Funções da API ---

def robot_login(username: str, password: str) -> bool:
    """Faz login na API, armazena o token e busca o ID do usuário robô."""
    global _api_token, _robot_user_id, _robot_login_username, _robot_login_password
    _api_token = None # Limpa token antigo
    _robot_user_id = None # Limpa ID antigo
    _robot_login_username = username
    _robot_login_password = password
    login_url = f"{API_BASE_URL}/login"
    payload = {'username': username, 'password': password}
    log.info(f"Tentando login na API como usuário '{username}' em {login_url}...")

    try:
        # Envia como form data
        response = requests.post(login_url, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
        response.raise_for_status() # Verifica se houve erro HTTP
        data = response.json()
        if data.get("access_token"):
            _api_token = data["access_token"]
            log.info("Login do robô na API bem-sucedido. Token armazenado.")
            # Busca o ID do usuário após o login bem-sucedido
            _robot_user_id = _fetch_robot_user_id()
            if _robot_user_id is None:
                log.error("Falha ao obter o ID do usuário robô após o login. Verifique as permissões ou a resposta da API /users/me.")
                _api_token = None # Invalida o token se não conseguir o ID
                return False # Falha o login se não conseguir obter o ID
            return True
        else:
            log.error("Login na API retornou status OK, mas token não foi encontrado na resposta.")
            return False
    except requests.exceptions.RequestException as e:
        log.error(f"Erro durante o login na API ({login_url}): {e}")
        if e.response is not None:
             try:
                 error_detail = e.response.json()
                 log.error(f"Detalhes do erro da API (status {e.response.status_code}): {error_detail}")
             except json.JSONDecodeError:
                  log.error(f"Não foi possível decodificar a resposta de erro da API (status {e.response.status_code}): {e.response.text}")
        return False
    except Exception as e:
         log.error(f"Erro inesperado durante o login: {e}", exc_info=True)
         return False

def resetar_solicitacoes_com_erro() -> bool:
    """Chama o endpoint para resetar solicitações com erro para Pendente."""
    reset_url = f"{API_BASE_URL}/solicitacoes/resetar-erros"
    headers = _build_headers()
    if not _api_token:
        log.error("Não é possível resetar erros: Robô não autenticado (token ausente).")
        return False

    log.info(f"Chamando endpoint para resetar solicitações com erro em {reset_url}...")
    try:
        # Método POST sem corpo (body) é comum para ações
        response = _request_with_reauth("post", reset_url, headers=headers, timeout=15) # Timeout um pouco maior
        response.raise_for_status()
        log.info(f"Resposta do reset de erros: {response.json().get('message', 'Status OK')}")
        return True
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao chamar API para resetar erros ({reset_url}): {e}")
        if e.response is not None:
             try:
                 error_detail = e.response.json()
                 # Verifica se é erro de permissão (403 Forbidden)
                 if e.response.status_code == 403:
                     # Usa ROBOT_USERNAME importado do config
                     log.error(f"Erro 403: Permissão negada para resetar erros. Verifique se o usuário '{ROBOT_USERNAME}' tem role 'admin'. Detalhe: {error_detail}")
                 else:
                     log.error(f"Detalhes do erro da API (status {e.response.status_code}): {error_detail}")
             except json.JSONDecodeError:
                  log.error(f"Não foi possível decodificar a resposta de erro da API (status {e.response.status_code}): {e.response.text}")
        return False
    except Exception as e:
        log.error(f"Erro inesperado ao resetar erros: {e}", exc_info=True)
        return False


def get_proxima_solicitacao_pendente() -> Optional[Dict[str, Any]]:
    """Busca a próxima solicitação (limit 1) com status 'Pendente'."""
    get_url = f"{API_BASE_URL}/solicitacoes/"
    params = {"status_robo": "Pendente", "limit": 1} # Busca apenas uma pendente
    headers = _build_headers()
    if not _api_token:
        log.error("Não é possível buscar solicitações: Robô não autenticado (token ausente).")
        return None

    log.info(f"Buscando próxima solicitação pendente em {get_url}...")
    try:
        response = _request_with_reauth("get", get_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        solicitacoes = response.json()
        if solicitacoes:
            # Verifica se a resposta é uma lista e pega o primeiro item
            if isinstance(solicitacoes, list) and len(solicitacoes) > 0:
                 log.info(f"Solicitação pendente encontrada: ID {solicitacoes[0].get('id')}")
                 return solicitacoes[0]
            else:
                 log.error(f"API retornou dados inesperados para solicitações pendentes: {solicitacoes}")
                 return None
        else:
            log.info("Nenhuma solicitação pendente encontrada.")
            return None
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao buscar solicitações pendentes da API ({get_url}): {e}")
        if e.response is not None:
             try:
                 error_detail = e.response.json()
                 log.error(f"Detalhes do erro da API (status {e.response.status_code}): {error_detail}")
             except json.JSONDecodeError:
                  log.error(f"Não foi possível decodificar a resposta de erro da API (status {e.response.status_code}): {e.response.text}")
        return None
    except Exception as e:
        log.error(f"Erro inesperado ao buscar próxima solicitação: {e}", exc_info=True)
        return None


def get_todas_solicitacoes_pendentes() -> List[Dict[str, Any]]:
    """Busca TODAS as solicitações com status 'Pendente'."""
    get_url = f"{API_BASE_URL}/solicitacoes/"
    params = {"status_robo": "Pendente"}
    headers = _build_headers()
    if not _api_token:
        log.error("Não é possível buscar solicitações: Robô não autenticado (token ausente).")
        return []

    log.info(f"Buscando TODAS as solicitações pendentes em {get_url}...")
    try:
        response = _request_with_reauth("get", get_url, params=params, headers=headers, timeout=20) # Timeout maior
        response.raise_for_status()
        solicitacoes = response.json()
        if solicitacoes and isinstance(solicitacoes, list):
            log.info(f"{len(solicitacoes)} solicitações pendentes encontradas.")
            # Retorna a lista ordenada por ID, da mais antiga para a mais nova
            return sorted(solicitacoes, key=lambda x: x.get('id', 0))
        else:
            log.info("Nenhuma solicitação pendente encontrada ou formato inválido.")
            return []
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao buscar TODAS as solicitações pendentes da API ({get_url}): {e}")
        if e.response is not None:
             try:
                 error_detail = e.response.json()
                 log.error(f"Detalhes do erro da API (status {e.response.status_code}): {error_detail}")
             except json.JSONDecodeError:
                  log.error(f"Não foi possível decodificar a resposta de erro da API (status {e.response.status_code}): {e.response.text}")
        return [] # Retorna lista vazia em caso de erro
    except Exception as e:
        log.error(f"Erro inesperado ao buscar todas as solicitações: {e}", exc_info=True)
        return []


def update_solicitacao_na_api(solicitacao_id: int, payload_original: Dict[str, Any]) -> bool:
    """Atualiza uma solicitação específica na API, enviando os campos corretos."""
    update_url = f"{API_BASE_URL}/solicitacoes/{solicitacao_id}"
    headers = _build_headers()
    if not _api_token:
        log.error(f"Não é possível atualizar solicitação ID {solicitacao_id}: Robô não autenticado.")
        return False

    headers['Content-Type'] = 'application/json'

    # --- <<< NOVO: Montagem cuidadosa do payload JSON >>> ---
    payload_final_json = {}

    # Campos que SEMPRE vêm do resultado do robô (mesmo que sejam None)
    campos_obrigatorios_robo = [
        "status_robo",
        "status_portal",
        "numero_processo", # Agora vem do resultado_final["numero_processo"]
        "especificacao",   # Agora vem do resultado_final["especificacao"]
        "comprovantes_path", # Agora vem do resultado_final["comprovantes_path"]
        "usuario_confirmacao_id", # Vem do resultado_final["usuario_confirmacao_id"]
        "monitoramento_ativo",
        "motivo_encerramento",
        "proxima_verificacao_em",
        "alerta_enviado_em"
    ]

    for key in campos_obrigatorios_robo:
        value = payload_original.get(key)
        # Trata strings vazias como None
        if isinstance(value, str) and not value.strip():
            payload_final_json[key] = None
        # Garante que comprovantes_path seja lista ou None
        elif key == "comprovantes_path":
             if isinstance(value, list):
                  # Garante que sejam strings e remove None/vazios da lista
                  payload_final_json[key] = [str(p) for p in value if p]
             elif value is not None:
                  log.warning(f"comprovantes_path para ID {solicitacao_id} não é uma lista ({type(value)}), enviando como None.")
                  payload_final_json[key] = None
             else:
                  payload_final_json[key] = None # Envia None se for None
        else:
             payload_final_json[key] = value # Mantém outros tipos (int, None)

    # Adiciona o campo valor SE ele existir no payload original (evita enviar valor=None desnecessariamente)
    # A API espera float para 'valor' no schema de update
    if 'valor' in payload_original and payload_original['valor'] is not None:
         try:
              # Converte Decimal ou string para float
              valor_decimal = Decimal(str(payload_original['valor']))
              payload_final_json['valor'] = float(round(valor_decimal, 2))
         except (InvalidOperation, ValueError, TypeError):
              log.error(f"Valor '{payload_original['valor']}' inválido para ID {solicitacao_id}, não será enviado.")


    # Remove chaves com valor None, EXCETO as permitidas explicitamente pela API no update
    # (status_portal, numero_processo, especificacao, comprovantes_path, usuario_confirmacao_id, valor)
    # O status_robo NUNCA deve ser None ao atualizar.
    payload_limpo_final = {}
    campos_permitidos_none_na_api = {
        'status_portal',
        'numero_processo',
        'especificacao',
        'comprovantes_path',
        'usuario_confirmacao_id',
        'valor',
        'motivo_encerramento',
        'proxima_verificacao_em',
        'alerta_enviado_em'
    }

    for k, v in payload_final_json.items():
        if v is not None:
            payload_limpo_final[k] = v
        elif k in campos_permitidos_none_na_api:
             payload_limpo_final[k] = None # Envia None explicitamente se permitido

    # Garante que status_robo nunca seja None (caso algo dê errado)
    if payload_limpo_final.get("status_robo") is None:
         log.warning(f"status_robo ficou None para ID {solicitacao_id}. Usando 'Erro: Status Desconhecido'. Payload original: {payload_original}")
         payload_limpo_final["status_robo"] = "Erro: Status Desconhecido"


    log.info(f"Enviando atualização JSON para API (ID {solicitacao_id}): {json.dumps(payload_limpo_final, default=str)}")
    try:
        response = _request_with_reauth("put", update_url, headers=headers, json=payload_limpo_final, timeout=15)
        response.raise_for_status() # Verifica erro HTTP
        log.info(f"Solicitação ID {solicitacao_id} atualizada com sucesso na API.")
        return True
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao atualizar solicitação ID {solicitacao_id} na API ({update_url}): {e}")
        if e.response is not None:
             try:
                 error_detail = e.response.json()
                 log.error(f"Detalhes do erro da API (status {e.response.status_code}): {error_detail}")
             except json.JSONDecodeError:
                  log.error(f"Não foi possível decodificar a resposta de erro da API (status {e.response.status_code}): {e.response.text}")
        return False
    except Exception as e:
        log.error(f"Erro inesperado ao enviar atualização para API (ID {solicitacao_id}): {e}", exc_info=True)
        return False
