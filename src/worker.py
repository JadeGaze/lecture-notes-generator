import os
import json
import tempfile
import subprocess
import requests
import boto3

from fastapi import FastAPI
from yandex_cloud_ml_sdk import YCloudML
from botocore.client import Config
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from db import update_task, get_task_by_id, logger

app = FastAPI()

print("Worker HTTP service started", flush=True)


def get_yandex_disk_download_url(public_url: str) -> str:
    """Получить прямую ссылку для скачивания файла с Яндекс Диска."""
    # Если это уже download-ссылка
    if 'downloader.disk' in public_url or 'download' in public_url.lower():
        logger.info(f"Using direct download URL: {public_url}")
        return public_url
    
    # Если это 360.yandex.ru - нужно получить download ссылку
    if '360.yandex' in public_url or 'disk.360.yandex' in public_url:
        logger.info(f"360.yandex URL detected, extracting download link from page")
        try:
            # Загружаем страницу
            page_response = requests.get(public_url, timeout=10)
            page_response.raise_for_status()
            page_html = page_response.text
            
            # Ищем download ссылку в HTML
            # Обычно она в виде: https://downloader.disk.360.yandex.ru/...
            import re
            download_match = re.search(r'(https://downloader\.disk\.360\.yandex\.[^"\']+)', page_html)
            if download_match:
                download_url = download_match.group(1)
                logger.info(f"Found download URL: {download_url}")
                return download_url
            
            # Альтернативный поиск через data атрибуты
            data_match = re.search(r'"download":\s*"([^"]+)"', page_html)
            if data_match:
                download_url = data_match.group(1).replace('\\/', '/')
                logger.info(f"Found download URL in data: {download_url}")
                return download_url
                
            raise Exception("Не удалось найти ссылку на скачивание на странице 360.yandex")
        except Exception as e:
            raise Exception(f"Ошибка парсинга 360.yandex ссылки: {e}. Используйте прямую ссылку на скачивание.")
    
    # Для обычного disk.yandex.ru используем API
    api_url = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
    try:
        response = requests.get(api_url, params={"public_key": public_url}, timeout=10)
        response.raise_for_status()
        return response.json()["href"]
    except requests.exceptions.RequestException as e:
        logger.warning(f"API failed: {e}")
        raise Exception(f"Не удалось получить ссылку на скачивание. Используйте прямую ссылку или обычный disk.yandex.ru")


def get_iam_token():
    """Получить IAM токен через метаданные."""
    response = requests.get(
        "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token",
        headers={"Metadata-Flavor": "Google"}
    )
    response.raise_for_status()
    return response.json()["access_token"]


def recognize_speech_rest_api(audio_path: str, folder_id: str) -> str:
    """Распознать речь через REST API SpeechKit."""
    import time
    
    iam_token = get_iam_token()
    
    # Проверяем размер файла
    file_size = os.path.getsize(audio_path)
    logger.info(f"Audio file size: {file_size / 1024 / 1024:.2f} MB")
    
    # Для коротких аудио (< 1 МБ) используем синхронное API
    if file_size < 1_000_000:
        logger.info("Using synchronous STT API for short audio")
        with open(audio_path, 'rb') as audio_file:
            audio_data = audio_file.read()
        
        response = requests.post(
            "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
            headers={"Authorization": f"Bearer {iam_token}"},
            params={
                "folderId": folder_id,
                "lang": "ru-RU",
                "format": "lpcm",
                "sampleRateHertz": "16000",
            },
            data=audio_data,
            timeout=60
        )
        response.raise_for_status()
        return response.json().get("result", "")
    
    # Для длинных аудио используем упрощенный подход - нарезка на части
    logger.info("Audio is too long for sync API, using chunked processing")
    
    # Простое решение: обработаем только первые 30 секунд для демо
    # В production нужно использовать Long Audio Recognition API с S3
    logger.warning("Processing only first 30 seconds of audio (demo limitation)")
    
    # Создаем короткий файл (первые 30 сек)
    short_audio = tempfile.mktemp(suffix=".wav")
    subprocess.run([
        "ffmpeg", "-y", "-i", audio_path,
        "-t", "30",  # Первые 30 секунд
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        short_audio
    ], check=True, capture_output=True)
    
    try:
        with open(short_audio, 'rb') as audio_file:
            audio_data = audio_file.read()
        
        response = requests.post(
            "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
            headers={"Authorization": f"Bearer {iam_token}"},
            params={
                "folderId": folder_id,
                "lang": "ru-RU",
                "format": "lpcm",
                "sampleRateHertz": "16000",
            },
            data=audio_data,
            timeout=60
        )
        response.raise_for_status()
        result = response.json().get("result", "")
        return result + "\n\n[Обработана только начальная часть аудио]"
    finally:
        if os.path.exists(short_audio):
            os.remove(short_audio)


def download_video(url: str, output_path: str):
    """Скачать видеофайл по URL."""
    logger.info(f"Скачивание видео: {url}")
    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()
    
    # Проверяем Content-Type
    content_type = response.headers.get('Content-Type', '')
    logger.info(f"Content-Type: {content_type}")
    
    if 'text/html' in content_type:
        raise Exception(f"URL вернул HTML вместо видео. Возможно, это не прямая ссылка на файл.")
    
    total_size = 0
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                total_size += len(chunk)
    
    logger.info(f"Видео сохранено: {output_path}, размер: {total_size / 1024 / 1024:.2f} MB")
    
    # Проверяем что файл не пустой
    if total_size < 1000:
        raise Exception(f"Скачанный файл слишком маленький ({total_size} байт). Возможно, ссылка неправильная.")


def extract_audio(video_path: str, audio_path: str):
    """Извлечь аудиодорожку из видео с помощью FFmpeg."""
    logger.info(f"Извлечение аудио из {video_path}")
    
    # Сначала проверим информацию о файле
    try:
        probe_result = subprocess.run([
            "ffmpeg", "-i", video_path
        ], capture_output=True, text=True)
        logger.info(f"FFmpeg probe output: {probe_result.stderr[:500]}")
    except Exception as e:
        logger.warning(f"Probe failed: {e}")
    
    # Извлекаем аудио
    result = subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-vn",  # без видео
        "-acodec", "pcm_s16le",  # формат аудио
        "-ar", "16000",  # частота дискретизации
        "-ac", "1",  # моно
        audio_path
    ], capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error(f"FFmpeg stderr: {result.stderr}")
        logger.error(f"FFmpeg stdout: {result.stdout}")
        raise Exception(f"FFmpeg failed with code {result.returncode}: {result.stderr[:500]}")
    
    logger.info(f"Аудио сохранено: {audio_path}")


def generate_pdf(title: str, notes: str, output_path: str):
    """Создать PDF-документ с конспектом."""
    # Регистрируем шрифты с кириллицей (иначе будут "квадратики")
    # В образе ставим fonts-dejavu-core, путь обычно такой:
    # /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
        base_font = "DejaVuSans"
        title_font = "DejaVuSans-Bold"
    except Exception as e:
        logger.warning(f"Не удалось зарегистрировать DejaVuSans шрифты для PDF: {e}")
        base_font = "Helvetica"
        title_font = "Helvetica-Bold"

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=title_font,
        fontSize=18,
        spaceAfter=30,
        alignment=1  # центрирование
    )
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontName=base_font,
        fontSize=12,
        leading=16,
        spaceAfter=12
    )
    
    story = []
    
    # Заголовок (название лекции)
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 20))
    
    # Конспект (разбиваем на параграфы)
    for paragraph in notes.split('\n\n'):
        if paragraph.strip():
            story.append(Paragraph(paragraph.strip(), body_style))
            story.append(Spacer(1, 10))
    
    doc.build(story)
    logger.info(f"PDF создан: {output_path}")


def process_one_message():
    """Обработать одно сообщение из очереди."""
    logger.info("Processing queue messages...")
    
    sqs = boto3.session.Session().client(
        service_name='sqs',
        endpoint_url='https://message-queue.api.cloud.yandex.net',
        region_name='ru-central1',
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY")
    )
    
    s3 = boto3.client(
        's3',
        endpoint_url='https://storage.yandexcloud.net',
        region_name='ru-central1',
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        config=Config(signature_version='s3v4')
    )

    sdk = YCloudML(folder_id=os.environ.get("FOLDER_ID"))

    msgs = sqs.receive_message(
        QueueUrl=os.environ.get("QUEUE_URL"),
        MaxNumberOfMessages=1,
        WaitTimeSeconds=5,  # Уменьшаем ожидание до 5 сек
    ).get("Messages", [])
    
    if not msgs:
        logger.info("No messages in queue")
        return {"status": "no_messages"}

    for m in msgs:
        task_id = json.loads(m["Body"])["task_id"]
        video_path = None
        audio_path = None
        pdf_path = None
        
        try:
            logger.info(f"Обработка задания: {task_id}")
            update_task(task_id, status="В обработке")
            
            # Получить данные задания из БД
            task = get_task_by_id(task_id)
            if not task:
                raise Exception(f"Задание {task_id} не найдено в БД")
            
            title = task.get("title", "Конспект лекции")
            video_url = task.get("video_url")
            
            if not video_url:
                raise Exception("URL видео не указан")
            
            # Создать временные файлы
            video_path = tempfile.mktemp(suffix=".mp4")
            audio_path = tempfile.mktemp(suffix=".wav")
            pdf_path = tempfile.mktemp(suffix=".pdf")
            
            # 1. Проверить и получить прямую ссылку с Яндекс Диска
            logger.info(f"Получение ссылки для скачивания: {video_url}")
            download_url = get_yandex_disk_download_url(video_url)
            
            # 2. Скачать видео
            download_video(download_url, video_path)
            
            # 3. Извлечь аудио
            extract_audio(video_path, audio_path)
            
            # 4. Распознать речь через SpeechKit
            logger.info("Распознавание речи...")
            
            # Используем SpeechKit для распознавания аудио
            with open(audio_path, 'rb') as audio_file:
                audio_data = audio_file.read()
            
            # Распознавание через SDK
            try:
                recognizer = sdk.models.speech_recognition("general")
                recognized_result = recognizer.transcribe(audio_data)
                transcript = str(recognized_result)
            except Exception as stt_error:
                logger.warning(f"Ошибка SpeechKit SDK: {stt_error}, пробуем REST API")
                # Fallback на REST API
                transcript = recognize_speech_rest_api(audio_path, os.environ.get("FOLDER_ID"))
            
            logger.info(f"Распознано {len(transcript)} символов")
            
            if not transcript or len(transcript) < 50:
                raise Exception("Не удалось распознать речь из аудио")
            
            # 5. Сгенерировать конспект с помощью YandexGPT
            logger.info("Генерация конспекта...")
            
            prompt = f"""Создай структурированный конспект лекции на основе следующего текста.
            
Требования к конспекту:
- Выдели основные темы и подтемы
- Используй нумерованные и маркированные списки
- Выдели ключевые определения и термины
- Добавь краткое резюме в конце

Текст лекции:
{transcript}"""
            
            try:
                gpt_model = sdk.models.completions("yandexgpt")
                gpt_model = gpt_model.configure(temperature=0.3)
                response = gpt_model.run(prompt)
                notes = str(response.alternatives[0].text)
            except Exception as gpt_error:
                logger.warning(f"Ошибка YandexGPT SDK: {gpt_error}, используем транскрипт как конспект")
                notes = transcript
            
            logger.info(f"Конспект сгенерирован: {len(notes)} символов")
            
            # 6. Создать PDF
            generate_pdf(title, notes, pdf_path)
            
            # 7. Загрузить PDF в Object Storage
            key = f"{task_id}.pdf"
            s3.upload_file(pdf_path, os.environ["BUCKET_NAME"], key)
            logger.info(f"PDF загружен в S3: {key}")
            
            # 8. Обновить статус задания
            update_task(task_id, status="Успешно завершено", pdf_object_key=key)
            logger.info(f"Задание {task_id} успешно завершено")

        except Exception as e:
            logger.error(f"Ошибка обработки задания {task_id}: {e}")
            update_task(task_id, status="Ошибка", error=str(e))
        
        finally:
            # Удалить временные файлы
            for path in [video_path, audio_path, pdf_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass
            
            # Удалить сообщение из очереди
            sqs.delete_message(
                QueueUrl=os.environ.get("QUEUE_URL"),
                ReceiptHandle=m["ReceiptHandle"],
            )
            
            return {"status": "processed", "task_id": task_id}
    
    return {"status": "no_messages"}


@app.get("/")
@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "lecture-notes-worker"}


@app.post("/")
@app.post("/process")
def process_queue():
    """HTTP endpoint для обработки очереди."""
    try:
        result = process_one_message()
        return result
    except Exception as e:
        logger.error(f"Error processing queue: {e}")
        return {"status": "error", "error": str(e)}