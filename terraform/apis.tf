locals {
  services = [
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "sts.googleapis.com",
    "iamcredentials.googleapis.com",
    "monitoring.googleapis.com",
  ]
}

resource "google_project_service" "enable" {
  for_each = toset(local.services)
  service  = each.value

  disable_on_destroy = false
}