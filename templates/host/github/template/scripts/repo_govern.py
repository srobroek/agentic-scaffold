#!/usr/bin/env python3
"""Apply the repository governance GitHub reads from no file.

    repo_govern.py [--check] [--repo OWNER/NAME]

Branch protection, required status checks, merge types, auto-merge, and which repository
features are on are all API-only. Verified against a live repository: `gh api repos/<slug>`
reports every merge and feature setting, `/rulesets` returned zero entries and
`/branches/<branch>/protection` returned `Branch not protected` on a fresh repository, and
GitHub reads no committed file for any of it. `rules/choices.md` records the split.

So this is a script rather than a layer: a layer renders a file, and there is no file.

`--check` reports what differs and changes nothing, which is what CI can run. Without it
the settings are applied.

Environment secrets are deliberately absent. A secret passed to a script is a secret in a
shell history, so those stay manual.

Exit codes:
    0  applied, or already correct under --check
    1  a setting differs under --check, or an API call failed
    2  usage error, or gh is unusable
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys

# Squash only. A merge commit puts a second author's subject into the history that
# release-please reads, and a rebase rewrites the commits CI already checked.
REPO_SETTINGS = {
    "allow_squash_merge": True,
    "allow_merge_commit": False,
    "allow_rebase_merge": False,
    # A merged branch left behind is a branch someone later force-pushes to.
    "delete_branch_on_merge": True,
    "allow_auto_merge": True,
    "has_issues": True,
    # A wiki is an unversioned second place for documentation the docs/ tree already owns.
    "has_wiki": False,
    "has_projects": False,
}

# Workflow token permissions, which live at their own endpoint rather than on the repository
# object, so they need their own request.
#
# `default_workflow_permissions: read` is the safe baseline: every workflow here requests what
# it needs per job, so a write default would only widen the token for jobs that never asked.
#
# `can_approve_pull_request_reviews` is misnamed. It is the switch that lets Actions CREATE a
# pull request, and release-please fails outright without it: `GitHub Actions is not permitted
# to create or approve pull requests`. Enabling it does not let the token merge anything, since
# branch protection still requires the `gate` check.
WORKFLOW_PERMISSIONS = {
    "default_workflow_permissions": "read",
    "can_approve_pull_request_reviews": True,
}

# `gate` is the only required check. It lists every other job in `needs:` and receives
# `toJSON(needs)`, so a new job is covered without touching branch protection: a
# path-filtered required check that never starts would block every unrelated pull request
# forever.
REQUIRED_CHECKS = ["gate"]


def gh(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check, timeout=60)


def slug(explicit: str | None) -> str:
    if explicit:
        return explicit
    result = gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
    if result.returncode != 0:
        print("cannot determine the repository; pass --repo OWNER/NAME", file=sys.stderr)
        raise SystemExit(2)
    return result.stdout.strip()


def current_settings(repo: str) -> dict:
    result = gh("api", f"repos/{repo}")
    if result.returncode != 0:
        print(f"cannot read repos/{repo}: {result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)
    return json.loads(result.stdout)


def apply_settings(repo: str, *, check: bool) -> list[str]:
    """Every setting that differs. Applied unless checking."""
    live = current_settings(repo)
    differences = [
        f"{key}: {live.get(key)!r} should be {value!r}"
        for key, value in REPO_SETTINGS.items()
        if live.get(key) != value
    ]
    if check or not differences:
        return differences

    argv = ["api", "--method", "PATCH", f"repos/{repo}"]
    for key, value in REPO_SETTINGS.items():
        argv += ["-F", f"{key}={'true' if value else 'false'}"]
    result = gh(*argv)
    if result.returncode != 0:
        print(f"failed to update settings: {result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)
    return differences


def apply_workflow_permissions(repo: str, *, check: bool) -> list[str]:
    """Every workflow-permission setting that differs. Applied unless checking."""
    result = gh("api", f"repos/{repo}/actions/permissions/workflow")
    if result.returncode != 0:
        print(f"cannot read workflow permissions: {result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)
    live = json.loads(result.stdout)

    differences = [
        f"{key}: {live.get(key)!r} should be {value!r}"
        for key, value in WORKFLOW_PERMISSIONS.items()
        if live.get(key) != value
    ]
    if check or not differences:
        return differences

    argv = ["api", "--method", "PUT", f"repos/{repo}/actions/permissions/workflow"]
    for key, value in WORKFLOW_PERMISSIONS.items():
        if isinstance(value, bool):
            argv += ["-F", f"{key}={'true' if value else 'false'}"]
        else:
            argv += ["-f", f"{key}={value}"]
    written = gh(*argv)
    if written.returncode != 0:
        print(f"failed to update workflow permissions: {written.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)
    return differences


def protection_differences(repo: str, branch: str) -> list[str]:
    result = gh("api", f"repos/{repo}/branches/{branch}/protection")
    if result.returncode != 0:
        # "Branch not protected" is the state of a fresh repository rather than an error.
        return [f"{branch} is not protected"]

    live = json.loads(result.stdout)
    contexts = (live.get("required_status_checks") or {}).get("contexts") or []
    problems = []
    if sorted(contexts) != sorted(REQUIRED_CHECKS):
        problems.append(f"required checks are {contexts} rather than {REQUIRED_CHECKS}")
    if not (live.get("required_pull_request_reviews") or {}):
        problems.append("a pull request is not required")
    return problems


def apply_protection(repo: str, branch: str) -> None:
    """Protect the branch with the gate as its only required check.

    Sent as a JSON body on stdin rather than as -F pairs: the endpoint takes nested objects
    and null values, which the field form cannot express.
    """
    body = {
        "required_status_checks": {"strict": True, "contexts": REQUIRED_CHECKS},
        # A pull request is required, but no approving review: a solo maintainer cannot
        # approve their own, and demanding one would make every merge an admin override.
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "required_approving_review_count": 0,
        },
        # No named restrictions on a personal repository. `null` is required rather than
        # omitted; the endpoint rejects the object without the key.
        "restrictions": None,
        "enforce_admins": False,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "required_conversation_resolution": True,
    }
    result = subprocess.run(
        [
            "gh",
            "api",
            "--method",
            "PUT",
            f"repos/{repo}/branches/{branch}/protection",
            "--input",
            "-",
        ],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        print(f"failed to protect {branch}: {result.stderr.strip()}", file=sys.stderr)
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(prog="repo_govern.py", description=__doc__)
    parser.add_argument("--check", action="store_true", help="report differences, change nothing")
    parser.add_argument("--repo", help="OWNER/NAME, otherwise the current repository")
    parser.add_argument("--branch", default="main", help="branch to protect")
    args = parser.parse_args()

    if shutil.which("gh") is None:
        print("gh is not on PATH; install it or apply these settings by hand", file=sys.stderr)
        return 2

    repo = slug(args.repo)
    problems = apply_settings(repo, check=args.check)
    problems += apply_workflow_permissions(repo, check=args.check)
    problems += protection_differences(repo, args.branch)

    if args.check:
        if problems:
            print(f"{repo}: governance differs", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            print("fix with: just repo-govern", file=sys.stderr)
            return 1
        print(f"{repo}: governance matches")
        return 0

    apply_protection(repo, args.branch)
    print(f"{repo}: settings applied, {args.branch} protected with {REQUIRED_CHECKS} required")
    print()
    print("Not automated, and deliberately: environment secrets. A secret passed to a")
    print("script is a secret in a shell history, so add those in the web interface.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
