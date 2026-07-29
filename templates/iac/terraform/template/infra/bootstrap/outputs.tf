# infra/bootstrap/outputs.tf -- what the main root module and CI need from bootstrap.

output "state_bucket" {
  description = "Bucket name to set as `bucket` in every envs/<env>.tfbackend."
  value       = aws_s3_bucket.state.id
}

output "ci_role_arn" {
  description = "Role ARN for the workflow's `role-to-assume`. Empty when github_repository was not set."
  value       = try(aws_iam_role.ci[0].arn, "")
}
