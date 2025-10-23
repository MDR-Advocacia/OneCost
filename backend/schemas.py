from pydantic import BaseModel, ConfigDict, field_validator, Field
from typing import Optional, List, Union
from datetime import date, datetime
import json
from decimal import Decimal

# --- Funções Auxiliares de Validação ---
# Função para validar e converter valor (string com vírgula/ponto ou número) para Decimal
def validate_valor_input(value: Union[str, float, Decimal, None]) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        # Arredonda para 2 casas decimais se for Decimal
        return round(value, 2)
    if isinstance(value, (float, int)):
        # Arredonda para 2 casas decimais se for float/int
        return round(Decimal(str(value)), 2)
    if isinstance(value, str):
        try:
            # Tenta converter string (aceitando ',' ou '.') para Decimal e arredonda
            cleaned_value = value.strip().replace(',', '.')
            if not cleaned_value: # String vazia vira None
                 return None
            # Verifica se o formato é válido antes de converter
            if not cleaned_value.replace('.', '', 1).isdigit():
                 raise ValueError("Formato numérico inválido")
            decimal_value = Decimal(cleaned_value)
            return round(decimal_value, 2)
        except Exception as e:
            raise ValueError(f"Valor inválido: '{value}'. Use formato numérico (ex: 1234,56). Erro: {e}")
    raise ValueError("Tipo de valor inválido")

# Função para converter Decimal para float na saída (serialização JSON)
def decimal_to_float(v: Optional[Decimal]) -> Optional[float]:
    if v is None:
        return None
    return float(v)

# --- Schema para Usuário (Base) ---
class UserBase(BaseModel):
    username: str = Field(..., min_length=3) # Adiciona validação mínima

# Schema para criação (recebe senha, permite role opcional)
class UserCreate(UserBase):
    password: str = Field(..., min_length=4) # Senha mínima de 4 caracteres
    role: str = 'user' # Default role
    is_active: bool = True # Ativo por padrão na criação

    @field_validator('role')
    @classmethod
    def role_must_be_valid(cls, v):
        if v not in ['admin', 'user']:
            raise ValueError("Role deve ser 'admin' ou 'user'")
        return v

# NOVO: Schema para atualização (campos opcionais)
class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3)
    password: Optional[str] = Field(None, min_length=4) # Senha mínima se fornecida
    role: Optional[str] = None
    is_active: Optional[bool] = None # Manter para o endpoint de status ou aqui? Vamos manter aqui por enquanto

    @field_validator('role')
    @classmethod
    def role_must_be_valid_optional(cls, v):
        if v is not None and v not in ['admin', 'user']:
            raise ValueError("Role deve ser 'admin' ou 'user'")
        return v


# Schema para exibir o usuário (resposta da API)
class User(UserBase):
    id: int
    role: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

# Schema apenas para ativar/desativar (usado pelo endpoint específico)
class UserUpdateStatus(BaseModel):
    is_active: bool

# --- Schema para Solicitação de Custa (Base) ---
class SolicitacaoCustaBase(BaseModel):
    npj: str
    numero_processo: Optional[str] = None
    numero_solicitacao: str
    # Usando float para entrada/saída API, validado na entrada
    valor: float
    data_solicitacao: date
    # Campo para indicar se usuário marcou necessidade de confirmação
    aguardando_confirmacao: bool = True

# Schema para criação (herda da base)
class SolicitacaoCustaCreate(SolicitacaoCustaBase):
    # Validador específico para o campo valor na criação
    _validate_valor: classmethod = field_validator('valor', mode='before')(validate_valor_input)

# Schema para atualização (usado pelo Robô e pelo Frontend)
class SolicitacaoCustaUpdate(BaseModel):
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    # Recebe lista de strings ou None do robô/api
    comprovantes_path: Optional[List[str]] = None
    # Recebe float ou None, validado no endpoint
    valor: Optional[float] = None
    numero_processo: Optional[str] = None
    # ID do robô que confirmou
    usuario_confirmacao_id: Optional[int] = None
    # Flags de ação (não são campos do DB)
    finalizar: Optional[bool] = None # Flag para marcar como finalizado/tratado
    arquivar: Optional[bool] = None  # Flag para arquivar/desarquivar (usado no endpoint /archive)

    # Garante que strings vazias sejam None para campos opcionais de string
    @field_validator('status_portal', 'status_robo', 'numero_processo', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        return None if isinstance(v, str) and v.strip() == "" else v

    # Validador para o campo valor na atualização (se presente)
    _validate_update_valor: classmethod = field_validator('valor', mode='before')(validate_valor_input)


# --- Schema para Solicitação de Custa (Completo - Resposta da API) ---
class SolicitacaoCusta(SolicitacaoCustaBase):
    id: int
    # ID e objeto do usuário que criou
    usuario_criacao_id: int
    usuario_criacao: User
    # Status e dados do robô
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    ultima_verificacao_robo: Optional[datetime] = None
    comprovantes_path: Optional[List[str]] = None # Deveria ser lista na resposta
    # ID e objeto do usuário (robô) que confirmou
    usuario_confirmacao_id: Optional[int] = None
    usuario_confirmacao: Optional[User] = None
    # ID e objeto do usuário que finalizou/tratou
    usuario_finalizacao_id: Optional[int] = None
    usuario_finalizacao: Optional[User] = None
    data_finalizacao: Optional[datetime] = None
    # Status de arquivamento
    is_archived: bool = False
    data_arquivamento: Optional[datetime] = None
    usuario_arquivamento_id: Optional[int] = None
    usuario_arquivamento: Optional[User] = None

    model_config = ConfigDict(from_attributes=True)

    # Validador para converter Decimal do DB para float na resposta
    _decimal_to_float: classmethod = field_validator('valor', mode='after')(decimal_to_float)

    # Validador para garantir que comprovantes_path seja sempre lista ou None na resposta
    @field_validator('comprovantes_path', mode='before')
    @classmethod
    def parse_json_string_or_list(cls, value):
        if isinstance(value, str):
            try:
                # Tenta decodificar string JSON (ex: '["path1", "path2"]')
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else None
            except json.JSONDecodeError:
                # Se for uma string simples (legado?), retorna como lista de um item
                # Ou retorna None se não for um caminho válido
                return [value] if value and '/' in value else None # Heurística simples
        # Se já for None ou List, retorna como está
        elif isinstance(value, list) or value is None:
            return value
        return None # Retorna None para outros tipos inesperados


# --- Schema para Token ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

