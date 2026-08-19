locals {
  db_secrets = {
    "db-user"     = "my-database-user"
    "db-password" = "my-database-password"
    "db-dsn"      = "my-database-dsn"
  }
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