#!/bin/bash

echo "👂 Iniciando Consumer Celery..."

# Navegar para diretório celery
cd celery

# Instalar dependências se necessário
if [ ! -d "venv" ]; then
    echo "🔧 Criando ambiente virtual..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Iniciar Celery Worker em background
echo "🔧 Iniciando Celery Worker..."
celery -A consumer worker --loglevel=info --detach

# Executar consumer
echo "🚀 Executando consumer..."
python consumer.py

echo "✅ Consumer finalizado!"
