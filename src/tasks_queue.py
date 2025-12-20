import os
import json
import boto3


def enqueue(task_id: str):
    sqs = boto3.session.Session().client(
        service_name='sqs',
        endpoint_url='https://message-queue.api.cloud.yandex.net',
        region_name='ru-central1',
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    sqs.send_message(
        QueueUrl=os.environ.get("QUEUE_URL"),
        MessageBody=json.dumps({"task_id": task_id}),
    )
