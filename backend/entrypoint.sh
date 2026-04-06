#!/bin/sh

APP_DIR="${APP_DIR:-/app}"
POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-admin}"

echo "[Entrypoint] Script iniciado."

echo "[Entrypoint] Aguardando o PostgreSQL..."
sleep 3
# Timeout mais longo para esperar o DB, se necessário
n=0
until [ $n -ge 20 ]
do
  pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -q -U "${POSTGRES_USER}" && break
  n=$((n+1))
  echo "[Entrypoint] PostgreSQL indisponível (tentativa $n/20) - aguardando 1s..."
  sleep 1
done
if [ $n -ge 20 ]; then
  echo "[Entrypoint] ERRO: Timeout esperando pelo PostgreSQL."
  exit 1
fi
>&2 echo "[Entrypoint] PostgreSQL está pronto."

# Script Python para aplicar migrações (criar tabelas) e verificar/criar usuários
echo "[Entrypoint] Iniciando script Python para setup do banco e usuários..."
python3 - <<END
import os
import sys
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

app_dir = os.getenv('APP_DIR', '/app')
dotenv_path = os.path.join(app_dir, '.env')
print(f"[Entrypoint-PY] Tentando carregar .env de: {dotenv_path}")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, verbose=True)
    print("[Entrypoint-PY] Arquivo .env carregado.")
else:
    print(f"[Entrypoint-PY] ATENÇÃO: Arquivo .env não encontrado em {dotenv_path}.")

# Adiciona o diretório da aplicação ao sys.path para encontrar os módulos
sys.path.insert(0, app_dir)
try:
    from bd.database import engine, SessionLocal
    from bd.models import Base, User
    from auth import get_password_hash
    from config import ADMIN_USERNAME, ADMIN_PASSWORD
    print("[Entrypoint-PY] Módulos importados com sucesso.")
except ImportError as e:
    print(f"[Entrypoint-PY] ERRO CRÍTICO ao importar módulos: {e}")
    # Lista o conteúdo para ajudar no debug
    print(f"[Entrypoint-PY] Conteúdo de {app_dir}:")
    os.system(f'ls -la {app_dir}')
    print(f"[Entrypoint-PY] Conteúdo de {app_dir}/bd:")
    os.system(f'ls -la {app_dir}/bd')
    sys.exit(1)

# Aplica migrações (cria tabelas)
print("[Entrypoint-PY] Aplicando migrações (criando/atualizando tabelas)...")
try:
    Base.metadata.create_all(bind=engine)
    print("[Entrypoint-PY] Migrações aplicadas com sucesso.")
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS setor VARCHAR")
        conn.exec_driver_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR DEFAULT 'local'")
        conn.exec_driver_sql("ALTER TABLE solicitacoes_custas ADD COLUMN IF NOT EXISTS setor_criacao VARCHAR")
        conn.exec_driver_sql("ALTER TABLE solicitacoes_custas ADD COLUMN IF NOT EXISTS prazo_fatal_em TIMESTAMPTZ")
        conn.exec_driver_sql("ALTER TABLE solicitacoes_custas ADD COLUMN IF NOT EXISTS proxima_verificacao_em TIMESTAMPTZ")
        conn.exec_driver_sql("ALTER TABLE solicitacoes_custas ADD COLUMN IF NOT EXISTS alerta_enviado_em TIMESTAMPTZ")
        conn.exec_driver_sql("ALTER TABLE solicitacoes_custas ADD COLUMN IF NOT EXISTS acao_apos_alerta VARCHAR")
        conn.exec_driver_sql("ALTER TABLE solicitacoes_custas ADD COLUMN IF NOT EXISTS monitoramento_ativo BOOLEAN DEFAULT TRUE")
        conn.exec_driver_sql("ALTER TABLE solicitacoes_custas ADD COLUMN IF NOT EXISTS motivo_encerramento VARCHAR")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_users_setor ON users (setor)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_solicitacoes_custas_setor_criacao ON solicitacoes_custas (setor_criacao)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_solicitacoes_custas_prazo_fatal_em ON solicitacoes_custas (prazo_fatal_em)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_solicitacoes_custas_proxima_verificacao_em ON solicitacoes_custas (proxima_verificacao_em)")
    print("[Entrypoint-PY] Migração leve de colunas de usuário aplicada.")
except Exception as e:
    print(f"[Entrypoint-PY] ERRO ao aplicar migrações: {e}")
    # Decide-se continuar mesmo se houver erro aqui, pode ser que as tabelas já existam
    # Em produção, uma ferramenta de migração mais robusta (como Alembic) seria ideal

db = SessionLocal()
exit_code = 0
try:
    # --- Usuário Admin ---
    admin_user = ADMIN_USERNAME
    admin_pass = ADMIN_PASSWORD
    user_exists = db.query(User).filter(User.username == admin_user).first()
    if not user_exists:
        print(f"[Entrypoint-PY] Criando usuário '{admin_user}' com role 'admin'...")
        hashed_password = get_password_hash(admin_pass)
        # Define a role como 'admin' e is_active como True na criação
        db_user = User(username=admin_user, hashed_password=hashed_password, role='admin', is_active=True)
        db.add(db_user)
        db.commit()
        print(f"[Entrypoint-PY] Usuário '{admin_user}' criado.")
    elif user_exists.role != 'admin' or not user_exists.is_active:
        print(f"[Entrypoint-PY] Usuário '{admin_user}' existe, garantindo role 'admin' e status 'active'...")
        user_exists.role = 'admin' # Garante que o usuário 'admin' sempre tenha a role 'admin'
        user_exists.is_active = True # Garante que o admin esteja ativo
        db.commit()
        print(f"[Entrypoint-PY] Usuário '{admin_user}' atualizado para role 'admin' e is_active=True.")
    else:
        print(f"[Entrypoint-PY] Usuário '{admin_user}' já existe com role 'admin' e está ativo.")

    # --- Usuário Robô ---
    robot_user = os.getenv('ROBOT_USERNAME', 'robot')
    robot_pass = os.getenv('ROBOT_PASSWORD')

    print(f"[Entrypoint-PY] Verificando usuário robô: '{robot_user}'")
    user_exists = db.query(User).filter(User.username == robot_user).first()
    if not user_exists:
        print(f"[Entrypoint-PY] Criando usuário '{robot_user}' com role 'admin'...") # <-- MUDANÇA NA MENSAGEM
        hashed_password = get_password_hash(robot_pass)
        # Robô agora é criado com role 'admin' e ativo
        db_user = User(username=robot_user, hashed_password=hashed_password, role='admin', is_active=True) # <-- MUDANÇA AQUI
        db.add(db_user)
        db.commit()
        print(f"[Entrypoint-PY] Usuário '{robot_user}' criado com role 'admin'.")
    elif user_exists.role != 'admin' or not user_exists.is_active: # Garante que seja admin e ativo
        print(f"[Entrypoint-PY] Usuário robô '{robot_user}' existe, garantindo role 'admin' e status 'active'...")
        user_exists.role = 'admin' 
        user_exists.is_active = True
        db.commit()
        print(f"[Entrypoint-PY] Usuário robô '{robot_user}' atualizado para role 'admin' e is_active=True.")
    else:
        print(f"[Entrypoint-PY] Usuário '{robot_user}' já existe com role 'admin' e está ativo.")

except Exception as e:
    print(f"[Entrypoint-PY] ERRO durante criação/verificação de usuários: {e}")
    db.rollback()
    exit_code = 1 # Define erro
finally:
    db.close()
    sys.exit(exit_code) # Sai com o código de erro (0 se sucesso)
END

python_exit_code=$?
echo "[Entrypoint] Script Python finalizado com código de saída: ${python_exit_code}."

# Só inicia o Uvicorn se o script Python terminou com sucesso
if [ ${python_exit_code} -ne 0 ]; then
  echo "[Entrypoint] ERRO: Script Python falhou. Abortando o início do Uvicorn."
  exit ${python_exit_code} # Sai do entrypoint com o mesmo erro
fi

echo "[Entrypoint] Setup do banco e usuários concluído com sucesso."
echo "[Entrypoint] Iniciando o comando principal: exec $@"
# Executa o comando passado como argumento para o entrypoint (definido no CMD do Dockerfile)
exec "$@"

# Se chegar aqui, o exec falhou
echo "[Entrypoint] ERRO CRÍTICO: Falha ao executar o comando CMD via exec: '$@'"
exit 1
