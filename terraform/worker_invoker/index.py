import os
import json


def handler(event, context):
    """Вызывает worker контейнер через HTTP."""
    import requests
    
    container_id = os.environ['CONTAINER_ID']
    
    # Правильный URL для вызова Serverless Container
    # Формат: https://<container_id>.containers.yandexcloud.net/
    url = f'https://{container_id}.containers.yandexcloud.net/'
    
    print(f"Invoking worker container: {url}")
    print(f"Container ID: {container_id}")
    
    try:
        # Вызываем контейнер (POST для обработки)
        print("Sending POST request...")
        response = requests.post(url, timeout=600, json={})
        
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text[:500]}")  # Первые 500 символов
        
        return {
            'statusCode': response.status_code,
            'body': response.text
        }
    except requests.exceptions.Timeout as e:
        error_msg = f"Timeout calling container: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 504,
            'body': json.dumps({'error': error_msg})
        }
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 503,
            'body': json.dumps({'error': error_msg})
        }
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': error_msg})
        }

