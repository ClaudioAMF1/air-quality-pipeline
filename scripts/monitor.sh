#!/bin/bash

echo "📊 Monitor do Pipeline Air Quality - Dataset Completo"
echo "=================================================="

echo "🔍 Verificando serviços..."
curl -s http://localhost:5000 > /dev/null && echo "✅ API Flask: Ativo" || echo "❌ API Flask: Inativo"
curl -s http://localhost:8501 > /dev/null && echo "✅ Streamlit: Ativo" || echo "❌ Streamlit: Inativo"
curl -s http://localhost:8080 > /dev/null && echo "✅ Airflow: Ativo" || echo "❌ Airflow: Inativo"
curl -s http://localhost:15672 > /dev/null && echo "✅ RabbitMQ: Ativo" || echo "❌ RabbitMQ: Inativo"
curl -s http://localhost:9001 > /dev/null && echo "✅ MinIO: Ativo" || echo "❌ MinIO: Inativo"

echo ""
echo "📊 Status dos containers:"
cd docker && docker-compose ps

echo ""
echo "📈 Estatísticas da API:"
curl -s http://localhost:5000/api/stats | python3 -m json.tool

echo ""
echo "🌐 ACESSE AGORA:"
echo "   📊 Dashboard com dados: http://localhost:8501"
echo "   ⚙️ Airflow: http://localhost:8080 (admin/admin)"
echo "   🔗 API Cache: http://localhost:5000/api/cache"
