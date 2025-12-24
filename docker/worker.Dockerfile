#FROM python:3.11-slim
#WORKDIR /src
#RUN apt-get update && apt-get install -y ffmpeg
#COPY src .
#RUN pip install -r requirements.txt
#CMD ["python", "-m", "worker.worker"]

#FROM python:3.11-slim
#
#WORKDIR /src
#
#RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
#
#COPY src/requirements.txt .
#RUN pip install --no-cache-dir -r requirements.txt
#
#COPY src/ .
#
## Важно для импортов
#ENV PYTHONPATH=/src
#
#CMD ["python", "-m", "worker.worker"]

FROM python:3.11-slim
WORKDIR /app

# Устанавливаем ffmpeg + шрифты с кириллицей (для PDF)
RUN apt-get update && apt-get install -y ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY /src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY src/ .

# Запускаем как HTTP-сервис
CMD ["uvicorn", "worker:app", "--host", "0.0.0.0", "--port", "8080"]