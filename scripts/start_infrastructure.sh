#!/bin/bash

echo "🚀 Iniciando Pipeline Air Quality - Dataset Completo (6500+ registros)"
echo "=================================================================="

# Verificar se arquivo de dados existe
if [ ! -f "data/AirQualityUCI_Treated.csv" ]; then
    echo "❌ ERRO: Arquivo data/AirQualityUCI_Treated.csv não encontrado!"
    echo "📝 Certifique-se de que o arquivo completo está na pasta data/"
    echo "💡 O arquivo deve ter 6500+ linhas com dados até 04/04/2005"
    exit 1
fi

# Verificar tamanho do arquivo
file_size=$(du -h data/AirQualityUCI_Treated.csv | cut -f1)
line_count=$(wc -l < data/AirQualityUCI_Treated.csv)

echo "📊 Verificando dataset:"
echo "   📁 Tamanho: $file_size"
echo "   📄 Linhas: $line_count"

if [ $line_count -lt 1000 ]; then
    echo "⚠️  AVISO: Arquivo parece pequeno (menos de 1000 linhas)"
    echo "❓ Tem certeza de que é o arquivo completo?"
    read -p "Continuar mesmo assim? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Execução cancelada"
        exit 1
    fi
fi

cd docker

echo ""
echo "🛑 Parando containers existentes..."
docker-compose down

echo ""
echo "🏗️  Construindo imagens customizadas..."
docker-compose build --no-cache

echo ""
echo "🚀 Iniciando todos os serviços..."
docker-compose up -d

echo ""
echo "⏳ Aguardando serviços ficarem prontos (3 minutos para grandes volumes)..."
echo "   ⏰ Tempo estimado: 180 segundos"

for i in {1..18}; do
    echo -n "⏳ $((i*10))s... "
    sleep 10
done
echo ""

echo ""
echo "📋 Status dos containers:"
docker-compose ps

echo ""
echo "🔍 Verificando conectividade..."
sleep 5

# Testar API
if curl -s http://localhost:5000/api/stats > /dev/null; then
    echo "✅ API Flask: Conectada"
else
    echo "❌ API Flask: Não respondendo"
fi

# Testar Streamlit
if curl -s http://localhost:8501 > /dev/null; then
    echo "✅ Streamlit: Conectado"
else
    echo "❌ Streamlit: Não respondendo"
fi

# Testar Airflow
if curl -s http://localhost:8080/health > /dev/null; then
    echo "✅ Airflow: Conectado"
else
    echo "❌ Airflow: Não respondendo"
fi

echo ""
echo "✅ INFRAESTRUTURA INICIADA COM SUCESSO!"
echo ""
echo "🌐 URLs dos serviços:"
echo "   📊 Dashboard Streamlit: http://localhost:8501"
echo "   ⚙️  Airflow (Orquestração): http://localhost:8080 (admin/admin)"
echo "   🔗 API Flask: http://localhost:5000"
echo "   🐰 RabbitMQ Management: http://localhost:15672 (admin/admin)"
echo "   💾 MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
echo ""
echo "🚀 PRÓXIMOS PASSOS:"
echo "   1. Acesse o Airflow: http://localhost:8080"
echo "   2. Faça login com: admin/admin"
echo "   3. Ative a DAG: 'air_quality_pipeline_full'"
echo "   4. Execute a DAG manualmente"
echo "   5. Acompanhe o dashboard: http://localhost:8501"
echo ""
echo "📊 PROCESSAMENTO ESPERADO:"
echo "   📈 O sistema processará $line_count registros"
echo "   ⏱️  Tempo estimado: 10-15 minutos para dataset completo"
echo "   💾 Serão criados milhares de arquivos no MinIO"
echo "   🚨 Alertas críticos serão detectados automaticamente"
echo ""
echo "🔧 Para monitorar:"
echo "   ./scripts/monitor.sh"
EOF

chmod +x scripts/start_infrastructure.sh