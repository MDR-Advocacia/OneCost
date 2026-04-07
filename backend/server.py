from fastapi import FastAPI, Depends, HTTPException, status, Query, Body
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy import update, func
from sqlalchemy.orm import Session, joinedload, selectinload
from datetime import timedelta, datetime, date, timezone
from typing import List, Optional
from decimal import Decimal, InvalidOperation
import json
import logging
import os
from pathlib import Path
import re  # Importar re para regex no CORS

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# --- MUDANÇA 1: IMPORTAR A BIBLIOTECA CORRETA ---
from prometheus_fastapi_instrumentator import Instrumentator

import schemas
from bd import models
from bd.database import SessionLocal, engine
from auth import verify_password, create_access_token, get_password_hash
from ad_integration import autenticar_e_obter_setor, listar_ous_bb_ad, mapear_setores_bb_por_usuarios
from config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM, ADMIN_USERNAME

from jose import JWTError, jwt
from pydantic import BaseModel, ValidationError

# Configura o logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

app = FastAPI()
PROTECTED_BACKFILL_USERNAMES = {
    username
    for username in {
        ADMIN_USERNAME,
        os.getenv("ROBOT_USERNAME", "robot"),
    }
    if username
}

# --- MUDANÇA 2: USAR O INSTRUMENTADOR ---
# Isso instrumenta o app (conta requests, etc.) e já expõe a rota /metrics
Instrumentator().instrument(app).expose(app)
# --- FIM DAS MUDANÇAS ---


# --- Configuração do CORS ---
cors_regex = r"http://(localhost|127\.0\.0\.1|192\.168\.50\.\d{1,3}|192\.168\.0\.\d{1,3}):3001|https?://onecost\.mdr\.local(:\d+)?|https://onecost\.mdradvocacia\.com"
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=cors_regex,  # Usa regex
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
log.info(f"CORS configurado para permitir regex: {cors_regex}")

# --- Servir Arquivos Estáticos ---
try:
    static_directory = Path(os.getenv("COMPROVANTES_STATIC_DIR", "/app/static/comprovantes"))
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


def random_unusable_password(username: str) -> str:
    return get_password_hash(f"ad-user::{username}::disabled-local-login")

# --- Funções de Autenticação e Permissão ---
def get_user(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()


def sync_ad_user(db: Session, username: str, setor: str) -> models.User:
    user = get_user(db, username=username)

    if user:
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuario inativo. Procure um administrador.",
            )

        changed = False
        if user.setor != setor:
            user.setor = setor
            changed = True
        if user.auth_provider != "ad":
            user.auth_provider = "ad"
            changed = True
        if changed:
            db.commit()
            db.refresh(user)
        return user

    user = models.User(
        username=username,
        hashed_password=random_unusable_password(username),
        role="user",
        is_active=True,
        setor=setor,
        auth_provider="ad",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

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
    user = None
    local_user = get_user(db, username=form_data.username)
    password_verified = local_user and verify_password(form_data.password, local_user.hashed_password)
    is_bootstrap_admin = (
        local_user
        and password_verified
        and local_user.is_active
        and local_user.role == "admin"
        and local_user.username == ADMIN_USERNAME
    )

    # Contas administrativas locais não devem depender do AD para autenticar.
    if is_bootstrap_admin:
        user = local_user
        log.info(f"[/login] Login local prioritario aceito para '{form_data.username}'.")

    if not user:
        ad_result = autenticar_e_obter_setor(form_data.username, form_data.password)
        if ad_result.get("status") == "sucesso":
            user = sync_ad_user(db, form_data.username, ad_result["setor"])
            log.info(f"[/login] Login AD aceito para '{form_data.username}' no setor '{user.setor}'.")
        elif local_user and password_verified and local_user.is_active:
            if local_user.auth_provider == "ad":
                log.warning(
                    "[/login] Login local bloqueado para '%s' porque o usuário é gerenciado pelo AD.",
                    form_data.username,
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=ad_result.get("mensagem") or "Usuario gerenciado pelo Active Directory. Use sua credencial do Windows.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            user = local_user
            log.info(f"[/login] Login local de fallback aceito para '{form_data.username}'.")
        else:
            log.warning(f"[/login] Falha na autenticação para '{form_data.username}'.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ad_result.get("mensagem") or "Usuário ou senha incorretos ou usuário inativo",
                headers={"WWW-Authenticate": "Bearer"},
            )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# --- Rotas de Usuário (Protegidas por Admin, exceto /me) ---

@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    """Retorna os dados do usuário logado e ativo."""
    return current_user


@app.get("/sectors/me")
def read_my_sector(current_user: models.User = Depends(get_current_active_user)):
    return {
        "username": current_user.username,
        "setor": current_user.setor,
        "role": current_user.role,
        "auth_provider": current_user.auth_provider,
    }


@app.get("/sectors/", dependencies=[Depends(require_admin_role)])
def read_ad_sectors(current_user: models.User = Depends(require_admin_role)):
    setores = listar_ous_bb_ad()
    return {"setores": setores}


@app.post("/users/backfill-ad", dependencies=[Depends(require_admin_role)])
def backfill_local_users_with_ad(
    payload: schemas.UserAdBackfillRequest = schemas.UserAdBackfillRequest(),
    db: Session = Depends(get_db),
    current_admin: models.User = Depends(require_admin_role),
):
    dry_run = payload.dry_run
    log.info(
        "[POST /users/backfill-ad] Admin '%s' iniciou backfill AD (dry_run=%s).",
        current_admin.username,
        dry_run,
    )

    local_users = (
        db.query(models.User)
        .filter(models.User.auth_provider == "local")
        .order_by(models.User.username)
        .all()
    )

    results = []
    candidate_users = []
    summary = {
        "usuarios_locais": len(local_users),
        "candidatos": 0,
        "atualizaveis": 0,
        "atualizados": 0,
        "sem_alteracao": 0,
        "nao_encontrados": 0,
        "sem_setor_bb": 0,
        "ignorados": 0,
        "erros": 0,
    }

    for user in local_users:
        if user.username in PROTECTED_BACKFILL_USERNAMES:
            summary["ignorados"] += 1
            results.append({
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "auth_provider": user.auth_provider,
                "current_setor": user.setor,
                "ad_setor": None,
                "action": "skipped",
                "detail": "Conta de sistema ignorada no backfill.",
            })
            continue
        candidate_users.append(user)

    summary["candidatos"] = len(candidate_users)

    if not candidate_users:
        return {
            "dry_run": dry_run,
            "summary": summary,
            "results": results,
        }

    try:
        ad_results = mapear_setores_bb_por_usuarios([user.username for user in candidate_users])
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        for user in candidate_users:
            ad_result = ad_results.get(user.username, {
                "status": "erro",
                "mensagem": "Usuario nao retornou resultado do AD.",
            })
            ad_status = ad_result.get("status")
            ad_setor = ad_result.get("setor")

            row = {
                "user_id": user.id,
                "username": user.username,
                "role": user.role,
                "auth_provider": user.auth_provider,
                "current_setor": user.setor,
                "ad_setor": ad_setor,
                "action": "",
                "detail": "",
            }

            if ad_status == "sucesso":
                should_update_setor = (user.setor or "").strip() != (ad_setor or "").strip()
                should_promote_provider = user.auth_provider != "ad"

                if not should_update_setor and not should_promote_provider:
                    summary["sem_alteracao"] += 1
                    row["action"] = "no_change"
                    row["detail"] = "Usuario ja esta alinhado ao AD."
                else:
                    summary["atualizaveis"] += 1
                    row["action"] = "update"
                    detalhes = []
                    if should_update_setor:
                        detalhes.append(
                            f"setor {'vazio' if not user.setor else user.setor!r} -> {ad_setor!r}"
                        )
                    if should_promote_provider:
                        detalhes.append(f"origem {user.auth_provider!r} -> 'ad'")
                    row["detail"] = ", ".join(detalhes)
                    if not dry_run:
                        if should_update_setor:
                            user.setor = ad_setor
                        if should_promote_provider:
                            user.auth_provider = "ad"
                        summary["atualizados"] += 1
            elif ad_status == "nao_encontrado":
                summary["nao_encontrados"] += 1
                row["action"] = "not_found"
                row["detail"] = ad_result.get("mensagem", "Usuario nao encontrado no AD.")
            elif ad_status == "sem_setor_bb":
                summary["sem_setor_bb"] += 1
                row["action"] = "no_bb_sector"
                row["detail"] = ad_result.get("mensagem", "Usuario sem OU BB_ no AD.")
            else:
                summary["erros"] += 1
                row["action"] = "error"
                row["detail"] = ad_result.get("mensagem", "Erro ao consultar o AD.")

            results.append(row)

        if not dry_run and summary["atualizados"] > 0:
            db.commit()
            log.info(
                "[POST /users/backfill-ad] Backfill aplicado com sucesso. %s usuarios atualizados.",
                summary["atualizados"],
            )
    except Exception as exc:
        db.rollback()
        log.error("[POST /users/backfill-ad] Falha ao aplicar backfill: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao aplicar o backfill de usuarios.",
        ) from exc

    action_order = {
        "update": 0,
        "error": 1,
        "not_found": 2,
        "no_bb_sector": 3,
        "no_change": 4,
        "skipped": 5,
    }
    results.sort(key=lambda item: (action_order.get(item["action"], 99), item["username"]))

    return {
        "dry_run": dry_run,
        "summary": summary,
        "results": results,
    }

@app.post("/users/", response_model=schemas.User, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_role)])
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db), current_admin: models.User = Depends(require_admin_role)):
    """Cria um novo usuário (apenas admin)."""
    log.info(f"[POST /users/] Admin '{current_admin.username}' criando usuário: '{user.username}' (role: '{user.role}')")
    db_user = get_user(db, username=user.username)
    if db_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nome de usuário já registrado")
    hashed_password = get_password_hash(user.password)
    new_user = models.User(
        username=user.username,
        hashed_password=hashed_password,
        role=user.role,
        is_active=True,
        setor=user.setor,
        auth_provider='local'
    )
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

        if 'setor' in update_data and update_data['setor'] != db_user.setor:
            db_user.setor = update_data['setor']
            updated = True
            log.info(f"Setor do usuário ID {user_id} atualizado para '{update_data['setor']}'.")

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
    npj_normalizado = solicitacao.npj.strip()
    numero_solicitacao_normalizado = solicitacao.numero_solicitacao.strip()
    log.info(f"[POST /solicitacoes/] Usuário '{current_user.username}' criando solicitação NPJ {npj_normalizado}")
    try:
        solicitacoes_existentes = db.query(models.SolicitacaoCusta).options(
            selectinload(models.SolicitacaoCusta.usuario_criacao)
        ).filter(
            models.SolicitacaoCusta.npj == npj_normalizado,
            models.SolicitacaoCusta.numero_solicitacao == numero_solicitacao_normalizado
        ).order_by(models.SolicitacaoCusta.id.desc()).all()

        if solicitacoes_existentes:
            solicitacao_existente = solicitacoes_existentes[0]
            pode_atualizar = current_user.role == 'admin' or solicitacao_existente.usuario_criacao_id == current_user.id
            criado_por = solicitacao_existente.usuario_criacao.username if solicitacao_existente.usuario_criacao else None
            log.warning(
                f"[POST /solicitacoes/] Tentativa de criar duplicata para NPJ {npj_normalizado} / "
                f"Solicitação {numero_solicitacao_normalizado}. Registro mais recente: ID {solicitacao_existente.id}."
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "duplicate_solicitacao",
                    "message": (
                        f"Ja existe uma solicitacao com NPJ {npj_normalizado} e numero {numero_solicitacao_normalizado}. "
                        "Atualize o registro existente em vez de criar outro."
                    ),
                    "existing_solicitacao": {
                        "id": solicitacao_existente.id,
                        "npj": solicitacao_existente.npj,
                        "numero_solicitacao": solicitacao_existente.numero_solicitacao,
                        "especificacao": solicitacao_existente.especificacao,
                        "status_portal": solicitacao_existente.status_portal,
                        "status_robo": solicitacao_existente.status_robo,
                        "monitoramento_ativo": solicitacao_existente.monitoramento_ativo,
                        "motivo_encerramento": solicitacao_existente.motivo_encerramento,
                        "data_solicitacao": solicitacao_existente.data_solicitacao.isoformat() if solicitacao_existente.data_solicitacao else None,
                        "valor": float(solicitacao_existente.valor) if solicitacao_existente.valor is not None else None,
                        "usuario_criacao_id": solicitacao_existente.usuario_criacao_id,
                        "criado_por": criado_por,
                        "can_update": pode_atualizar,
                        "duplicate_count": len(solicitacoes_existentes),
                    }
                }
            )

        db_solicitacao = models.SolicitacaoCusta(
            npj=npj_normalizado,
            numero_processo=solicitacao.numero_processo,
            numero_solicitacao=numero_solicitacao_normalizado,
            especificacao=solicitacao.especificacao,
            status_portal=solicitacao.status_portal,
            prazo_fatal_em=solicitacao.prazo_fatal_em,
            monitoramento_ativo=solicitacao.monitoramento_ativo,
            valor=solicitacao.valor, # Já validado pelo schema
            data_solicitacao=solicitacao.data_solicitacao,
            aguardando_confirmacao=solicitacao.aguardando_confirmacao,
            setor_criacao=current_user.setor,
            usuario_criacao_id=current_user.id,
            status_robo="Pendente",
            is_archived=False
        )
        db.add(db_solicitacao)
        db.commit()
        db.refresh(db_solicitacao)
        # Recarrega com relacionamentos para o retorno
        db_solicitacao_com_rel = db.query(models.SolicitacaoCusta).options(
                selectinload(models.SolicitacaoCusta.usuario_criacao) # Carrega o criador
            ).filter(models.SolicitacaoCusta.id == db_solicitacao.id).first()
        log.info(f"[POST /solicitacoes/] Solicitação ID {db_solicitacao.id} criada.")
        # Retorna o objeto com o relacionamento carregado, ou o original se a recarga falhar
        return db_solicitacao_com_rel if db_solicitacao_com_rel else db_solicitacao
    except ValidationError as ve:
        log.error(f"[POST /solicitacoes/] Erro de validação: {ve}", exc_info=False)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=ve.errors())
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        log.error(f"[POST /solicitacoes/] Erro interno: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno.")

@app.get("/solicitacoes/", response_model=List[schemas.SolicitacaoCusta])
async def read_solicitacoes(
    skip: int = 0,
    limit: Optional[int] = Query(None, ge=1),
    status_robo: Optional[str] = Query(None),
    status_robo_ne: Optional[str] = Query(None), # Para excluir status
    include_archived: bool = Query(False),
    scope: Optional[str] = Query(None, description="Escopo: me, sector ou all"),
    # NOVO: Filtro por usuário criador
    usuario_id: Optional[int] = Query(None, description="Filtrar por ID do usuário criador"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Lista solicitações com filtros opcionais."""
    log.info(f"[GET /solicitacoes/] Buscando: skip={skip}, limit={limit}, status_robo={status_robo}, status_robo_ne={status_robo_ne}, archived={include_archived}, usuario_id={usuario_id}, scope={scope} por '{current_user.username}'")

    # Regra de permissão para ver arquivadas
    if include_archived and current_user.role != 'admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas admins podem ver solicitações arquivadas.")

    try:
        # Eager load relationships to avoid N+1 queries
        query = db.query(models.SolicitacaoCusta).options(
            selectinload(models.SolicitacaoCusta.usuario_criacao),
            selectinload(models.SolicitacaoCusta.usuario_confirmacao),
            selectinload(models.SolicitacaoCusta.usuario_finalizacao),
            selectinload(models.SolicitacaoCusta.usuario_arquivamento)
        )

        # Aplica filtros
        if status_robo:
            status_list = [s.strip() for s in status_robo.split(',') if s.strip()]
            if status_list:
                query = query.filter(models.SolicitacaoCusta.status_robo.in_(status_list))

        if status_robo_ne:
            status_list_ne = [s.strip() for s in status_robo_ne.split(',') if s.strip()]
            if status_list_ne:
                query = query.filter(models.SolicitacaoCusta.status_robo.notin_(status_list_ne))

        # Filtro de arquivadas
        if not include_archived:
            query = query.filter(models.SolicitacaoCusta.is_archived == False)

        normalized_scope = (scope or '').strip().lower()

        # Filtro por escopo do usuário
        if current_user.role != 'admin':
            if normalized_scope in ('', 'me'):
                query = query.filter(models.SolicitacaoCusta.usuario_criacao_id == current_user.id)
            elif normalized_scope == 'sector':
                if not current_user.setor:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Usuário sem setor vinculado.")
                query = query.filter(
                    (models.SolicitacaoCusta.setor_criacao == current_user.setor) |
                    (
                        (models.SolicitacaoCusta.setor_criacao.is_(None)) &
                        models.SolicitacaoCusta.usuario_criacao.has(models.User.setor == current_user.setor)
                    )
                )
            elif normalized_scope == 'all':
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuários comuns não podem visualizar todas as solicitações.")
            else:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Escopo inválido. Use 'me' ou 'sector'.")
        elif normalized_scope == 'me':
            query = query.filter(models.SolicitacaoCusta.usuario_criacao_id == current_user.id)
        elif normalized_scope == 'sector':
            if not current_user.setor:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Admin sem setor vinculado.")
            query = query.filter(
                (models.SolicitacaoCusta.setor_criacao == current_user.setor) |
                (
                    (models.SolicitacaoCusta.setor_criacao.is_(None)) &
                    models.SolicitacaoCusta.usuario_criacao.has(models.User.setor == current_user.setor)
                )
            )
        elif normalized_scope not in ('', 'all'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Escopo inválido. Use 'me', 'sector' ou 'all'.")

        # NOVO: Filtro por usuário explícito
        if usuario_id is not None:
            # Verifica se o usuário tentando filtrar por outro ID é admin
            if usuario_id != current_user.id and current_user.role != 'admin':
                 raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas admins podem filtrar por outros usuários.")
            query = query.filter(models.SolicitacaoCusta.usuario_criacao_id == usuario_id)

        # Ordenação e paginação opcional
        query = query.order_by(models.SolicitacaoCusta.id.desc()).offset(skip)
        if limit is not None:
            query = query.limit(limit)

        solicitacoes = query.all()
        log.info(f"[GET /solicitacoes/] Encontradas {len(solicitacoes)} solicitações após filtros.")
        return solicitacoes
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"[GET /solicitacoes/] Erro interno ao buscar solicitações: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro interno ao buscar solicitações.")


@app.put("/solicitacoes/{id}", response_model=schemas.SolicitacaoCusta)
def update_solicitacao(
    id: int, solicitacao_update: schemas.SolicitacaoCustaUpdate,
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_active_user)
):
    """Atualiza uma solicitação (usado pelo robô para status/arquivos e pelo usuário para finalizar)."""
    log.info(f"[PUT /solicitacoes/{id}] Tentativa de atualização por usuário '{current_user.username}'. Dados: {solicitacao_update.model_dump(exclude_unset=True)}")

    # Carrega a solicitação com relacionamentos para retorno
    db_solicitacao = db.query(models.SolicitacaoCusta).options(
        selectinload(models.SolicitacaoCusta.usuario_criacao),
        selectinload(models.SolicitacaoCusta.usuario_confirmacao),
        selectinload(models.SolicitacaoCusta.usuario_finalizacao),
        selectinload(models.SolicitacaoCusta.usuario_arquivamento)
    ).filter(models.SolicitacaoCusta.id == id).first()

    if db_solicitacao is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitação não encontrada")

    # Impede finalizar se já estiver arquivada
    if db_solicitacao.is_archived and solicitacao_update.finalizar:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Não é possível finalizar uma solicitação arquivada.")

    if current_user.role != 'admin' and db_solicitacao.usuario_criacao_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Você não tem permissão para alterar esta solicitação.")

    # Pega os dados enviados, excluindo as flags 'finalizar' e 'arquivar' que são tratadas separadamente
    update_data = solicitacao_update.model_dump(exclude_unset=True, exclude={'finalizar', 'arquivar'})
    updated = False

    try:
        # Aplica atualizações dos campos vindos do robô ou outras fontes
        for key, value in update_data.items():
            current_value = getattr(db_solicitacao, key, None)

            # Tratamento especial para 'valor' (comparar Decimal)
            if key == 'valor' and value is not None:
                try:
                    # Converte o valor recebido (float) para Decimal antes de comparar/atribuir
                    decimal_value = schemas.validate_valor_input(value)
                    if db_solicitacao.valor != decimal_value:
                        setattr(db_solicitacao, key, decimal_value)
                        updated = True
                except ValueError:
                    log.warning(f"Valor inválido recebido para atualização: {value}. Ignorando.")
                continue # Pula para o próximo item do loop

            # Atualiza numero_processo somente se estiver vazio e um novo valor for fornecido
            if key == 'numero_processo' and value and not db_solicitacao.numero_processo:
                setattr(db_solicitacao, key, value)
                updated = True
                continue

            # Atualiza usuario_confirmacao_id apenas se ainda não estiver definido
            if key == 'usuario_confirmacao_id' and value is not None and db_solicitacao.usuario_confirmacao_id is None:
                setattr(db_solicitacao, key, value)
                updated = True
                continue

            # Atualiza outros campos se existirem no modelo e o valor for diferente
            if hasattr(db_solicitacao, key) and current_value != value and key not in ['valor', 'numero_processo', 'usuario_confirmacao_id']:
                setattr(db_solicitacao, key, value)
                updated = True

        # Atualiza timestamp se status_robo foi modificado
        if 'status_robo' in update_data:
            db_solicitacao.ultima_verificacao_robo = datetime.now(timezone.utc)
            updated = True # Garante que updated seja True

        # --- Lógica de Finalização pelo Usuário ---
        now_utc = datetime.now(timezone.utc)
        if not db_solicitacao.is_archived: # Só finaliza se não estiver arquivada
            if solicitacao_update.finalizar is True and db_solicitacao.usuario_finalizacao_id is None:
                log.info(f"Usuário '{current_user.username}' marcando solicitação ID {id} como finalizada (tratada).")
                db_solicitacao.usuario_finalizacao_id = current_user.id
                db_solicitacao.data_finalizacao = now_utc
                updated = True
            elif solicitacao_update.finalizar is False and db_solicitacao.usuario_finalizacao_id is not None:
                log.info(f"Usuário '{current_user.username}' reabrindo solicitação ID {id} para novo acompanhamento.")
                db_solicitacao.usuario_finalizacao_id = None
                db_solicitacao.data_finalizacao = None
                updated = True

        # Se houve alguma alteração, commita
        if updated:
            db.commit()
            db.refresh(db_solicitacao) # Recarrega o objeto com os dados atualizados do DB
            # Precisamos recarregar as relações explicitamente após o refresh
            db.refresh(db_solicitacao.usuario_criacao)
            if db_solicitacao.usuario_confirmacao_id: db.refresh(db_solicitacao.usuario_confirmacao)
            if db_solicitacao.usuario_finalizacao_id: db.refresh(db_solicitacao.usuario_finalizacao)
            if db_solicitacao.usuario_arquivamento_id: db.refresh(db_solicitacao.usuario_arquivamento)
            log.info(f"[PUT /solicitacoes/{id}] Solicitação atualizada com sucesso.")
        else:
            log.info(f"[PUT /solicitacoes/{id}] Nenhuma alteração detectada nos dados enviados.")

        return db_solicitacao
    except Exception as e:
         db.rollback()
         log.error(f"[PUT /solicitacoes/{id}] Erro interno ao atualizar solicitação: {e}", exc_info=True)
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao atualizar solicitação: {e}")


@app.put("/solicitacoes/{id}/archive", response_model=schemas.SolicitacaoCusta, dependencies=[Depends(require_admin_role)])
def archive_solicitacao(
    id: int, archive_body: schemas.SolicitacaoCustaUpdate = Body(...), # Reutiliza schema, pegando só 'arquivar'
    db: Session = Depends(get_db), current_user: models.User = Depends(require_admin_role)
):
    """Arquiva ou desarquiva uma solicitação (apenas admin)."""
    archive_status = archive_body.arquivar # Pega o valor booleano do corpo
    if archive_status is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="O campo 'arquivar' (true/false) é obrigatório no corpo da requisição.")

    log.info(f"[PUT /solicitacoes/{id}/archive] Admin '{current_user.username}' solicitou definir is_archived={archive_status}.")

    # Carrega solicitação com relacionamentos
    db_solicitacao = db.query(models.SolicitacaoCusta).options(
        selectinload('*') # Carrega tudo
    ).filter(models.SolicitacaoCusta.id == id).first()

    if db_solicitacao is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitação não encontrada")

    # Verifica se o status já é o desejado
    if db_solicitacao.is_archived == archive_status:
        log.info(f"[PUT /solicitacoes/{id}/archive] Solicitação já está no estado desejado (is_archived={archive_status}). Nenhuma alteração.")
        return db_solicitacao # Retorna o estado atual sem fazer nada

    try:
        now_utc = datetime.now(timezone.utc)
        db_solicitacao.is_archived = archive_status
        if archive_status: # Se está arquivando
            db_solicitacao.data_arquivamento = now_utc
            db_solicitacao.usuario_arquivamento_id = current_user.id
        else: # Se está desarquivando
            db_solicitacao.data_arquivamento = None
            db_solicitacao.usuario_arquivamento_id = None

        db.commit()
        db.refresh(db_solicitacao) # Recarrega do DB
        # Recarrega relações
        db.refresh(db_solicitacao.usuario_criacao)
        if db_solicitacao.usuario_confirmacao_id: db.refresh(db_solicitacao.usuario_confirmacao)
        if db_solicitacao.usuario_finalizacao_id: db.refresh(db_solicitacao.usuario_finalizacao)
        if db_solicitacao.usuario_arquivamento_id: db.refresh(db_solicitacao.usuario_arquivamento)

        log.info(f"[PUT /solicitacoes/{id}/archive] Status de arquivamento atualizado para: {db_solicitacao.is_archived}.")
        return db_solicitacao
    except Exception as e:
        db.rollback()
        log.error(f"[PUT /solicitacoes/{id}/archive] Erro interno: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao atualizar arquivamento: {e}")

@app.post("/solicitacoes/resetar-erros", status_code=status.HTTP_200_OK, dependencies=[Depends(require_admin_role)])
def resetar_status_erro(db: Session = Depends(get_db), current_user: models.User = Depends(require_admin_role)):
    """Reseta o status_robo de 'Erro:*' para 'Pendente' (apenas admin)."""
    log.info(f"[POST /resetar-erros] Admin '{current_user.username}' iniciando reset de status de erro.")
    try:
        # Define os valores a serem atualizados
        values_to_update = {
            'status_robo': 'Pendente',
            'ultima_verificacao_robo': None, # Limpa última verificação
            'status_portal': None, # Limpa status do portal
            'usuario_confirmacao_id': None # Limpa confirmação se houve
        }
        # Cria a declaração de update
        stmt = (
            update(models.SolicitacaoCusta)
            .where(func.lower(models.SolicitacaoCusta.status_robo).like('erro%'))
            .values(**values_to_update)
            .returning(models.SolicitacaoCusta.id) # Retorna os IDs afetados
        )
        # Executa e obtém os IDs
        result = db.execute(stmt)
        updated_ids = result.scalars().all()
        db.commit() # Confirma a transação
        count = len(updated_ids)
        log.info(f"[POST /resetar-erros] {count} solicitações com status de erro foram resetadas para 'Pendente'. IDs: {updated_ids}")
        return {"message": f"{count} solicitações com erro foram resetadas para 'Pendente'."}
    except Exception as e:
        db.rollback() # Desfaz em caso de erro
        log.error(f"[POST /resetar-erros] Erro interno ao resetar status: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Erro interno ao resetar status: {e}")

@app.get("/health")
def health_check():
    """Verifica se a API está online."""
    return {"status": "ok"}
