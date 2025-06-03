#!/bin/bash

echo "📊 Monitor do Pipeline Air Quality - Dataset Completo"
echo "=================================================="

check_service() {
    local service_name=$1
    local url=$2
    
    if curl -s "$url" > /dev/null 2>&1; then
        echo "✅ $service_name: Ativo"
    else
        echo "❌ $service_name: Inativo"
    fi
}

echo "🔍 Verificando serviços..."
check_service "API Flask" "http://localhost:5000"
check_service "Streamlit" "http://localhost:8501"
check_service "Airflow" "http://localhost:8080"
check_service "RabbitMQ" "http://localhost:15672"
check_service "MinIO" "http://localhost:9001"

echo ""
echo "📊 Status dos containers:"
cd docker && docker-compose ps

echo ""
echo "📈 Estatísticas detalhadas da API:"
api_stats=$(curl -s http://localhost:5000/api/stats 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "$api_stats" | python3 -m json.tool 2>/dev/null || echo "$api_stats"
    
    # Extrair números para análise (com validação)
    cache_records=$(echo "$api_stats" | grep -o '"cache_records":[0-9]*' | cut -d: -f2)
    historical_files=$(echo "$api_stats" | grep -o '"historical_files":[0-9]*' | cut -d: -f2)
    pending_alerts=$(echo "$api_stats" | grep -o '"pending_alerts":[0-9]*' | cut -d: -f2)
    
    # Validar valores
    cache_records=${cache_records:-0}
    historical_files=${historical_files:-0}
    pending_alerts=${pending_alerts:-0}
    
    echo ""
    echo "📊 RESUMO DO PROCESSAMENTO:"
    echo "   💾 Cache (Redis): $cache_records registros"
    echo "   📁 Histórico (MinIO): $historical_files arquivos"
    echo "   🚨 Alertas pendentes: $pending_alerts"
    
    if [ "$cache_records" -gt 100 ]; then
        echo "   ✅ Dataset grande sendo processado com sucesso!"
    elif [ "$cache_records" -gt 0 ]; then
        echo "   🔄 Processamento em andamento..."
    else
        echo "   ⏳ Aguardando execução da DAG no Airflow"
    fi
else
    echo "❌ API não disponível"
fi

echo ""
echo "📋 Verificar progresso detalhado:"
echo "   🔍 Logs do Airflow: cd docker && docker-compose logs -f airflow"
echo "   🔍 Logs da API: cd docker && docker-compose logs -f api"
echo "   🔍 Logs do Kafka: cd docker && docker-compose logs -f kafka"
echo ""
echo "🌐 Links rápidos:"
echo "   📊 Dashboard: http://localhost:8501"
echo "   ⚙️  Airflow: http://localhost:8080"
echo "   🔗 API Stats: http://localhost:5000/api/stats"
echo "   💾 Cache Data: http://localhost:5000/api/cache"
