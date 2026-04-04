import os

# Use uma chave secreta forte e aleatória em produção.
# Você pode gerar uma com: openssl rand -hex 32
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

AD_SERVER_IP = os.getenv("AD_SERVER_IP", "206.42.43.192")
AD_DOMAIN = os.getenv("AD_DOMAIN", "mdr.local")
AD_BASE_DN = os.getenv("AD_BASE_DN", "DC=mdr,DC=local")
AD_SERVICE_USER = os.getenv("AD_SERVICE_USER", os.getenv("ONELOG_USERNAME", ""))
AD_SERVICE_PASS = os.getenv("AD_SERVICE_PASS", os.getenv("ONELOG_PASSWORD", ""))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin@db:5432/onecost")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
