import requests
import logging
from typing import Optional, Dict, List, Any
import json

# Importar configs
from config import API_BASE_URL

log = logging.getLogger(__name__) # Logger específico

# Variável global para armazenar o token JWT após o login
_api_token: Optional[str] = None

# --- Funções Auxiliares ---

def _get_auth_headers() -> Dict[str, str]:
    """Retorna o cabeçalho de autorização se o token existir."""
    headers = {'Accept': 'application/json'}
    if _api_token:
        headers['Authorization'] = f'Bearer {_api_token}'
    return headers

# --- Funções da API ---

def robot_login(username: str, password: str) -> bool:
    """Faz login na API e armazena o token globalmente."""
    global _api_token
    _api_token = None # Reseta o token antes de tentar logar
    login_url = f"{API_BASE_URL}/login"
    payload = {'username': username, 'password': password}
    log.info(f"Tentando login na API como usuário '{username}' em {login_url}...")

    try:
        # O /login espera dados de formulário (x-www-form-urlencoded)
        response = requests.post(login_url, data=payload, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        response.raise_for_status() # Lança exceção para 4xx/5xx
        data = response.json()
        if data.get("access_token"):
            _api_token = data["access_token"]
            log.info("Login do robô na API bem-sucedido. Token armazenado.")
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

def resetar_solicitacoes_com_erro() -> bool:
    """Chama o endpoint para resetar solicitações com erro para Pendente."""
    reset_url = f"{API_BASE_URL}/solicitacoes/resetar-erros"
    headers = _get_auth_headers()
    if not _api_token: # Verifica se estamos logados
        log.error("Não é possível resetar erros: Robô não autenticado (token ausente).")
        return False

    log.info(f"Chamando endpoint para resetar solicitações com erro em {reset_url}...")
    try:
        # Usando POST para a nova rota
        response = requests.post(reset_url, headers=headers)
        response.raise_for_status()
        log.info(f"Resposta do reset de erros: {response.json().get('message', 'Status OK')}")
        return True
    except requests.exceptions.RequestException as e:
        log.error(f"Erro ao chamar API para resetar erros ({reset_url}): {e}")
        if e.response is not None:
             try:
                 error_detail = e.response.json()
                 log.error(f"Detalhes do erro da API (status {e.response.status_code}): {error_detail}")
             except json.JSONDecodeError:
                  log.error(f"Não foi possível decodificar a resposta de erro da API (status {e.response.status_code}): {e.response.text}")
        return False


def get_proxima_solicitacao_pendente() -> Optional[Dict[str, Any]]:
    """Busca a próxima solicitação com status 'Pendente'."""
    get_url = f"{API_BASE_URL}/solicitacoes/"
    params = {"status_robo": "Pendente", "limit": 1}
    headers = _get_auth_headers()
    if not _api_token:
        log.error("Não é possível buscar solicitações: Robô não autenticado (token ausente).")
        return None

    log.info(f"Buscando próxima solicitação pendente em {get_url}...")
    try:
        response = requests.get(get_url, params=params, headers=headers)
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

def update_solicitacao_na_api(solicitacao_id: int, payload: Dict[str, Any]) -> bool:
    """Atualiza uma solicitação específica na API."""
    update_url = f"{API_BASE_URL}/solicitacoes/{solicitacao_id}"
    headers = _get_auth_headers()
    if not _api_token:
        log.error(f"Não é possível atualizar solicitação ID {solicitacao_id}: Robô não autenticado.")
        return False

    headers['Content-Type'] = 'application/json'

    # Remove chaves com valor None para evitar sobrescrever dados existentes com null
    # O backend (server.py) foi ajustado para lidar com "Pendente" limpando os outros campos
    payload_limpo = {}
    for k, v in payload.items():
        if k == 'status_portal' or k == 'ultima_verificacao_robo': # Permite limpar esses campos enviando None
            payload_limpo[k] = v
        elif v is not None: # Ignora outros Nones
            payload_limpo[k] = v
            
    # Garante que comprovantes_path seja uma lista de strings
    if 'comprovantes_path' in payload_limpo:
        payload_limpo['comprovantes_path'] = [str(p) for p in payload_limpo['comprovantes_path']]

    log.info(f"Enviando atualização para API (ID {solicitacao_id}): {json.dumps(payload_limpo, default=str)}")
    try:
        response = requests.put(update_url, headers=headers, json=payload_limpo)
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

