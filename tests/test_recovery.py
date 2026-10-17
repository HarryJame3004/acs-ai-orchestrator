"""CLOUD_REAL: SQLite/WAL, manifest boundaries, migrations and staging."""

import json
import sqlite3
import os
import subprocess
import sys
import threading

import pytest

from acs_team.recovery import (MIGRATIONS, Migration, apply_migrations, create_backup, integrity,
                               migrate, preflight, promote_application, restore_backup, stage_upgrade, verify_backup)


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "source.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE missions (id INTEGER PRIMARY KEY, goal TEXT)")
        con.execute("INSERT INTO missions VALUES (1, 'preserve history')")
    con.close()  # Finish the fixture's WAL checkpoint before byte-level assertions.
    return path


def test_wal_backup_during_concurrent_writes_and_restore(database, tmp_path):
    active, stop = threading.Event(), threading.Event()
    def writer():
        with sqlite3.connect(database) as con:
            index = 2
            while not stop.is_set():
                con.execute("INSERT INTO missions VALUES (?,?)", (index, "concurrent"))
                con.commit()
                index += 1
                active.set()
    thread = threading.Thread(target=writer)
    thread.start()
    try:
        assert active.wait(5)
        manifest = create_backup(database, tmp_path / "backup")
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()
    assert manifest["integrity"] == "ok"
    restored = restore_backup(tmp_path / "backup", tmp_path / "restored")
    with sqlite3.connect(restored / "database.sqlite3") as con:
        assert con.execute("SELECT goal FROM missions WHERE id=1").fetchone()[0] == "preserve history"
        assert con.execute("SELECT count(*) FROM missions").fetchone()[0] >= 2
    assert (restored.stat().st_mode & 0o777) == 0o700
    assert ((restored / "database.sqlite3").stat().st_mode & 0o777) == 0o600


def test_secret_references_excluded_by_default(database, tmp_path):
    private = tmp_path / ".env"
    private.write_text("synthetic fixture only")
    public = tmp_path / "config.toml"
    public.write_text('mode = "development"')
    manifest = create_backup(database, tmp_path / "backup", (private, public))
    assert manifest["references"][0]["included"] is False
    assert manifest["references"][1]["included"] is True
    assert not (tmp_path / "backup" / "reference-0000").exists()


@pytest.mark.parametrize("attack", ["checksum", "traversal", "symlink", "extra"])
def test_malicious_or_corrupt_backup_rejected(database, tmp_path, attack):
    root = tmp_path / "backup"
    create_backup(database, root)
    if attack == "checksum":
        (root / "database.sqlite3").write_bytes(b"corrupt")
    elif attack == "traversal":
        manifest = json.loads((root / "manifest.json").read_text())
        manifest["files"][0]["path"] = "../outside"
        (root / "manifest.json").write_text(json.dumps(manifest))
    elif attack == "symlink":
        (root / "database.sqlite3").unlink()
        (root / "database.sqlite3").symlink_to(database)
    else:
        (root / "extra").write_text("unexpected")
    with pytest.raises(ValueError):
        verify_backup(root)
    assert integrity(database) == "ok"


def test_migrations_are_copy_first_idempotent_and_transactional(database, tmp_path):
    before = database.read_bytes()
    assert migrate(database)["applied_to_copy"] == [m.version for m in MIGRATIONS]
    assert database.read_bytes() == before
    assert migrate(database, dry_run=False, backup_directory=tmp_path / "backup")["applied"] == [m.version for m in MIGRATIONS]
    assert apply_migrations(database) == []
    failing = (*MIGRATIONS, Migration(len(MIGRATIONS)+1, "broken", (
        "CREATE TABLE should_rollback (value TEXT)", "INVALID SQL",
    )))
    with pytest.raises(sqlite3.Error):
        apply_migrations(database, failing)
    with sqlite3.connect(database) as con:
        assert con.execute("SELECT goal FROM missions").fetchone()[0] == "preserve history"
        assert not con.execute("SELECT name FROM sqlite_master WHERE name='should_rollback'").fetchone()
        assert con.execute("SELECT count(*) FROM acs_schema_migrations").fetchone()[0] == len(MIGRATIONS)


def test_restore_refuses_existing_installation(database, tmp_path):
    create_backup(database, tmp_path / "backup")
    with pytest.raises(FileExistsError):
        restore_backup(tmp_path / "backup", tmp_path)


def test_stage_never_activates_or_modifies_original(database, tmp_path):
    source = tmp_path / "app"
    source.mkdir()
    (source / "main.py").write_text("print('working')")
    (source / ".env").write_text("synthetic fixture only")
    original = database.read_bytes()
    observed = []
    result = stage_upgrade(source, tmp_path / "candidate", database,
                           health_check=lambda app: observed.append(app) or (app / "main.py").is_file())
    assert result["health"] == "PASS" and result["activated"] is False
    assert observed == [tmp_path / "candidate" / "application"]
    assert not (observed[0] / ".env").exists()
    assert database.read_bytes() == original


def test_readonly_preflight(database, tmp_path):
    result = preflight(tmp_path, database)
    assert result["migration_dry_run"]["dry_run"] is True
    assert result["live_service"] == "LOCAL_VERIFICATION_REQUIRED"


def test_cli_backup_verify_restore_and_dry_run(database, tmp_path):
    env = os.environ.copy()
    env.update(ACS_ENABLE_RECOVERY="1", ACS_HOME=str(tmp_path / "runtime"),
               ACS_BACKUPS_DIR=str(tmp_path / "private-backups"),
               ACS_CREDENTIALS_FILE=str(tmp_path / "absent.json"), ACS_API_PORT="0")
    def cli(*argv):
        result = subprocess.run([sys.executable, "-m", "acs_team.cli", *argv],
                                capture_output=True, text=True, env=env, check=True)
        return json.loads(result.stdout)
    backup = str(tmp_path / "backup")
    assert cli("backup", "create", "--database", str(database), "--target", backup)["integrity"] == "ok"
    assert cli("backup", "verify", backup)["schema_version"] == 1
    assert cli("backup", "restore", backup, "--target", str(tmp_path / "restored"))["restored_to"]
    assert cli("migrate", "--database", str(database))["dry_run"] is True


@pytest.mark.simulated
def test_application_health_failure_restores_previous_pointer(database, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.py").write_text("print('candidate')")
    deployment = tmp_path / "deploy"
    previous = deployment / "previous"
    previous.mkdir(parents=True)
    current = deployment / "current"
    current.symlink_to(previous, target_is_directory=True)
    candidate = deployment / "candidate"
    stage_upgrade(source, candidate, database)
    calls = []
    with pytest.raises(RuntimeError, match="original application pointer restored"):
        promote_application(candidate, deployment, approved=True,
                            stop=lambda: calls.append("stop"), start=lambda: calls.append("start"), health=lambda: False)
    assert current.resolve() == previous
    assert calls == ["stop", "start", "stop", "start"]
    assert integrity(database) == "ok"
    with pytest.raises(PermissionError):
        promote_application(candidate, deployment, approved=False,
                            stop=lambda: None, start=lambda: None, health=lambda: True)
