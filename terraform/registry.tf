resource "google_artifact_registry_repository" "docker" {
  location      = var.region
  repository_id = var.repo_name
  format        = "DOCKER"

  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "apagar-tudo"
    action = "DELETE"
    condition {
      tag_state = "ANY"
    }
  }

  cleanup_policies {
    id     = "manter-3-recentes"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }

  depends_on = [google_project_service.enable]
}