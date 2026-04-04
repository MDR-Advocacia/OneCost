from sqlalchemy import Column, Integer, String, Boolean, Date, Numeric, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime, timezone # Importar timezone

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default='user', nullable=False) # 'admin' ou 'user'
    is_active = Column(Boolean, default=True, nullable=False)
    setor = Column(String, nullable=True, index=True)
    auth_provider = Column(String, default='local', nullable=False)

    # Relacionamentos
    solicitacoes_criadas = relationship("SolicitacaoCusta", back_populates="usuario_criacao", foreign_keys="[SolicitacaoCusta.usuario_criacao_id]")
    solicitacoes_confirmadas = relationship("SolicitacaoCusta", back_populates="usuario_confirmacao", foreign_keys="[SolicitacaoCusta.usuario_confirmacao_id]")
    solicitacoes_finalizadas = relationship("SolicitacaoCusta", back_populates="usuario_finalizacao", foreign_keys="[SolicitacaoCusta.usuario_finalizacao_id]")
    solicitacoes_arquivadas = relationship("SolicitacaoCusta", back_populates="usuario_arquivamento", foreign_keys="[SolicitacaoCusta.usuario_arquivamento_id]")


class SolicitacaoCusta(Base):
    __tablename__ = "solicitacoes_custas"

    id = Column(Integer, primary_key=True, index=True)
    npj = Column(String, index=True, nullable=False)
    numero_processo = Column(String, index=True, nullable=True) # Número CNJ
    numero_solicitacao = Column(String, nullable=False) # Número da solicitação no portal
    valor = Column(Numeric(10, 2), nullable=False)
    data_solicitacao = Column(Date, nullable=False)
    aguardando_confirmacao = Column(Boolean, default=True) # Se usuário marcou
    setor_criacao = Column(String, nullable=True, index=True)

    # --- CAMPO ESPECIFICAÇÃO ADICIONADO ---
    especificacao = Column(String, nullable=True) # Ex: "Custas iniciais"

    # --- CAMPOS DO ROBÔ ---
    status_portal = Column(String, nullable=True)
    status_robo = Column(String, default="Pendente", nullable=False)
    ultima_verificacao_robo = Column(DateTime, nullable=True)
    prazo_fatal_em = Column(DateTime(timezone=True), nullable=True, index=True)
    proxima_verificacao_em = Column(DateTime(timezone=True), nullable=True, index=True)
    alerta_enviado_em = Column(DateTime(timezone=True), nullable=True)
    acao_apos_alerta = Column(String, nullable=True)
    monitoramento_ativo = Column(Boolean, default=True, nullable=False)
    motivo_encerramento = Column(String, nullable=True)
    comprovantes_path = Column(JSON, nullable=True) # Lista de caminhos relativos

    # --- CAMPOS DE RASTREABILIDADE ---
    usuario_criacao_id = Column(Integer, ForeignKey("users.id"), nullable=False) # Quem criou no OneCost
    usuario_confirmacao_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Robô que confirmou
    usuario_finalizacao_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Usuário que marcou como tratado
    data_finalizacao = Column(DateTime(timezone=True), nullable=True) # Quando foi marcado como tratado (com timezone)

    # --- CAMPOS DE ARQUIVAMENTO ---
    is_archived = Column(Boolean, default=False, nullable=False, index=True) # Para arquivar
    data_arquivamento = Column(DateTime(timezone=True), nullable=True) # Com timezone
    usuario_arquivamento_id = Column(Integer, ForeignKey("users.id"), nullable=True) # Admin que arquivou

    # --- Relacionamentos ---
    usuario_criacao = relationship("User", back_populates="solicitacoes_criadas", foreign_keys=[usuario_criacao_id])
    usuario_confirmacao = relationship("User", back_populates="solicitacoes_confirmadas", foreign_keys=[usuario_confirmacao_id])
    usuario_finalizacao = relationship("User", back_populates="solicitacoes_finalizadas", foreign_keys=[usuario_finalizacao_id])
    usuario_arquivamento = relationship("User", back_populates="solicitacoes_arquivadas", foreign_keys=[usuario_arquivamento_id])
