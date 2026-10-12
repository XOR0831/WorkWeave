variable "project_id" {
  description = "New project ID (globally unique, 6–30 chars), e.g. workweave-demo-1234."
  type        = string
}

variable "project_name" {
  type    = string
  default = "WorkWeave Demo"
}

variable "billing_account" {
  description = "Billing account ID (XXXXXX-XXXXXX-XXXXXX) of the free-trial account."
  type        = string
}

variable "org_id" {
  description = "Organization ID, if the account has one. Personal accounts usually don't; leave null."
  type        = string
  default     = null
}

variable "region" {
  type    = string
  default = "asia-east1"
}
