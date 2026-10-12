variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "asia-east1"
}

variable "billing_account" {
  type = string
}

variable "alert_email" {
  type = string
}

variable "site_id" {
  description = "Firebase Hosting site ID (globally unique). Default URL: https://<site_id>.web.app"
  type        = string
}

variable "api_image" {
  description = "API image pinned by digest; leave empty for the first (pre-image) apply."
  type        = string
  default     = ""
}

variable "sql_tier" {
  type    = string
  default = "db-f1-micro"
}

variable "db_password_version" {
  type    = number
  default = 1
}

variable "evaluator_voice_key_ready" {
  description = "Set true after adding a version to gemini-api-key-evaluator (paid evaluator voice listening)."
  type        = bool
  default     = false
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  description = "Keep 1 while the calendar sign-in is kept in memory (ADR-052)."
  type        = number
  default     = 1
}

variable "budget_usd" {
  type    = number
  default = 300
}

variable "trial_start" {
  type = object({ year = number, month = number, day = number })
}

variable "trial_end" {
  type = object({ year = number, month = number, day = number })
}

variable "ai_gemini" {
  description = "vertex (default when deployed) or api_key (as used locally; the fallback if a model isn't on Vertex AI), for the graphs' Gemini calls."
  type        = string
  default     = "vertex"
}

variable "gemini_models" {
  description = "The graphs' model settings (the AI engineer's .env values)."
  type        = map(string)
  default = {
    GEMINI_MODEL              = "gemini-3.5-flash-lite"
    GEMINI_REASONING_MODEL    = "gemini-3.6-flash"
    GEMINI_REASONING_THINKING = "low"
    GEMINI_EMBED_MODEL        = "gemini-embedding-2"
    GEMINI_EMBED_DIM          = "768"
  }
}

variable "calendar_oauth_ready" {
  description = "Set true after adding versions to google-oauth-client-id and google-oauth-client-secret."
  type        = bool
  default     = false
}

variable "calendar_account_email" {
  description = "The demo's Google test account (the only one the calendar service accepts). Keep it in terraform.tfvars."
  type        = string
  default     = ""
}
