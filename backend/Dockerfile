# Usa a imagem base do Python
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala o cliente do PostgreSQL para o comando pg_isready
RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

# Copia e instala as dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia TODOS os outros arquivos do backend
COPY . .

# A CORREÇÃO DEFINITIVA:
# Executa o entrypoint usando o interpretador 'sh'.
# Isso bypassa qualquer erro de "permission denied".
ENTRYPOINT ["sh", "entrypoint.sh"]

# Comando padrão que o entrypoint.sh irá executar no final
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

