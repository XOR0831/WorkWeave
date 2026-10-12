variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "api_image" {
  description = "Image pinned by digest: <region>-docker.pkg.dev/<project>/workweave/api@sha256:..."
  type        = string
  validation {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", var.api_image))
    error_message = "Pin the image by digest (…@sha256:<64 hex>), not by a mutable tag."
  }
}

variable "vertex_location" {
  description = "Vertex AI location for server-side Gemini calls ('global' has the widest model availability)."
  type        = string
  default     = "global"
}

variable "min_instances" {
  description = "0 saves credits (cold starts); raise to 1 only during judging."
  type        = number
  default     = 0
}

variable "max_instances" {
  description = "Keep 1: the calendar sign-in and its Google callback must reach the same instance (ADR-052)."
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

variable "scheduler_sa" {
  type = string
}

variable "sql_connection_name" {
  type = string
}

variable "database_url_secret" {
  type = string
}

variable "gemini_api_key_secret" {
  type = string
}

variable "gemini_evaluator_api_key_secret" {
  type = string
}

variable "evaluator_voice_key_ready" {
  description = "True once a version of the evaluator voice key secret has been added."
  type        = bool
  default     = false
}

variable "labels" {
  type = map(string)
}

# ---------------------------------------------------------------- ADR-052: graphs, calendar, inbox
variable "api_memory" {
  description = "API container memory (API + graph host + calendar service; ~320 MiB measured idle after a full demo run)."
  type        = string
  default     = "1Gi"
}

variable "cpu_always_allocated" {
  description = "Keep CPU between requests for the notification dispatcher and background work (instance-based billing)."
  type        = bool
  default     = true
}

variable "ai_gemini" {
  description = "How the graphs reach Gemini: vertex (service account, the deployed default) or api_key (the gemini-api-key secret, as used locally)."
  type        = string
  default     = "vertex"
  validation {
    condition     = contains(["api_key", "vertex"], var.ai_gemini)
    error_message = "ai_gemini is api_key or vertex."
  }
}

variable "gemini_models" {
  description = "The graphs' model settings (the AI engineer's .env values); all are required by her graphs at import."
  type        = map(string)
}

variable "graph_thread_ttl_hours" {
  description = "Graph conversation threads unused for this long are deleted (demo runs expire sooner)."
  type        = number
  default     = 24
}

variable "public_origin" {
  description = "The site's public origin, e.g. https://<site_id>.web.app (for the Google sign-in callback)."
  type        = string
}

variable "calendar_oauth_ready" {
  description = "True once both Google OAuth secrets have a version; turns the Companion calendar on."
  type        = bool
  default     = false
}

variable "calendar_account_email" {
  description = "The one Google account the calendar service accepts (the demo's test calendar)."
  type        = string
  default     = ""
}

variable "google_oauth_secrets" {
  type = object({ client_id = string, client_secret = string })
}
