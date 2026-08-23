resource "google_cloud_scheduler_job" "keepalive" {
  name        = "ticketops-adb-keepalive"
  region      = var.region
  description = "GET diário em /ready para manter o ADB Always Free acordado"

  schedule         = "0 9 * * *"
  time_zone        = "America/Sao_Paulo"
  attempt_deadline = "60s"

  retry_config {
    retry_count = 3
  }

  http_target {
    uri         = "${google_cloud_run_v2_service.api.uri}/ready"
    http_method = "GET"
  }

  depends_on = [google_project_service.enable]
}
