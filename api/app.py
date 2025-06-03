from flask import Flask, jsonify, request
import redis
import boto3
import json
import pika
import os
from botocore.exceptions import ClientError, NoCredentialsError

app = Flask(__name__)

# Configurações - CORRIGIDAS para usar nomes dos containers
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'http://minio:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
BUCKET = 'air-quality'

# Configurar Redis com tratamento de erro
try:
    redis_client = redis.StrictRedis(host=REDIS_HOST, port=6379, db=0, decode_responses=True, socket_timeout=5)
    redis_client.ping()
    print(f"✅ Redis conectado em {REDIS_HOST}")
except Exception as e:
    print(f"❌ Erro ao conectar Redis: {e}")
    redis_client = None

# Configurar MinIO com tratamento de erro
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=MINIO_ENDPOINT,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name='us-east-1'
    )
    s3_client.list_buckets()
    print(f"✅ MinIO conectado em {MINIO_ENDPOINT}")
except Exception as e:
    print(f"❌ Erro ao conectar MinIO: {e}")
    s3_client = None

@app.route('/', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'message': 'Air Quality API is running',
        'services': {
            'redis': 'connected' if redis_client else 'disconnected',
            'minio': 'connected' if s3_client else 'disconnected',
        },
        'endpoints': {
            'cache': '/api/cache/<key>',
            'all_cache': '/api/cache',
            'history': '/api/history/<filename>',
            'all_history': '/api/history',
            'alerts': '/api/alerts',
            'stats': '/api/stats'
        }
    })

@app.route('/api/cache/<key>', methods=['GET'])
def get_cache(key):
    """Buscar dados específicos do Redis"""
    if not redis_client:
        return jsonify({'error': 'Redis not connected'}), 503
    
    try:
        data = redis_client.hgetall(key)
        if not data:
            return jsonify({'error': 'Key not found'}), 404
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cache', methods=['GET'])
def get_all_cache():
    """Buscar todos os dados do Redis"""
    if not redis_client:
        return jsonify({'error': 'Redis not connected'}), 503
    
    try:
        keys = redis_client.keys('sensor:*')
        
        if not keys:
            return jsonify({'message': 'No cached data found', 'data': []})
        
        data = []
        for key in keys:
            sensor_data = redis_client.hgetall(key)
            sensor_data['cache_key'] = key
            data.append(sensor_data)
        
        return jsonify({
            'total_records': len(data),
            'data': data
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history/<filename>', methods=['GET'])
def get_history(filename):
    """Buscar dados históricos específicos do MinIO"""
    if not s3_client:
        return jsonify({'error': 'MinIO not connected'}), 503
    
    try:
        if not filename.endswith('.json'):
            filename += '.json'
        
        obj = s3_client.get_object(Bucket=BUCKET, Key=f"processed/{filename}")
        data = json.loads(obj['Body'].read().decode('utf-8'))
        return jsonify(data)
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return jsonify({'error': 'File not found'}), 404
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_all_history():
    """Listar todos os arquivos históricos do MinIO"""
    if not s3_client:
        return jsonify({'error': 'MinIO not connected'}), 503
    
    try:
        try:
            s3_client.head_bucket(Bucket=BUCKET)
        except ClientError:
            s3_client.create_bucket(Bucket=BUCKET)
            return jsonify({'message': 'Bucket created, no historical data yet', 'files': []})
        
        response = s3_client.list_objects_v2(Bucket=BUCKET, Prefix='processed/')
        
        if 'Contents' not in response:
            return jsonify({'message': 'No historical data found', 'files': []})
        
        files = []
        for obj in response['Contents']:
            files.append({
                'filename': obj['Key'].replace('processed/', ''),
                'size': obj['Size'],
                'last_modified': obj['LastModified'].isoformat()
            })
        
        return jsonify({
            'total_files': len(files),
            'files': files
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Buscar alertas da fila RabbitMQ"""
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, socket_timeout=5)
        )
        channel = connection.channel()
        channel.queue_declare(queue='sensor_alert', durable=True)

        alerts = []
        
        for _ in range(10):
            method_frame, header_frame, body = channel.basic_get(queue='sensor_alert')
            if method_frame:
                try:
                    alert_data = json.loads(body.decode())
                    alerts.append(alert_data)
                    channel.basic_ack(method_frame.delivery_tag)
                except json.JSONDecodeError:
                    alerts.append({'message': body.decode()})
                    channel.basic_ack(method_frame.delivery_tag)
            else:
                break
        
        connection.close()
        
        if alerts:
            return jsonify({
                'total_alerts': len(alerts),
                'alerts': alerts
            })
        else:
            return jsonify({
                'message': 'No alerts in queue',
                'total_alerts': 0,
                'alerts': []
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Estatísticas gerais do sistema"""
    stats = {
        'cache_records': 0,
        'historical_files': 0,
        'pending_alerts': 0,
        'services_status': {
            'redis': 'disconnected',
            'minio': 'disconnected',
            'rabbitmq': 'disconnected'
        }
    }
    
    # Contar registros no Redis
    if redis_client:
        try:
            cache_keys = redis_client.keys('sensor:*')
            stats['cache_records'] = len(cache_keys)
            stats['services_status']['redis'] = 'connected'
        except:
            pass
    
    # Contar arquivos no MinIO
    if s3_client:
        try:
            response = s3_client.list_objects_v2(Bucket=BUCKET, Prefix='processed/')
            stats['historical_files'] = len(response.get('Contents', []))
            stats['services_status']['minio'] = 'connected'
        except:
            pass
    
    # Contar mensagens na fila RabbitMQ
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, socket_timeout=5)
        )
        channel = connection.channel()
        method = channel.queue_declare(queue='sensor_alert', durable=True, passive=True)
        stats['pending_alerts'] = method.method.message_count
        stats['services_status']['rabbitmq'] = 'connected'
        connection.close()
    except:
        pass
    
    return jsonify(stats)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
