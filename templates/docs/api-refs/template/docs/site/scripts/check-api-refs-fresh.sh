#!/usr/bin/env bash
# Fail when a committed API reference page no longer matches the source.
#
# Two properties, and the second is the one that catches a broken renderer.
#
#   1. STALENESS. `--check` renders to memory and reports a page whose committed copy differs.
#      It writes nothing, so this gate cannot repair the drift it reports and pass on a rerun.
#
#   2. DETERMINISM. The generator runs twice and the two outputs are compared. A renderer that
#      iterates a hash map, embeds a timestamp, or sorts unstably produces a different page
#      each run, which makes every commit carry a reference diff and makes the staleness check
#      above meaningless.
#
# macOS ships bash 3.2: no mapfile, no readarray.
set -uo pipefail

cd "$(dirname "$0")/../../.." || exit 1

if [ ! -f docs/site/scripts/gen-api-refs.mjs ]; then
  echo "no API reference harness; nothing to check"
  exit 0
fi

echo "==> staleness"
if ! node docs/site/scripts/gen-api-refs.mjs --check; then
  exit 1
fi

echo "==> determinism"
first=$(mktemp -d)
second=$(mktemp -d)
trap 'rm -rf "$first" "$second"' EXIT

section="${API_REF_SECTION:-reference}"
pages="docs/site/src/content/docs/$section"

# Rendered into a copy each time rather than over the tree: a check that rewrites what it is
# checking leaves a dirty tree behind and passes on the second run.
if [ -d "$pages" ]; then
  cp -R "$pages/." "$first/" 2>/dev/null || true
fi

node docs/site/scripts/gen-api-refs.mjs >/dev/null || exit 1
if [ -d "$pages" ]; then
  cp -R "$pages/." "$second/" 2>/dev/null || true
fi

node docs/site/scripts/gen-api-refs.mjs >/dev/null || exit 1

# No page directory after two renders means no extractor exists yet, which is the state a repo
# is in between selecting this layer and writing its first extractor. Diffing against a
# directory that was never created reports a nondeterministic generator, which is wrong and
# unfixable.
if [ ! -d "$pages" ]; then
  echo "no extractors yet, so there are no pages to compare"
  exit 0
fi

if ! diff -r "$second" "$pages" >/dev/null 2>&1; then
  echo "the generator is not deterministic: two runs produced different pages" >&2
  diff -r "$second" "$pages" | head -20 >&2
  exit 1
fi

# Restore whatever was committed, so the check leaves no change behind.
if [ -d "$first" ] && [ -n "$(ls -A "$first" 2>/dev/null)" ]; then
  cp -R "$first/." "$pages/" 2>/dev/null || true
fi

echo "API reference pages are current and the generator is deterministic"
