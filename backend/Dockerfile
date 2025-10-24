# Usa a imagem base do Python
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala o cliente do PostgreSQL, dos2unix e python3-dotenv
RUN apt-get update && apt-get install -y postgresql-client dos2unix python3-dotenv --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Copia APENAS o requirements.txt primeiro para aproveitar o cache do Docker
COPY ./backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia TODO o conteúdo da pasta backend local para /app no container
COPY ./backend /app

# *** REINTRODUZIDO: Usa dos2unix para converter line endings ***
RUN dos2unix /app/entrypoint.sh

# Garante que o entrypoint seja executável
RUN chmod +x /app/entrypoint.sh

# *** MANTIDO: Executa o entrypoint explicitamente com /bin/sh ***
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]

# Comando padrão que o entrypoint.sh irá executar via 'exec "$@"'
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

