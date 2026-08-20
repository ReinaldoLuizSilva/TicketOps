output "service_url" {
  description = "URL do serviço Cloud Run"
  value       = google_cloud_run_v2_service.api.uri
}

output "image_repo" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
  description = "URL do repositório de imagens do Artifact Registry"
}

output "runtime_service_account" {
  value       = google_service_account.run.email
  description = "E-mail da Service Account usada pelo serviço Cloud Run"
}

output "wif_provider" {
  value       = google_iam_workload_identity_pool_provider.github.name
  description = "Nome completo do provider de WIF, para colar em workload_identity_provider no workflow"
}

output "deploy_service_account" {
  value       = google_service_account.deploy.email
  description = "E-mail da SA que o GitHub Actions assume por WIF"
}