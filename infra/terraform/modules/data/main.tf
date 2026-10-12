# Cloud SQL for PostgreSQL 16 (+ pgvector, enabled by the migration job), the app database/user,
# and the secrets the runtime reads. No secret value is stored in Terraform state:
#   - the DB password is an ephemeral random value written with write-only arguments;
#   - the Gemini API key secret is created empty; add its value out of band:
#       printf %s "$KEY" | gcloud secrets versions add gemini-api-key --data-file=-

terraform {
  required_providers {
    google = { source = "hashicorp/google" }
    random = { source = "hashicorp/random" }
  }
}

resource "google_sql_database_instance" "main" {
  project             = var.project_id
  name                = "workweave-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = true

  settings {
    tier = var.tier
    # Must be explicit: PostgreSQL 16 defaults to ENTERPRISE_PLUS, which rejects shared-core tiers.
    edition                     = "ENTERPRISE"
    availability_type           = "ZONAL"
    disk_size                   = 10
    disk_autoresize             = true
    deletion_protection_enabled = true
    # Only the Cloud SQL connector/Auth Proxy may connect (Cloud Run's built-in connection uses it).
    connector_enforcement = "REQUIRED"
    user_labels           = var.labels

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "18:00" # UTC = 02:00 Asia/Manila
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 7
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      # Public IP with NO authorized networks: reachable only through the connector (IAM-checked).
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = false
      record_client_address   = false
    }

    password_validation_policy {
      enable_password_policy      = true
      min_length                  = 16
      disallow_username_substring = true
    }

    maintenance_window {
      day  = 7  # Sunday
      hour = 18 # UTC
    }
  }

  lifecycle {
    # Autoresize grows the disk; don't let Terraform try to shrink it back.
    ignore_changes = [settings[0].disk_size]
  }
}

resource "google_sql_database" "app" {
  project         = var.project_id
  name            = "workweave"
  instance        = google_sql_database_instance.main.name
  deletion_policy = "ABANDON"
}

ephemeral "random_password" "db" {
  length  = 32
  special = false # URL-safe: it's embedded in DATABASE_URL
}

resource "google_sql_user" "app" {
  project  = var.project_id
  name     = "workweave"
  instance = google_sql_database_instance.main.name
  # Write-only (Terraform >= 1.11): never stored in state. Bump the version to rotate.
  password_wo         = ephemeral.random_password.db.result
  password_wo_version = var.db_password_version
  deletion_policy     = "ABANDON"
}

# ---------------------------------------------------------------- secrets
resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "database-url"
  labels    = var.labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  # Cloud Run mounts the instance socket at /cloudsql/<connection name>.
  secret_data_wo         = "postgresql+psycopg://${google_sql_user.app.name}:${ephemeral.random_password.db.result}@/${google_sql_database.app.name}?host=/cloudsql/${google_sql_database_instance.main.connection_name}"
  secret_data_wo_version = tostring(var.db_password_version)
}

resource "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project_id
  secret_id = "gemini-api-key"
  labels    = var.labels
  replication {
    auto {}
  }
}

# Optional paid-tier Gemini key used only for evaluator voice listening (ADR-029). Created empty;
# add a version out of band, like gemini-api-key. Billed to the card, not the trial credits.
resource "google_secret_manager_secret" "gemini_evaluator_api_key" {
  project   = var.project_id
  secret_id = "gemini-api-key-evaluator"
  labels    = var.labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "gemini_evaluator_api_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.gemini_evaluator_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.api_sa}"
}

locals {
  database_url_readers = { api = var.api_sa, migrate = var.migrate_sa, cleanup = var.cleanup_sa }
}

resource "google_secret_manager_secret_iam_member" "database_url" {
  for_each  = local.database_url_readers
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value}"
}

# Only the API reads the Gemini key (it mints single-use voice tokens).
resource "google_secret_manager_secret_iam_member" "gemini_api_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.api_sa}"
}

# ---------------------------------------------------------------- notification inbox (ADR-048)
# Firestore holds only recipient notification projections and read markers; PostgreSQL stays
# authoritative. The dispatcher in the API writes here; nothing else does.
resource "google_firestore_database" "inbox" {
  project                 = var.project_id
  name                    = "(default)"
  location_id             = var.firestore_location
  type                    = "FIRESTORE_NATIVE"
  concurrency_mode        = "PESSIMISTIC"
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"
}

# ---------------------------------------------------------------- Companion calendar sign-in (ADR-052)
# The Google OAuth client the AI engineer's calendar service uses. Created empty; add the values out
# of band, then set calendar_oauth_ready = true:
#   printf %s "$CLIENT_ID"     | gcloud secrets versions add google-oauth-client-id --data-file=-
#   printf %s "$CLIENT_SECRET" | gcloud secrets versions add google-oauth-client-secret --data-file=-
locals {
  google_oauth_secrets = toset(["google-oauth-client-id", "google-oauth-client-secret"])
}

resource "google_secret_manager_secret" "google_oauth" {
  for_each  = local.google_oauth_secrets
  project   = var.project_id
  secret_id = each.value
  labels    = var.labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "google_oauth" {
  for_each  = local.google_oauth_secrets
  project   = var.project_id
  secret_id = google_secret_manager_secret.google_oauth[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.api_sa}"
}
