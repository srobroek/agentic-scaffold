"""container/image: the Dockerfile, its lint, and the build-scan-push order.

The base image policy is measured rather than asserted. Against the same static Go
binary: distroless static 9.58MB with 12 HIGH or CRITICAL findings, alpine 16.8MB with
12, debian stable-slim 143MB with 34. distroless also carries no shell, where
`docker run --entrypoint sh` succeeded as uid 0 on alpine.

The docker tests need a running daemon and are skipped without one.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import render_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent

GO = """\
project_name: probeapp
container_language: go
container_runtime_base: distroless
expose_port: 8080
default_branch: main
"""


def answers(language: str, base: str, port: int = 8080) -> str:
    return (
        f"project_name: probeapp\ncontainer_language: {language}\n"
        f"container_runtime_base: {base}\nexpose_port: {port}\ndefault_branch: main\n"
    )


def hadolint_bin() -> str | None:
    root = Path.home() / ".local/share/mise/installs"
    if root.is_dir():
        for candidate in root.rglob("hadolint"):
            if candidate.is_file() and candidate.stat().st_mode & 0o111:
                return str(candidate)
    return shutil.which("hadolint")


def docker_up() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


needs_hadolint = pytest.mark.skipif(hadolint_bin() is None, reason="hadolint absent")
needs_docker = pytest.mark.skipif(not docker_up(), reason="no docker daemon")
slow = pytest.mark.skipif(
    os.environ.get("SCAFFOLD_SKIP_SLOW") == "1", reason="SCAFFOLD_SKIP_SLOW=1"
)


def render(dest: Path, spec: str) -> subprocess.CompletedProcess[str]:
    return render_recipe("container/image", dest, spec)


@pytest.fixture
def container(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render(dest, GO)
    assert result.returncode == 0, result.stderr
    return dest


@pytest.fixture
def buildable(container: Path) -> Path:
    """A real Go program, so the build stage has something to compile."""
    (container / "go.mod").write_text("module probeapp\n\ngo 1.24\n")
    (container / "main.go").write_text(
        'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("probeapp up") }\n'
    )
    return container


# --- the base image policy -------------------------------------------------


def test_distroless_is_the_default(container: Path) -> None:
    """Smallest, fewest findings, and no shell for a compromise to use."""
    body = (container / "Dockerfile").read_text()
    assert "gcr.io/distroless/static-debian12:nonroot" in body


def test_the_policy_is_recorded_beside_the_choice(container: Path) -> None:
    """The bead required a base image policy to be recorded, and a decision stated where
    it is made survives better than one in a document nobody opens."""
    body = (container / "Dockerfile").read_text()
    assert "9.58MB" in body, "the measured sizes belong beside the FROM"
    assert "NO SHELL" in body


def test_a_compiled_language_gets_the_static_variant(container: Path) -> None:
    """`static` needs a static binary, which is why CGO is disabled in the build stage."""
    body = (container / "Dockerfile").read_text()
    assert "CGO_ENABLED=0" in body
    assert "distroless/static" in body


def test_an_interpreted_language_gets_its_interpreter(tmp_path: Path) -> None:
    """`static` has no interpreter, so python and ts take the language variant."""
    for language, expected in (("python", "python3-debian12"), ("ts", "nodejs22-debian12")):
        dest = tmp_path / language
        dest.mkdir()
        subprocess.run(["git", "init", "-q", str(dest)], check=True)
        assert render(dest, answers(language, "distroless")).returncode == 0
        assert expected in (dest / "Dockerfile").read_text()


def test_a_base_that_defaults_to_root_creates_a_user(tmp_path: Path) -> None:
    """distroless:nonroot already runs as 65532. alpine and debian default to root, so the
    user is created and selected explicitly."""
    for base, command in (("alpine", "adduser"), ("debian", "useradd")):
        dest = tmp_path / base
        dest.mkdir()
        subprocess.run(["git", "init", "-q", str(dest)], check=True)
        assert render(dest, answers("go", base)).returncode == 0
        body = (dest / "Dockerfile").read_text()
        assert command in body
        assert "\nUSER app" in body


def test_distroless_writes_no_user_line(container: Path) -> None:
    body = (container / "Dockerfile").read_text()
    assert "\nUSER " not in body, "distroless:nonroot is already uid 65532"


# --- the Dockerfile itself -------------------------------------------------


def test_it_is_multi_stage(container: Path) -> None:
    """The toolchain that builds must not ship."""
    body = (container / "Dockerfile").read_text()
    assert body.count("FROM ") >= 2
    assert "AS build" in body
    assert "COPY --from=build" in body


def test_no_expose_when_the_port_is_zero(tmp_path: Path) -> None:
    """A batch job or a CLI listens on nothing."""
    dest = tmp_path / "noport"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render(dest, answers("go", "distroless", port=0)).returncode == 0
    assert "EXPOSE" not in (dest / "Dockerfile").read_text()


def test_the_dockerignore_excludes_state_and_secrets(container: Path) -> None:
    """The context is uploaded before the first instruction runs, and a .env copied into a
    layer stays in the image history even if a later layer deletes it."""
    patterns = {
        line.strip()
        for line in (container / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    for name in (".git", ".env", ".venv", "node_modules", ".beads"):
        assert name in patterns, f"{name} belongs out of the build context"


def test_an_existing_dockerfile_is_not_overwritten(container: Path) -> None:
    """The bead's other open question: whoever wrote the Dockerfile owns it, and the layer
    contributes the CI and hooks around whatever is there."""
    (container / "Dockerfile").write_text("FROM scratch\n# hand-written\n")
    assert render(container, GO).returncode == 0
    assert "hand-written" in (container / "Dockerfile").read_text()


# --- order: build, scan, then push -----------------------------------------


def test_the_scan_precedes_the_push(container: Path) -> None:
    """An image already in a registry can be pulled by anything watching it, so a scan
    that runs after the push reports a vulnerability that has already shipped."""
    workflow = yaml.safe_load(
        (container / ".github" / "workflows" / "wc-container.yml").read_text()
    )
    names = [step.get("name", "") for step in workflow["jobs"]["image"]["steps"]]

    build = names.index("Build")
    fail = names.index("Fail on findings")
    push = names.index("Push")
    assert build < fail < push, f"order must be build, scan, push; got {names}"


def test_the_build_step_does_not_push(container: Path) -> None:
    """`push: false` regardless of the input, because the push is a later step gated on
    the scan."""
    workflow = yaml.safe_load(
        (container / ".github" / "workflows" / "wc-container.yml").read_text()
    )
    build = next(s for s in workflow["jobs"]["image"]["steps"] if s.get("name") == "Build")
    assert build["with"]["push"] is False
    # Loaded into the local daemon, or the scan has no image to read.
    assert build["with"]["load"] is True


def test_the_push_is_conditional(container: Path) -> None:
    """A pull request builds and scans without publishing."""
    workflow = yaml.safe_load(
        (container / ".github" / "workflows" / "wc-container.yml").read_text()
    )
    push = next(s for s in workflow["jobs"]["image"]["steps"] if s.get("name") == "Push")
    assert push["if"] == "inputs.push"


def test_the_gitlab_job_scans_before_pushing_too(container: Path) -> None:
    fragment = yaml.safe_load((container / ".gitlab" / "ci" / "container.yml").read_text())
    script = "\n".join(fragment["container-build"]["script"])
    assert script.index("trivy") < script.index("docker push")
    for name in fragment:
        assert name.lstrip(".").startswith("container"), f"{name} is not namespaced"


def test_only_the_lint_runs_at_commit_time(container: Path) -> None:
    """Building an image takes minutes and needs a daemon, so the build and scan are CI."""
    fragment = yaml.safe_load((container / ".pre-commit.d" / "container.yaml").read_text())
    ids = {hook["id"] for repo in fragment["repos"] for hook in repo["hooks"]}
    assert ids == {"hadolint"}


def test_every_action_is_pinned_to_a_sha(container: Path) -> None:
    for line in (container / ".github" / "workflows" / "wc-container.yml").read_text().splitlines():
        if "uses:" not in line:
            continue
        reference = line.split("uses:", 1)[1].strip().split()[0]
        if reference.startswith("./"):
            continue
        _, _, version = reference.partition("@")
        assert len(version) == 40 and all(c in "0123456789abcdef" for c in version), (
            f"{reference} is not pinned to a SHA"
        )


# --- the real tools --------------------------------------------------------


@needs_hadolint
@pytest.mark.parametrize(
    ("language", "base"),
    [
        ("go", "distroless"),
        ("rust", "distroless"),
        ("python", "distroless"),
        ("ts", "distroless"),
        ("go", "alpine"),
        ("go", "debian"),
    ],
)
def test_hadolint_accepts_every_combination(tmp_path: Path, language: str, base: str) -> None:
    """A rendered Dockerfile has to pass the hook the layer ships."""
    dest = tmp_path / f"{language}-{base}"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render(dest, answers(language, base)).returncode == 0

    result = subprocess.run(
        [hadolint_bin(), "Dockerfile"], cwd=dest, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


@needs_docker
@slow
def test_the_rendered_dockerfile_builds_and_runs(buildable: Path) -> None:
    """The bead's acceptance criterion, against a real daemon."""
    tag = "scaffold-test-probeapp:pytest"
    build = subprocess.run(
        ["docker", "build", "-t", tag, "."],
        cwd=buildable,
        capture_output=True,
        text=True,
        check=False,
        timeout=1200,
    )
    assert build.returncode == 0, build.stdout[-2000:] + build.stderr[-2000:]

    try:
        run = subprocess.run(
            ["docker", "run", "--rm", tag], capture_output=True, text=True, check=False, timeout=120
        )
        assert run.returncode == 0, run.stderr
        assert "probeapp up" in run.stdout

        # uid 65532 is distroless:nonroot. A root image would leave root-owned files in
        # any mounted volume.
        user = subprocess.run(
            ["docker", "inspect", tag, "--format", "{{.Config.User}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert user.stdout.strip() == "65532"

        # No shell for a compromised process to reach.
        shell = subprocess.run(
            ["docker", "run", "--rm", "--entrypoint", "sh", tag, "-c", "id"],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert shell.returncode != 0, "the runtime base must carry no shell"
    finally:
        subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, check=False)


# --- provenance attestation ------------------------------------------------


def workflow(dest: Path) -> dict:
    return yaml.safe_load((dest / ".github" / "workflows" / "wc-container.yml").read_text())


def test_the_attestation_binds_the_digest_not_the_tag(container: Path) -> None:
    """A tag is mutable, so an attestation bound to one says nothing about what a puller
    receives later. The digest comes from the push step's own output, which is why that step
    carries an id."""
    steps = workflow(container)["jobs"]["image"]["steps"]
    push = next(s for s in steps if s.get("name") == "Push")
    assert push["id"] == "push"

    attest = next(s for s in steps if "attest-build-provenance" in str(s.get("uses", "")))
    assert attest["with"]["subject-digest"] == "${{ steps.push.outputs.digest }}"
    assert "subject-path" not in attest["with"], "a path would re-hash a file, not the manifest"


def test_the_attestation_only_runs_on_a_push(container: Path) -> None:
    """There is no digest without a push, and a pull request builds without publishing."""
    steps = workflow(container)["jobs"]["image"]["steps"]
    attest = next(s for s in steps if "attest-build-provenance" in str(s.get("uses", "")))
    assert attest["if"] == "inputs.push"


def test_the_attestation_follows_the_push(container: Path) -> None:
    """The subject is a digest, and a digest exists only once the artefact does."""
    steps = workflow(container)["jobs"]["image"]["steps"]
    push = next(i for i, s in enumerate(steps) if s.get("name") == "Push")
    attest = next(
        i for i, s in enumerate(steps) if "attest-build-provenance" in str(s.get("uses", ""))
    )
    assert attest > push


def test_the_attestation_permissions_are_granted(container: Path) -> None:
    """id-token mints the short-lived signing certificate and attestations writes the bundle.
    A called workflow cannot hold more than its caller granted, so both are also documented
    as the caller's to grant."""
    permissions = workflow(container)["jobs"]["image"]["permissions"]
    assert permissions["id-token"] == "write"
    assert permissions["attestations"] == "write"


def test_the_bundle_is_pushed_beside_the_image(container: Path) -> None:
    """Without it `gh attestation verify oci://...` fails for someone who has the image and
    not the repository."""
    steps = workflow(container)["jobs"]["image"]["steps"]
    attest = next(s for s in steps if "attest-build-provenance" in str(s.get("uses", "")))
    assert attest["with"]["push-to-registry"] is True


def test_attestation_can_be_turned_off(tmp_path: Path) -> None:
    """A repository pushing to a registry that does not host attestations has no use for the
    step, and the two extra permissions should not be requested for nothing."""
    dest = tmp_path / "off"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render(dest, GO + "container_attest: false\n").returncode == 0

    job = workflow(dest)["jobs"]["image"]
    assert "id-token" not in job["permissions"]
    assert "attestations" not in job["permissions"]
    assert not any("attest" in str(s.get("uses", "")) for s in job["steps"])


def test_the_publishing_job_does_not_cache(container: Path) -> None:
    """This job pushes an image users pull, so a poisoned cache entry would end up inside it.
    zizmor reports the combination of a cache opt-in and a publish step as cache-poisoning at
    high severity, and reported exactly that against this workflow before the change. Only
    hadolint and just come from mise here, so a cold install costs seconds."""
    steps = workflow(container)["jobs"]["image"]["steps"]
    mise = next(s for s in steps if "mise-action" in str(s.get("uses", "")))
    assert mise["with"]["cache"] is False
