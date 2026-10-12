output "image_repository" {
  description = "Push images here: <region>-docker.pkg.dev/<project>/workweave/api@sha256:..."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "service_accounts" {
  value = {
    api       = google_service_account.api.email
    migrate   = google_service_account.migrate.email
    cleanup   = google_service_account.cleanup.email
    scheduler = google_service_account.scheduler.email
  }
}

output "hosting_site_id" {
  value = google_firebase_hosting_site.site.site_id
}

output "hosting_url" {
  value = google_firebase_hosting_site.site.default_url
}

output "apis" {
  description = "Enabled services (for depends_on in other modules)."
  value       = [for s in google_project_service.apis : s.service]
}
