from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, date
from typing import List, Optional # Importar List e Optional

# CORREÇÃO: Importar o CORSMiddleware
from fastapi.middleware.cors import CORSMiddleware 

import schemas # Importa o novo arquivo de schemas
from bd import models
from bd.database import SessionLocal, engine
# CORREÇÃO: Remover a importação de get_current_user, pois ela está definida neste arquivo
from auth import verify_password, create_access_token
from config import ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM

# JWT e Segurança
from jose import JWTError, jwt
from pydantic import BaseModel

# Cria as tabelas (se não existirem)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- Configuração do CORS ---
origins = [
    "http://localhost:3000", # A porta do seu dashboard React
    "http://localhost:3001", # Porta alternativa que vimos no docker-compose
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# --- Funções de Autenticação (Movidas para cá) ---
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
    # Adicionada a busca pelo usuário que faltava
    user = get_user(db, username=form_data.username)
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
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
    """
    Cria uma nova solicitação de custa no banco de dados.
    A solicitação é automaticamente associada ao usuário que está logado.
    """
    db_solicitacao = models.SolicitacaoCusta(
        **solicitacao.dict(), 
        usuario_id=current_user.id,
        status_robo="Pendente", # Define o status inicial
        status_portal="Aguardando Robô" # Define o status inicial
    )
    db.add(db_solicitacao)
    db.commit()
    db.refresh(db_solicitacao)
    return db_solicitacao

@app.get("/solicitacoes/", response_model=List[schemas.SolicitacaoCusta])
def read_solicitacoes(
    skip: int = 0, 
    limit: int = 100, 
    status_robo: Optional[str] = Query(None), # Filtro para o robô (ex: "Pendente,Erro")
    status_robo_ne: Optional[str] = Query(None), # Filtro de "não igual" (ex: "Finalizado com Sucesso")
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user) # Garante que só usuários logados vejam
):
    """
    Retorna uma lista de todas as solicitações de custas.
    Inclui filtros para o robô.
    """
    query = db.query(models.SolicitacaoCusta)

    if status_robo:
        status_list = [status.strip() for status in status_robo.split(',')]
        query = query.filter(models.SolicitacaoCusta.status_robo.in_(status_list))
    
    if status_robo_ne:
        status_list_ne = [status.strip() for status in status_robo_ne.split(',')]
        query = query.filter(models.SolicitacaoCusta.status_robo.notin_(status_list_ne))

    # Adiciona ordenação para mostrar os mais recentes primeiro
    solicitacoes = query.order_by(models.SolicitacaoCusta.id.desc()).offset(skip).limit(limit).all()
    return solicitacoes

@app.put("/solicitacoes/{id}", response_model=schemas.SolicitacaoCusta)
def update_solicitacao(
    id: int, 
    solicitacao_update: schemas.SolicitacaoCustaUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user) # TODO: Idealmente, apenas o "robô" deveria poder fazer isso
):
    """
    Atualiza uma solicitação de custa.
    Usado pelo robô para enviar o status do processamento.
    """
    db_solicitacao = db.query(models.SolicitacaoCusta).filter(models.SolicitacaoCusta.id == id).first()
    
    if db_solicitacao is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")
        
    # Atualiza apenas os campos que foram enviados no payload
    update_data = solicitacao_update.dict(exclude_unset=True)
    
    # Adiciona o carimbo de data/hora da verificação
    update_data["ultima_verificacao_robo"] = datetime.utcnow()

    for key, value in update_data.items():
        setattr(db_solicitacao, key, value)
        
    db.commit()
    db.refresh(db_solicitacao)
    return db_solicitacao

