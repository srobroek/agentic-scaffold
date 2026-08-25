# rtk recipes, imported by the root justfile.
#
# rtk filters rewrite what an agent sees, so rtk gates them behind a content hash on
# purpose. The filter file is committed and travels with the clone; the trust is
# per-machine and does not, which is why setup is a recipe rather than a render step.

# Telemetry consent is machine-global, in rtk's own config directory. Verified against
# rtk 0.44.1: a project `.rtk/config.toml` carrying `[telemetry] enabled = false` left
# `rtk telemetry status` unchanged, so nothing a render writes can disable it.
#
# The comment directly above a recipe becomes its `--list` description, so the rationale
# goes here and the description stays on the last line.

# Trust the project filters and turn telemetry off
[group('rtk')]
rtk-setup:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v rtk >/dev/null 2>&1; then
      echo "rtk is not on PATH; skipping" >&2
      exit 0
    fi
    rtk telemetry disable
    if [ -f .rtk/filters.toml ]; then
      rtk trust --yes
      # Runs the filter file's own inline tests beside rtk's built-in ones. A filter
      # that silently matches nothing is the failure this catches.
      rtk verify
    fi

# What rtk currently trusts, and whether telemetry is off
[group('rtk')]
rtk-status:
    @rtk trust --list
    @rtk telemetry status

# Run the filter tests, this file's and rtk's own
[group('rtk')]
rtk-verify:
    rtk verify
