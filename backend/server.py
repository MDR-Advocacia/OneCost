from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy import update
# sqlalchemy.orm: options e joinedload/selectinload para carregar relacionamentos
from sqlalchemy.orm import Session, joinedload, selectinload, subqueryload
from datetime import timedelta, datetime, date, timezone # Adicionar timezone
from typing import List, Optional
from decimal import Decimal, InvalidOperation
import json
import logging
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# Importações locais
import schemas
from bd import models # Importar models corretamente
from bd.database import SessionLocal, engine
from auth import verify_password, create_access_token
from config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM

from jose import JWTError, jwt
from pydantic import BaseModel

# Configura o logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Cria tabelas (incluindo as novas colunas se não existirem)
try:
    log.info("Tentando criar/atualizar tabelas no banco de dados...")
    models.Base.metadata.create_all(bind=engine)
    log.info("Criação/atualização de tabelas concluída.")
except Exception as e_db_create:
    log.error(f"Erro ao criar/atualizar tabelas: {e_db_create}", exc_info=True)

app = FastAPI()

# --- Configuração do CORS ---
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

# --- Funções de Autenticação ---
def get_user(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # ... (código existente de get_current_user sem alterações) ...
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            log.warning("[get_current_user] Token decodificado, mas sem 'sub' (username).")
            raise credentials_exception
        token_data = schemas.TokenData(username=username) # Usar schema TokenData
    except JWTError as e:
        log.warning(f"[get_current_user] Erro ao decodificar JWT: {e}")
        raise credentials_exception

    user = get_user(db, username=token_data.username)
    if user is None:
        log.warning(f"[get_current_user] Usuário '{token_data.username}' do token não encontrado no DB.")
        raise credentials_exception
    log.debug(f"[get_current_user] Usuário '{user.username}' autenticado com sucesso.")
    return user

# --- Rotas da API ---

@app.post("/login", response_model=schemas.Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # ... (código existente de login_for_access_token sem alterações) ...
    log.info(f"[/login] Tentativa de login recebida para usuário: '{form_data.username}'")
    user = get_user(db, username=form_data.username)

    if not user:
        log.warning(f"[/login] Usuário '{form_data.username}' não encontrado.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    password_verified = verify_password(form_data.password, user.hashed_password)

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
    # O Pydantic já validou e converteu para Decimal no schema
    valor_decimal = solicitacao.valor

    try:
        db_solicitacao = models.SolicitacaoCusta(
            npj=solicitacao.npj,
            numero_processo=solicitacao.numero_processo,
            numero_solicitacao=solicitacao.numero_solicitacao,
            valor=valor_decimal, # Salva como Decimal
            data_solicitacao=solicitacao.data_solicitacao,
            aguardando_confirmacao=solicitacao.aguardando_confirmacao,
            usuario_criacao_id=current_user.id, # Registra quem criou
            status_robo="Pendente",
            status_portal=None
        )
        db.add(db_solicitacao)
        db.commit()
        db.refresh(db_solicitacao)
        log.info(f"Solicitação ID {db_solicitacao.id} criada com sucesso.")
        # Recarrega com os relacionamentos para retornar dados completos
        db.refresh(db_solicitacao, attribute_names=['usuario_criacao'])
        return db_solicitacao
    except Exception as e:
        log.error(f"Erro ao criar solicitação no DB: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao salvar solicitação.")


@app.get("/solicitacoes/", response_model=List[schemas.SolicitacaoCusta])
def read_solicitacoes(
    skip: int = 0,
    limit: int = 100,
    status_robo: Optional[str] = Query(None, description="Filtrar por status do robô (ex: Pendente, Finalizado)"),
    status_robo_ne: Optional[str] = Query(None, description="Filtrar por status do robô diferente de (ex: Erro)"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    log.info(f"Buscando solicitações: skip={skip}, limit={limit}, status_robo={status_robo}, status_robo_ne={status_robo_ne}")
    try:
        query = db.query(models.SolicitacaoCusta).options(
            # Carrega os usuários relacionados para evitar consultas N+1
            joinedload(models.SolicitacaoCusta.usuario_criacao),
            joinedload(models.SolicitacaoCusta.usuario_confirmacao),
            joinedload(models.SolicitacaoCusta.usuario_finalizacao)
        )

        # Filtros...
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
        log.error(f"Erro ao buscar solicitações do DB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar solicitações.")


@app.put("/solicitacoes/{id}", response_model=schemas.SolicitacaoCusta)
def update_solicitacao(
    id: int,
    solicitacao_update: schemas.SolicitacaoCustaUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    log.info(f"Recebida atualização para solicitação ID {id} por usuário {current_user.username}")
    # Carrega a solicitação incluindo os relacionamentos para o retorno
    db_solicitacao = db.query(models.SolicitacaoCusta).options(
        joinedload(models.SolicitacaoCusta.usuario_criacao),
        joinedload(models.SolicitacaoCusta.usuario_confirmacao),
        joinedload(models.SolicitacaoCusta.usuario_finalizacao)
    ).filter(models.SolicitacaoCusta.id == id).first()

    if db_solicitacao is None:
        log.error(f"Solicitação ID {id} não encontrada para atualização.")
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    # Pega os dados enviados, excluindo os não definidos
    update_data = solicitacao_update.model_dump(exclude_unset=True)
    log.debug(f"Dados recebidos para atualização ID {id}: {json.dumps(update_data, default=str)}") # Log como JSON

    # Verifica se a ação é de finalização
    is_finalizacao_action = update_data.pop('finalizar', False)

    # Define a data da última verificação se o robô está atualizando status
    if not is_finalizacao_action and ('status_robo' in update_data or 'status_portal' in update_data):
         update_data["ultima_verificacao_robo"] = datetime.now(timezone.utc) # Usar timezone aware

    try:
        # Lógica de Finalização pelo Usuário
        if is_finalizacao_action and db_solicitacao.usuario_finalizacao_id is None:
            log.info(f"Usuário {current_user.username} está finalizando a solicitação ID {id}.")
            db_solicitacao.usuario_finalizacao_id = current_user.id
            db_solicitacao.data_finalizacao = datetime.now(timezone.utc) # Usar timezone aware
            # Opcional: Mudar status_robo para algo como "Finalizado pelo Usuário"
            # db_solicitacao.status_robo = "Finalizado pelo Usuário"

        # Aplica as outras atualizações recebidas
        for key, value in update_data.items():
            if key == 'valor' and value is not None:
                # O Pydantic já validou/converteu para Decimal
                setattr(db_solicitacao, key, value)
            elif key == 'comprovantes_path':
                # Garante que seja lista ou None antes de salvar
                 if isinstance(value, list) or value is None:
                     setattr(db_solicitacao, key, value) # SQLAlchemy lida com JSON
                 else:
                     log.warning(f"Recebido 'comprovantes_path' inválido (tipo {type(value)} para ID {id}), salvando como None.")
                     setattr(db_solicitacao, key, None)
            elif key == 'numero_processo':
                # Atualiza numero_processo somente se enviado e não existir ainda
                if value and not db_solicitacao.numero_processo:
                    setattr(db_solicitacao, key, value)
                elif value:
                     log.info(f"Número do processo para ID {id} já existe ('{db_solicitacao.numero_processo}'), ignorando atualização para '{value}'.")
            # Atualiza outros campos normalmente se existirem no modelo
            elif hasattr(db_solicitacao, key):
                 setattr(db_solicitacao, key, value)
            else:
                 log.warning(f"Tentando atualizar campo inexistente '{key}' na solicitação ID {id}. Ignorando.")

        db.commit()
        db.refresh(db_solicitacao) # Recarrega do DB
        # Recarrega explicitamente os relacionamentos após o refresh, se necessário
        # (geralmente não é preciso se carregado inicialmente com options)
        # db.refresh(db_solicitacao, attribute_names=['usuario_criacao', 'usuario_confirmacao', 'usuario_finalizacao'])
        log.info(f"Solicitação ID {id} atualizada com sucesso.")
        return db_solicitacao
    except Exception as e:
         log.error(f"Erro ao atualizar solicitação ID {id} no DB: {e}", exc_info=True)
         db.rollback()
         raise HTTPException(status_code=500, detail="Erro interno ao atualizar solicitação.")

# --- Endpoint para resetar erros ---
@app.post("/solicitacoes/resetar-erros", status_code=status.HTTP_200_OK)
def resetar_status_erro(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # ... (código existente de resetar_status_erro sem alterações) ...
    log.info(f"Usuário '{current_user.username}' solicitou reset de status de erro.")
    try:
        stmt = (
            update(models.SolicitacaoCusta)
            .where(models.SolicitacaoCusta.status_robo.like('%Erro%'))
            .values(
                status_robo='Pendente',
                ultima_verificacao_robo=None,
                status_portal=None,
                # Decide-se se resetar também os IDs de confirmação/finalização
                usuario_confirmacao_id=None,
                usuario_finalizacao_id=None,
                data_finalizacao=None,
            )
        )
        result = db.execute(stmt)
        db.commit()
        count = result.rowcount
        log.info(f"{count} solicitações com erro foram resetadas para 'Pendente'.")
        return {"message": f"{count} solicitações com erro foram resetadas para 'Pendente'."}
    except Exception as e:
        log.error(f"Erro ao resetar status de erro no DB: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao resetar status.")

# --- Health Check ---
@app.get("/health")
def health_check():
    return {"status": "ok"}

