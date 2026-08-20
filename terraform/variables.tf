variable "project_id" {
  description = "ID do projeto GCP"
  type        = string
}

variable "region" {
  description = "Região do projeto GCP"
  type        = string
  default     = "us-central1"
}

variable "repo_name" {
  description = "Nome do repositório"
  type        = string
  default     = "ticketops"
}

variable "service_name" {
  description = "Nome do serviço Cloud Run"
  type        = string
  default     = "ticketops"
}

variable "image" {
  description = "Imagem da primeira revisão. Aponta para a imagem pública de exemplo do Google porque no primeiro apply o Artifact Registry acabou de ser criado, vazio. Do M3 em diante quem publica imagem é o CI, e o lifecycle do serviço ignora mudanças neste campo."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "github_repo" {
  description = "Repositório do GitHub"
  type        = string
}