from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta, date, datetime
from decimal import Decimal
from typing import List, Optional
from fastapi.middleware.cors import CORSMiddleware

from bd import models
from bd.database import SessionLocal
from auth import verify_password, create_access_token, SECRET_KEY, ALGORITHM
from config import ACCESS_TOKEN_EXPIRE_MINUTES
import schemas
from jose import JWTError, jwt


app = FastAPI()

origins = ["http://localhost:3001"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- FUNÇÃO PARA OBTER USUÁRIO ATUAL ---
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    return user


@app.post("/login")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # CORREÇÃO: Adicionada a linha que busca o usuário no banco de dados
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", response_model=schemas.User)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

# --- ENDPOINTS ATUALIZADOS E NOVOS PARA SOLICITAÇÕES ---

@app.post("/solicitacoes/", response_model=schemas.SolicitacaoCusta)
def create_solicitacao(
    solicitacao: schemas.SolicitacaoCustaCreate, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """
    Cria uma nova solicitação de custa no banco de dados.
    """
    # A data já vem no formato correto do frontend, o Pydantic valida
    db_solicitacao = models.SolicitacaoCusta(
        **solicitacao.dict(), 
        usuario_id=current_user.id,
        status_robo="Pendente" # Garante o status inicial
    )
    db.add(db_solicitacao)
    db.commit()
    db.refresh(db_solicitacao)
    return db_solicitacao

@app.get("/solicitacoes/", response_model=List[schemas.SolicitacaoCusta])
def read_solicitacoes(
    skip: int = 0, 
    limit: int = 100, 
    status_robo: Optional[str] = None, # Filtro para o robô
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retorna uma lista de solicitações, com filtro opcional por status do robô.
    """
    query = db.query(models.SolicitacaoCusta)
    if status_robo:
        # Permite buscar por múltiplos status separados por vírgula, ex: "Pendente,Erro"
        status_list = [status.strip() for status in status_robo.split(',')]
        query = query.filter(models.SolicitacaoCusta.status_robo.in_(status_list))
    
    solicitacoes = query.offset(skip).limit(limit).all()
    return solicitacoes

@app.put("/solicitacoes/{solicitacao_id}", response_model=schemas.SolicitacaoCusta)
def update_solicitacao(
    solicitacao_id: int,
    solicitacao_update: schemas.SolicitacaoCustaUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user) # Protege a rota
):
    """
    Rota para o robô atualizar o status de uma solicitação.
    """
    db_solicitacao = db.query(models.SolicitacaoCusta).filter(models.SolicitacaoCusta.id == solicitacao_id).first()

    if db_solicitacao is None:
        raise HTTPException(status_code=404, detail="Solicitação não encontrada")

    update_data = solicitacao_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_solicitacao, key, value)
    
    # Garante que a data de verificação seja atualizada se o status do robô mudar
    if 'status_robo' in update_data:
        db_solicitacao.ultima_verificacao_robo = datetime.utcnow()

    db.commit()
    db.refresh(db_solicitacao)
    return db_solicitacao

