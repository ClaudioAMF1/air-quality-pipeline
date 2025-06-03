#!/bin/bash

echo "📤 Iniciando Producer Kafka..."

# Navegar para diretório kafka
cd kafka

# Instalar dependências se necessário
if [ ! -d "venv" ]; then
    echo "🔧 Criando ambiente virtual..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Executar producer
echo "🚀 Executando producer..."
python producer.py

echo "✅ Producer finalizado!"
