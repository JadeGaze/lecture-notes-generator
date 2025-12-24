variable "cloud_id" {
  type = string
}

variable "folder_id" {
  type = string
}

variable "yc_token" {
  description = "Токен Yandex Cloud"
  type        = string
  sensitive   = true
}

variable "prefix" {
  type = string
}
