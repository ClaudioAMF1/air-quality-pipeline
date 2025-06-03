import pandas as pd
from kafka import KafkaProducer
import json
import time
import sys
import os

def create_producer():
    """Criar e configurar o producer Kafka otimizado para grandes volumes"""
    try:
        producer = KafkaProducer(
            bootstrap_servers='kafka:9092',
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            retry_backoff_ms=300,
            request_timeout_ms=10000,
            max_in_flight_requests_per_connection=5,  # Aumentado para melhor throughput
            acks='1',  # Reduzido para melhor performance
            batch_size=32768,  # Lotes maiores
            linger_ms=5,       # Aguardar formar lotes
            compression_type='gzip'  # Compressão para reduzir tráfego
        )
        print("✅ Producer Kafka criado com sucesso (otimizado para grandes volumes)!")
        return producer
    except Exception as e:
        print(f"❌ Erro ao criar producer: {e}")
        return None

def load_and_send_data(producer, csv_path, topic='sensor_raw'):
    """Carregar dados completos do CSV e enviar para o Kafka"""
    try:
        print(f"📖 Carregando dataset completo de: {csv_path}")
        data = pd.read_csv(csv_path, sep=';')
        print(f"📊 Dataset carregado: {len(data)} registros")
        
        if len(data) == 0:
            print("❌ Dataset vazio!")
            return
        
        print(f"📅 Período dos dados: {data.iloc[0]['Date']} até {data.iloc[-1]['Date']}")
        
        sent_count = 0
        error_count = 0
        start_time = time.time()
        
        for index, row in data.iterrows():
            # Verificar se dados são válidos
            if pd.isna(row['Date']) or pd.isna(row['Time']):
                error_count += 1
                continue
                
            message = {
                'date': str(row['Date']),
                'time': str(row['Time']),
                'CO': float(row['CO']) if pd.notna(row['CO']) else 0.0,
                'NO2': float(row['NO2']) if pd.notna(row['NO2']) else 0.0,
                'Temperature': float(row['Temperature']) if pd.notna(row['Temperature']) else 0.0,
                'Relative_Humidity': float(row['Relative_Humidity']) if pd.notna(row['Relative_Humidity']) else 0.0,
                'Absolute_Humidity': float(row['Absolute_Humidity']) if pd.notna(row['Absolute_Humidity']) else 0.0,
                'timestamp': time.time(),
                'record_id': index
            }
            
            key = f"{row['Date']}_{row['Time']}"
            
            try:
                # Envio assíncrono para melhor performance
                future = producer.send(topic, key=key, value=message)
                sent_count += 1
                
                # Log de progresso a cada 500 registros
                if sent_count % 500 == 0:
                    elapsed = time.time() - start_time
                    rate = sent_count / elapsed if elapsed > 0 else 0
                    progress = (sent_count / len(data)) * 100
                    print(f"📤 Progresso: {sent_count}/{len(data)} ({progress:.1f}%) - {rate:.1f} msgs/s")
                
                # Pausa mínima para não sobrecarregar
                if sent_count % 100 == 0:
                    time.sleep(0.01)
                    
            except Exception as e:
                error_count += 1
                if error_count % 100 == 0:
                    print(f"❌ Erros acumulados: {error_count}")
        
        print("🔄 Aguardando confirmação de todas as mensagens...")
        producer.flush()  # Garantir que todas as mensagens foram enviadas
        
        elapsed = time.time() - start_time
        final_rate = sent_count / elapsed if elapsed > 0 else 0
        
        print(f"✅ INGESTÃO CONCLUÍDA!")
        print(f"📊 Total enviado: {sent_count} registros")
        print(f"❌ Erros: {error_count} registros")
        print(f"⏱️ Tempo total: {elapsed:.2f} segundos")
        print(f"⚡ Taxa média: {final_rate:.1f} mensagens/segundo")
        
    except Exception as e:
        print(f"❌ Erro durante o processamento: {e}")
    finally:
        producer.close()

def main():
    """Função principal"""
    csv_path = '../data/AirQualityUCI_Treated.csv'
    
    if not os.path.exists(csv_path):
        print(f"❌ Arquivo não encontrado: {csv_path}")
        print("📝 Certifique-se de que o arquivo AirQualityUCI_Treated.csv está na pasta data/")
        return
    
    # Verificar tamanho do arquivo
    file_size = os.path.getsize(csv_path) / (1024 * 1024)  # MB
    print(f"📁 Tamanho do arquivo: {file_size:.2f} MB")
    
    producer = create_producer()
    if producer is None:
        return
    
    load_and_send_data(producer, csv_path)

if __name__ == "__main__":
    main()