output "site_url" {
  value = module.platform.hosting_url
}

output "image_repository" {
  value = module.platform.image_repository
}

output "sql_connection_name" {
  value = module.data.connection_name
}

output "api_url" {
  value = try(module.runtime[0].api_url, null)
}

output "service_accounts" {
  value = module.platform.service_accounts
}
