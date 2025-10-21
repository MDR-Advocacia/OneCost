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
    numero_processo = Column(String, index=True, nullable=True)
    numero_solicitacao = Column(String, nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    data_solicitacao = Column(Date, nullable=False)
    aguardando_confirmacao = Column(Boolean, default=True)
    usuario_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # --- NOVOS CAMPOS PARA O ROBÔ ---
    status_portal = Column(String, nullable=True)
    status_robo = Column(String, default="Pendente", nullable=False)
    ultima_verificacao_robo = Column(DateTime, nullable=True)
    comprovantes_path = Column(JSON, nullable=True) # Armazenará uma lista de caminhos

    usuario = relationship("User", back_populates="solicitacoes")

