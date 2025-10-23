# Usa a imagem base do Python
FROM python:3.9-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala o cliente do PostgreSQL para o comando pg_isready
# E instala python3-dotenv para o entrypoint.sh conseguir ler o .env
RUN apt-get update && apt-get install -y postgresql-client python3-dotenv --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Copia APENAS o requirements.txt primeiro para aproveitar o cache do Docker
# Assume que requirements.txt está DENTRO da pasta backend
COPY ./backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copia TODO o conteúdo da pasta backend local para /app no container
COPY ./backend /app

# *** DEBUG: Lista o conteúdo de /app para verificar a cópia ***
RUN ls -la /app

# Garante que o entrypoint seja executável
RUN chmod +x /app/entrypoint.sh

# Executa o entrypoint diretamente.
ENTRYPOINT ["/app/entrypoint.sh"]

# Comando padrão que o entrypoint.sh irá executar via 'exec "$@"'
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]

