resource "google_service_account" "run" {
  account_id   = "ticketops-run"
  display_name = "TicketOps - runtime Cloud Run"
  description  = "Identidade do serviço Cloud Run. Existe para não usar a SA default do Compute Engine, que vem com roles/editor no projeto."

  depends_on = [google_project_service.enable]
}

resource "google_secret_manager_secret_iam_member" "run_accessor" {
  for_each = google_secret_manager_secret.db

  project   = each.value.project
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run.email}"
}

