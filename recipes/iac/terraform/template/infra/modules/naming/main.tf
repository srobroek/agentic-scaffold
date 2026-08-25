# modules/naming -- derives the name prefix every other module reuses.
#
# A worked example of the module contract rather than a placeholder: it has real
# variables, a real output, and the root module calls it, so `tofu validate` and
# `tofu test` both exercise the wiring. Deleting it means deleting its call in
# ../../main.tf too.
#
# It declares `required_version` but no provider. tflint's
# `terraform_required_version` rule applies to a child module too, not only a root
# one -- verified against tflint 0.64.0 with the aws ruleset, where omitting it here
# failed `just tf-lint`. A provider block is a different matter and stays out: a
# child module that configures its own provider cannot be given an aliased one by
# its caller.

terraform {
  # A range rather than the root module's exact floor: a child module pinning a
  # narrow version constrains every caller that ever vendors it.
  required_version = ">= 1.10"
}

variable "project_name" {
  description = "Name prefix for every resource."
  type        = string
}

variable "environment" {
  description = "Environment the name is scoped to."
  type        = string
}

output "prefix" {
  description = "The <project>-<environment> prefix."
  value       = "${var.project_name}-${var.environment}"
}
