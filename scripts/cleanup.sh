#!/bin/bash

echo "🧹 Limpando ambiente do Pipeline Air Quality..."

echo "🛑 Parando containers..."
cd docker && docker-compose down

echo "🧹 Limpando imagens não utilizadas..."
docker image prune -f

echo "�� Parando processos..."
pkill -f celery || true

echo "✅ Limpeza concluída!"
