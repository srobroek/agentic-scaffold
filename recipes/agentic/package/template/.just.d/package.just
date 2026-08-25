# Marketplace recipes, contributed by agentic/package and imported by the root justfile.
#
# `.omp-plugin/marketplace.json` and `.claude-plugin/marketplace.json` are COMMITTED
# generated artefacts. OMP and Claude Code resolve a marketplace straight from a clone
# with no build step, so a catalog that exists only after a build is one nobody can
# install from. scripts/build_catalog.py is their only writer, which is what makes the
# check below able to report drift rather than its own idea of the bytes.
#
# Registering the marketplace with a runtime is machine-global and per user, so nothing
# here does it: `omp plugin marketplace add <owner>/<repo>` writes under ~/.omp/, outside
# any repository. OMP reads the .omp-plugin catalog and falls back to .claude-plugin, so
# the one registration serves both.

# Rebuild both marketplace catalogs from the plugin manifests
[group('marketplace')]
marketplace-build:
    @python3 scripts/build_catalog.py .

# `--check` writes nothing, so the gate cannot repair the drift it reports. The generator
# that regenerates first and diffs afterwards always passes, and leaves CI with a dirty
# tree; this one compares the committed bytes and exits 1 on a difference.

# Fail when a committed catalog is stale
[group('marketplace')]
marketplace-check:
    @python3 scripts/build_catalog.py . --check
