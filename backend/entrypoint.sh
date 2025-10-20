#!/bin/sh

echo "Aguardando o PostgreSQL..."
while ! pg_isready -h db -p 5432 -q -U admin; do
  >&2 echo "PostgreSQL indisponível - aguardando..."
  sleep 1
done
>&2 echo "PostgreSQL está pronto."

# Script Python para verificar e criar o usuário admin
# É executado aqui para garantir que o banco está 100% pronto
python - <<END
import time
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from bd.models import Base, User
from auth import get_password_hash

# Pequena espera extra para garantir que o serviço do postgres esteja totalmente inicializado
time.sleep(2)

engine = create_engine("postgresql://admin:admin@db:5432/onecost")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Cria as tabelas
print("Aplicando migrações (criando tabelas)...")
Base.metadata.create_all(bind=engine)
print("Migrações aplicadas.")

db = SessionLocal()
try:
    user_exists = db.query(User).filter(User.username == 'admin').first()
    if not user_exists:
        print("Nenhum usuário 'admin' encontrado. Criando usuário inicial...")
        hashed_password = get_password_hash('admin')
        admin_user = User(username='admin', hashed_password=hashed_password)
        db.add(admin_user)
        db.commit()
        print("Usuário 'admin' com senha 'admin' criado com sucesso.")
    else:
        print("Usuário 'admin' já existe. Pulando a criação.")
finally:
    db.close()
END

echo "Iniciando a aplicação..."
exec "$@"

