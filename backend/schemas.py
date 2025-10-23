from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Union # Adicionado Union
from datetime import date, datetime
import json
from decimal import Decimal, InvalidOperation # Importar Decimal e InvalidOperation

# --- Schema para Usuário (Base) ---
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

# Schema para exibir o usuário (sem a senha)
class User(UserBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


# --- Schema para Solicitação de Custa (Base) ---
class SolicitacaoCustaBase(BaseModel):
    npj: str
    numero_processo: Optional[str] = None
    numero_solicitacao: str
    # Aceita float na entrada, mas valida como Decimal internamente
    valor: Union[float, Decimal, str]
    data_solicitacao: date
    # Campo que o usuário informa se a solicitação criada no BB precisará de confirmação
    aguardando_confirmacao: bool = True

    # Validador para garantir que o valor seja um Decimal válido na ENTRADA
    @field_validator('valor', mode='before')
    @classmethod
    def validate_valor_input(cls, v):
        if isinstance(v, (float, int, Decimal)):
            try:
                # Converte para string para evitar imprecisão de float
                return Decimal(str(v))
            except InvalidOperation:
                raise ValueError("Valor numérico inválido")
        if isinstance(v, str):
            try:
                # Tenta limpar string (ex: "1.234,56" ou "1234.56")
                cleaned_v = v.replace(".", "").replace(",", ".")
                if not cleaned_v: # Handle empty string after cleaning
                    raise ValueError("String de valor vazia")
                return Decimal(cleaned_v)
            except InvalidOperation:
                raise ValueError(f"String de valor inválida: '{v}'")
        raise ValueError("Tipo de valor inválido")

# Schema para criação (herda da base)
class SolicitacaoCustaCreate(SolicitacaoCustaBase):
    pass

# Schema para atualização (usado pelo Robô e pelo Frontend para finalizar)
class SolicitacaoCustaUpdate(BaseModel):
    # Campos que o robô pode atualizar
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    comprovantes_path: Optional[List[str]] = None
    # Aceita float/str, valida como Decimal
    valor: Optional[Union[float, Decimal, str]] = None
    numero_processo: Optional[str] = None # Robô pode preencher
    usuario_confirmacao_id: Optional[int] = None # Robô informa quem confirmou

    # Campos/Flags para finalização pelo usuário no frontend
    finalizar: Optional[bool] = None # Flag para indicar ação de finalização

    # Garante que campos string vazios sejam None
    @field_validator('status_portal', 'status_robo', 'numero_processo', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        return None if v == "" else v

    # Validador para valor na atualização (usa a mesma lógica da base)
    @field_validator('valor', mode='before')
    @classmethod
    def validate_update_valor(cls, v):
        if v is None:
            return None # Permite não enviar o valor
        try:
            # Reutiliza validador da base para consistência
            return SolicitacaoCustaBase.validate_valor_input(v)
        except ValueError:
            # Se a validação falhar, retorna None para ignorar a atualização deste campo
            return None


# --- Schema para Solicitação de Custa (Completo - Resposta da API) ---
class SolicitacaoCusta(SolicitacaoCustaBase):
    id: int
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    ultima_verificacao_robo: Optional[datetime] = None
    comprovantes_path: Optional[List[str]] = None

    # Campos de rastreabilidade
    usuario_criacao_id: int # Renomeado de usuario_id
    usuario_confirmacao_id: Optional[int] = None
    usuario_finalizacao_id: Optional[int] = None
    data_finalizacao: Optional[datetime] = None

    # Relacionamentos para exibir nomes de usuário
    usuario_criacao: Optional[User] = None # Quem criou no OneCost (Optional para evitar erro se não carregado)
    usuario_confirmacao: Optional[User] = None # Quem confirmou (robô)
    usuario_finalizacao: Optional[User] = None # Quem finalizou (humano)

    # Permitir carregar dos atributos do modelo SQLAlchemy
    model_config = ConfigDict(from_attributes=True)

    # Validador para converter JSON do banco para lista Python
    @field_validator('comprovantes_path', mode='before')
    @classmethod
    def parse_json_string(cls, value):
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    # Garante que todos os itens sejam strings
                    return [str(item) for item in parsed]
                return None # Retorna None se não for lista
            except json.JSONDecodeError:
                # Considera string simples como lista de um item
                return [value] if value else None
        # Se já for None ou List, retorna como está (garante strings na lista)
        if isinstance(value, list):
            return [str(item) for item in value]
        return value

    # Validador para garantir que o valor Decimal seja convertido para float na SAÍDA da API
    @field_validator('valor', mode='after') # <<< MUDANÇA AQUI: mode='after'
    @classmethod
    def decimal_to_float(cls, v):
        if isinstance(v, Decimal):
            return float(v)
        # Se já for float (ex: vindo de SolicitacaoCustaBase), retorna como está
        return v

# --- Schema para Token ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

