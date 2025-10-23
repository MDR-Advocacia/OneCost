from pydantic import BaseModel, ConfigDict, field_validator # Adicionado field_validator
from typing import Optional, List
from datetime import date, datetime
import json # Adicionado json

# --- Schema para Solicitação de Custa (Base) ---
class SolicitacaoCustaBase(BaseModel):
    npj: str
    numero_processo: Optional[str] = None
    numero_solicitacao: str
    valor: float # Mantido como float para entrada/saída API, convertido no backend
    data_solicitacao: date
    aguardando_confirmacao: bool = True

# Schema para criação (herda da base)
class SolicitacaoCustaCreate(SolicitacaoCustaBase):
    pass

# Schema para atualização (usado pelo Robô)
class SolicitacaoCustaUpdate(BaseModel):
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    # CORREÇÃO: Deve ser uma lista de strings
    comprovantes_path: Optional[List[str]] = None
    valor: Optional[float] = None # Robô pode corrigir o valor se necessário
    numero_processo: Optional[str] = None # Permitir que robô atualize nº processo

    # Garante que campos vazios sejam None
    @field_validator('status_portal', 'status_robo', 'numero_processo', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v

# --- Schema para Usuário (Base) ---
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

# Schema para exibir o usuário (sem a senha)
class User(UserBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# --- Schema para Solicitação de Custa (Completo - Resposta da API) ---
class SolicitacaoCusta(SolicitacaoCustaBase):
    id: int
    usuario_id: int
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    ultima_verificacao_robo: Optional[datetime] = None
    # CORREÇÃO: Deve ser uma lista de strings ou None
    comprovantes_path: Optional[List[str]] = None

    usuario: User

    model_config = ConfigDict(from_attributes=True)

    # Adicionado validador para garantir que o JSON do banco seja convertido para lista
    @field_validator('comprovantes_path', mode='before')
    @classmethod
    def parse_json_string(cls, value):
        if isinstance(value, str):
            try:
                # Tenta decodificar string JSON (ex: '["path1", "path2"]')
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
                # Se não for uma lista após parse, retorna None ou trata como erro
                return None
            except json.JSONDecodeError:
                # Se for uma string simples (legado?), retorna como lista de um item
                # Ou retorna None se não for um caminho válido
                # Ajuste essa lógica se necessário
                return [value] if value else None
        # Se já for None ou List, retorna como está
        return value

# --- Schema para Token ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

