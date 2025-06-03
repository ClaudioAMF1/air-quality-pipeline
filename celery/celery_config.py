from celery import Celery
import os

broker_url = os.getenv('CELERY_BROKER', 'redis://redis:6379/0')
result_backend = os.getenv('CELERY_BACKEND', 'redis://redis:6379/0')

task_serializer = 'json'
accept_content = ['json']
result_serializer = 'json'
timezone = 'America/Sao_Paulo'
enable_utc = True

worker_prefetch_multiplier = 1
task_acks_late = True
worker_concurrency = 4
