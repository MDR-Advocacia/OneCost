from sqlalchemy import Column, Integer, String, Boolean, Date, Numeric, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship # Importar relationship
from .database import Base
# Remover import datetime daqui se não for usado diretamente para default
# from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    # Relacionamentos para buscar solicitações por usuário
    solicitacoes_criadas = relationship(
        "SolicitacaoCusta",
        foreign_keys="[SolicitacaoCusta.usuario_criacao_id]",
        back_populates="usuario_criacao"
    )
    solicitacoes_confirmadas = relationship(
        "SolicitacaoCusta",
        foreign_keys="[SolicitacaoCusta.usuario_confirmacao_id]",
        back_populates="usuario_confirmacao"
    )
    solicitacoes_finalizadas = relationship(
        "SolicitacaoCusta",
        foreign_keys="[SolicitacaoCusta.usuario_finalizacao_id]",
        back_populates="usuario_finalizacao"
    )


class SolicitacaoCusta(Base):
    __tablename__ = "solicitacoes_custas"

    id = Column(Integer, primary_key=True, index=True)
    npj = Column(String, index=True, nullable=False)
    numero_processo = Column(String, index=True, nullable=True) # Robô preenche se vazio
    numero_solicitacao = Column(String, nullable=False)
    valor = Column(Numeric(10, 2), nullable=False) # Armazenar como Numeric no DB
    data_solicitacao = Column(Date, nullable=False)
    aguardando_confirmacao = Column(Boolean, default=True) # Indica se o usuário marcou que precisa de confirmação

    # --- CAMPOS DO ROBÔ ---
    status_portal = Column(String, nullable=True) # Status lido do portal BB
    status_robo = Column(String, default="Pendente", nullable=False) # Status interno do robô
    ultima_verificacao_robo = Column(DateTime, nullable=True) # Data da última ação/verificação do robô
    comprovantes_path = Column(JSON, nullable=True) # Lista de caminhos relativos

    # --- CAMPOS DE RASTREABILIDADE ---
    usuario_criacao_id = Column(Integer, ForeignKey("users.id"), nullable=False) # Quem cadastrou no OneCost
    usuario_confirmacao_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Quem confirmou (geralmente o robô)
    usuario_finalizacao_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Quem marcou como finalizado/tratado
    data_finalizacao = Column(DateTime, nullable=True) # Quando foi finalizado

    # --- RELACIONAMENTOS ---
    usuario_criacao = relationship(
        "User",
        foreign_keys=[usuario_criacao_id],
        back_populates="solicitacoes_criadas"
    )
    usuario_confirmacao = relationship(
        "User",
        foreign_keys=[usuario_confirmacao_id],
        back_populates="solicitacoes_confirmadas"
    )
    usuario_finalizacao = relationship(
        "User",
        foreign_keys=[usuario_finalizacao_id],
        back_populates="solicitacoes_finalizadas"
    )

