output "connection_name" {
  value = google_sql_database_instance.main.connection_name
}

output "database_url_secret" {
  value = google_secret_manager_secret.database_url.secret_id
}

output "gemini_evaluator_api_key_secret" {
  value = google_secret_manager_secret.gemini_evaluator_api_key.secret_id
}

output "gemini_api_key_secret" {
  value = google_secret_manager_secret.gemini_api_key.secret_id
}

output "google_oauth_secrets" {
  value = { client_id = google_secret_manager_secret.google_oauth["google-oauth-client-id"].secret_id, client_secret = google_secret_manager_secret.google_oauth["google-oauth-client-secret"].secret_id }
}

output "firestore_database" {
  value = google_firestore_database.inbox.name
}
