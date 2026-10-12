variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "site_id" {
  description = "Firebase Hosting site ID (globally unique); the site is https://<site_id>.web.app."
  type        = string
}

variable "labels" {
  type = map(string)
}
