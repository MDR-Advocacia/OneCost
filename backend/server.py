from fastapi import FastAPI, Depends, HTTPException, status, Query, Body
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy import update
from sqlalchemy.orm import Session, joinedload, selectinload
from datetime import timedelta, datetime, date, timezone
from typing import List, Optional
from decimal import Decimal, InvalidOperation
import json
import logging
from pathlib import Path
import re # Importar re para regex no CORS

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import schemas
from bd import models
from bd.database import SessionLocal, engine
from auth import verify_password, create_access_token, get_password_hash
from config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM

from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError

# Configura o logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

app = FastAPI()

# --- Configuração do CORS ---
# Permite localhost e IPs na rede 192.168.50.x na porta 3001
cors_regex = r"http://(localhost|127\.0\.0\.1|192\.168\.50\.\d{1,3}):3001"
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=cors_regex, # Usa regex
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
log.info(f"CORS configurado para permitir regex: {cors_regex}")

# --- Servir Arquivos Estáticos ---
try:
    static_directory = Path("/app/static/comprovantes")
    static_directory.mkdir(parents=True, exist_ok=True)
    app.mount("/static/comprovantes", StaticFiles(directory=static_directory), name="static_comprovantes")
    log.info(f"Servindo arquivos estáticos de '{static_directory}' em '/static/comprovantes'")
except Exception as e_static:
    log.error(f"Erro CRÍTICO ao configurar arquivos estáticos: {e_static}", exc_info=True)

# --- Dependências ---
def get_db():
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
    return db.query(models.User).filter(models.User.username == username).first()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    user = get_user(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário inativo")
    return current_user

async def require_admin_role(current_user: models.User = Depends(get_current_active_user)) -> models.User:
    if current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permissão insuficiente. Apenas administradores podem realizar esta ação."
        )
    return current_user

# --- Rotas da API ---

@app.post("/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    log.info(f"[/login] Tentativa de login para usuário: '{form_data.username}'")
    user = get_user(db, username=form_data.username)
    password_verified = user and verify_password(form_data.password, user.hashed_password)
    if not user or not user.is_active or not password_verified:
        log.warning(f"[/login] Falha na autenticação para '{form_data.username}'.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos ou usuário inativo",
            headers={"WWW-Authenticate": "Bearer"},
        )
    log.info(f"[/login] Autenticação OK para '{form_data.username}'. Gerando token...")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# --- Rotas de Usuário (Protegidas por Admin, exceto /me) ---

@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    """Retorna os dados do usuário logado e ativo."""
    return current_user

@app.post("/users/", response_model=schemas.User, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_role)])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db), current_admin: models.User = Depends(require_admin_role)):
    """Cria um novo usuário (apenas admin)."""
    log.info(f"[POST /users/] Admin '{current_admin.username}' criando usuário: '{user.username}' (role: '{user.role}')")
    db_user = get_user(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nome de usuário já registrado")
    hashed_password = get_password_hash(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_password, role=user.role, is_active=True)
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        log.info(f"[POST /users/] Usuário '{user.username}' criado com sucesso.")
        return new_user
    except Exception as e:
        db.rollback()
        log.error(f"[POST /users/] Erro interno ao criar usuário: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao criar usuário: {e}")

@app.get("/users/", response_model=List[schemas.User], dependencies=[Depends(require_admin_role)])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Lista todos os usuários (apenas admin)."""
    log.info(f"[GET /users/] Admin buscando lista de usuários.")
    try:
        users = db.query(models.User).order_by(models.User.id).offset(skip).limit(limit).all()
        return users
    except Exception as e:
        log.error(f"[GET /users/] Erro interno ao buscar usuários: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao buscar usuários: {e}")

@app.put("/users/{user_id}/status", response_model=schemas.User, dependencies=[Depends(require_admin_role)])
def update_user_status(user_id: int, status_update: schemas.UserUpdateStatus, db: Session = Depends(get_db), current_admin: models.User = Depends(require_admin_role)):
    """Ativa ou desativa um usuário (apenas admin)."""
    log.info(f"[PUT /users/{user_id}/status] Admin '{current_admin.username}' atualizando status para is_active={status_update.is_active}.")
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")
    if db_user.id == current_admin.id and not status_update.is_active:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível desativar a si mesmo")
    if db_user.username == 'admin' and not status_update.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível desativar o usuário 'admin'")
    try:
        db_user.is_active = status_update.is_active
        db.commit()
        db.refresh(db_user)
        log.info(f"[PUT /users/{user_id}/status] Status do usuário '{db_user.username}' atualizado para is_active={db_user.is_active}.")
        return db_user
    except Exception as e:
        db.rollback()
        log.error(f"[PUT /users/{user_id}/status] Erro interno ao atualizar status: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao atualizar status: {e}")

@app.put("/users/{user_id}", response_model=schemas.User, dependencies=[Depends(require_admin_role)])
def update_user(user_id: int, user_update: schemas.UserUpdate, db: Session = Depends(get_db), current_admin: models.User = Depends(require_admin_role)):
    """Atualiza dados de um usuário (username, password opcional, role) - Apenas Admin."""
    log.info(f"[PUT /users/{user_id}] Admin '{current_admin.username}' tentando atualizar usuário ID {user_id}.")

    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado")

    update_data = user_update.model_dump(exclude_unset=True) # Pega apenas os campos enviados
    log.debug(f"[PUT /users/{user_id}] Dados recebidos para atualização: {update_data}")

    if not update_data:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nenhum dado fornecido para atualização.")

    updated = False
    try:
        # Atualiza Username (se fornecido e diferente, e não for o user 'admin')
        if 'username' in update_data and update_data['username'] != db_user.username:
            new_username = update_data['username']
            if db_user.username == 'admin':
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível renomear o usuário 'admin'.")
            existing_user = get_user(db, username=new_username)
            if existing_user and existing_user.id != user_id: # Verifica se o novo username já existe em OUTRO usuário
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nome de usuário já registrado por outro usuário.")
            db_user.username = new_username
            updated = True
            log.info(f"Username do usuário ID {user_id} atualizado para '{new_username}'.")

        # Atualiza Senha (se fornecida e não vazia)
        if 'password' in update_data and update_data['password']:
            db_user.hashed_password = get_password_hash(update_data['password'])
            updated = True
            log.info(f"Senha do usuário ID {user_id} atualizada.")

        # Atualiza Role (se fornecida e diferente, e não for o user 'admin' tentando mudar sua própria role ou a do 'admin')
        if 'role' in update_data and update_data['role'] != db_user.role:
            new_role = update_data['role']
            if db_user.username == 'admin' and new_role != 'admin':
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível remover a role 'admin' do usuário 'admin'.")
            # Adicional: Impede admin de rebaixar a si mesmo? (Descomentar se necessário)
            # if db_user.id == current_admin.id and new_role != 'admin':
            #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível remover sua própria role de admin.")
            db_user.role = new_role
            updated = True
            log.info(f"Role do usuário ID {user_id} atualizada para '{new_role}'.")

        if updated:
            db.commit()
            db.refresh(db_user)
            log.info(f"[PUT /users/{user_id}] Usuário atualizado com sucesso.")
        else:
            log.info(f"[PUT /users/{user_id}] Nenhum dado foi alterado.")

        return db_user
    except HTTPException as http_exc:
         db.rollback()
         raise http_exc
    except Exception as e:
        db.rollback()
        log.error(f"[PUT /users/{user_id}] Erro interno ao atualizar usuário: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao atualizar usuário: {e}")

# --- Rotas de Solicitação de Custas ---

@app.post("/solicitacoes/", response_model=schemas.SolicitacaoCusta)
def create_solicitacao(
    solicitacao: schemas.SolicitacaoCustaCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Cria uma nova solicitação de custa."""
    log.info(f"[POST /solicitacoes/] Usuário '{current_user.username}' criando solicitação NPJ {solicitacao.npj}")
    try:
        db_solicitacao = models.SolicitacaoCusta(
            npj=solicitacao.npj,
            numero_processo=solicitacao.numero_processo,
            numero_solicitacao=solicitacao.numero_solicitacao,
            valor=solicitacao.valor, # Já validado pelo schema
            data_solicitacao=solicitacao.data_solicitacao,
            aguardando_confirmacao=solicitacao.aguardando_confirmacao,
            usuario_criacao_id=current_user.id,
            status_robo="Pendente",
            is_archived=False
        )
        db.add(db_solicitacao)
        db.commit()
        db.refresh(db_solicitacao)
        db_solicitacao_com_rel = db.query(models.SolicitacaoCusta).options(
                selectinload(models.SolicitacaoCusta.usuario_criacao)
            ).filter(models.SolicitacaoCusta.id == db_solicitacao.id).first()
        log.info(f"[POST /solicitacoes/] Solicitação ID {db_solicitacao.id} criada.")
        return db_solicitacao_com_rel if db_solicitacao_com_rel else db_solicitacao
    except ValidationError as ve:
        log.error(f"[POST /solicitacoes/] Erro de validação: {ve}", exc_info=False)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=ve.errors())
    except Exception as e:
        log.error(f"[POST /solicitacoes/] Erro interno: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno.")

@app.get("/solicitacoes/", response_model=List[schemas.SolicitacaoCusta])
async def read_solicitacoes(
    skip: int = 0, limit: int = 100,
    status_robo: Optional[str] = Query(None), status_robo_ne: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)
):
    """Lista solicitações."""
    log.info(f"[GET /solicitacoes/] Buscando: skip={skip}, limit={limit}, status_robo={status_robo}, archived={include_archived} por '{current_user.username}'")
    if include_archived and current_user.role != 'admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas admins podem ver arquivadas.")
    try:
        query = db.query(models.SolicitacaoCusta).options(
            selectinload('*') # Carrega todos relacionamentos
        )
        if status_robo:
            status_list = [s.strip() for s in status_robo.split(',') if s.strip()]
            if status_list: query = query.filter(models.SolicitacaoCusta.status_robo.in_(status_list))
        if status_robo_ne:
            status_list_ne = [s.strip() for s in status_robo_ne.split(',') if s.strip()]
            if status_list_ne: query = query.filter(models.SolicitacaoCusta.status_robo.notin_(status_list_ne))
        if not include_archived:
            query = query.filter(models.SolicitacaoCusta.is_archived == False)
        solicitacoes = query.order_by(models.SolicitacaoCusta.id.desc()).offset(skip).limit(limit).all()
        log.info(f"[GET /solicitacoes/] Encontradas {len(solicitacoes)}.")
        return solicitacoes
    except Exception as e:
        log.error(f"[GET /solicitacoes/] Erro: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno.")

@app.put("/solicitacoes/{id}", response_model=schemas.SolicitacaoCusta)
def update_solicitacao(
    id: int, solicitacao_update: schemas.SolicitacaoCustaUpdate,
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)
):
    """Atualiza uma solicitação (robô ou finalizar)."""
    log.info(f"[PUT /solicitacoes/{id}] Atualização por '{current_user.username}'.")
    db_solicitacao = db.query(models.SolicitacaoCusta).options(
        selectinload('*')
    ).filter(models.SolicitacaoCusta.id == id).first()

    if db_solicitacao is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Não encontrado")
    if db_solicitacao.is_archived and solicitacao_update.finalizar: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não pode finalizar arquivada.")

    update_data = solicitacao_update.model_dump(exclude_unset=True, exclude={'finalizar', 'arquivar'})
    updated = False
    try:
        for key, value in update_data.items():
            current_value = getattr(db_solicitacao, key, None)
            if key == 'valor' and value is not None:
                if isinstance(value, Decimal) and db_solicitacao.valor != value: setattr(db_solicitacao, key, value); updated = True
                continue
            if key == 'numero_processo' and value and not db_solicitacao.numero_processo: setattr(db_solicitacao, key, value); updated = True; continue
            if key == 'usuario_confirmacao_id' and value is not None and db_solicitacao.usuario_confirmacao_id is None: setattr(db_solicitacao, key, value); updated = True; continue
            if hasattr(db_solicitacao, key) and current_value != value and key not in ['valor', 'numero_processo', 'usuario_confirmacao_id']: setattr(db_solicitacao, key, value); updated = True

        if 'status_robo' in update_data: db_solicitacao.ultima_verificacao_robo = datetime.now(timezone.utc); updated = True

        now_utc = datetime.now(timezone.utc)
        if not db_solicitacao.is_archived:
            if solicitacao_update.finalizar is True and db_solicitacao.usuario_finalizacao_id is None:
                log.info(f"Usuário '{current_user.username}' finalizando ID {id}.")
                db_solicitacao.usuario_finalizacao_id = current_user.id; db_solicitacao.data_finalizacao = now_utc; updated = True
            elif solicitacao_update.finalizar is False and db_solicitacao.usuario_finalizacao_id is not None:
                log.info(f"Usuário '{current_user.username}' desmarcando finalização ID {id}.")
                db_solicitacao.usuario_finalizacao_id = None; db_solicitacao.data_finalizacao = None; updated = True

        if updated: db.commit(); db.refresh(db_solicitacao); log.info(f"[PUT /solicitacoes/{id}] Atualizada.")
        else: log.info(f"[PUT /solicitacoes/{id}] Nenhuma alteração.")
        return db_solicitacao
    except Exception as e:
         db.rollback(); log.error(f"[PUT /solicitacoes/{id}] Erro: {e}", exc_info=True); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {e}")

@app.put("/solicitacoes/{id}/archive", response_model=schemas.SolicitacaoCusta, dependencies=[Depends(require_admin_role)])
def archive_solicitacao(
    id: int, archive_body: schemas.SolicitacaoCustaUpdate = Body(...),
    db: Session = Depends(get_db), current_user: models.User = Depends(require_admin_role)
):
    """Arquiva ou desarquiva uma solicitação (admin)."""
    archive_status = archive_body.arquivar
    if archive_status is None: raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="'arquivar' é obrigatório.")
    log.info(f"[PUT /solicitacoes/{id}/archive] Admin '{current_user.username}' definindo is_archived={archive_status}.")
    db_solicitacao = db.query(models.SolicitacaoCusta).options(selectinload('*')).filter(models.SolicitacaoCusta.id == id).first()
    if db_solicitacao is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Não encontrado")
    if db_solicitacao.is_archived == archive_status: return db_solicitacao
    try:
        db_solicitacao.is_archived = archive_status; now_utc = datetime.now(timezone.utc)
        if archive_status: db_solicitacao.data_arquivamento = now_utc; db_solicitacao.usuario_arquivamento_id = current_user.id
        else: db_solicitacao.data_arquivamento = None; db_solicitacao.usuario_arquivamento_id = None
        db.commit(); db.refresh(db_solicitacao); log.info(f"[PUT /solicitacoes/{id}/archive] Status arquivado: {db_solicitacao.is_archived}.")
        return db_solicitacao
    except Exception as e: db.rollback(); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {e}")

@app.post("/solicitacoes/resetar-erros", status_code=status.HTTP_200_OK, dependencies=[Depends(require_admin_role)])
def resetar_status_erro(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin_role)):
    """Reseta status de erro para 'Pendente' (admin)."""
    log.info(f"[POST /resetar-erros] Admin '{current_user.username}' iniciando reset.")
    try:
        values = {'status_robo': 'Pendente', 'ultima_verificacao_robo': None, 'status_portal': None, 'usuario_confirmacao_id': None}
        stmt = update(models.SolicitacaoCusta).where(models.SolicitacaoCusta.status_robo.like('%Erro%')).values(**values).returning(models.SolicitacaoCusta.id)
        result = db.execute(stmt); updated_ids = result.scalars().all(); db.commit(); count = len(updated_ids)
        log.info(f"[POST /resetar-erros] {count} resetadas. IDs: {updated_ids}")
        return {"message": f"{count} solicitações com erro resetadas."}
    except Exception as e: db.rollback(); raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro: {e}")

@app.get("/health")
def health_check():
    """Verifica se a API está online."""
    return {"status": "ok"}

