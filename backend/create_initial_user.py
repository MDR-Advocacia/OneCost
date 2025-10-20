from bd.database import SessionLocal, engine
from bd.models import User, Base
from auth import get_password_hash

print("Verificando a existência do usuário 'admin'...")
db = SessionLocal()
Base.metadata.create_all(bind=engine)
user = db.query(User).filter(User.username == "admin").first()

if not user:
    print("Nenhum usuário 'admin' encontrado. Criando usuário inicial...")
    hashed_password = get_password_hash("admin")
    db_user = User(username="admin", hashed_password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    print("Usuário 'admin' com senha 'admin' criado com sucesso.")
else:
    print("Usuário 'admin' já existe. Nenhuma ação necessária.")

db.close()

