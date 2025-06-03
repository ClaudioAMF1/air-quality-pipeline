from kafka import KafkaConsumer
from celery import Celery
import redis
import json
import boto3
import pika
import time
import os
from botocore.exceptions import ClientError

# Configurações
KAFKA_SERVER = os.getenv('KAFKA_SERVER', 'kafka:9092')
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
BUCKET = 'air-quality'

# Configurar o Celery
app = Celery('air_quality_tasks', 
             broker=f'redis://{REDIS_HOST}:6379/0',
             backend=f'redis://{REDIS_HOST}:6379/0')

# Configurar o Redis
redis_client = redis.StrictRedis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)

# Configurar o MinIO
s3_client = boto3.client(
    's3',
    endpoint_url=MINIO_ENDPOINT,
    aws_access_key_id=MINIO_ACCESS_KEY,
    aws_secret_access_key=MINIO_SECRET_KEY
)

def setup_minio():
    """Configurar bucket no MinIO"""
    try:
        s3_client.head_bucket(Bucket=BUCKET)
        print(f"✅ Bucket '{BUCKET}' já existe")
    except ClientError:
        try:
            s3_client.create_bucket(Bucket=BUCKET)
            print(f"✅ Bucket '{BUCKET}' criado com sucesso")
        except Exception as e:
            print(f"❌ Erro ao criar bucket: {e}")

def setup_rabbitmq():
    """Configurar fila no RabbitMQ"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST)
        )
        channel = connection.channel()
        channel.queue_declare(queue='sensor_alert', durable=True)
        connection.close()
        print("✅ Fila RabbitMQ configurada")
    except Exception as e:
        print(f"❌ Erro ao configurar RabbitMQ: {e}")

@app.task
def process_sensor_data(data):
    """Processar dados do sensor - Tarefa Celery"""
    try:
        # 1. Armazenar no Redis (cache em tempo real)
        cache_key = f"sensor:{data['date']}:{data['time']}"
        redis_client.hset(cache_key, mapping=data)
        redis_client.expire(cache_key, 3600)  # Expirar em 1 hora
        
        # 2. Verificar alertas críticos
        co_level = float(data.get('CO', 0))
        no2_level = float(data.get('NO2', 0))
        
        if co_level > 10 or no2_level > 200:
            alert_data = {
                'timestamp': time.time(),
                'date': data['date'],
                'time': data['time'],
                'alert_type': 'CRITICAL',
                'CO': co_level,
                'NO2': no2_level,
                'message': f"Níveis críticos detectados! CO: {co_level}, NO2: {no2_level}"
            }
            
            # Enviar alerta para RabbitMQ
            try:
                connection = pika.BlockingConnection(
                    pika.ConnectionParameters(host=RABBITMQ_HOST)
                )
                channel = connection.channel()
                channel.basic_publish(
                    exchange='',
                    routing_key='sensor_alert',
                    body=json.dumps(alert_data),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
                connection.close()
                print(f"🚨 ALERTA ENVIADO: {alert_data['message']}")
            except Exception as e:
                print(f"❌ Erro ao enviar alerta: {e}")
        
        # 3. Armazenar dados históricos no MinIO
        file_key = f"processed/{data['date']}_{data['time']}.json"
        s3_client.put_object(
            Bucket=BUCKET,
            Key=file_key,
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )
        
        print(f"✅ Processado: {data['date']} {data['time']} - CO: {co_level}, NO2: {no2_level}")
        return f"Processado: {cache_key}"
        
    except Exception as e:
        print(f"❌ Erro ao processar dados: {e}")
        return f"Erro: {str(e)}"

def start_consumer():
    """Iniciar o consumer Kafka"""
    print("🚀 Iniciando consumer Kafka...")
    
    setup_minio()
    setup_rabbitmq()
    
    consumer = KafkaConsumer(
        'sensor_raw',
        bootstrap_servers=KAFKA_SERVER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        key_deserializer=lambda x: x.decode('utf-8') if x else None,
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        group_id='air_quality_group'
    )
    
    print("👂 Aguardando mensagens do Kafka...")
    
    try:
        for message in consumer:
            data = message.value
            key = message.key
            
            print(f"📨 Recebido do Kafka: {key}")
            process_sensor_data.delay(data)
            
    except KeyboardInterrupt:
        print("\n🛑 Consumer interrompido pelo usuário")
    except Exception as e:
        print(f"❌ Erro no consumer: {e}")
    finally:
        consumer.close()

if __name__ == "__main__":
    start_consumer()
