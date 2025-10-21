from pydantic import BaseModel
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List

# --- SCHEMAS DE USUÁRIO ---
class User(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True

# --- SCHEMAS DE SOLICITAÇÃO DE CUSTA ---

# Schema base com os campos que o usuário preenche
class SolicitacaoCustaBase(BaseModel):
    npj: str
    numero_processo: Optional[str] = None
    numero_solicitacao: str
    valor: Decimal
    data_solicitacao: date
    aguardando_confirmacao: bool = True

# Schema para a criação de uma solicitação
class SolicitacaoCustaCreate(SolicitacaoCustaBase):
    pass

# Schema para o robô atualizar uma solicitação
class SolicitacaoCustaUpdate(BaseModel):
    status_portal: Optional[str] = None
    status_robo: Optional[str] = None
    ultima_verificacao_robo: Optional[datetime] = None
    comprovantes_path: Optional[List[str]] = None

# Schema completo para exibir os dados no frontend
class SolicitacaoCusta(SolicitacaoCustaBase):
    id: int
    usuario: User
    
    # Novos campos que o robô preenche
    status_portal: Optional[str] = None
    status_robo: str
    ultima_verificacao_robo: Optional[datetime] = None
    comprovantes_path: Optional[List[str]] = None

    class Config:
        from_attributes = True

