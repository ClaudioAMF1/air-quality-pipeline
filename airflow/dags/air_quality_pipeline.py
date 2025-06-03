from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
from kafka import KafkaProducer, KafkaConsumer
import redis
import json
import pandas as pd
import boto3
import io
import time
import pika
from botocore.exceptions import ClientError
import os

# Configurações Globais
KAFKA_SERVER = 'kafka:9092'
REDIS_HOST = 'redis'
RABBITMQ_HOST = 'rabbitmq'
MINIO_ENDPOINT = 'http://minio:9000'
MINIO_ACCESS_KEY = 'minioadmin'
MINIO_SECRET_KEY = 'minioadmin'
BUCKET = 'air-quality'

def upload_csv_to_minio():
    """Upload do CSV completo para o MinIO"""
    print("📤 Fazendo upload do CSV completo para MinIO...")
    
    s3 = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY
    )
    
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=BUCKET)
        print(f"✅ Bucket '{BUCKET}' criado")
    
    # Ler arquivo CSV local completo (6500+ registros)
    csv_local_path = '/opt/airflow/data/AirQualityUCI_Treated.csv'
    
    try:
        with open(csv_local_path, 'rb') as file:
            s3.put_object(
                Bucket=BUCKET,
                Key='AirQualityUCI_Treated.csv',
                Body=file.read()
            )
        print("✅ Arquivo CSV completo (6500+ registros) uploaded para MinIO")
        
        # Verificar tamanho do arquivo
        response = s3.head_object(Bucket=BUCKET, Key='AirQualityUCI_Treated.csv')
        size_mb = response['ContentLength'] / (1024 * 1024)
        print(f"📊 Tamanho do arquivo: {size_mb:.2f} MB")
        
    except FileNotFoundError:
        print("❌ Arquivo AirQualityUCI_Treated.csv não encontrado em /opt/airflow/data/")
        print("📝 Certifique-se de que o arquivo está na pasta data/ do projeto")
        raise

def load_csv_to_kafka():
    """Carregar CSV completo do MinIO e enviar para Kafka"""
    print("📤 Carregando CSV completo do MinIO para Kafka...")
    
    s3 = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY
    )

    obj = s3.get_object(Bucket=BUCKET, Key='AirQualityUCI_Treated.csv')
    df = pd.read_csv(io.BytesIO(obj['Body'].read()), sep=';')
    
    print(f"📊 Dataset carregado: {len(df)} registros")
    print(f"📅 Data inicial: {df.iloc[0]['Date']} {df.iloc[0]['Time']}")
    print(f"📅 Data final: {df.iloc[-1]['Date']} {df.iloc[-1]['Time']}")

    producer = KafkaProducer(
        bootstrap_servers=KAFKA_SERVER,
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        batch_size=16384,  # Otimização para grandes volumes
        linger_ms=5,       # Aguardar 5ms para formar batches
        compression_type='gzip'  # Compressão para reduzir tráfego
    )

    sent_count = 0
    batch_size = 50  # Processar em lotes
    
    for _, row in df.iterrows():
        # Verificar se dados são válidos
        if pd.isna(row['Date']) or pd.isna(row['Time']):
            continue
            
        message = {
            'date': str(row['Date']),
            'time': str(row['Time']),
            'CO': float(row['CO']) if pd.notna(row['CO']) else 0.0,
            'NO2': float(row['NO2']) if pd.notna(row['NO2']) else 0.0,
            'Temperature': float(row['Temperature']) if pd.notna(row['Temperature']) else 0.0,
            'Relative_Humidity': float(row['Relative_Humidity']) if pd.notna(row['Relative_Humidity']) else 0.0,
            'Absolute_Humidity': float(row['Absolute_Humidity']) if pd.notna(row['Absolute_Humidity']) else 0.0,
            'timestamp': time.time()
        }
        
        producer.send('sensor_raw', value=message)
        sent_count += 1
        
        # Log de progresso a cada 500 registros
        if sent_count % 500 == 0:
            print(f"📤 Progresso: {sent_count}/{len(df)} registros enviados ({sent_count/len(df)*100:.1f}%)")
        
        # Pausa menor para processar grandes volumes
        if sent_count % batch_size == 0:
            time.sleep(0.1)  # Pausa a cada lote

    producer.flush()
    producer.close()
    print(f"✅ TOTAL ENVIADO: {sent_count} registros de {len(df)} disponíveis")

def consume_from_kafka(**context):
    """Consumir TODAS as mensagens do Kafka"""
    print("👂 Consumindo TODAS as mensagens do Kafka...")
    
    consumer = KafkaConsumer(
        'sensor_raw',
        bootstrap_servers=KAFKA_SERVER,
        value_deserializer=lambda x: json.loads(x.decode('utf-8')),
        auto_offset_reset='earliest',
        enable_auto_commit=True,
        consumer_timeout_ms=120000,  # 2 minutos timeout
        max_poll_records=500,        # Mais registros por poll
        fetch_min_bytes=8192        # Otimização
    )

    data_list = []
    start_time = time.time()
    total_expected = 6500  # Aproximadamente
    
    print(f"🎯 Meta: Consumir todos os ~{total_expected} registros")
    
    for msg in consumer:
        data = msg.value
        data_list.append(data)
        
        # Log de progresso a cada 100 registros
        if len(data_list) % 100 == 0:
            elapsed = time.time() - start_time
            rate = len(data_list) / elapsed if elapsed > 0 else 0
            progress = (len(data_list) / total_expected) * 100
            print(f"📨 Progresso: {len(data_list)}/{total_expected} ({progress:.1f}%) - {rate:.1f} msgs/s")

        # Processar em lotes muito maiores para capturar tudo
        if len(data_list) >= 6500:  # Aumentado para pegar tudo
            print("🎯 Limite de segurança atingido, processando lote")
            break
    
    # Se não chegou no limite, aguardar mais um pouco para pegar registros restantes
    if len(data_list) < total_expected:
        print(f"⏳ Aguardando mais registros... Atual: {len(data_list)}")
        additional_timeout = 30  # 30 segundos adicionais
        end_time = time.time() + additional_timeout
        
        while time.time() < end_time:
            try:
                msg_batch = consumer.poll(timeout_ms=5000, max_records=100)
                if msg_batch:
                    for tp, messages in msg_batch.items():
                        for msg in messages:
                            data = msg.value
                            data_list.append(data)
                            if len(data_list) % 100 == 0:
                                print(f"📨 Total acumulado: {len(data_list)} registros")
                else:
                    print("⏸️ Sem mais mensagens, finalizando...")
                    break
            except Exception as e:
                print(f"⚠️ Timeout ou fim das mensagens: {e}")
                break

    consumer.close()
    context['ti'].xcom_push(key='sensor_data', value=data_list)
    
    elapsed = time.time() - start_time
    print(f"✅ CONSUMO TOTAL CONCLUÍDO:")
    print(f"📊 Registros consumidos: {len(data_list)}")
    print(f"⏱️ Tempo total: {elapsed:.2f}s")
    print(f"⚡ Taxa média: {len(data_list)/elapsed:.1f} msgs/s")
    
    if len(data_list) >= total_expected * 0.9:  # 90% ou mais
        print("🎉 SUCESSO: Praticamente todo o dataset foi consumido!")
    else:
        print(f"⚠️ ATENÇÃO: Apenas {len(data_list)} de ~{total_expected} registros consumidos")

def process_and_store_to_minio_and_redis(**context):
    """Processar e armazenar TODOS os dados"""
    print("⚙️ Processando e armazenando TODOS os dados...")
    
    data_list = context['ti'].xcom_pull(key='sensor_data', task_ids='consume_from_kafka')
    
    if not data_list:
        print("⚠️ Nenhum dado recebido do Kafka")
        return

    total_records = len(data_list)
    print(f"📊 Total a processar: {total_records} registros")

    r = redis.StrictRedis(host=REDIS_HOST, port=6379, db=0)
    s3 = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY
    )

    processed_count = 0
    redis_pipeline = r.pipeline()
    start_time = time.time()
    
    # Limpar cache anterior se necessário
    print("🧹 Limpando cache anterior...")
    old_keys = r.keys('sensor:*')
    if old_keys:
        r.delete(*old_keys)
        print(f"🗑️ Removidas {len(old_keys)} chaves antigas")
    
    for i, data in enumerate(data_list):
        key = f"sensor:{data['date']}:{data['time']}"
        
        # Redis: usar pipeline para melhor performance
        redis_pipeline.hset(key, mapping=data)
        redis_pipeline.expire(key, 86400)  # 24 horas
        
        # MinIO: armazenar arquivo JSON
        s3.put_object(
            Bucket=BUCKET,
            Key=f"processed/{data['date']}_{data['time']}.json",
            Body=json.dumps(data, indent=2),
            ContentType='application/json'
        )

        processed_count += 1
        
        # Executar pipeline Redis a cada 50 registros
        if (i + 1) % 50 == 0:
            redis_pipeline.execute()
            redis_pipeline = r.pipeline()
            
            # Log de progresso
            elapsed = time.time() - start_time
            rate = processed_count / elapsed if elapsed > 0 else 0
            progress = (processed_count / total_records) * 100
            print(f"💾 Progresso: {processed_count}/{total_records} ({progress:.1f}%) - {rate:.1f} rec/s")

    # Executar pipeline final
    if len(redis_pipeline.command_stack) > 0:
        redis_pipeline.execute()

    elapsed = time.time() - start_time
    print(f"✅ PROCESSAMENTO TOTAL CONCLUÍDO:")
    print(f"📊 Registros processados: {processed_count}")
    print(f"💾 Redis: {processed_count} chaves criadas")
    print(f"📁 MinIO: {processed_count} arquivos JSON salvos")
    print(f"⏱️ Tempo total: {elapsed:.2f} segundos")
    print(f"⚡ Taxa média: {processed_count/elapsed:.1f} registros/segundo")

def send_alert_to_rabbitmq(**context):
    """Enviar alertas críticos para RabbitMQ (otimizado para grandes volumes)"""
    print("🚨 Verificando e enviando alertas (grandes volumes)...")
    
    data_list = context['ti'].xcom_pull(key='sensor_data', task_ids='consume_from_kafka')
    
    if not data_list:
        print("⚠️ Nenhum dado recebido para análise de alertas")
        return

    connection = pika.BlockingConnection(pika.ConnectionParameters(host=RABBITMQ_HOST))
    channel = connection.channel()
    channel.queue_declare(queue='sensor_alert', durable=True)

    alert_count = 0
    critical_co_count = 0
    critical_no2_count = 0
    
    for data in data_list:
        co_level = float(data.get('CO', 0))
        no2_level = float(data.get('NO2', 0))
        
        is_critical_co = co_level > 10
        is_critical_no2 = no2_level > 200
        
        if is_critical_co:
            critical_co_count += 1
        if is_critical_no2:
            critical_no2_count += 1
        
        if is_critical_co or is_critical_no2:
            alert = {
                'timestamp': time.time(),
                'date': data['date'],
                'time': data['time'],
                'alert_type': 'CRITICAL',
                'CO': co_level,
                'NO2': no2_level,
                'critical_co': is_critical_co,
                'critical_no2': is_critical_no2,
                'message': f"🚨 CRÍTICO! CO: {co_level} {'(ALTO)' if is_critical_co else '(OK)'}, NO2: {no2_level} {'(ALTO)' if is_critical_no2 else '(OK)'}"
            }
            
            channel.basic_publish(
                exchange='', 
                routing_key='sensor_alert', 
                body=json.dumps(alert),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            alert_count += 1

    connection.close()
    
    print(f"✅ ANÁLISE DE ALERTAS CONCLUÍDA:")
    print(f"📊 Total analisado: {len(data_list)} registros")
    print(f"🚨 Alertas críticos: {alert_count}")
    print(f"⚠️ CO crítico (>10): {critical_co_count} ocorrências")
    print(f"⚠️ NO2 crítico (>200): {critical_no2_count} ocorrências")

# Definição da DAG
default_args = {
    'owner': 'admin',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=3),
}

with DAG(
    dag_id='air_quality_pipeline_full',
    default_args=default_args,
    description='Pipeline completo Air Quality com dataset de 6500+ registros',
    schedule_interval=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['air-quality', 'big-data', 'full-dataset'],
) as dag:

    t1 = PythonOperator(
        task_id='upload_csv_to_minio',
        python_callable=upload_csv_to_minio,
    )

    t2 = PythonOperator(
        task_id='load_csv_to_kafka',
        python_callable=load_csv_to_kafka,
    )

    t3 = PythonOperator(
        task_id='consume_from_kafka',
        python_callable=consume_from_kafka,
    )

    t4 = PythonOperator(
        task_id='process_and_store_to_minio_and_redis',
        python_callable=process_and_store_to_minio_and_redis,
    )

    t5 = PythonOperator(
        task_id='send_alert_to_rabbitmq',
        python_callable=send_alert_to_rabbitmq,
    )

    t1 >> t2 >> t3 >> [t4, t5]