terraform {
  # 1.11+ for write-only arguments (used in the submission environment).
  required_version = ">= 1.11.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "8.5.0"
    }
  }
  # Bootstrap keeps LOCAL state (git-ignored): the state bucket doesn't exist until this runs.
  # After the first apply, optionally migrate it into the bucket under prefix "bootstrap".
}

provider "google" {
  region = var.region
}
