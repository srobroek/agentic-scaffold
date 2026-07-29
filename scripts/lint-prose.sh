#!/usr/bin/env bash
# Run the prose gate over the docs. Internal genre everywhere except README.md.
#
# No `mapfile`: macOS ships bash 3.2, where it does not exist. A `while read`
# loop works on both.
set -uo pipefail

GATE="${HOME}/.claude/skills/review-docs/scripts/slop-lint.sh"
if [[ ! -f "$GATE" ]]; then
  echo "prose gate absent at $GATE, skipping" >&2
  exit 0
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root" || exit 1

status=0
internal=()
while IFS= read -r file; do
  [[ "$file" == "docs/INDEX.md" ]] && continue
  internal+=("$file")
done < <(git ls-files 'docs/*.md' 'docs/**/*.md' 'rules/*.md' 'profiles/*.md' 'AGENTS.md')

if [[ ${#internal[@]} -gt 0 ]]; then
  bash "$GATE" --genre internal "${internal[@]}" || status=1
fi

if [[ -f README.md ]]; then
  bash "$GATE" --genre consumer README.md || status=1
fi

exit "$status"
