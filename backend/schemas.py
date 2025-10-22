from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import date, datetime

# --- Schema para Solicitação de Custa (Base) ---
# Campos que o usuário envia ao criar
class SolicitacaoCustaBase(BaseModel):
    npj: str
    numero_processo: Optional[str] = None
    numero_solicitacao: str
    valor: float
    data_solicitacao: date
    aguardando_confirmacao: bool = True

# Schema para criação (herda da base)
class SolicitacaoCustaCreate(SolicitacaoCustaBase):
    pass

# Schema para atualização (usado pelo Robô)
# Todos os campos são opcionais, pois o robô pode atualizar só o status ou só os comprovantes
class SolicitacaoCustaUpdate(BaseModel):
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    comprovantes_path: Optional[str] = None
    valor: Optional[float] = None # Robô pode corrigir o valor se necessário

# --- Schema para Usuário (Base) ---
class UserBase(BaseModel):
    username: str

class UserCreate(UserBase):
    password: str

# Schema para exibir o usuário (sem a senha)
class User(UserBase):
    id: int
    # Configuração para ler o modelo do SQLAlchemy
    model_config = ConfigDict(from_attributes=True)


# --- Schema para Solicitação de Custa (Completo) ---
# Campos que são lidos da API (inclui dados do robô e do usuário)
class SolicitacaoCusta(SolicitacaoCustaBase):
    id: int
    usuario_id: int
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    ultima_verificacao_robo: Optional[datetime] = None
    comprovantes_path: Optional[str] = None
    
    # Aninha o schema do usuário para mostrar quem criou
    usuario: User 

    # Configuração para ler o modelo do SQLAlchemy
    model_config = ConfigDict(from_attributes=True)


# --- Schema para Token (ESSENCIAL PARA O LOGIN) ---
# Esta é a classe que estava faltando
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

