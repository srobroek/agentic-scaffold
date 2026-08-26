#!/usr/bin/env python3
"""End-to-end permutations: real generator, then render, setup, and build per profile.

    permutations.py [--only NAME[,NAME...]] [--keep]

`just profiles-build` proves what the recipes produce and deliberately skips the
generators, because they reach the network. This harness is the other half: for
every profile it runs the REAL generator the skill would run, renders the profile
over it, runs `just setup` on the pristine tree, then the profile's own build
commands. rust-gui additionally exercises `just add` for both member kinds, which
is the monorepo path nothing else covers end to end.

Network-heavy and slow by design. Run it before a release, not in CI.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
PROFILES = REPO / "profiles"


def sh(command: str, cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def bts_payload(profile: dict, name: str) -> str:
    """create-json, not the flag form: --yes rejects any stack flag.

    No projectDir key -- the CLI rejects it and creates <cwd>/<projectName>.
    """
    generated = profile.get("generator_answers") or {}
    payload = {
        "projectName": name,
        "frontend": [generated.get("bts_frontend", "tanstack-router")],
        "backend": generated.get("bts_backend", "hono"),
        "runtime": generated.get("bts_runtime", "bun"),
        "api": generated.get("bts_api", "orpc"),
        "addons": generated.get("bts_addons", ["biome", "turborepo"]),
        "database": "none",
        "orm": "none",
        "auth": "none",
        "payments": "none",
        "webDeploy": "none",
        "serverDeploy": "none",
        "dbSetup": "none",
        "examples": [],
        "git": False,
        "install": True,
        "packageManager": "bun",
    }
    return json.dumps(payload)


def generator_command(name: str, profile: dict) -> str | None:
    """The concrete command behind each profile's generator line."""
    slug = name.replace("-", "_")
    match profile.get("generator"):
        case None | "none":
            return None
        case "uv init --lib":
            return f"uv init --lib --name {slug} --no-workspace ."
        case "uv init":
            return f"uv init --name {slug} --no-workspace ."
        case "cargo new --lib":
            return f"cargo init --lib --name {slug} ."
        case "cargo new" if name == "rust-gui":
            return None  # members arrive through `just add` after the render
        case "cargo new":
            return f"cargo init --name {slug} ."
        case "go mod init <path>":
            return f"go mod init github.com/srobroek/{name}"
        case "bun init":
            return "bun init -y"
        case generator if generator.startswith("create-better-t-stack"):
            payload = bts_payload(profile, name)
            return f"bunx create-better-t-stack@latest create-json --json '{payload}'"
        case "projen new awscdk-app-ts":
            # npx, not bunx: projen's vm.runInContext crashes under bun's runtime.
            return "npx --yes projen new awscdk-app-ts --no-git"
        case other:
            return f"echo 'unmapped generator: {other}' && false"


def run_profile(name: str, scratch: Path) -> dict:
    profile = yaml.safe_load((PROFILES / f"{name}.yml").read_text())
    dest = scratch / name
    steps: list[tuple[str, str]] = []
    failures: list[str] = []

    def step(label: str, command: str, cwd: Path, timeout: int = 900) -> bool:
        result = sh(command, cwd, timeout)
        ok = result.returncode == 0
        steps.append((label, "ok" if ok else f"FAIL ({result.returncode})"))
        if not ok:
            tail = (result.stdout + result.stderr).splitlines()[-12:]
            failures.append(f"--- {name}: {label} failed: {command}\n    " + "\n    ".join(tail))
        return ok

    generator = generator_command(name, profile)
    # better-t-stack creates <cwd>/<projectName> itself and refuses a directory
    # that already exists, so its generator runs in the scratch parent; every
    # other generator initialises in place.
    bts = bool(generator) and "create-better-t-stack" in (generator or "")
    if not bts:
        dest.mkdir()
    if generator and not step("generator", generator, scratch if bts else dest, timeout=1800):
        return {"profile": name, "steps": steps, "ok": False, "failures": failures}

    render = f"uv run {REPO}/scripts/scaffold.py render --profile {name} --dest {dest} --demo"
    if not step("render", render, REPO):
        return {"profile": name, "steps": steps, "ok": False, "failures": failures}

    ok = True
    if name == "rust-gui":
        # Members FIRST: the workspace glob matches nothing until one exists, and
        # cargo refuses a memberless workspace. The ts shell is generator_then
        # territory (create-tauri-app, agent-run), so this exercises the rust
        # member path plus the moon resync the stale-check prescribes.
        env_prefix = f"SCAFFOLD={REPO} "
        ok = step("add rust member", env_prefix + "just add core rust", dest)
        ok = step("moon resync", "just moon-sync", dest) and ok

    ok = step("setup", "just setup", dest, timeout=1800) and ok

    for command in profile.get("build") or []:
        binary = command.split()[0]
        if shutil.which(binary) is None:
            steps.append((command, "skip (binary absent)"))
            continue
        ok = step(command, command, dest, timeout=1800) and ok

    return {"profile": name, "steps": steps, "ok": ok, "failures": failures}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="comma-separated profile names")
    parser.add_argument("--keep", action="store_true", help="keep the scratch tree")
    args = parser.parse_args()

    names = args.only.split(",") if args.only else sorted(p.stem for p in PROFILES.glob("*.yml"))
    scratch = Path(tempfile.mkdtemp(prefix="scaffold-permutations-"))
    print(f"scratch: {scratch}")

    # Independent temp dirs; the suite already proves concurrent renders safe
    # (pytest -n auto runs twelve at once). Five workers keeps one generator
    # family per lane, so toolchain caches contend less.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda n: run_profile(n, scratch), names))

    for result in results:
        for text in result["failures"]:
            print(f"\n{text}", file=sys.stderr)

    print(f"\n{'profile':<14} result   steps")
    failures = 0
    for result in results:
        failures += 0 if result["ok"] else 1
        summary = ", ".join(f"{label}={verdict}" for label, verdict in result["steps"])
        print(f"{result['profile']:<14} {'ok' if result['ok'] else 'FAIL':<8} {summary}")

    if not args.keep:
        shutil.rmtree(scratch, ignore_errors=True)
    print(f"\n{len(results) - failures}/{len(results)} profiles green")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
