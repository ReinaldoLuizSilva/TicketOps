resource "google_cloud_run_v2_service" "api" {
  name     = var.service_name
  location = var.region

  deletion_protection = false

  template {
    service_account = google_service_account.run.email

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    # A wallet do ADB entra como ARQUIVO, montado de um secret. Nunca como
    # variável de ambiente: é binário, é grande, e apareceria inteiro num
    # "gcloud run services describe".
    volumes {
      name = "wallet"
      secret {
        secret = google_secret_manager_secret.wallet.secret_id
        items {
          path    = "ewallet.pem"
          version = "latest"
          mode    = 256
        }
      }
    }

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        cpu_idle = true
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      volume_mounts {
        name       = "wallet"
        mount_path = "/wallet"
      }

      # DB_USER, DB_PASSWORD e DB_DSN — um env por secret do for_each.
      dynamic "env" {
        for_each = google_secret_manager_secret.db
        content {
          name = upper(replace(env.key, "-", "_"))
          value_source {
            secret_key_ref {
              secret  = env.value.secret_id
              version = "latest"
            }
          }
        }
      }

      env {
        name  = "DB_WALLET_LOCATION"
        value = "/wallet"
      }

      env {
        name = "DB_WALLET_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.wallet_password.secret_id
            version = "latest"
          }
        }
      }

      # O Cloud Run injeta PORT, K_SERVICE, K_REVISION e K_CONFIGURATION — não o ID do projeto.
      # O campo de trace do Cloud Logging exige "projects/PROJETO/traces/ID", daí esta env.
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      scaling,
    ]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.run_accessor,
    google_secret_manager_secret_iam_member.run_accessor_wallet,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = google_cloud_run_v2_service.api.project
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
