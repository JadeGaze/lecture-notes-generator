terraform {
  required_providers {
    yandex = {
      source  = "yandex-cloud/yandex"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}
