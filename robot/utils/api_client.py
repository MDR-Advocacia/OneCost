import requests
import logging
from typing import Optional, Dict, List, Any
import json

# Importar configs
try:
    from config import API_BASE_URL
except ImportError:
    # Fallback se executado de forma isolada (pouco provável)
    API_BASE_URL = "http://localhost:8001"


log = logging.getLogger(__name__) # Logger específico

# Variáveis globais para armazenar o token JWT e o ID do usuário robô
_api_token: Optional[str] = None
_robot_user_id: Optional[int] = None

# --- Funções Auxiliares ---

def _get_auth_headers() -> Dict[str, str]:
    """Retorna o cabeçalho de autorização se o token existir."""
    headers = {'Accept': 'application/json'}
    if _api_token:
        headers['Authorization'] = f'Bearer {_api_token}'
    return headers

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
        response.raise_for_status()
        user_data = response.json()
        user_id = user_data.get('id')
        if isinstance(user_id, int):
            log.info(f"ID do usuário robô obtido com sucesso: {user_id}")
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
    global _api_token, _robot_user_id
    _api_token = None
    _robot_user_id = None
    login_url = f"{API_BASE_URL}/login"
    payload = {'username': username, 'password': password}
    log.info(f"Tentando login na API como usuário '{username}' em {login_url}...")

    try:
        response = requests.post(login_url, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("access_token"):
            _api_token = data["access_token"]
            log.info("Login do robô na API bem-sucedido. Token armazenado.")
            # Busca o ID do usuário após o login
            _robot_user_id = _fetch_robot_user_id()
            if _robot_user_id is None:
                log.error("Falha ao obter o ID do usuário robô após o login. Verifique as permissões ou a resposta da API /users/me.")
                return False # Falha o login se não conseguir obter o ID
            return True
        else:
            log.error("Login na API OK, mas token não recebido.")
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

# ----- FUNÇÃO RESTAURADA -----
def resetar_solicitacoes_com_erro() -> bool:
    """Chama o endpoint para resetar solicitações com erro para Pendente."""
    reset_url = f"{API_BASE_URL}/solicitacoes/resetar-erros"
    headers = _get_auth_headers()
    if not _api_token:
        log.error("Não é possível resetar erros: Robô não autenticado (token ausente).")
        return False

    log.info(f"Chamando endpoint para resetar solicitações com erro em {reset_url}...")
    try:
        response = requests.post(reset_url, headers=headers, timeout=15) # Timeout um pouco maior para esta operação
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
                     log.error(f"Erro 403: Permissão negada para resetar erros. Verifique se o usuário '{ROBOT_USERNAME}' tem role 'admin'. Detalhe: {error_detail}")
                 else:
                     log.error(f"Detalhes do erro da API (status {e.response.status_code}): {error_detail}")
             except json.JSONDecodeError:
                  log.error(f"Não foi possível decodificar a resposta de erro da API (status {e.response.status_code}): {e.response.text}")
        return False
# ----- FIM DA FUNÇÃO RESTAURADA -----


def get_proxima_solicitacao_pendente() -> Optional[Dict[str, Any]]:
    """Busca a próxima solicitação (limit 1) com status 'Pendente'."""
    get_url = f"{API_BASE_URL}/solicitacoes/"
    params = {"status_robo": "Pendente", "limit": 1} # Busca apenas uma pendente
    headers = _get_auth_headers()
    if not _api_token:
        log.error("Não é possível buscar solicitações: Robô não autenticado (token ausente).")
        return None

    log.info(f"Buscando próxima solicitação pendente em {get_url}...")
    try:
        response = requests.get(get_url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        solicitacoes = response.json()
        if solicitacoes:
            log.info(f"Solicitação pendente encontrada: ID {solicitacoes[0].get('id')}")
            return solicitacoes[0]
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

# *** NOVA FUNÇÃO *** (Já estava presente, mantida)
def get_todas_solicitacoes_pendentes() -> List[Dict[str, Any]]:
    """Busca TODAS as solicitações com status 'Pendente'."""
    get_url = f"{API_BASE_URL}/solicitacoes/"
    # Busca por status "Pendente" e um limite alto (ex: 500)
    # O ideal seria paginar, mas para este caso, um limite alto resolve.
    params = {"status_robo": "Pendente", "limit": 500}
    headers = _get_auth_headers()
    if not _api_token:
        log.error("Não é possível buscar solicitações: Robô não autenticado (token ausente).")
        return []

    log.info(f"Buscando TODAS as solicitações pendentes em {get_url}...")
    try:
        response = requests.get(get_url, params=params, headers=headers, timeout=20)
        response.raise_for_status()
        solicitacoes = response.json()
        if solicitacoes:
            log.info(f"{len(solicitacoes)} solicitações pendentes encontradas.")
            # Retorna a lista ordenada por ID, da mais antiga para a mais nova (opcional, mas bom)
            return sorted(solicitacoes, key=lambda x: x.get('id', 0))
        else:
            log.info("Nenhuma solicitação pendente encontrada.")
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

def update_solicitacao_na_api(solicitacao_id: int, payload: Dict[str, Any]) -> bool:
    """Atualiza uma solicitação específica na API."""
    update_url = f"{API_BASE_URL}/solicitacoes/{solicitacao_id}"
    headers = _get_auth_headers()
    if not _api_token:
        log.error(f"Não é possível atualizar solicitação ID {solicitacao_id}: Robô não autenticado.")
        return False

    headers['Content-Type'] = 'application/json'

    # Limpa o payload de chaves com valor None, exceto as permitidas
    payload_limpo = {}
    campos_permitidos_none = {'status_portal', 'ultima_verificacao_robo', 'numero_processo', 'usuario_confirmacao_id'}
    for k, v in payload.items():
        if k in campos_permitidos_none:
            payload_limpo[k] = v
        elif v is not None: # Ignora outros Nones
            payload_limpo[k] = v

    # Garante que comprovantes_path seja uma lista de strings, se existir e não for None
    if 'comprovantes_path' in payload_limpo and payload_limpo['comprovantes_path'] is not None:
        if isinstance(payload_limpo['comprovantes_path'], list):
             payload_limpo['comprovantes_path'] = [str(p) for p in payload_limpo['comprovantes_path'] if p] # Garante que sejam strings e remove None/vazios da lista
        else:
             log.warning(f"comprovantes_path para ID {solicitacao_id} não é uma lista, enviando como None.")
             payload_limpo['comprovantes_path'] = None

    log.info(f"Enviando atualização para API (ID {solicitacao_id}): {json.dumps(payload_limpo, default=str)}")
    try:
        response = requests.put(update_url, headers=headers, json=payload_limpo, timeout=15)
        response.raise_for_status()
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