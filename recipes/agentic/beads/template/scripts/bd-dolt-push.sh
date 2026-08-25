#!/usr/bin/env bash
# Push the beads issue database, from the pre-push hook.
#
# The database does not travel with a git push on its own: it moves over
# `refs/dolt/data` on the same remote, and `bd hooks run pre-push` pushes nothing. Without
# this the issues stay on one machine.
#
# Never blocking. A push that fails on an unreachable remote or a missing wrapper must not
# stop the git push, and `bd dolt push` is recoverable by running it again.
#
# bd's own `dolt.auto-push` is left off. It pushes after a write on a 5-minute debounce,
# which means a window where the remote is behind and nothing says so; here the push
# happens exactly when the git push does. It also ignores `custom.bd-push-command`, so on a
# machine needing the wrapper it would hang every write until its timeout.
set -uo pipefail

command -v bd >/dev/null 2>&1 || exit 0

# `bd config get` prints "<key> (not set)" rather than failing, so both forms are checked.
remote=$(bd config get sync.remote 2>/dev/null || true)
case "$remote" in
  "" | *"not set"*) exit 0 ;;
esac

# Where the database runs in a container, a direct `bd dolt push` hangs until it times
# out and the wrapper named here is what works. Reading the configured value rather than
# assuming `bd` means the hook works on either kind of machine.
#
# `custom.*` is bd's namespace for user-defined keys, so this is a local convention
# rather than something bd reads itself. bd's own guard message names the same key.
pusher=$(bd config get custom.bd-push-command 2>/dev/null || true)
case "$pusher" in
  "" | *"not set"*) pusher=bd ;;
esac

if ! command -v "$pusher" >/dev/null 2>&1; then
  echo "beads: $pusher is not on PATH, skipping the database push" >&2
  exit 0
fi

if ! "$pusher" dolt push; then
  echo "beads: the database push failed. Run '$pusher dolt push' once the remote is reachable." >&2
fi

exit 0
