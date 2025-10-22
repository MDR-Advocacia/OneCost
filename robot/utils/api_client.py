import requests
import logging
from typing import List, Dict, Any, Optional

class ApiClient:
    """Cliente para interagir com a API do OneCost."""
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token = self._authenticate()

    def _authenticate(self) -> Optional[str]:
        """Realiza a autenticação na API e obtém um token de acesso."""
        logging.info("Autenticando na API do OneCost...")
        try:
            login_data = {'username': self.username, 'password': self.password}
            response = requests.post(f"{self.base_url}/login", data=login_data)
            response.raise_for_status()
            logging.info("[SUCESSO] Autenticação na API realizada.")
            return response.json().get("access_token")
        except requests.exceptions.RequestException as e:
            logging.error(f"Falha ao autenticar na API: {e}")
            return None

    def _get_auth_headers(self) -> Dict[str, str]:
        """Retorna os headers de autenticação."""
        if not self.token:
            raise Exception("Não autenticado. Não é possível criar os headers.")
        return {"Authorization": f"Bearer {self.token}"}

    def get_solicitacoes(self, status: Optional[str] = None, status_ne: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Busca a lista de solicitações da API.
        Pode filtrar por status (ex: "Pendente,Erro") ou por status_ne (not equal).
        """
        if not self.token:
            return []
        
        params = {}
        if status:
            params['status_robo'] = status
            logging.info(f"Buscando solicitações com status: '{status}'")
        elif status_ne:
            params['status_robo_ne'] = status_ne
            logging.info(f"Buscando solicitações com status diferente de: '{status_ne}'")
        else:
            logging.info("Buscando todas as solicitações.")

        try:
            response = requests.get(
                f"{self.base_url}/solicitacoes/",
                headers=self._get_auth_headers(),
                params=params
            )
            response.raise_for_status()
            solicitacoes = response.json()
            logging.info(f"Encontradas {len(solicitacoes)} solicitações para processar.")
            return solicitacoes
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao buscar solicitações da API: {e}")
            return []

    def update_solicitacao(self, solicitacao_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Atualiza uma solicitação específica na API."""
        if not self.token:
            return None
        
        logging.info(f"Atualizando solicitação ID {solicitacao_id} com dados: {data}")
        try:
            response = requests.put(
                f"{self.base_url}/solicitacoes/{solicitacao_id}",
                headers=self._get_auth_headers(),
                json=data
            )
            response.raise_for_status()
            logging.info(f"[SUCESSO] Solicitação ID {solicitacao_id} atualizada.")
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao atualizar solicitação ID {solicitacao_id}: {e}")
            return None

