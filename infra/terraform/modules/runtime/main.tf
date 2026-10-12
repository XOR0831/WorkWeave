# Cloud Run: the API service and two jobs from the SAME image (pinned by digest), plus the
# schedule that runs demo cleanup. The API is public because Firebase Hosting's /api/** rewrite
# calls it as an unauthenticated request; the app enforces its own session and permission checks.

terraform {
  required_providers {
    google = { source = "hashicorp/google" }
  }
}

locals {
  socket = "/cloudsql"
  common_env = {
    WORKWEAVE_ENV = "release"
    COOKIE_SECURE = "true"
    # Hybrid Gemini (ADR-026): server-side calls through Vertex AI with the service account.
    GOOGLE_GENAI_USE_VERTEXAI = "true"
    GOOGLE_CLOUD_PROJECT      = var.project_id
    GOOGLE_CLOUD_LOCATION     = var.vertex_location
  }
  # The API service only (ADR-052): the graph host and calendar service run in the same container
  # on 127.0.0.1 (backend/start.sh); notifications go to Firestore through the in-process dispatcher.
  graph_host = "http://127.0.0.1:8123"
  service_env = merge(var.gemini_models, {
    TUTOR_ENGINE            = "langgraph"
    LANGGRAPH_URL           = local.graph_host
    COMPANION_ENGINE        = "langgraph"
    LANGGRAPH_COMPANION_URL = local.graph_host
    LANGGRAPH_HANDOVER_URL  = local.graph_host
    LANGGRAPH_EXIT_KT_URL   = local.graph_host
    AI_GEMINI               = var.ai_gemini
    GRAPH_THREAD_TTL_HOURS  = tostring(var.graph_thread_ttl_hours)
    NOTIFICATIONS           = "firestore"
    FIRESTORE_PROJECT       = var.project_id
    DISPATCHER_IN_PROCESS   = "true"
    # Uploaded source originals (the text itself is stored in PostgreSQL); the image's /srv is read-only
    # for the app user, and there is no Cloud Storage adapter yet.
    LOCAL_STORAGE_DIR = "/tmp/workweave-storage"
    # Calendar sign-in through the API; only the configured test account can connect.
    COMPANION_CALENDAR       = tostring(var.calendar_oauth_ready)
    CALENDAR_CONNECT_URL     = "/api/calendar/auth/google"
    GOOGLE_REDIRECT_URI      = "${var.public_origin}/api/calendar/auth/google/callback"
    WORKWEAVE_EMPLOYEE_EMAIL = var.calendar_account_email
    # Connections must stay under the Cloud SQL tier's limit (db-f1-micro ~25): API 4 + 2, graph host
    # 4 graphs x (1 + 2) + 3 checkpoint connections = 21 per instance, plus a job while it runs.
    DB_POOL_SIZE    = "4"
    DB_MAX_OVERFLOW = "2"
  })
}

resource "google_cloud_run_v2_service" "api" {
  project             = var.project_id
  name                = "workweave-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true
  labels              = var.labels

  template {
    service_account                  = var.api_sa
    max_instance_request_concurrency = 40
    # Firebase Hosting ends rewritten requests at 60 s; longer runs (ingestion) are background work.
    timeout = "300s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = var.api_memory
        }
        # The notification dispatcher, graph-thread expiry and calendar sign-in live in the instance
        # between requests, so CPU stays allocated (instance-based billing) unless switched off.
        cpu_idle          = !var.cpu_always_allocated
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = merge(local.common_env, local.service_env)
        # Demo caps live in the database (demo_usage_limits, ADR-029) and are changed with the CLI.
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.database_url_secret
            version = "latest"
          }
        }
      }

      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = var.gemini_api_key_secret
            version = "latest"
          }
        }
      }

      # Optional paid-tier key for evaluator voice listening (ADR-029). Only wired once a version
      # exists (Cloud Run refuses a secret with no versions): set evaluator_voice_key_ready = true.
      dynamic "env" {
        for_each = var.evaluator_voice_key_ready ? [1] : []
        content {
          name = "GEMINI_EVALUATOR_API_KEY"
          value_source {
            secret_key_ref {
              secret  = var.gemini_evaluator_api_key_secret
              version = "latest"
            }
          }
        }
      }

      # The Companion calendar's Google OAuth client, once its secret versions exist.
      dynamic "env" {
        for_each = var.calendar_oauth_ready ? { GOOGLE_CLIENT_ID = var.google_oauth_secrets.client_id, GOOGLE_CLIENT_SECRET = var.google_oauth_secrets.client_secret } : {}
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = local.socket
      }

      # The API starts once the graphs have loaded (backend/start.sh), so allow about two minutes.
      startup_probe {
        http_get {
          path = "/api/health"
        }
        initial_delay_seconds = 5
        period_seconds        = 3
        failure_threshold     = 40
      }

      liveness_probe {
        http_get {
          path = "/api/health"
        }
        period_seconds = 30
      }
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [var.sql_connection_name]
      }
    }
  }
}

# Firebase Hosting rewrites reach the API as public, unauthenticated requests.
resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------- jobs
# Migrations: fresh database -> reviewed baseline + Alembic; otherwise Alembic only. Run on deploy:
#   gcloud run jobs execute workweave-migrate --region <region> --wait
#   (first time also: --args=-m,app.ops.migrate,--activate-reviewed-packs)
resource "google_cloud_run_v2_job" "migrate" {
  project             = var.project_id
  name                = "workweave-migrate"
  location            = var.region
  deletion_protection = true
  labels              = var.labels

  template {
    task_count = 1
    template {
      service_account = var.migrate_sa
      max_retries     = 0
      timeout         = "900s"

      containers {
        image   = var.api_image
        command = ["python"]
        args    = ["-m", "app.ops.migrate"]

        dynamic "env" {
          for_each = { WORKWEAVE_ENV = "release", COOKIE_SECURE = "true" }
          content {
            name  = env.key
            value = env.value
          }
        }

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = var.database_url_secret
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = local.socket
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [var.sql_connection_name]
        }
      }
    }
  }
}

# Demo cleanup: purges expired visitor runs with proof (migration 0004 guards every delete).
resource "google_cloud_run_v2_job" "cleanup" {
  project             = var.project_id
  name                = "workweave-cleanup"
  location            = var.region
  deletion_protection = true
  labels              = var.labels

  template {
    task_count = 1
    template {
      service_account = var.cleanup_sa
      max_retries     = 1
      timeout         = "600s"

      containers {
        image   = var.api_image
        command = ["python"]
        args    = ["-m", "app.workers.cleanup", "--confirm", "--grace-minutes", "60", "--limit", "50"]

        dynamic "env" {
          for_each = { WORKWEAVE_ENV = "release", COOKIE_SECURE = "true" }
          content {
            name  = env.key
            value = env.value
          }
        }

        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = var.database_url_secret
              version = "latest"
            }
          }
        }

        volume_mounts {
          name       = "cloudsql"
          mount_path = local.socket
        }
      }

      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [var.sql_connection_name]
        }
      }
    }
  }
}

# Only the scheduler identity may start the cleanup job (roles/run.invoker includes run.jobs.run).
resource "google_cloud_run_v2_job_iam_member" "scheduler_runs_cleanup" {
  project  = var.project_id
  location = google_cloud_run_v2_job.cleanup.location
  name     = google_cloud_run_v2_job.cleanup.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.scheduler_sa}"
}

resource "google_cloud_scheduler_job" "cleanup" {
  project          = var.project_id
  region           = var.region
  name             = "workweave-cleanup-every-6h"
  description      = "Starts the demo cleanup job (expired visitor runs only)."
  schedule         = "0 */6 * * *"
  time_zone        = "Asia/Manila"
  attempt_deadline = "320s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.cleanup.name}:run"
    oauth_token {
      service_account_email = var.scheduler_sa
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_runs_cleanup]
}
