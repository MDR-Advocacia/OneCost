#!/bin/sh

echo "[Entrypoint] Script iniciado."

echo "[Entrypoint] Aguardando o PostgreSQL..."
# Aumentar um pouco a espera inicial, só por garantia
sleep 3
while ! pg_isready -h db -p 5432 -q -U admin; do
  >&2 echo "[Entrypoint] PostgreSQL indisponível - aguardando..."
  sleep 1
done
>&2 echo "[Entrypoint] PostgreSQL está pronto."

# Script Python para verificar/criar usuários
# Requer python3-dotenv instalado (feito no Dockerfile)
echo "[Entrypoint] Iniciando script Python para usuários..."
python3 - <<END
import os
import sys
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Carrega variáveis do .env localizado em /app (montado via volume)
dotenv_path = '/app/.env'
print(f"[Entrypoint-PY] Tentando carregar .env de: {dotenv_path}")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, verbose=True)
    print("[Entrypoint-PY] Arquivo .env carregado.")
else:
    print(f"[Entrypoint-PY] ATENÇÃO: Arquivo .env não encontrado em {dotenv_path}. Usando fallbacks se existirem.")

# Adiciona /app ao sys.path para encontrar os módulos bd e auth
sys.path.insert(0, '/app')
try:
    from bd.models import Base, User
    from auth import get_password_hash
    print("[Entrypoint-PY] Módulos importados com sucesso.")
except ImportError as e:
    print(f"[Entrypoint-PY] ERRO CRÍTICO ao importar módulos: {e}")
    print(f"[Entrypoint-PY] Conteúdo de /app:")
    os.system('ls -la /app') # Lista conteúdo se a importação falhar
    sys.exit(1)


# Configurações do banco
DATABASE_URL = "postgresql://admin:admin@db:5432/onecost"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Pequena espera extra
time.sleep(2)

# Cria as tabelas se não existirem
print("[Entrypoint-PY] Aplicando migrações (criando tabelas)...")
try:
    Base.metadata.create_all(bind=engine)
    print("[Entrypoint-PY] Migrações aplicadas.")
except Exception as e:
    print(f"[Entrypoint-PY] ERRO ao aplicar migrações: {e}")
    # Considerar sair se a criação das tabelas falhar? Depende da estratégia.

db = SessionLocal()
exit_code = 0 # <-- Adicionado para guardar o status
try:
    # --- Usuário Admin ---
    admin_user = 'admin'
    admin_pass = 'admin' # Senha fixa para admin
    user_exists = db.query(User).filter(User.username == admin_user).first()
    if not user_exists:
        print(f"[Entrypoint-PY] Criando usuário '{admin_user}'...")
        hashed_password = get_password_hash(admin_pass)
        db_user = User(username=admin_user, hashed_password=hashed_password)
        db.add(db_user)
        db.commit()
        print(f"[Entrypoint-PY] Usuário '{admin_user}' criado.")
    else:
        print(f"[Entrypoint-PY] Usuário '{admin_user}' já existe.")

    # --- Usuário Robô ---
    robot_user = os.getenv('ROBOT_USERNAME', 'robot') # Default 'robot'
    robot_pass = os.getenv('ROBOT_PASSWORD')

    print(f"[Entrypoint-PY] Usuário robô lido do .env: '{robot_user}'")
    if robot_pass:
        # Apenas loga o comprimento, não a senha
        print(f"[Entrypoint-PY] Senha robô lida do .env (comprimento: {len(robot_pass)})")
    else:
        print("[Entrypoint-PY] ATENÇÃO: Senha do robô NÃO encontrada no .env!")
        print("[Entrypoint-PY] ERRO: ROBOT_PASSWORD não definida no ambiente/arquivo .env. Abortando.")
        exit_code = 1

    if exit_code == 0: # Só continua se a senha foi encontrada
        user_exists = db.query(User).filter(User.username == robot_user).first()
        if not user_exists:
            print(f"[Entrypoint-PY] Criando usuário '{robot_user}'...")
            # Usa a senha lida para criar o hash
            hashed_password = get_password_hash(robot_pass)
            db_user = User(username=robot_user, hashed_password=hashed_password)
            db.add(db_user)
            db.commit()
            print(f"[Entrypoint-PY] Usuário '{robot_user}' criado.")
        else:
            print(f"[Entrypoint-PY] Usuário '{robot_user}' já existe.")

except Exception as e:
    print(f"[Entrypoint-PY] ERRO durante criação/verificação de usuários: {e}")
    db.rollback() # Desfaz qualquer mudança parcial
    exit_code = 1 # <-- Guarda o erro
finally:
    db.close()
    sys.exit(exit_code) # <-- Sai com o código de erro guardado
END

# Captura o código de saída do script Python
python_exit_code=$?
echo "[Entrypoint] Script Python finalizado com código de saída: ${python_exit_code}."

# Só tenta executar o CMD se o script Python terminou com sucesso (código 0)
if [ ${python_exit_code} -ne 0 ]; then
  echo "[Entrypoint] ERRO: Script Python falhou. Abortando o início do Uvicorn."
  exit ${python_exit_code} # Sai do entrypoint com o mesmo erro
fi

echo "[Entrypoint] Verificação/Criação de usuários concluída com sucesso."
echo "[Entrypoint] Argumentos recebidos (\$@): $@"
echo "[Entrypoint] Tentando iniciar o comando principal via exec: exec $@"
exec "$@"

# Se chegar aqui, o exec falhou
echo "[Entrypoint] ERRO CRÍTICO: Falha ao executar o comando CMD via exec: '$@'"
exit 1 # Sai com erro se o exec falhar

