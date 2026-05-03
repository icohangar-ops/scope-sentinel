# Scope.Sentinel Terraform Variables

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "scope-sentinel"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must be lowercase alphanumeric with hyphens only."
  }
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "glue_database" {
  description = "Glue/Athena database name"
  type        = string
  default     = "scope_sentinel"
}

variable "edgar_user_agent" {
  description = "SEC EDGAR User-Agent header"
  type        = string
  default     = "Scope Sentinel research@example.com"
}

variable "alpha_vantage_key" {
  description = "AlphaVantage API key"
  type        = string
  sensitive   = true
}

variable "fred_api_key" {
  description = "FRED API key"
  type        = string
  sensitive   = true
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for Claude"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}
