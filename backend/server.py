from fastapi import FastAPI, Depends, HTTPException, status, Query
# NOVO: Importar Body para usar no endpoint de arquivamento
from fastapi.params import Body
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload, selectinload
from datetime import timedelta, datetime, date, timezone
from typing import List, Optional
from decimal import Decimal, InvalidOperation
import json
import logging
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import schemas
from bd import models
from bd.database import SessionLocal, engine
from auth import verify_password, create_access_token, get_password_hash # Importar get_password_hash
from config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM

from jose import JWTError, jwt
from pydantic import BaseModel

# Configura o logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

# Cria tabelas (se não existirem)
# models.Base.metadata.create_all(bind=engine)
# Nota: A criação agora é feita principalmente pelo entrypoint.sh para garantir a ordem

app = FastAPI()

# --- Configuração do CORS (Manter no início) ---
origins = [
    "http://localhost:3000",
    "http://localhost:3001", # Assume que o dashboard roda na 3001 via docker-compose
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Servir Arquivos Estáticos ---
try:
    # Caminho dentro do container Docker
    static_directory = Path("/app/static/comprovantes")
    static_directory.mkdir(parents=True, exist_ok=True)
    app.mount("/static/comprovantes", StaticFiles(directory=static_directory), name="static_comprovantes")
    log.info(f"Servindo arquivos estáticos de '{static_directory}' em '/static/comprovantes'")
except Exception as e_static:
    log.error(f"Erro CRÍTICO ao configurar arquivos estáticos: {e_static}", exc_info=True)

# --- Dependências ---
def get_db():
    """Obtém uma sessão do banco de dados."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Funções de Autenticação e Permissão ---
def get_user(db: Session, username: str) -> Optional[models.User]:
    """Busca um usuário pelo nome de usuário no banco."""
    return db.query(models.User).filter(models.User.username == username).first()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    """Obtém o usuário a partir do token JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            log.warning("[get_current_user] Token inválido: 'sub' (username) ausente.")
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError as e:
        log.warning(f"[get_current_user] Erro ao decodificar token: {e}")
        raise credentials_exception

    user = get_user(db, username=token_data.username)
    if user is None:
        log.warning(f"[get_current_user] Usuário '{token_data.username}' não encontrado no banco.")
        raise credentials_exception
    log.debug(f"[get_current_user] Usuário '{user.username}' autenticado.")
    return user

# NOVA Dependência: Verifica se o usuário está ativo
async def get_current_active_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Obtém o usuário atual e verifica se ele está ativo."""
    if not current_user.is_active:
        log.warning(f"[get_current_active_user] Tentativa de acesso por usuário inativo: '{current_user.username}'.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário inativo")
    return current_user

# NOVA Dependência: Exige que o usuário seja admin
async def require_admin_role(current_user: models.User = Depends(get_current_active_user)) -> models.User:
    """Verifica se o usuário atual tem a role 'admin'."""
    if current_user.role != 'admin':
        log.warning(f"[require_admin_role] Acesso negado para usuário '{current_user.username}' (role: {current_user.role}). Ação requer 'admin'.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão insuficiente. Apenas administradores podem realizar esta ação."
        )
    log.debug(f"[require_admin_role] Acesso admin concedido para '{current_user.username}'.")
    return current_user

# --- Rotas da API ---

@app.post("/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Realiza o login do usuário e retorna um token JWT."""
    log.info(f"[/login] Tentativa de login recebida para usuário: '{form_data.username}'")
    user = get_user(db, username=form_data.username)

    password_verified = user and verify_password(form_data.password, user.hashed_password)

    # Verifica se usuário existe, está ativo e a senha está correta
    if not user or not user.is_active or not password_verified:
        log.warning(f"[/login] Falha na autenticação para '{form_data.username}' (usuário inexistente, inativo ou senha incorreta).")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos ou usuário inativo",
            headers={"WWW-Authenticate": "Bearer"},
        )

    log.info(f"[/login] Autenticação bem-sucedida para '{form_data.username}'. Gerando token...")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


# --- Rotas de Usuário (Protegidas) ---

# Usa get_current_active_user para garantir que o usuário está logado e ativo
@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    """Retorna os dados do usuário logado e ativo."""
    return current_user

# NOVO: Criar usuário (Admin)
@app.post("/users/", response_model=schemas.User, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_role)])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db), current_admin: models.User = Depends(require_admin_role)):
    """Cria um novo usuário (apenas admin)."""
    log.info(f"[POST /users/] Admin '{current_admin.username}' criando usuário: '{user.username}' com role: '{user.role}'")
    db_user = get_user(db, username=user.username)
    if db_user:
        log.warning(f"[POST /users/] Usuário '{user.username}' já existe.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nome de usuário já registrado")
    hashed_password = get_password_hash(user.password)
    # Garante que is_active seja True na criação
    new_user = models.User(username=user.username, hashed_password=hashed_password, role=user.role, is_active=True)
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        log.info(f"[POST /users/] Usuário '{user.username}' criado com sucesso.")
        return new_user
    except Exception as e:
        log.error(f"[POST /users/] Erro ao criar usuário '{user.username}': {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao criar usuário.")

# NOVO: Listar usuários (Admin)
@app.get("/users/", response_model=List[schemas.User], dependencies=[Depends(require_admin_role)])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lista todos os usuários (apenas admin)."""
    log.info(f"[GET /users/] Admin buscando lista de usuários (skip={skip}, limit={limit}).")
    try:
        # Ordena por ID para consistência
        users = db.query(models.User).order_by(models.User.id).offset(skip).limit(limit).all()
        log.info(f"[GET /users/] Encontrados {len(users)} usuários.")
        return users
    except Exception as e:
        log.error(f"[GET /users/] Erro ao buscar usuários: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao buscar usuários.")

# NOVO: Ativar/desativar usuário (Admin)
@app.put("/users/{user_id}/status", response_model=schemas.User, dependencies=[Depends(require_admin_role)])
def update_user_status(user_id: int, status_update: schemas.UserUpdateStatus, db: Session = Depends(get_db), current_admin: models.User = Depends(require_admin_role)):
    """Ativa ou desativa um usuário (apenas admin)."""
    log.info(f"[PUT /users/{user_id}/status] Admin '{current_admin.username}' atualizando status para is_active={status_update.is_active}.")
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        log.error(f"[PUT /users/{user_id}/status] Usuário ID {user_id} não encontrado.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    # Impede desativar a si mesmo (o admin logado) e o usuário 'admin' padrão
    if db_user.id == current_admin.id and not status_update.is_active:
         log.warning(f"[PUT /users/{user_id}/status] Admin '{current_admin.username}' tentou desativar a si mesmo.")
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível desativar a si mesmo")
    if db_user.username == 'admin' and not status_update.is_active:
        log.warning(f"[PUT /users/{user_id}/status] Tentativa de desativar o usuário 'admin' bloqueada.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível desativar o usuário 'admin'")

    try:
        db_user.is_active = status_update.is_active
        db.commit()
        db.refresh(db_user)
        log.info(f"[PUT /users/{user_id}/status] Status do usuário '{db_user.username}' (ID: {user_id}) atualizado para is_active={db_user.is_active}.")
        return db_user
    except Exception as e:
        log.error(f"[PUT /users/{user_id}/status] Erro ao atualizar status do usuário ID {user_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao atualizar status do usuário.")


# --- Rotas de Solicitação de Custas (Com Permissões) ---

# Criação protegida por get_current_active_user
@app.post("/solicitacoes/", response_model=schemas.SolicitacaoCusta)
def create_solicitacao(
    solicitacao: schemas.SolicitacaoCustaCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user) # Usuário logado e ativo
):
    """Cria uma nova solicitação de custa."""
    log.info(f"[POST /solicitacoes/] Recebida nova solicitação para NPJ {solicitacao.npj} do usuário '{current_user.username}' (ID: {current_user.id})")
    try:
        # O schema já validou e converteu para Decimal
        valor_decimal = solicitacao.valor

        db_solicitacao = models.SolicitacaoCusta(
            npj=solicitacao.npj,
            numero_processo=solicitacao.numero_processo,
            numero_solicitacao=solicitacao.numero_solicitacao,
            valor=valor_decimal,
            data_solicitacao=solicitacao.data_solicitacao,
            aguardando_confirmacao=solicitacao.aguardando_confirmacao,
            usuario_criacao_id=current_user.id, # Associa ao usuário logado
            status_robo="Pendente",
            status_portal=None,
            is_archived=False # Garante que não comece arquivada
        )
        db.add(db_solicitacao)
        db.commit()
        db.refresh(db_solicitacao)

        # Recarrega com relacionamentos para retornar dados completos
        # Usa db.get() que é mais direto para buscar por PK
        db_solicitacao_com_rel = db.query(models.SolicitacaoCusta).options(
                selectinload(models.SolicitacaoCusta.usuario_criacao) # Usar selectinload pode ser melhor aqui
            ).filter(models.SolicitacaoCusta.id == db_solicitacao.id).first()

        log.info(f"[POST /solicitacoes/] Solicitação ID {db_solicitacao.id} criada com sucesso.")
        # Retorna o objeto com relacionamento carregado
        return db_solicitacao_com_rel if db_solicitacao_com_rel else db_solicitacao

    except ValueError as ve: # Captura erro de validação do schema
        log.error(f"[POST /solicitacoes/] Erro de validação ao criar solicitação: {ve}", exc_info=False) # Não loga stack trace completo
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Erro nos dados fornecidos: {ve}")
    except Exception as e:
        log.error(f"[POST /solicitacoes/] Erro interno ao criar solicitação: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao salvar solicitação.")


# Leitura com filtro de arquivamento e permissão para incluir arquivadas
@app.get("/solicitacoes/", response_model=List[schemas.SolicitacaoCusta])
async def read_solicitacoes(
    skip: int = 0,
    limit: int = 100,
    status_robo: Optional[str] = Query(None, description="Filtrar por status do robô (ex: Pendente,Finalizado)"),
    status_robo_ne: Optional[str] = Query(None, description="Excluir status do robô (ex: Erro)"),
    include_archived: bool = Query(False, description="Incluir solicitações arquivadas na lista (apenas admin)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user) # Usuário precisa estar ativo
):
    """Lista solicitações. Por padrão, apenas as não arquivadas. Para incluir arquivadas, requer role admin."""
    log.info(f"[GET /solicitacoes/] Buscando solicitações: skip={skip}, limit={limit}, status_robo={status_robo}, include_archived={include_archived} por usuário '{current_user.username}'")

    # Verifica permissão para incluir arquivadas
    if include_archived and current_user.role != 'admin':
        log.warning(f"[GET /solicitacoes/] Usuário '{current_user.username}' (role='{current_user.role}') tentou incluir arquivadas sem permissão.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas administradores podem visualizar solicitações arquivadas."
        )

    try:
        query = db.query(models.SolicitacaoCusta).options(
            # Carrega relacionamentos de usuário eficientemente
            selectinload(models.SolicitacaoCusta.usuario_criacao),
            selectinload(models.SolicitacaoCusta.usuario_confirmacao),
            selectinload(models.SolicitacaoCusta.usuario_finalizacao),
            selectinload(models.SolicitacaoCusta.usuario_arquivamento),
        )

        # Filtro de status_robo (se fornecido)
        if status_robo:
            status_list = [status.strip() for status in status_robo.split(',') if status.strip()]
            if status_list:
                query = query.filter(models.SolicitacaoCusta.status_robo.in_(status_list))

        # Filtro de status_robo_ne (se fornecido)
        if status_robo_ne:
            status_list_ne = [status.strip() for status in status_robo_ne.split(',') if status.strip()]
            if status_list_ne:
                query = query.filter(models.SolicitacaoCusta.status_robo.notin_(status_list_ne))

        # Filtro de arquivamento (padrão ou baseado no parâmetro e permissão)
        if not include_archived:
            query = query.filter(models.SolicitacaoCusta.is_archived == False)

        solicitacoes = query.order_by(models.SolicitacaoCusta.id.desc()).offset(skip).limit(limit).all()
        log.info(f"[GET /solicitacoes/] Encontradas {len(solicitacoes)} solicitações.")
        return solicitacoes
    except Exception as e:
        log.error(f"[GET /solicitacoes/] Erro ao buscar solicitações: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao buscar solicitações.")


# Atualização protegida por get_current_active_user
@app.put("/solicitacoes/{id}", response_model=schemas.SolicitacaoCusta)
def update_solicitacao(
    id: int,
    solicitacao_update: schemas.SolicitacaoCustaUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user) # Usuário logado e ativo
):
    """Atualiza uma solicitação (usado pelo robô ou para marcar como finalizada)."""
    log.info(f"[PUT /solicitacoes/{id}] Recebida atualização por usuário '{current_user.username}' (ID: {current_user.id})")

    # Carrega com relacionamentos para poder retornar dados completos
    db_solicitacao = db.query(models.SolicitacaoCusta).options(
        selectinload(models.SolicitacaoCusta.usuario_criacao),
        selectinload(models.SolicitacaoCusta.usuario_confirmacao),
        selectinload(models.SolicitacaoCusta.usuario_finalizacao),
        selectinload(models.SolicitacaoCusta.usuario_arquivamento),
    ).filter(models.SolicitacaoCusta.id == id).first()

    if db_solicitacao is None:
        log.error(f"[PUT /solicitacoes/{id}] Solicitação não encontrada.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitação não encontrada")

    # Verifica se a solicitação está arquivada antes de permitir certas alterações
    if db_solicitacao.is_archived:
        # Permite apenas desarquivar via endpoint /archive
        if solicitacao_update.finalizar:
             log.warning(f"[PUT /solicitacoes/{id}] Tentativa de finalizar solicitação já arquivada.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível finalizar uma solicitação arquivada.")
        # Adicionar outras verificações se necessário (ex: impedir robô de alterar solicitação arquivada)
        log.warning(f"[PUT /solicitacoes/{id}] Tentativa de modificar solicitação arquivada (exceto por desarquivamento via /archive).")
        # Poderia retornar 400, mas vamos apenas logar por enquanto e não aplicar mudanças abaixo
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solicitação arquivada não pode ser modificada.")


    # model_dump substitui dict() em Pydantic v2
    update_data = solicitacao_update.model_dump(exclude_unset=True, exclude={'finalizar', 'arquivar'}) # Exclui flags de ação
    log.debug(f"[PUT /solicitacoes/{id}] Dados recebidos para atualização (sem flags): {update_data}")
    log.debug(f"[PUT /solicitacoes/{id}] Flags de ação: finalizar={solicitacao_update.finalizar}, arquivar={solicitacao_update.arquivar}")

    # Adiciona carimbo de data/hora apenas se for atualização do robô (status_robo presente)
    if 'status_robo' in update_data:
        update_data["ultima_verificacao_robo"] = datetime.now(timezone.utc)

    try:
        updated = False
        # Aplica atualizações dos dados recebidos (exceto flags e id)
        for key, value in update_data.items():
            current_value = getattr(db_solicitacao, key, None)

            # Lógica específica para campos que não devem ser sobrescritos ou têm condições
            if key == 'valor' and value is not None:
                if isinstance(value, Decimal):
                    if db_solicitacao.valor != value:
                        setattr(db_solicitacao, key, value)
                        updated = True
                else: log.warning(f"Ignorando atualização de valor inválido: {value}")
                continue # Pula para o próximo item do loop

            elif key == 'numero_processo':
                if value and not db_solicitacao.numero_processo: # Só preenche se estiver vazio
                    setattr(db_solicitacao, key, value)
                    updated = True
                elif value: log.info(f"Ignorando atualização de numero_processo (já preenchido): {db_solicitacao.numero_processo}")
                continue

            elif key == 'usuario_confirmacao_id':
                if value is not None and db_solicitacao.usuario_confirmacao_id is None: # Só preenche se estiver vazio
                    setattr(db_solicitacao, key, value)
                    updated = True
                elif value is not None: log.info(f"Ignorando atualização de usuario_confirmacao_id (já preenchido)")
                continue

            # Para outros campos, atualiza se o valor for diferente
            if current_value != value:
                 setattr(db_solicitacao, key, value)
                 updated = True

        # Lógica para finalizar (marcar como tratado) - APENAS se não estiver arquivado
        if not db_solicitacao.is_archived:
            if solicitacao_update.finalizar is True and db_solicitacao.usuario_finalizacao_id is None:
                log.info(f"[PUT /solicitacoes/{id}] Usuário '{current_user.username}' marcando solicitação como finalizada/tratada.")
                db_solicitacao.usuario_finalizacao_id = current_user.id
                db_solicitacao.data_finalizacao = datetime.now(timezone.utc)
                updated = True
            elif solicitacao_update.finalizar is False and db_solicitacao.usuario_finalizacao_id is not None:
                 # Permite desfazer, mas apenas se o próprio usuário finalizou (ou admin?) - Simplificado: qualquer um pode desfazer por enquanto
                 log.info(f"[PUT /solicitacoes/{id}] Usuário '{current_user.username}' desmarcando solicitação como finalizada/tratada.")
                 db_solicitacao.usuario_finalizacao_id = None
                 db_solicitacao.data_finalizacao = None
                 updated = True

        if updated:
            db.commit()
            db.refresh(db_solicitacao) # Atualiza o objeto db_solicitacao com dados do DB
            log.info(f"[PUT /solicitacoes/{id}] Solicitação atualizada com sucesso.")
        else:
            log.info(f"[PUT /solicitacoes/{id}] Nenhuma alteração aplicada.")

        # Retorna o objeto atualizado (com relacionamentos já carregados)
        return db_solicitacao
    except Exception as e:
         log.error(f"[PUT /solicitacoes/{id}] Erro ao atualizar solicitação: {e}", exc_info=True)
         db.rollback()
         raise HTTPException(status_code=500, detail="Erro interno ao atualizar solicitação.")


# NOVO: Endpoint para arquivar/desarquivar solicitação (Admin)
@app.put("/solicitacoes/{id}/archive", response_model=schemas.SolicitacaoCusta, dependencies=[Depends(require_admin_role)])
def archive_solicitacao(
    id: int,
    # Recebe o status desejado no corpo da requisição { "is_archived": true/false }
    archive_status_body: schemas.SolicitacaoCustaUpdate = Body(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin_role)
):
    """Arquiva ou desarquiva uma solicitação (apenas admin)."""
    archive_status = archive_status_body.arquivar # Pega o valor da flag 'arquivar'
    if archive_status is None:
         raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Campo 'arquivar' (true/false) é obrigatório no corpo da requisição.")

    log.info(f"[PUT /solicitacoes/{id}/archive] Admin '{current_user.username}' definindo is_archived={archive_status}.")

    # Carrega com relacionamentos para poder retornar dados completos
    db_solicitacao = db.query(models.SolicitacaoCusta).options(
        selectinload(models.SolicitacaoCusta.usuario_criacao),
        selectinload(models.SolicitacaoCusta.usuario_confirmacao),
        selectinload(models.SolicitacaoCusta.usuario_finalizacao),
        selectinload(models.SolicitacaoCusta.usuario_arquivamento),
    ).filter(models.SolicitacaoCusta.id == id).first()

    if db_solicitacao is None:
        log.error(f"[PUT /solicitacoes/{id}/archive] Solicitação não encontrada.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitação não encontrada")

    if db_solicitacao.is_archived == archive_status:
        log.info(f"[PUT /solicitacoes/{id}/archive] Solicitação já está no estado desejado (is_archived={archive_status}). Nenhuma alteração.")
        return db_solicitacao # Retorna o estado atual

    try:
        db_solicitacao.is_archived = archive_status
        now = datetime.now(timezone.utc)
        if archive_status: # Arquivando
            db_solicitacao.data_arquivamento = now
            db_solicitacao.usuario_arquivamento_id = current_user.id
            log.info(f"[PUT /solicitacoes/{id}/archive] Arquivando solicitação.")
        else: # Desarquivando
            db_solicitacao.data_arquivamento = None
            db_solicitacao.usuario_arquivamento_id = None
            log.info(f"[PUT /solicitacoes/{id}/archive] Desarquivando solicitação.")

        db.commit()
        db.refresh(db_solicitacao) # Atualiza o objeto db_solicitacao
        log.info(f"[PUT /solicitacoes/{id}/archive] Status de arquivamento atualizado para {db_solicitacao.is_archived}.")
        return db_solicitacao
    except Exception as e:
         log.error(f"[PUT /solicitacoes/{id}/archive] Erro ao atualizar status de arquivamento: {e}", exc_info=True)
         db.rollback()
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao arquivar/desarquivar solicitação.")


# Rota de reset (protegida por admin)
@app.post("/solicitacoes/resetar-erros", status_code=status.HTTP_200_OK, dependencies=[Depends(require_admin_role)])
def resetar_status_erro(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_admin_role) # Garante que apenas admin possa resetar
):
    """Reseta o status de solicitações com erro para 'Pendente' (apenas admin)."""
    log.info(f"[POST /solicitacoes/resetar-erros] Admin '{current_user.username}' solicitou reset de status de erro.")
    try:
        # Define os valores a serem atualizados
        values_to_update = {
            'status_robo': 'Pendente',
            'ultima_verificacao_robo': None,
            'status_portal': None,
            'usuario_confirmacao_id': None, # Limpa confirmação se houve erro
            # Não limpa finalização ou arquivamento
        }
        # Constrói a query de update
        stmt = (
            update(models.SolicitacaoCusta)
            .where(models.SolicitacaoCusta.status_robo.like('%Erro%'))
            .values(**values_to_update)
            # Retorna os IDs das linhas afetadas (opcional, mas útil para log)
            .returning(models.SolicitacaoCusta.id)
        )
        result = db.execute(stmt)
        updated_ids = result.scalars().all() # Pega todos os IDs que foram atualizados
        db.commit()
        count = len(updated_ids)
        log.info(f"[POST /solicitacoes/resetar-erros] {count} solicitações com erro foram resetadas para 'Pendente'. IDs: {updated_ids}")
        return {"message": f"{count} solicitações com erro foram resetadas para 'Pendente'."}
    except Exception as e:
        log.error(f"[POST /solicitacoes/resetar-erros] Erro ao resetar status de erro: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao resetar status.")

# Health check (público)
@app.get("/health")
def health_check():
    """Verifica se a API está online."""
    return {"status": "ok"}

