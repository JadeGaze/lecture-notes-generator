#FROM python:3.11-slim
#WORKDIR /src
#COPY src .
#RUN pip install -r requirements.txt
#CMD ["uvicorn", "web.main:src", "--host", "0.0.0.0", "--port", "8080"]

#FROM python:3.11-slim
#WORKDIR /src
#COPY src .
#RUN pip install -r requirements.txt
#CMD ["uvicorn", "web.main:src", "--host", "0.0.0.0", "--port", "8080"]

FROM python:3.11-slim
WORKDIR /app

# Копируем зависимости
COPY /src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY src/ .

# Создаем папку templates если нужно
RUN mkdir -p templates && \
    if [ -d "templates" ]; then mv templates/* ./templates/ 2>/dev/null || true; fi

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]