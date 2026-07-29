#!/usr/bin/env bash
# Regenerate .terraform.lock.hcl for every platform that runs OpenTofu here.
#
# A lock file records provider hashes per platform. Generated on a Mac it carries
# darwin_arm64 only, and `tofu init` on a linux CI runner then fails with "provider
# ... does not have a package available for your current platform". The failure lands
# in CI rather than at the commit that caused it, which is what this prevents.
#
# `-platform` is repeatable and REPLACES the detected set, so every platform has to be
# named -- including the one this machine runs on.
#
# macOS ships bash 3.2: no mapfile, no readarray, no associative arrays.
set -euo pipefail

# Every root module. A child module under modules/ has no lock file of its own; its
# providers are resolved by whichever root module calls it.
ROOTS="infra infra/bootstrap"

PLATFORMS="linux_amd64 linux_arm64 darwin_arm64 darwin_amd64"

tofu_bin="${PCT_TFPATH:-tofu}"
if ! command -v "$tofu_bin" >/dev/null 2>&1; then
  echo "tofu_lock: $tofu_bin is not on PATH" >&2
  exit 1
fi

args=""
for platform in $PLATFORMS; do
  args="$args -platform=$platform"
done

status=0
for root in $ROOTS; do
  [ -d "$root" ] || continue

  # No .tf file means nothing to lock. A directory holding only a README would
  # otherwise fail init.
  if ! ls "$root"/*.tf >/dev/null 2>&1; then
    continue
  fi

  # A root module with no `required_providers` has no providers to lock, and
  # `providers lock` exits non-zero on one. Skipping it keeps the hook quiet for a
  # configuration that has not grown a provider yet.
  if ! grep -rq "required_providers" "$root"/*.tf; then
    echo "tofu_lock: $root declares no providers, skipping"
    continue
  fi

  echo "tofu_lock: $root"
  # -backend=false: the backend is partial, so a real init would need
  # -backend-config and credentials. Locking needs neither.
  if ! (cd "$root" && "$tofu_bin" init -backend=false -input=false >/dev/null); then
    echo "tofu_lock: init failed in $root" >&2
    status=1
    continue
  fi
  # shellcheck disable=SC2086  # $args is a deliberate list of -platform flags.
  if ! (cd "$root" && "$tofu_bin" providers lock $args >/dev/null); then
    echo "tofu_lock: providers lock failed in $root" >&2
    status=1
  fi
done

exit "$status"
