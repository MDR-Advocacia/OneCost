import os
import sys
import time

from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError


APP_DIR = os.getenv("APP_DIR", "/app")
DOTENV_PATH = os.path.join(APP_DIR, ".env")

if os.path.exists(DOTENV_PATH):
    load_dotenv(dotenv_path=DOTENV_PATH, verbose=True)

sys.path.insert(0, APP_DIR)

from bd.database import engine, SessionLocal  # noqa: E402
from bd.models import Base, User  # noqa: E402
from auth import get_password_hash, verify_password  # noqa: E402
from config import ADMIN_USERNAME, ADMIN_PASSWORD  # noqa: E402


def wait_for_db(max_attempts: int = 30, delay_seconds: int = 2) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            print(f"[bootstrap] PostgreSQL pronto na tentativa {attempt}.")
            return
        except OperationalError as exc:
            print(f"[bootstrap] PostgreSQL indisponivel ({attempt}/{max_attempts}): {exc}")
            time.sleep(delay_seconds)
    raise RuntimeError("Timeout aguardando o PostgreSQL.")


def run_light_migrations() -> None:
    Base.metadata.create_all(bind=engine)
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
    print("[bootstrap] Migrações leves aplicadas.")


def ensure_user(db, username: str, password: str, role: str = "admin", sync_password: bool = False) -> None:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        user = User(
            username=username,
            hashed_password=get_password_hash(password),
            role=role,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"[bootstrap] Usuario '{username}' criado com role '{role}'.")
        return

    changed = False
    if user.role != role:
        user.role = role
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if sync_password and password and not verify_password(password, user.hashed_password):
        user.hashed_password = get_password_hash(password)
        changed = True
    if changed:
        db.commit()
        print(f"[bootstrap] Usuario '{username}' atualizado com role '{role}' e ativo.")
    else:
        print(f"[bootstrap] Usuario '{username}' ja estava correto.")


def main() -> int:
    wait_for_db()
    run_light_migrations()

    db = SessionLocal()
    try:
        ensure_user(
            db,
            ADMIN_USERNAME,
            ADMIN_PASSWORD,
            "admin",
            sync_password=bool(os.getenv("ADMIN_PASSWORD")),
        )
        robot_username = os.getenv("ROBOT_USERNAME", "robot")
        robot_password = os.getenv("ROBOT_PASSWORD")
        if robot_password:
            ensure_user(db, robot_username, robot_password, "admin", sync_password=True)
        else:
            print("[bootstrap] ROBOT_PASSWORD ausente; usuario do robo nao foi ajustado.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
