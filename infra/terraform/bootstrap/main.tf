# One-time setup: the project, its billing link, the APIs Terraform itself needs, and the private,
# versioned bucket that holds the submission environment's Terraform state.
#
# If project creation fails because the account has no Organization (the provider docs note this
# requirement), create the project in the console with the same ID, link billing, then:
#   terraform import google_project.main <project_id>

locals {
  labels = { app = "workweave", env = "submission", managed_by = "terraform" }
}

resource "google_project" "main" {
  project_id          = var.project_id
  name                = var.project_name
  billing_account     = var.billing_account
  org_id              = var.org_id
  auto_create_network = false
  deletion_policy     = "PREVENT"
  labels              = local.labels
}

resource "google_project_service" "bootstrap" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "storage.googleapis.com",
    "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com",
  ])
  project            = google_project.main.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "tfstate" {
  project                     = google_project.main.project_id
  name                        = "${var.project_id}-tfstate"
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  deletion_policy             = "PREVENT"
  labels                      = local.labels

  versioning {
    enabled = true
  }

  soft_delete_policy {
    retention_duration_seconds = 604800
  }

  # Keep the last 20 versions of each state file.
  lifecycle_rule {
    condition {
      num_newer_versions = 20
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.bootstrap]
}
