# Alerts: uptime of the public site's API path, and spending against the free-trial credits.

terraform {
  required_providers {
    google = { source = "hashicorp/google" }
  }
}

resource "google_monitoring_notification_channel" "email" {
  project      = var.project_id
  display_name = "WorkWeave owner email"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

# Checks the full path users take: Firebase Hosting -> /api/** rewrite -> Cloud Run -> database.
resource "google_monitoring_uptime_check_config" "api" {
  count        = var.enable_uptime ? 1 : 0
  project      = var.project_id
  display_name = "WorkWeave /api/health via Hosting"
  timeout      = "10s"
  period       = "300s"

  http_check {
    path         = "/api/health"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.site_host
    }
  }
}

resource "google_monitoring_alert_policy" "api_down" {
  count                 = var.enable_uptime ? 1 : 0
  project               = var.project_id
  display_name          = "WorkWeave API unreachable"
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.email.id]

  conditions {
    display_name = "Uptime check failing"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.label.check_id=\"${google_monitoring_uptime_check_config.api[0].uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "300s"
      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.*"]
      }
      trigger {
        count = 1
      }
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }
}

# Budget over the 90-day free trial, measured on usage BEFORE credits (credits would otherwise
# hide the spend until they run out).
resource "google_billing_budget" "trial" {
  billing_account = var.billing_account
  display_name    = "WorkWeave free-trial credits"

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_usd)
    }
  }

  budget_filter {
    projects               = ["projects/${var.project_number}"]
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
    custom_period {
      start_date {
        year  = var.trial_start.year
        month = var.trial_start.month
        day   = var.trial_start.day
      }
      end_date {
        year  = var.trial_end.year
        month = var.trial_end.month
        day   = var.trial_end.day
      }
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.25, 0.5, 0.75, 0.9]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
    disable_default_iam_recipients   = false
  }
}
