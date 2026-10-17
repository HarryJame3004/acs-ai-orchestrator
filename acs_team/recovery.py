"""Consistent, private SQLite backups and non-destructive staged upgrades.

Backups detect corruption; their unsigned manifests are not an authenticity
proof. Every destination must be new. No operation replaces the running app.
"""

from __future__ import annotations

from .upgrade_schema import RUNTIME_SQL, COORD_SQL, METRICS_SQL, REVIEW_SQL, DISPATCH_SQL

from dataclasses import dataclass
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import subprocess
import sys
import tempfile
import uuid
import shutil
import time
from typing import Callable
from urllib.parse import quote


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def readonly_database(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Database must be an existing regular file")
    return sqlite3.connect(f"file:{quote(str(path.resolve()), safe='/')}?mode=ro", uri=True, timeout=5)


def integrity(path: Path) -> str:
    with closing(readonly_database(path)) as con:
        rows = con.execute("PRAGMA integrity_check").fetchall()
    if rows != [("ok",)]:
        raise ValueError("SQLite integrity check failed")
    return "ok"


def new_directory(path: Path) -> Path:
    if path.exists() or path.is_symlink():
        raise FileExistsError("Destination must not already exist")
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    return path.resolve()


def private_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)


def snapshot(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        raise FileExistsError("SQLite snapshot target exists")
    private_write(target, b"")
    with closing(readonly_database(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.execute("BEGIN")
        src.execute("SELECT count(*) FROM sqlite_master").fetchone()
        deadline = time.monotonic() + 30
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError("SQLite snapshot exceeded its 30 second budget")
        with dst:
            src.backup(dst, pages=128, sleep=0.01, progress=progress)
    integrity(target)


def sensitive_reference(path: Path, content: bytes) -> bool:
    name = path.name.lower()
    if name.startswith(".env") or name in {"credentials.json", "auth.json", "auth.token", ".netrc", "id_rsa", "id_ed25519"}:
        return True
    if path.suffix.lower() in {".pem", ".key", ".p12", ".db", ".sqlite", ".sqlite3"}:
        return True
    return bool(re.search(rb"(?i)BEGIN [A-Z ]*PRIVATE KEY|(?:password|api[_-]?key|access[_-]?token)\s*[=:]\s*['\"][^'\"\r\n]+", content))


def create_backup(source: Path, destination: Path, references: tuple[Path, ...] = (),
                  include_credentials: bool = False) -> dict:
    source = Path(source)
    integrity(source)
    root = new_directory(Path(destination))
    snapshot(source, root / "database.sqlite3")
    manifest: dict = {"schema_version": 1, "integrity": "ok", "files": [],
                      "credentials_included": include_credentials, "references": []}
    for index, reference in enumerate(references):
        if reference.is_symlink() or not reference.is_file():
            raise ValueError("References must be regular files, never symlinks/directories")
        # Never read real .env files unless the local operator explicitly opts in.
        if not include_credentials and reference.name.lower().startswith(".env"):
            manifest["references"].append({"name": reference.name, "included": False})
            continue
        if reference.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Reference exceeds the 4 MiB limit")
        data = reference.read_bytes()
        if not include_credentials and sensitive_reference(reference, data):
            manifest["references"].append({"name": reference.name, "included": False})
            continue
        relative = f"reference-{index:04d}"
        private_write(root / relative, data)
        manifest["references"].append({"name": reference.name, "file": relative, "included": True})
    for path in sorted(root.iterdir()):
        manifest["files"].append({"path": path.name, "size": path.stat().st_size, "sha256": file_digest(path)})
    private_write(root / "manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    verify_backup(root)
    return manifest


def verify_backup(root: Path) -> dict:
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Backup must be a real directory")
    manifest_path = root / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 1024 * 1024:
        raise ValueError("Unsafe backup manifest")
    manifest = json.loads(manifest_path.read_text())
    files = manifest.get("files")
    if manifest.get("schema_version") != 1 or not isinstance(files, list) or not 1 <= len(files) <= 10000:
        raise ValueError("Invalid backup manifest schema")
    seen = {"manifest.json"}
    for item in files:
        name = item["path"]
        if not isinstance(name, str) or len(PurePosixPath(name).parts) != 1 or name in {".", ".."} or "\\" in name or "/" in name or name in seen:
            raise ValueError("Invalid or duplicate backup member")
        seen.add(name)
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Backup member missing or symlinked")
        if path.stat().st_size != item["size"] or file_digest(path) != item["sha256"]:
            raise ValueError("Backup checksum mismatch")
    if seen != {p.name for p in root.iterdir()} or "database.sqlite3" not in seen:
        raise ValueError("Unexpected or missing backup members")
    integrity(root / "database.sqlite3")
    return manifest


def restore_backup(root: Path, target: Path) -> Path:
    manifest = verify_backup(root)
    destination = new_directory(target)
    for item in manifest["files"]:
        source = root / item["path"]
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        output = os.open(destination / item["path"], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb") as stream, os.fdopen(output, "wb") as target_stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                target_stream.write(chunk)
        if digest.hexdigest() != item["sha256"]:
            raise ValueError("Backup changed during restore")
    integrity(destination / "database.sqlite3")
    return destination


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]



MIGRATIONS = (
    Migration(1, "upgrade metadata", (
        "CREATE TABLE IF NOT EXISTS acs_upgrade_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    )),
    Migration(2, "runtime emergency controls", RUNTIME_SQL),
    Migration(3, "fenced team coordination", COORD_SQL),
    Migration(4, "measured worker intelligence", METRICS_SQL),
    Migration(5, "review intake and daemon dispatch", REVIEW_SQL + DISPATCH_SQL),
)


def apply_migrations(database: Path, migrations: tuple[Migration, ...] = MIGRATIONS) -> list[int]:
    integrity(database)
    if [m.version for m in migrations] != list(range(1, len(migrations) + 1)):
        raise ValueError("Migrations must be ordered and contiguous")
    with closing(sqlite3.connect(database, isolation_level=None)) as con:
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("BEGIN IMMEDIATE")
        try:
            con.execute("CREATE TABLE IF NOT EXISTS acs_schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            applied = {row[0]: row[1] for row in con.execute("SELECT version,name FROM acs_schema_migrations")}
            if any(version > len(migrations) or migrations[version - 1].name != name for version, name in applied.items()):
                raise ValueError("Unknown or divergent migration history")
            if sorted(applied) != list(range(1, len(applied) + 1)):
                raise ValueError("Migration history has gaps")
            done = []
            for migration in migrations:
                if migration.version not in applied:
                    for statement in migration.statements:
                        con.execute(statement)
                    con.execute("INSERT INTO acs_schema_migrations VALUES (?,?)", (migration.version, migration.name))
                    done.append(migration.version)
            if con.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("Migrated database failed integrity check")
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    return done


def migrate(database: Path, *, dry_run: bool = True, backup_directory: Path | None = None) -> dict:
    if dry_run:
        with tempfile.TemporaryDirectory(prefix="acs-migration-") as temporary:
            copied = Path(temporary) / "database.sqlite3"
            snapshot(database, copied)
            return {"dry_run": True, "applied_to_copy": apply_migrations(copied), "integrity": integrity(copied)}
    if backup_directory is None:
        raise ValueError("Applying migrations requires a new pre-migration backup destination")
    create_backup(database, backup_directory)
    return {"dry_run": False, "applied": apply_migrations(database), "integrity": integrity(database)}


def stage_upgrade(source: Path, destination: Path, database: Path,
                  health_check: Callable[[Path], bool] | None = None) -> dict:
    """Create a private candidate. Failure leaves current app/database untouched."""
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Source must be a real directory")
    if source.resolve() in destination.resolve().parents:
        raise ValueError("Staging must be outside the source installation")
    root = new_directory(destination)
    application = root / "application"
    application.mkdir(mode=0o700)
    excluded = {".git", ".venv", "venv", "state", "logs", "backups", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
    for parent, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = [name for name in dirs if name not in excluded and not (Path(parent) / name).is_symlink()]
        relative = Path(parent).relative_to(source)
        output = application / relative
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name in files:
            path = Path(parent) / name
            if path.is_symlink() or name.lower().startswith(".env") or path.stat().st_size > 4 * 1024 * 1024:
                continue
            data = path.read_bytes()
            if not sensitive_reference(path, data):
                private_write(output / name, data)
    create_backup(database, root / "pre-migration-backup")
    snapshot(database, root / "candidate.sqlite3")
    apply_migrations(root / "candidate.sqlite3")
    healthy = bool(health_check(application)) if health_check else None
    result = {"staged": str(root), "integrity": "ok", "health": "NOT_TESTED" if healthy is None else "PASS" if healthy else "FAIL",
              "activated": False, "rollback": "Original installation and database unchanged"}
    private_write(root / "upgrade.json", json.dumps(result, indent=2).encode())
    return result


def preflight(source: Path, database: Path, minimum_free_gib: float = 1) -> dict:
    if sys.version_info < (3, 12) or not source.is_dir():
        raise ValueError("Python 3.12+ and an existing source directory are required")
    free = shutil.disk_usage(source).free / 1024 ** 3
    if free < minimum_free_gib:
        raise ValueError("Insufficient staging space")
    git = subprocess.run(["git", "--version"], check=True, text=True, capture_output=True).stdout.strip()
    return {"python": sys.version.split()[0], "git": git, "free_gib": round(free, 2),
            "migration_dry_run": migrate(database), "live_service": "LOCAL_VERIFICATION_REQUIRED"}


def promote_application(candidate: Path, deployment_root: Path, *, approved: bool,
                        stop: Callable[[], None], start: Callable[[], None],
                        health: Callable[[], bool]) -> dict:
    """Operator-only reversible application pointer update, never DB rollback.

    The local operator must quiesce migrations separately and explicitly approve
    activation. Callbacks control a dedicated service. Cloud tests use fakes.
    """
    if not approved:
        raise PermissionError("Explicit local activation approval is required")
    root, application = deployment_root.resolve(), (candidate / "application").resolve()
    if root not in application.parents or not application.is_dir():
        raise ValueError("Candidate application must be inside the deployment root")
    verify_backup(candidate / "pre-migration-backup")
    integrity(candidate / "candidate.sqlite3")
    current = root / "current"
    if current.exists() and not current.is_symlink():
        raise ValueError("Current installation must be a managed symlink")
    previous = current.resolve() if current.is_symlink() else None
    if previous is not None and (root not in previous.parents or not previous.is_dir()):
        raise ValueError("Previous installation escapes deployment root")
    pending = root / f".current-{uuid.uuid4().hex}"
    stop()
    try:
        pending.symlink_to(application, target_is_directory=True)
        os.replace(pending, current)
        start()
        if not health():
            raise RuntimeError("Candidate health verification failed")
        return {"activated": True, "application": str(application), "database_replaced": False}
    except Exception:
        stop()
        if previous is not None:
            pending.symlink_to(previous, target_is_directory=True)
            os.replace(pending, current)
            start()
        elif current.is_symlink() and current.resolve() == application:
            current.unlink()
        raise RuntimeError("Activation failed; original application pointer restored; inspect service health") from None
    finally:
        if pending.is_symlink():
            pending.unlink()
