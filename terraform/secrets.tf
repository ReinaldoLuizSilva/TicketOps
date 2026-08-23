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

resource "google_secret_manager_secret" "wallet" {
  secret_id = "ticketops-db-wallet"

  replication {
    auto {}
  }

  labels = {
    app = "ticketops"
  }

  depends_on = [google_project_service.enable]
}

resource "google_secret_manager_secret" "wallet_password" {
  secret_id = "ticketops-db-wallet-password"

  replication {
    auto {}
  }

  labels = {
    app = "ticketops"
  }

  depends_on = [google_project_service.enable]
}
