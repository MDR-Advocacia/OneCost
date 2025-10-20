import getpass
from sqlalchemy.orm import Session
from bd import database as db
from bd.database import User, get_password_hash

def create_admin_user():
    """
    Script interativo para criar um usuário administrador no banco de dados.
    """
    db_session: Session = next(db.get_db())
    
    print("--- CRIAÇÃO DE USUÁRIO ADMINISTRADOR ---")
    
    try:
        # Pede o nome do usuário
        while True:
            username = input("Digite o nome do usuário admin: ").strip()
            if not username:
                print("O nome de usuário não pode ser vazio.")
                continue
            
            user_exists = db_session.query(User).filter(User.username == username).first()
            if user_exists:
                print(f"O usuário '{username}' já existe. Por favor, escolha outro nome.")
            else:
                break
        
        # Pede a senha
        while True:
            password = getpass.getpass("Digite a senha do admin: ")
            if len(password) < 4:
                print("A senha deve ter pelo menos 4 caracteres.")
                continue
            
            password_confirm = getpass.getpass("Confirme a senha: ")
            if password != password_confirm:
                print("As senhas não coincidem. Tente novamente.")
            else:
                break

        # Cria o novo usuário
        hashed_password = get_password_hash(password)
        new_admin = User(
            username=username,
            hashed_password=hashed_password,
            is_admin=True
        )
        
        db_session.add(new_admin)
        db_session.commit()
        
        print("\n✅ Usuário administrador criado com sucesso!")
        print(f"   Usuário: {username}")

    except Exception as e:
        print(f"\n❌ Erro ao criar usuário: {e}")
        db_session.rollback()
    finally:
        db_session.close()
        print("-----------------------------------------")

if __name__ == "__main__":
    create_admin_user()

