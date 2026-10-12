variable "project_id" {
  type = string
}

variable "project_number" {
  type = string
}

variable "billing_account" {
  type = string
}

variable "alert_email" {
  type = string
}

variable "site_host" {
  description = "Host of the public site, e.g. <site_id>.web.app."
  type        = string
}

variable "budget_usd" {
  type    = number
  default = 300
}

variable "trial_start" {
  description = "Free-trial start date."
  type        = object({ year = number, month = number, day = number })
}

variable "trial_end" {
  description = "Free-trial end date (90 days after the start)."
  type        = object({ year = number, month = number, day = number })
}

variable "enable_uptime" {
  description = "Create the uptime check and alert (only once the API is deployed)."
  type        = bool
  default     = false
}
