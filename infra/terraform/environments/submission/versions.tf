terraform {
  required_version = ">= 1.11.0" # write-only arguments
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "8.5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "8.5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.9.1"
    }
  }

  # Remote state in the bootstrap bucket (versioned, private). Partial config:
  #   terraform init -backend-config="bucket=<project_id>-tfstate"
  backend "gcs" {
    prefix = "submission"
  }
}

# user_project_override + billing_project: required by the Budgets and Firebase APIs when running
# with user credentials (gcloud auth application-default login).
provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

provider "google-beta" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}
