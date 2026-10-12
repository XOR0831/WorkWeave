output "project_id" {
  value = google_project.main.project_id
}

output "project_number" {
  value = google_project.main.number
}

output "state_bucket" {
  value = google_storage_bucket.tfstate.name
}
