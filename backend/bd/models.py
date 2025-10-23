from sqlalchemy import Column, Integer, String, Boolean, Date, Numeric, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    solicitacoes = relationship("SolicitacaoCusta", back_populates="usuario")

class SolicitacaoCusta(Base):
    __tablename__ = "solicitacoes_custas"

    id = Column(Integer, primary_key=True, index=True)
    npj = Column(String, index=True, nullable=False)
    # Permitir que seja nulo inicialmente, pois o robô vai preencher
    numero_processo = Column(String, index=True, nullable=True) 
    numero_solicitacao = Column(String, nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    data_solicitacao = Column(Date, nullable=False)
    aguardando_confirmacao = Column(Boolean, default=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # --- CAMPOS DO ROBÔ ---
    status_portal = Column(String, nullable=True, default="Aguardando Robô") # Status inicial
    status_robo = Column(String, default="Pendente", nullable=False) # Status inicial
    ultima_verificacao_robo = Column(DateTime, nullable=True)
    # ALTERAÇÃO: Usar JSON para armazenar a lista de caminhos
    comprovantes_path = Column(JSON, nullable=True) 

    usuario = relationship("User", back_populates="solicitacoes")
