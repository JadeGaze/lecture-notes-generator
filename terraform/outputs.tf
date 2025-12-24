output "registry_id" {
  value = yandex_container_registry.registry.id
}


output "api_gateway_url" {
  value = yandex_api_gateway.api.domain
}

output "ydb_endpoint" {
  value = yandex_ydb_database_serverless.ydb.ydb_api_endpoint
}

output "ydb_database_path" {
  value = yandex_ydb_database_serverless.ydb.database_path
}