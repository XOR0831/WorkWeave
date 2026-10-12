# The single cloud environment (ADR-026). Apply in stages:
#   1. without api_image: platform, data and operations (budget) only;
#   2. build and push the image, then set api_image (digest) and apply again: runtime + uptime.

locals {
  labels = { app = "workweave", env = "submission", managed_by = "terraform" }
}

data "google_project" "this" {
  project_id = var.project_id
}

module "platform" {
  source     = "../../modules/platform"
  project_id = var.project_id
  region     = var.region
  site_id    = var.site_id
  labels     = local.labels
}

module "data" {
  source              = "../../modules/data"
  project_id          = var.project_id
  region              = var.region
  tier                = var.sql_tier
  db_password_version = var.db_password_version
  api_sa              = module.platform.service_accounts.api
  migrate_sa          = module.platform.service_accounts.migrate
  cleanup_sa          = module.platform.service_accounts.cleanup
  labels              = local.labels
  depends_on          = [module.platform]
}

module "runtime" {
  count                 = var.api_image == "" ? 0 : 1
  source                = "../../modules/runtime"
  project_id            = var.project_id
  region                = var.region
  api_image             = var.api_image
  min_instances         = var.min_instances
  max_instances         = var.max_instances
  api_sa                = module.platform.service_accounts.api
  migrate_sa            = module.platform.service_accounts.migrate
  cleanup_sa            = module.platform.service_accounts.cleanup
  scheduler_sa          = module.platform.service_accounts.scheduler
  sql_connection_name   = module.data.connection_name
  database_url_secret   = module.data.database_url_secret
  gemini_api_key_secret = module.data.gemini_api_key_secret

  gemini_evaluator_api_key_secret = module.data.gemini_evaluator_api_key_secret
  evaluator_voice_key_ready       = var.evaluator_voice_key_ready

  # ADR-052: the AI engineer's graphs and calendar service in the API container; Firestore inbox.
  ai_gemini              = var.ai_gemini
  gemini_models          = var.gemini_models
  public_origin          = module.platform.hosting_url
  calendar_oauth_ready   = var.calendar_oauth_ready
  calendar_account_email = var.calendar_account_email
  google_oauth_secrets   = module.data.google_oauth_secrets

  labels = local.labels
}

module "operations" {
  source          = "../../modules/operations"
  project_id      = var.project_id
  project_number  = data.google_project.this.number
  billing_account = var.billing_account
  alert_email     = var.alert_email
  site_host       = "${var.site_id}.web.app"
  budget_usd      = var.budget_usd
  trial_start     = var.trial_start
  trial_end       = var.trial_end
  enable_uptime   = var.api_image != ""
  depends_on      = [module.platform]
}
