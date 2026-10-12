# APIs, image registry, service identities (least privilege) and Firebase Hosting.

terraform {
  required_providers {
    google      = { source = "hashicorp/google" }
    google-beta = { source = "hashicorp/google-beta" }
  }
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "aiplatform.googleapis.com",         # Vertex AI / Agent Platform (server-side Gemini)
    "generativelanguage.googleapis.com", # Gemini Developer API (browser voice ephemeral tokens)
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "firestore.googleapis.com", # notification inbox projection (ADR-048)
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = "workweave"
  format        = "DOCKER"
  description   = "WorkWeave API images (deploys pin a digest)."
  labels        = var.labels

  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "delete-untagged-after-7-days"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s"
    }
  }
  cleanup_policies {
    id     = "keep-10-most-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------- service identities
resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "workweave-api"
  display_name = "WorkWeave API (Cloud Run service runtime)"
}

resource "google_service_account" "migrate" {
  project      = var.project_id
  account_id   = "workweave-migrate"
  display_name = "WorkWeave migrations and catalog activation (Cloud Run job)"
}

resource "google_service_account" "cleanup" {
  project      = var.project_id
  account_id   = "workweave-cleanup"
  display_name = "WorkWeave demo-run cleanup (Cloud Run job)"
}

resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "workweave-scheduler"
  display_name = "Cloud Scheduler: starts the cleanup job"
}

locals {
  # Project-level roles only where no narrower resource-level binding exists.
  project_roles = {
    api_sql    = { member = google_service_account.api.member, role = "roles/cloudsql.client" }
    api_vertex = { member = google_service_account.api.member, role = "roles/aiplatform.user" }
    # Firestore has no per-database IAM binding; the project holds only the inbox database.
    api_inbox   = { member = google_service_account.api.member, role = "roles/datastore.user" }
    migrate_sql = { member = google_service_account.migrate.member, role = "roles/cloudsql.client" }
    cleanup_sql = { member = google_service_account.cleanup.member, role = "roles/cloudsql.client" }
  }
}

resource "google_project_iam_member" "roles" {
  for_each = local.project_roles
  project  = var.project_id
  role     = each.value.role
  member   = each.value.member
}

# ---------------------------------------------------------------- Firebase Hosting (google-beta only)
resource "google_firebase_project" "default" {
  provider   = google-beta
  project    = var.project_id
  depends_on = [google_project_service.apis]
}

resource "google_firebase_web_app" "web" {
  provider     = google-beta
  project      = var.project_id
  display_name = "WorkWeave"
  depends_on   = [google_firebase_project.default]
}

resource "google_firebase_hosting_site" "site" {
  provider = google-beta
  project  = var.project_id
  site_id  = var.site_id
  app_id   = google_firebase_web_app.web.app_id
}
