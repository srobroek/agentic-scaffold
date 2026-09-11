from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def copy_template(tmp_path: Path):
    def render(destination: Path, **answers: object) -> Path:
        command = ["uvx", "copier", "copy", "--defaults"]
        for key, value in answers.items():
            command.extend(["--data", f"{key}={str(value).lower() if isinstance(value, bool) else value}"])
        command.extend([str(ROOT), str(destination)])
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        return destination

    return render


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)


def git_commit(path: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", message], check=True)
