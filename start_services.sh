#!/bin/bash
# Script para iniciar todos os serviços do OneCost via Docker

echo "--- 🚀 Iniciando todos os serviços do OneCost (DB, Backend, Dashboard) ---"

# Verifica se o Docker está em execução
if ! docker info > /dev/null 2>&1; then
  echo "🚨 ERRO: O Docker não parece estar em execução. Por favor, inicie o Docker Desktop e tente novamente."
  exit 1
fi

echo "[1/2] Construindo e subindo os containers em modo 'detached'..."
# O comando --build força a reconstrução se houver mudanças nos Dockerfiles
# O -d (detached) faz com que ele rode em segundo plano e libere seu terminal
docker-compose up --build -d

echo ""
echo "[2/2] Verificando o status dos containers..."
docker-compose ps

echo ""
echo "✅ Serviços iniciados! Acesse o dashboard em:"
echo "   👉 http://localhost:3001"
echo ""
echo "Para parar os serviços, execute: ./stop_services.sh"
