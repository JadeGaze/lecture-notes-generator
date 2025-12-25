from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
import uuid
import os
import boto3
from botocore.client import Config

from db import save_task, list_tasks
from tasks_queue import enqueue

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/tasks")
def create_task(title: str = Form(...), video_url: str = Form(...)):
    task_id = str(uuid.uuid4())
    print("task_id=" + task_id)
    save_task(task_id, title, video_url)
    enqueue(task_id)
    return RedirectResponse("/tasks", status_code=303)


@app.get("/tasks")
def tasks(request: Request):
    result = list_tasks()
    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "tasks": result},
    )


@app.get("/download/{object_key}")
def download_pdf(object_key: str):
    try:
        s3 = boto3.client(
            's3',
            endpoint_url='https://storage.yandexcloud.net',
            region_name='ru-central1',
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            config=Config(signature_version='s3v4')
        )
        
        presigned_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': os.environ.get("BUCKET_NAME"),
                'Key': object_key
            },
            ExpiresIn=3600  # 1 час
        )
        
        return RedirectResponse(presigned_url)
    except Exception as e:
        return {"error": str(e)}, 500
