"""Real Git object packaging excludes secret files and does not overwrite artifacts."""

import json
import subprocess
import zipfile

import pytest

from scripts.build_local_bundle import build


def test_bundle_uses_committed_blobs_excludes_credentials_and_symlinks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout

    git("init", "-b", "main")
    git("config", "user.name", "Fixture")
    git("config", "user.email", "fixture@example.invalid")
    (repo / "app.py").write_text("answer=42\n")
    (repo / ".env").write_text("fixture only\n")
    (repo / "outside-link").symlink_to(tmp_path / "outside")
    git("add", ".")
    git("commit", "-m", "fixture")
    (repo / "app.py").write_text("uncommitted change must not be packaged\n")
    archive = tmp_path / "bundle.zip"
    result = build(repo, archive)
    assert (
        result["automatic_activation"] is False
        and archive.stat().st_mode & 0o777 == 0o600
    )
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.read("app.py") == b"answer=42\n"
        assert (
            ".env" not in bundle.namelist() and "outside-link" not in bundle.namelist()
        )
        manifest = json.loads(bundle.read("ACS_BUNDLE_MANIFEST.json"))
        assert sorted(manifest["excluded"]) == [".env", "outside-link"]
    with pytest.raises(FileExistsError):
        build(repo, archive)
