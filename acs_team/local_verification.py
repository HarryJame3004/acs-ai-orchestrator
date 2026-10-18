"""Read-only host inspection and explicitly requested disposable probe execution."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import time
from typing import Literal

from pydantic import Field

from .db import DatabaseManager
from .evidence import EvidenceEngine
from .recovery import (
    create_backup,
    restore_backup,
    verify_backup,
    migrate,
    new_directory,
    private_write,
)
from .runtime_control import RuntimeControl
from .schemas import Data, Text, parse_data
from .security import sandbox_argv, redact
from .supervision import ProcessSupervisor


class LocalCheck(Data):
    id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,127}$")
    label: Literal["LOCAL_VERIFICATION_REQUIRED"] = "LOCAL_VERIFICATION_REQUIRED"
    status: Literal["PASS", "FAIL", "SKIPPED", "ERROR"]
    evidence: Text
    duration_s: float = Field(ge=0, le=3600)


class LocalReport(Data):
    generated_at: Text
    repo_commit: str = Field(pattern=r"^(?:[a-f0-9]{40,64}|UNKNOWN)$")
    environment: dict = Field(max_length=32)
    checks: list[LocalCheck] = Field(max_length=128)
    summary: dict[str, int] = Field(max_length=4)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, timeout=10
    ).stdout.strip()


def installation_drift(repository: Path, operational: Path) -> list[str]:
    from .config import PROTECTED_PATHS

    operational = operational.resolve()
    if any(operational == p or p in operational.parents for p in PROTECTED_PATHS):
        raise PermissionError("Protected installation path")
    names = _git(repository, "ls-files", "-z").split("\0")
    changed = []
    for name in names[:10000]:
        if (
            not name
            or any(
                part in {"state", "logs", "backups", ".git", ".aws", ".codex"}
                for part in Path(name).parts
            )
            or Path(name).name.startswith(".env")
            or Path(name).name in {"auth.token", "credentials.json", "auth.json"}
        ):
            continue
        left, right = repository / name, operational / name
        if (
            left.is_symlink()
            or right.is_symlink()
            or not left.is_file()
            or not right.is_file()
        ):
            changed.append(name)
            continue
        if (
            left.stat().st_size > 4 * 1024 * 1024
            or right.stat().st_size > 4 * 1024 * 1024
        ):
            changed.append(name)
            continue
        with left.open("rb") as a, right.open("rb") as b:
            if (
                hashlib.file_digest(a, "sha256").digest()
                != hashlib.file_digest(b, "sha256").digest()
            ):
                changed.append(name)
    return changed


def disposable_sandbox_probe(root: Path) -> tuple[str, str]:
    if not shutil.which("bwrap"):
        return "SKIPPED", "bubblewrap is not installed"
    workspace = root / "workspace"
    home = root / "home"
    private = root / "controller-private"
    workspace.mkdir()
    home.mkdir()
    private.write_text("disposable canary only")
    (workspace / "escape").symlink_to(private)
    # Constant controller script, never model text. The fixture private path is
    # outside every bind. No operational home/Core/database is inspected.
    code = 'test ! -e "$1" && test ! -r escape && test ! -e ../controller-private && printf allowed > allowed.txt'
    argv = sandbox_argv(
        workspace,
        ["/bin/sh", "-c", code, "probe", str(private)],
        home=home,
        private_paths=(private,),
    )
    result = ProcessSupervisor().run(argv, workspace, timeout=5)
    if result["exit_code"] != 0:
        if any(
            word in result["output"].casefold()
            for word in (
                "operation not permitted",
                "namespace",
                "permission denied",
                "setting up uid map: read-only file system",
            )
        ):
            return (
                "SKIPPED",
                "Host/container does not permit requested bubblewrap namespaces; verify on laptop",
            )
        return (
            "FAIL",
            "Disposable sandbox probe failed; see local supervisor exit status "
            + str(result["exit_code"]),
        )
    if (
        workspace / "allowed.txt"
    ).read_text() != "allowed" or private.read_text() != "disposable canary only":
        return "FAIL", "Sandbox write/denial invariant failed"
    return (
        "PASS",
        "Allowed workspace write, fixture private/symlink/traversal denial verified in real bwrap",
    )


def run_local_suite(repository: Path) -> tuple[str, str]:
    baseline = repository / "reports/baseline_tests.json"
    if not baseline.is_file():
        return "SKIPPED", "Local suite requires the reviewed ACS AI source checkout"
    metadata = json.loads(baseline.read_text())
    nodes = [
        row["nodeid"]
        for row in metadata["tests"]
        if row["label"] == "LOCAL_VERIFICATION_REQUIRED"
    ]
    for node in nodes:
        relative = Path(node.split("::", 1)[0])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not relative.parts
            or relative.parts[0] != "tests"
        ):
            raise ValueError("Invalid local test manifest")
    with tempfile.TemporaryDirectory(prefix="acs-local-suite-") as temporary:
        root = Path(temporary)
        environment = {
            "ACS_HOME": str(root / "runtime"),
            "ACS_BACKUPS_DIR": str(root / "backups"),
            "ACS_CREDENTIALS_FILE": str(root / "absent.json"),
        }
        environment.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        import sys

        result = ProcessSupervisor(output_limit=65536).run(
            [
                sys.executable,
                "-m",
                "pytest",
                *nodes,
                "tests/local",
                "-q",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(root / "pytest"),
            ],
            repository,
            env=environment,
            timeout=120,
        )
        return (
            "PASS"
            if result["exit_code"] == 0 and result["reason"] == "completed"
            else "FAIL",
            "Explicit local_only suite exit="
            + str(result["exit_code"])
            + "; includes legacy availability assertions, which do not prove authenticated provider tasks",
        )


def verify_local(
    repository: Path,
    *,
    execute_probes: bool = False,
    database: Path | None = None,
    operational_dir: Path | None = None,
    run_local_tests: bool = False,
) -> dict:
    repository = repository.resolve()
    checks = []

    def record(identifier, status, evidence, started):
        checks.append(
            LocalCheck(
                id=identifier,
                status=status,
                evidence=redact(evidence)[:4096],
                duration_s=round(time.monotonic() - started, 3),
            )
        )

    start = time.monotonic()
    try:
        commit = _git(repository, "rev-parse", "HEAD")
    except (OSError, subprocess.SubprocessError):
        commit = "UNKNOWN"
    environment = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "bwrap": bool(shutil.which("bwrap")),
        "git": bool(shutil.which("git")),
        "systemd_user_session": bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")),
        "disk_free_bytes": shutil.disk_usage(repository).free,
        "probe_execution_requested": execute_probes,
    }
    record(
        "environment.python",
        "PASS"
        if tuple(map(int, platform.python_version_tuple()[:2])) >= (3, 12)
        else "FAIL",
        "Python " + platform.python_version(),
        start,
    )
    record(
        "environment.git",
        "PASS" if environment["git"] else "FAIL",
        "Git executable discovery only",
        start,
    )
    if operational_dir:
        try:
            differences = installation_drift(repository, operational_dir)
            record(
                "installation.drift",
                "PASS" if not differences else "FAIL",
                f"{len(differences)} differing/missing tracked files; no secret/state files inspected",
                time.monotonic(),
            )
        except Exception:
            record(
                "installation.drift",
                "ERROR",
                "Could not safely inspect installation drift",
                time.monotonic(),
            )
    else:
        record(
            "installation.drift",
            "SKIPPED",
            "Pass --operational-dir explicitly for read-only nonsecret file comparison",
            time.monotonic(),
        )
    for name, var, binary in (
        ("codex", "CODEX_BIN", "codex"),
        ("agy_a", "AGY_A_BIN", "agy"),
        ("agy_b", "AGY_B_BIN", "agy-b"),
    ):
        executable = os.environ.get(var) or shutil.which(binary)
        record(
            "workers." + name + ".discovery",
            "PASS" if executable and Path(executable).is_file() else "SKIPPED",
            "Executable present"
            if executable and Path(executable).is_file()
            else "Executable absent; configure local path",
            time.monotonic(),
        )
        record(
            "workers." + name + ".auth_task_cleanup",
            "SKIPPED",
            "Provider authentication, harmless task, timeout/cancellation and independent HOME/XDG require completed local role adapters; discovery is not readiness",
            time.monotonic(),
        )
    record(
        "workers.environment",
        "SKIPPED",
        "Actual provider environment not captured; supervised/MCP environment boundaries require local verification",
        time.monotonic(),
    )
    with tempfile.TemporaryDirectory(prefix="acs-local-verification-") as temporary:
        root = Path(temporary)
        if execute_probes:
            begin = time.monotonic()
            try:
                status, evidence = disposable_sandbox_probe(root)
            except Exception:
                status, evidence = "ERROR", "Could not execute disposable sandbox probe"
            record("sandbox.fixture_boundaries", status, evidence, begin)
            begin = time.monotonic()
            try:
                db = DatabaseManager(root / "fixture.db")
                db.create_mission("probe", "probe", str(root), "Disposable fixture")
                control = RuntimeControl(db)
                control.stop()
                assert control.stopped()
                control = RuntimeControl(DatabaseManager(root / "fixture.db"))
                assert control.stopped()
                control.resume(operator_confirmed=True)
                assert not control.stopped()
                record(
                    "emergency_stop.test_state",
                    "PASS",
                    "Persistent stop/resume on a disposable DB; no live daemon touched",
                    begin,
                )
                engine = EvidenceEngine("disposable-local-fixture-key")
                signed_evidence = engine.create_evidence(
                    "probe", "task", "a" * 40, {"passed": True}, {}
                ).to_dict()
                assert engine.verify_evidence(signed_evidence, "a" * 40)
                signed_evidence["mission_id"] = "tampered"
                assert not engine.verify_evidence(signed_evidence, "a" * 40)
                record(
                    "guardian.fixture_hmac",
                    "PASS",
                    "Fixture evidence round trip and tamper rejection; operational key not read",
                    begin,
                )
                source = database or root / "fixture.db"
                if database:
                    from .config import PROTECTED_PATHS

                    if any(
                        source.resolve() == p or p in source.resolve().parents
                        for p in PROTECTED_PATHS
                    ):
                        raise PermissionError("Protected DB path")
                create_backup(source, root / "backup")
                verify_backup(root / "backup")
                restored = restore_backup(root / "backup", root / "restored")
                result = migrate(restored / "database.sqlite3")
                assert result["integrity"] == "ok"
                record(
                    "database.snapshot_restore_migration",
                    "PASS",
                    "SQLite API snapshot, checksums, scratch restore and migration dry-run; source not replaced",
                    begin,
                )
            except Exception:
                record(
                    "database_or_fixture.probes",
                    "ERROR",
                    "Disposable recovery/control/HMAC probe failed; no automatic live repair attempted",
                    begin,
                )
        else:
            for name in (
                "sandbox.fixture_boundaries",
                "emergency_stop.test_state",
                "guardian.fixture_hmac",
                "database.snapshot_restore_migration",
            ):
                record(
                    name,
                    "SKIPPED",
                    "Read-only default: pass --execute-probes for disposable fixture operations",
                    time.monotonic(),
                )
    if run_local_tests:
        begin = time.monotonic()
        try:
            status, explanation = run_local_suite(repository)
        except Exception:
            status, explanation = "ERROR", "Local-only suite could not safely execute"
        record("suite.local_only", status, explanation, begin)
    for name, reason in (
        (
            "guardian.operational_key_isolation",
            "Operational key location/isolation not proven; fixture HMAC does not verify the live key",
        ),
        (
            "mcp.configured_servers",
            "Use explicit approved policy with acsai mcp verify; configured servers are not assumed operational",
        ),
        (
            "service.watchdog",
            "Inspect the local user service/watchdog; no service actions are run by this command",
        ),
        (
            "multiagent.real_e2e",
            "Run acsai verify-team --output NEW_DIRECTORY --report NEW_REPORT --execute-probe after real activation; discovery is not team verification",
        ),
        (
            "suite.local_only",
            "Dedicated real provider local_only assertions remain pending; cloud availability tests do not prove authentication",
        ),
    ):
        if name != "suite.local_only" or not run_local_tests:
            record(name, "SKIPPED", reason, time.monotonic())
    counts = Counter(c.status.casefold() for c in checks)
    return LocalReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        repo_commit=commit,
        environment=environment,
        checks=checks,
        summary={name: counts[name] for name in ("pass", "fail", "skipped", "error")},
    ).model_dump()


def import_local_report(raw: bytes, destination: Path) -> dict:
    report = parse_data(LocalReport, raw, 131072)
    counts = Counter(c.status.casefold() for c in report.checks)
    if report.summary != {
        name: counts[name] for name in ("pass", "fail", "skipped", "error")
    }:
        raise ValueError("Local report summary does not match check outcomes")
    if len({c.id for c in report.checks}) != len(report.checks):
        raise ValueError("Duplicate local checks")
    root = new_directory(destination)
    private_write(
        root / "local_verification_report.json",
        (json.dumps(redact(report.model_dump()), indent=2) + "\n").encode(),
    )
    lines = [
        "# Imported local verification\n",
        "User-supplied evidence; not independently authenticated by the cloud.\n",
        "| Check | Status | Evidence |",
        "|---|---|---|",
    ]
    for check in report.checks:
        evidence = redact(check.evidence).replace("|", "/").replace("\n", " ")[:512]
        lines.append(f"| {check.id} | {check.status} | {evidence} |")
    private_write(
        root / "LOCAL_VERIFICATION_CHECKLIST.md", ("\n".join(lines) + "\n").encode()
    )
    return {
        "status": "IMPORTED_UNTRUSTED_EVIDENCE",
        "summary": report.summary,
        "automatic_feature_activation": False,
    }
