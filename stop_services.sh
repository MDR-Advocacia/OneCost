#!/bin/bash
# Script para parar todos os serviços do OneCost via Docker

echo "--- 🛑 Parando todos os serviços do OneCost... ---"

# Verifica se o Docker está em execução
if ! docker info > /dev/null 2>&1; then
  echo "🚨 ERRO: O Docker não parece estar em execução."
  exit 1
fi

docker-compose down

echo "✅ Serviços parados com sucesso."
