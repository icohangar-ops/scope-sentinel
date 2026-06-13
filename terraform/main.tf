# Scope.Sentinel AWS Infrastructure
# S3 + Iceberg + Glue + Athena + Lambda + Step Functions + EventBridge

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ============================================================
# S3 Buckets
# ============================================================

resource "aws_s3_bucket" "raw" {
  bucket = "${var.project_name}-raw-${var.environment}"

  lifecycle_rule {
    id      = "transition-to-ia"
    enabled = true
    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

resource "aws_s3_bucket" "iceberg_warehouse" {
  bucket = "${var.project_name}-warehouse-${var.environment}"
}

resource "aws_s3_bucket" "athena_output" {
  bucket = "${var.project_name}-queries-${var.environment}"

  lifecycle_rule {
    id      = "cleanup"
    enabled = true
    expiration {
      days = 30
    }
  }
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each = toset([aws_s3_bucket.raw.id, aws_s3_bucket.iceberg_warehouse.id, aws_s3_bucket.athena_output.id])

  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ============================================================
# Glue Database & Tables
# ============================================================

resource "aws_glue_catalog_database" "sentinel" {
  name = var.glue_database
}

resource "aws_glue_catalog_table" "reits" {
  name          = "reits"
  database_name = aws_glue_catalog_database.sentinel.name

  table_type    = "ICEBERG"
  parameters = {
    "table_type"             = "ICEBERG"
    "format_version"         = "2"
    "metadata_compression"   = "gzip"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.iceberg_warehouse.bucket}/reits/"
    input_format  = "org.apache.hadoop.mapred.FileInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
      parameters = {
        "serialization.format" = "1"
      }
    }

    columns {
      name = "ticker"
      type = "string"
    }
    columns {
      name = "name"
      type = "string"
    }
    columns {
      name = "sector"
      type = "string"
    }
    columns {
      name = "sub_sector"
      type = "string"
    }
    columns {
      name = "market_cap"
      type = "double"
    }
    columns {
      name = "dividend_yield"
      type = "double"
    }
    columns {
      name = "payout_ratio"
      type = "double"
    }
    columns {
      name = "latest_ffo_per_share"
      type = "double"
    }
    columns {
      name = "property_count"
      type = "int"
    }
    columns {
      name = "created_at"
      type = "timestamp"
    }
  }
}

resource "aws_glue_catalog_table" "financial_metrics" {
  name          = "financial_metrics"
  database_name = aws_glue_catalog_database.sentinel.name

  table_type  = "ICEBERG"
  parameters  = { "table_type" = "ICEBERG", "format_version" = "2" }

  storage_descriptor {
    location = "s3://${aws_s3_bucket.iceberg_warehouse.bucket}/financial_metrics/"

    ser_de_info {
      serialization_library = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
    }

    columns {
      name = "reit_ticker"
      type = "string"
    }
    columns {
      name = "fiscal_year"
      type = "int"
    }
    columns {
      name = "quarter"
      type = "int"
    }
    columns {
      name = "ffo_per_share"
      type = "double"
    }
    columns {
      name = "affo_per_share"
      type = "double"
    }
    columns {
      name = "same_store_noi_growth"
      type = "double"
    }
    columns {
      name = "net_debt_to_ebitda"
      type = "double"
    }
    columns {
      name = "dividend_per_share"
      type = "double"
    }
  }
}

# ============================================================
# Athena Workgroup
# ============================================================

resource "aws_athena_workgroup" "sentinel" {
  name = "${var.project_name}-wg"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_output.bucket}/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
  }
}

# ============================================================
# IAM Role for Lambda
# ============================================================

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project_name}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy" "lambda" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject", "s3:PutObject", "s3:ListBucket",
          "athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults",
          "glue:*",
          "bedrock:Converse",
          "logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
        ]
        Resource = "*"
      }
    ]
  })
}

# ============================================================
# Dead Letter Queue (analysis Lambda)
# ============================================================

# Async invocations of the analysis function (EventBridge / Step Functions
# retries) that exhaust retries are captured here instead of being dropped.
resource "aws_sqs_queue" "analysis_dlq" {
  name                      = "${var.project_name}-analysis-dlq"
  message_retention_seconds = 1209600 # 14 days
}

# Allow the Lambda role to deliver failed async events to the DLQ.
resource "aws_iam_role_policy" "lambda_dlq" {
  name = "${var.project_name}-lambda-dlq-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.analysis_dlq.arn
      }
    ]
  })
}

# ============================================================
# Lambda Functions
# ============================================================

resource "aws_lambda_function" "sec_ingestion" {
  function_name = "${var.project_name}-sec-ingestion"
  role          = aws_iam_role.lambda.arn
  handler       = "src.lambda.sec_ingestion_handler.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 512

  source_code_hash = filebase64sha256("${path.module}/../src/lambda/sec_ingestion_handler.py")

  environment {
    variables = {
      RAW_BUCKET         = aws_s3_bucket.raw.id
      GLUE_DATABASE      = var.glue_database
      SEC_EDGAR_USER_AGENT = var.edgar_user_agent
      ALPHA_VANTAGE_KEY = var.alpha_vantage_key
      FRED_API_KEY       = var.fred_api_key
      AWS_REGION         = var.aws_region
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      ATHENA_OUTPUT      = "s3://${aws_s3_bucket.athena_output.bucket}/"
    }
  }
}

resource "aws_lambda_function" "analysis" {
  function_name = "${var.project_name}-analysis"
  role          = aws_iam_role.lambda.arn
  handler       = "src.lambda.analysis_handler.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 1024

  dead_letter_config {
    target_arn = aws_sqs_queue.analysis_dlq.arn
  }

  environment {
    variables = {
      RAW_BUCKET       = aws_s3_bucket.raw.id
      GLUE_DATABASE    = var.glue_database
      AWS_REGION       = var.aws_region
      BEDROCK_MODEL_ID = var.bedrock_model_id
      ATHENA_OUTPUT    = "s3://${aws_s3_bucket.athena_output.bucket}/"
    }
  }
}

# ============================================================
# EventBridge Rules
# ============================================================

resource "aws_cloudwatch_event_rule" "daily_sec_check" {
  name                = "${var.project_name}-daily-sec"
  description         = "Daily SEC filing check at 6 AM ET (11 AM UTC)"
  schedule_expression = "cron(0 11 * * ? *)"
}

resource "aws_cloudwatch_event_target" "daily_sec_check" {
  rule      = aws_cloudwatch_event_rule.daily_sec_check.name
  target_id = "sec-ingestion"
  arn       = aws_lambda_function.sec_ingestion.arn
}

resource "aws_lambda_permission" "daily_sec" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sec_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_sec_check.arn
}

resource "aws_cloudwatch_event_rule" "weekly_analysis" {
  name                = "${var.project_name}-weekly-analysis"
  description         = "Weekly REIT analysis on Sundays at 8 AM ET (13 PM UTC)"
  schedule_expression = "cron(0 13 ? * SUN *)"
}

resource "aws_cloudwatch_event_target" "weekly_analysis" {
  rule      = aws_cloudwatch_event_rule.weekly_analysis.name
  target_id = "analysis"
  arn       = aws_lambda_function.analysis.arn
}

# ============================================================
# Step Functions State Machine
# ============================================================

resource "aws_iam_role" "step_functions" {
  name = "${var.project_name}-sf-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "step_functions" {
  name = "${var.project_name}-sf-policy"
  role = aws_iam_role.step_functions.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["lambda:InvokeFunction"]
      Resource = [
        aws_lambda_function.sec_ingestion.arn,
        aws_lambda_function.analysis.arn,
      ]
    }]
  })
}

resource "aws_sfn_state_machine" "sentinel_pipeline" {
  name     = "${var.project_name}-pipeline"
  role_arn = aws_iam_role.step_functions.arn

  definition = jsonencode({
    Comment = "Scope.Sentinel REIT Analysis Pipeline"
    StartAt = "ComputeScores"
    States = {
      "ComputeScores" = {
        Type = "Task"
        Resource = aws_lambda_function.analysis.arn
        Parameters = {
          "step.$" = "$.step"
          "tickers.$" = "$.tickers"
        }
        ResultPath = "$.scores"
        Next = "BedrockAnalysis"
      }
      "BedrockAnalysis" = {
        Type = "Task"
        Resource = aws_lambda_function.analysis.arn
        Parameters = {
          "step" = "bedrock_analysis"
          "signals.$" = "$.scores.body"
        }
        ResultPath = "$.analysis"
        Next = "WriteSignals"
      }
      "WriteSignals" = {
        Type = "Task"
        Resource = aws_lambda_function.analysis.arn
        Parameters = {
          "step" = "write_signals"
          "signals.$" = "$.analysis.body"
        }
        End = true
      }
    }
  })
}
