variable "alert_email" {
  description = "E-mail que recebe as notificações do Cloud Monitoring"
  type        = string
}

resource "google_monitoring_notification_channel" "email" {
  display_name = "TicketOps - operador"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [google_project_service.enable]
}

resource "google_monitoring_alert_policy" "erro_5xx" {
  display_name = "TicketOps - respostas 5xx no Cloud Run"
  combiner     = "OR"
  severity     = "ERROR"

  conditions {
    display_name = "3 ou mais respostas 5xx em 5 minutos"

    condition_threshold {
      filter = join(" AND ", [
        "metric.type = \"run.googleapis.com/request_count\"",
        "resource.type = \"cloud_run_revision\"",
        "resource.label.\"service_name\" = \"${var.service_name}\"",
        "metric.label.\"response_code_class\" = \"5xx\"",
      ])

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.label.service_name"]
      }

      comparison      = "COMPARISON_GT"
      threshold_value = 2
      duration        = "0s"

      trigger {
        count = 1
      }

      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
    }
  }

  alert_strategy {
    auto_close = "1800s"

    notification_rate_limit {
      period = "3600s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      Respostas 5xx no servico TicketOps.

      1. `severity>=ERROR` no Logs Explorer: se houver traceback, e bug da aplicacao.
      2. `GET /health`: se devolver 503, a dependencia e o Autonomous Database.
      3. ADB parado por inatividade e o caso mais provavel — religar na console da OCI.
      4. Deploy recente: `gcloud run revisions list` e rollback por troca de trafego.
    EOT
  }
}

# Aponta para /ready, que toca o banco: além de detectar indisponibilidade sem depender de
# tráfego, é o que mantém o ADB Always Free acordado — substituindo o Cloud Scheduler do M4.
# Duas regiões no mínimo: com uma só, um problema de rede daquela região é indistinguível de
# queda do serviço, e o primeiro falso-positivo custa mais do que o alerta vale.
resource "google_monitoring_uptime_check_config" "ready" {
  display_name = "TicketOps - /ready"
  timeout      = "10s"
  period       = "900s"

  http_check {
    path         = "/ready"
    port         = 443
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = replace(google_cloud_run_v2_service.api.uri, "https://", "")
    }
  }

  selected_regions = ["USA_IOWA", "USA_OREGON"]
}

# Segunda política, separada da de 5xx de propósito: "ninguém consegue chegar" e "as
# requisições estão falhando" são incidentes diferentes, com diagnósticos diferentes.
resource "google_monitoring_alert_policy" "uptime_falhou" {
  display_name = "TicketOps - /ready inalcançável"
  combiner     = "OR"
  severity     = "ERROR"

  conditions {
    display_name = "uptime check falhando"

    condition_threshold {
      filter = join(" AND ", [
        "metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\"",
        "resource.type = \"uptime_url\"",
        "metric.label.\"check_id\" = \"${google_monitoring_uptime_check_config.ready.uptime_check_id}\"",
      ])

      aggregations {
        alignment_period     = "1200s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }

      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "0s"

      trigger {
        count = 1
      }

      evaluation_missing_data = "EVALUATION_MISSING_DATA_INACTIVE"
    }
  }

  alert_strategy {
    auto_close = "1800s"

    notification_rate_limit {
      period = "3600s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  documentation {
    mime_type = "text/markdown"
    content   = <<-EOT
      O uptime check em `/ready` falhou em mais de uma regiao.

      1. Abra a URL do servico: se `/health` responde e `/ready` nao, o problema e o banco.
      2. ADB parado por inatividade e o caso mais provavel — religar na console da OCI.
      3. Se nem `/health` responde, veja as revisoes do Cloud Run e o log de boot.
    EOT
  }
}