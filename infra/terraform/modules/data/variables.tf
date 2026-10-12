variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "tier" {
  description = "Cloud SQL tier. db-f1-micro (~25 connections, shared CPU, no SLA) for testing; switch to db-g1-small (~50) for the judged validation window."
  type        = string
  default     = "db-f1-micro"
}

variable "db_password_version" {
  description = "Increment to rotate the database password (write-only arguments re-send only on change)."
  type        = number
  default     = 1
}

variable "api_sa" {
  type = string
}

variable "migrate_sa" {
  type = string
}

variable "cleanup_sa" {
  type = string
}

variable "labels" {
  type = map(string)
}

variable "firestore_location" {
  description = "Firestore location for the notification inbox (cannot be changed after creation)."
  type        = string
  default     = "asia-east1"
}
