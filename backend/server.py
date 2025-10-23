from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy import update
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, date
from typing import List, Optional
from decimal import Decimal, InvalidOperation
import json
import logging
from pathlib import Path # Importar Path

from fastapi.middleware.cors import CORSMiddleware
# ---> IMPORTAR StaticFiles <---
from fastapi.staticfiles import StaticFiles

import schemas
from bd import models
from bd.database import SessionLocal, engine
from auth import verify_password, create_access_token
from config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM

from jose import JWTError, jwt
from pydantic import BaseModel

# Configura o logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("server")

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- Configuração do CORS (Manter no início) ---
origins = [
    "http://localhost:3000",
    "http://localhost:3001",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---> MOVIDO PARA CIMA E SIMPLIFICADO: SERVIR ARQUIVOS ESTÁTICOS <---
try:
    # Define o caminho absoluto DENTRO do container onde os arquivos estão
    static_directory = Path("/app/static/comprovantes")
    # Garante que o diretório exista (embora o volume deva criá-lo)
    static_directory.mkdir(parents=True, exist_ok=True)

    # Monta o diretório na URL '/static/comprovantes'
    # REMOVIDO o argumento 'name'
    app.mount("/static/comprovantes", StaticFiles(directory=static_directory), name="static_comprovantes") # Nome unico
    log.info(f"Servindo arquivos estáticos de '{static_directory}' em '/static/comprovantes'")

    # Teste: Tenta listar o conteúdo (APENAS PARA DEBUG)
    if static_directory.exists() and static_directory.is_dir():
        log.debug(f"Conteúdo de {static_directory}: {list(static_directory.iterdir())}")
    else:
        log.warning(f"Diretório estático {static_directory} não encontrado ou não é um diretório após mkdir.")

except Exception as e_static:
    log.error(f"Erro CRÍTICO ao configurar arquivos estáticos: {e_static}", exc_info=True)
# ---> FIM DA SEÇÃO DE ARQUIVOS ESTÁTICOS <---


# --- Dependências ---
def get_db():
# ... (resto do arquivo server.py SEM alterações) ...
# ... (get_db, oauth2_scheme, TokenData, get_user, get_current_user, login) ...
# ... (read_users_me, create_solicitacao, read_solicitacoes, update_solicitacao) ...
# ... (resetar_status_erro, health_check) ...

# (O restante do seu server.py continua igual)
# Copie apenas as linhas de import e a seção MOVIDA E SIMPLIFICADA
# para o seu arquivo server.py no Canvas.

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

class TokenData(BaseModel):
    username: Optional[str] = None

# --- Funções de Autenticação ---
def get_user(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
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

# --- Rotas da API ---

@app.post("/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    log.info(f"[/login] Tentativa de login recebida para usuário: '{form_data.username}'")
    user = get_user(db, username=form_data.username)

    password_verified = user and verify_password(form_data.password, user.hashed_password)

    if not password_verified:
        log.warning(f"[/login] Senha INCORRETA para usuário '{form_data.username}'.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    log.info(f"[/login] Autenticação bem-sucedida para '{form_data.username}'. Gerando token...")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# --- Rotas de Solicitação de Custas ---

@app.post("/solicitacoes/", response_model=schemas.SolicitacaoCusta)
def create_solicitacao(
    solicitacao: schemas.SolicitacaoCustaCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    log.info(f"Recebida nova solicitação para NPJ {solicitacao.npj} do usuário {current_user.username}")
    try:
        db_solicitacao = models.SolicitacaoCusta(
            npj=solicitacao.npj,
            numero_processo=solicitacao.numero_processo,
            numero_solicitacao=solicitacao.numero_solicitacao,
            valor=Decimal(str(solicitacao.valor)), # Converte float para Decimal
            data_solicitacao=solicitacao.data_solicitacao,
            aguardando_confirmacao=solicitacao.aguardando_confirmacao,
            usuario_id=current_user.id,
            status_robo="Pendente",
            status_portal=None
        )
        db.add(db_solicitacao)
        db.commit()
        db.refresh(db_solicitacao)
        log.info(f"Solicitação ID {db_solicitacao.id} criada com sucesso.")
        return db_solicitacao
    except Exception as e:
        log.error(f"Erro ao criar solicitação: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao salvar solicitação.")


@app.get("/solicitacoes/", response_model=List[schemas.SolicitacaoCusta])
def read_solicitacoes(
    skip: int = 0,
    limit: int = 100,
    status_robo: Optional[str] = Query(None),
    status_robo_ne: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    log.info(f"Buscando solicitações: skip={skip}, limit={limit}, status_robo={status_robo}, status_robo_ne={status_robo_ne}")
    try:
        query = db.query(models.SolicitacaoCusta)

        if status_robo:
            status_list = [status.strip() for status in status_robo.split(',')]
            query = query.filter(models.SolicitacaoCusta.status_robo.in_(status_list))

        if status_robo_ne:
            status_list_ne = [status.strip() for status in status_robo_ne.split(',')]
            query = query.filter(models.SolicitacaoCusta.status_robo.notin_(status_list_ne))

        solicitacoes = query.order_by(models.SolicitacaoCusta.id.desc()).offset(skip).limit(limit).all()
        log.info(f"Encontradas {len(solicitacoes)} solicitações.")
        return solicitacoes
    except Exception as e:
        log.error(f"Erro ao buscar solicitações: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar solicitações.")


@app.put("/solicitacoes/{id}", response_model=schemas.SolicitacaoCusta)
def update_solicitacao(
    id: int,
    solicitacao_update: schemas.SolicitacaoCustaUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    log.info(f"Recebida atualização para solicitação ID {id} por usuário {current_user.username}")
    db_solicitacao = db.query(models.SolicitacaoCusta).filter(models.SolicitacaoCusta.id == id).first()

    if db_solicitacao is None:
        log.error(f"Solicitação ID {id} não encontrada para atualização.")
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    update_data = solicitacao_update.dict(exclude_unset=True)
    log.debug(f"Dados recebidos para atualização ID {id}: {update_data}")

    # Adiciona o carimbo de data/hora da verificação
    update_data["ultima_verificacao_robo"] = datetime.utcnow()

    try:
        for key, value in update_data.items():
            if key == 'valor' and value is not None:
                try:
                    setattr(db_solicitacao, key, Decimal(str(value)))
                except InvalidOperation:
                     log.error(f"Valor inválido recebido para atualização ({key}={value}), ignorando.")
                     continue
            elif key == 'comprovantes_path':
                 if isinstance(value, list) or value is None:
                     setattr(db_solicitacao, key, value) # Salva a lista Python diretamente
                 else:
                      log.warning(f"Recebido 'comprovantes_path' inválido (tipo {type(value)}), salvando como None.")
                      setattr(db_solicitacao, key, None)
            elif key == 'numero_processo':
                if value and not db_solicitacao.numero_processo:
                    setattr(db_solicitacao, key, value)
                elif value:
                     log.info(f"Número do processo para ID {id} já existe ('{db_solicitacao.numero_processo}'), ignorando atualização para '{value}'.")
            else:
                 setattr(db_solicitacao, key, value)

        db.commit()
        db.refresh(db_solicitacao)
        log.info(f"Solicitação ID {id} atualizada com sucesso.")
        return db_solicitacao
    except Exception as e:
         log.error(f"Erro ao atualizar solicitação ID {id}: {e}", exc_info=True)
         db.rollback()
         raise HTTPException(status_code=500, detail="Erro interno ao atualizar solicitação.")


@app.post("/solicitacoes/resetar-erros", status_code=status.HTTP_200_OK)
def resetar_status_erro(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Busca todas as solicitações cujo status_robo contenha 'Erro'
    e as atualiza para 'Pendente'.
    """
    log.info(f"Usuário '{current_user.username}' solicitou reset de status de erro.")
    try:
        stmt = (
            update(models.SolicitacaoCusta)
            .where(models.SolicitacaoCusta.status_robo.like('%Erro%'))
            .values(
                status_robo='Pendente',
                ultima_verificacao_robo=None,
                status_portal=None
            )
        )
        result = db.execute(stmt)
        db.commit()
        count = result.rowcount
        log.info(f"{count} solicitações com erro foram resetadas para 'Pendente'.")
        return {"message": f"{count} solicitações com erro foram resetadas para 'Pendente'."}
    except Exception as e:
        log.error(f"Erro ao resetar status de erro: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao resetar status.")


@app.get("/health")
def health_check():
    return {"status": "ok"}

