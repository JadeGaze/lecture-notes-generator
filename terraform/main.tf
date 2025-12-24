provider "yandex" {
  cloud_id  = var.cloud_id
  token     = var.yc_token
  folder_id = var.folder_id
}

# --------------------
# Service Account
# --------------------
resource "yandex_iam_service_account" "sa" {
  name = "${var.prefix}-sa"
}

resource "yandex_resourcemanager_folder_iam_binding" "editor" {
  folder_id = var.folder_id
  role      = "editor"
  members   = ["serviceAccount:${yandex_iam_service_account.sa.id}"]
}

# Ключ сервисного аккаунта
resource "yandex_iam_service_account_key" "sa_key" {
  service_account_id = yandex_iam_service_account.sa.id
  description        = "Key for object storage access"
}

resource "yandex_iam_service_account_static_access_key" "sa_static_key" {
  service_account_id = yandex_iam_service_account.sa.id
  description        = "Static access key for Object Storage"
}

# Роли сервисного аккаунта
resource "yandex_resourcemanager_folder_iam_member" "sa_roles" {
  for_each = toset([
    "editor",
    "storage.editor",
    "ydb.editor",
    "serverless.containers.invoker",
    "ymq.writer",
    "ai.speechkit-stt.user",
    "ai.languageModels.user",
  ])

  folder_id = var.folder_id
  role      = each.value
  member    = "serviceAccount:${yandex_iam_service_account.sa.id}"
}

# Также добавьте права на чтение из очереди для worker-контейнера:
resource "yandex_resourcemanager_folder_iam_member" "ymq_reader" {
  folder_id = var.folder_id
  role      = "ymq.reader"
  member    = "serviceAccount:${yandex_iam_service_account.sa.id}"
}

# Или можно использовать одну binding с несколькими ролями:
resource "yandex_resourcemanager_folder_iam_binding" "ymq_roles" {
  folder_id = var.folder_id
  role      = "ymq.writer"
  members   = ["serviceAccount:${yandex_iam_service_account.sa.id}"]
}

resource "yandex_resourcemanager_folder_iam_binding" "ymq_reader_role" {
  folder_id = var.folder_id
  role      = "ymq.reader"
  members   = ["serviceAccount:${yandex_iam_service_account.sa.id}"]
}

# --------------------
# YDB Serverless
# --------------------
resource "yandex_ydb_database_serverless" "ydb" {
  name      = "${var.prefix}-ydb"
  folder_id = var.folder_id
}

# --------------------
# Message Queue
# --------------------
resource "yandex_message_queue" "queue" {
  name       = "${var.prefix}-queue"
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
}

# --------------------
# Object Storage
# --------------------
resource "yandex_storage_bucket" "bucket" {
  bucket     = "${var.prefix}-pdf-bucket"
  access_key = yandex_iam_service_account_static_access_key.sa_static_key.access_key
  secret_key = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
}

# --------------------
# Container Registry
# --------------------
resource "yandex_container_registry" "registry" {
  name = "${var.prefix}-registry"
}

# --------------------
# Serverless Containers
# --------------------
resource "yandex_serverless_container" "web" {
  name               = "${var.prefix}-web"
  service_account_id = yandex_iam_service_account.sa.id

  image {
    url = "cr.yandex/${yandex_container_registry.registry.id}/web:latest"
    environment = {
      YDB_ENDPOINT          = yandex_ydb_database_serverless.ydb.ydb_api_endpoint
      YDB_DATABASE          = yandex_ydb_database_serverless.ydb.database_path
      QUEUE_URL             = yandex_message_queue.queue.id
      FOLDER_ID             = var.folder_id
      BUCKET_NAME           = yandex_storage_bucket.bucket.bucket
      AWS_ACCESS_KEY_ID     = yandex_iam_service_account_static_access_key.sa_static_key.access_key
      AWS_SECRET_ACCESS_KEY = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
    }
  }
  memory = 512
}

resource "yandex_serverless_container" "worker" {
  name               = "${var.prefix}-worker"
  service_account_id = yandex_iam_service_account.sa.id

  image {
    url = "cr.yandex/${yandex_container_registry.registry.id}/worker:latest"
    environment = {
      YDB_ENDPOINT          = yandex_ydb_database_serverless.ydb.ydb_api_endpoint
      YDB_DATABASE          = yandex_ydb_database_serverless.ydb.database_path
      QUEUE_URL             = yandex_message_queue.queue.id
      FOLDER_ID             = var.folder_id
      BUCKET_NAME           = yandex_storage_bucket.bucket.bucket
      AWS_ACCESS_KEY_ID     = yandex_iam_service_account_static_access_key.sa_static_key.access_key
      AWS_SECRET_ACCESS_KEY = yandex_iam_service_account_static_access_key.sa_static_key.secret_key
    }
  }

  memory             = 2048
  execution_timeout  = "600s"
  concurrency        = 2
  
  connectivity {
    network_id = ""
  }
}

# --------------------
# Архив с Cloud Function для вызова Worker контейнера
# --------------------
data "archive_file" "worker_invoker" {
  type        = "zip"
  output_path = "${path.module}/worker_invoker.zip"
  source_dir  = "${path.module}/worker_invoker"
}

# --------------------
# Cloud Function для вызова Worker контейнера
# --------------------
resource "yandex_function" "worker_invoker" {
  name               = "${var.prefix}-worker-invoker"
  runtime            = "python312"
  entrypoint         = "index.handler"
  memory             = "128"
  execution_timeout  = "600"  # 10 минут - достаточно для обработки задания
  service_account_id = yandex_iam_service_account.sa.id

  environment = {
    CONTAINER_ID = yandex_serverless_container.worker.id
  }

  user_hash = data.archive_file.worker_invoker.output_base64sha256
  content {
    zip_filename = data.archive_file.worker_invoker.output_path
  }
}

# --------------------
# Timer Trigger для вызова Worker
# --------------------
resource "yandex_function_trigger" "worker_timer" {
  name = "${var.prefix}-worker-timer"

  timer {
    cron_expression = "* * * * ? *"
  }

  function {
    id                 = yandex_function.worker_invoker.id
    service_account_id = yandex_iam_service_account.sa.id
  }
}

# --------------------
# API Gateway
# --------------------
resource "yandex_api_gateway" "api" {
  name = "${var.prefix}-api"

  spec = <<EOF
openapi: 3.0.0
info:
  title: Lecture Notes Generator
  version: 1.0.0
paths:
  /:
    get:
      x-yc-apigateway-integration:
        type: serverless_containers
        container_id: ${yandex_serverless_container.web.id}
        service_account_id: ${yandex_iam_service_account.sa.id}
  /tasks:
    get:
      x-yc-apigateway-integration:
        type: serverless_containers
        container_id: ${yandex_serverless_container.web.id}
        service_account_id: ${yandex_iam_service_account.sa.id}
    post:
      x-yc-apigateway-integration:
        type: serverless_containers
        container_id: ${yandex_serverless_container.web.id}
        service_account_id: ${yandex_iam_service_account.sa.id}
  /download/{object_key}:
    get:
      parameters:
        - name: object_key
          in: path
          required: true
          schema:
            type: string
      x-yc-apigateway-integration:
        type: serverless_containers
        container_id: ${yandex_serverless_container.web.id}
        service_account_id: ${yandex_iam_service_account.sa.id}
EOF
}
