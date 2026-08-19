locals {
  db_secrets = toset(["db-user", "db-password", "db-dsn"])
}

resource "google_secret_manager_secret" "db" {
  for_each = local.db_secrets

  secret_id = "ticketops-${each.key}"

  replication {
    auto {}
  }

  labels = {
    app = "ticketops"
  }

  depends_on = [google_project_service.enable]
}