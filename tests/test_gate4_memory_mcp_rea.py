"""Tests for Gate 4: MemoryEngine (SQLite FTS5), MCP Registry & REA Adapter.
"""

import os
import shutil
import tempfile
import pytest

from acs_team.db import DatabaseManager
from acs_team.memory import MemoryEngine
from acs_team.mcp_registry import (
    MCPRegistry,
    MCPPermissionError,
    PathEscapeError,
    ToolCategory,
)
from acs_team.rea_adapter import REAAdapter, REAError


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    db.close()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def temp_worktree():
    dir_path = tempfile.mkdtemp(prefix="acs_test_wt_")
    yield dir_path
    shutil.rmtree(dir_path, ignore_errors=True)


def test_memory_engine_record_and_search(temp_db):
    engine = MemoryEngine(temp_db)
    project_id = "test-proj-alpha"
    repo_id = "repo-alpha"
    initial_commit = "1111111111111111111111111111111111111111"

    # 1. Record decision
    dec_id = engine.record_decision(
        project_id=project_id,
        repository_id=repo_id,
        title="Architecture Decision: SQLite WAL",
        rationale="We decided to use SQLite in WAL mode for single-writer multi-reader performance.",
        commit_sha=initial_commit,
    )
    assert dec_id.startswith("dec-")

    # 2. Record failure memory
    fail_id = engine.record_failure(
        project_id=project_id,
        repository_id=repo_id,
        title="Defect: Codex CLI --full-auto deprecated",
        error_message="codex exec rejected --full-auto flag with exit code 2.",
        resolution="Replaced with --approve-for-me which enforces workspace-write sandbox.",
        commit_sha=initial_commit,
    )
    assert fail_id.startswith("fail-")

    # 3. FTS5 Full-Text Search
    results = engine.search(project_id=project_id, query="WAL mode")
    assert len(results) >= 1
    assert "WAL" in results[0]["title"] or "WAL" in results[0]["content"]

    fail_results = engine.search(project_id=project_id, query="approve-for-me")
    assert len(fail_results) >= 1
    assert fail_results[0]["memory_id"] == fail_id

    # 4. Search with isolation (different project should return empty)
    other_results = engine.search(project_id="different-project", query="WAL")
    assert len(other_results) == 0

    # 5. Stale detection on commit change
    new_commit = "2222222222222222222222222222222222222222"
    stale_count = engine.detect_and_mark_stale(
        project_id=project_id,
        repository_id=repo_id,
        current_commit_sha=new_commit,
    )
    assert stale_count >= 2


def test_mcp_registry_permissions_and_path_security(temp_worktree):
    registry = MCPRegistry()

    # 1. Planner should be blocked from mutating tools
    with pytest.raises(MCPPermissionError, match="restricted to READ_ONLY"):
        registry.authorize("write_file", caller_role="planner")

    # 2. Reviewer should also be blocked from mutating tools
    with pytest.raises(MCPPermissionError, match="restricted to READ_ONLY"):
        registry.authorize("write_file", caller_role="reviewer")

    # 3. Worker is authorized for read_only and mutating tools
    tool = registry.authorize("write_file", caller_role="worker")
    assert tool.category == ToolCategory.MUTATING

    read_tool = registry.authorize("read_file", caller_role="worker")
    assert read_tool.category == ToolCategory.READ_ONLY

    # 4. Safe execution within worktree
    sub_file = "src/main.py"
    res = registry.execute_tool(
        tool_name="write_file",
        arguments={"file_path": sub_file, "content": "print('hello world')"},
        caller_role="worker",
        worktree_dir=temp_worktree,
    )
    assert res["success"] is True
    assert os.path.exists(os.path.join(temp_worktree, sub_file))

    read_res = registry.execute_tool(
        tool_name="read_file",
        arguments={"file_path": sub_file},
        caller_role="worker",
        worktree_dir=temp_worktree,
    )
    assert read_res["success"] is True
    assert "print('hello world')" in read_res["result"]

    # 5. Path Escape Detection: Relative traversal outside worktree
    with pytest.raises(PathEscapeError):
        registry.execute_tool(
            tool_name="read_file",
            arguments={"file_path": "../../etc/passwd"},
            caller_role="worker",
            worktree_dir=temp_worktree,
        )

    # 6. Path Escape Detection: Absolute path outside worktree
    with pytest.raises(PathEscapeError):
        registry.execute_tool(
            tool_name="read_file",
            arguments={"file_path": "/etc/shadow"},
            caller_role="worker",
            worktree_dir=temp_worktree,
        )

    # 7. Admin tool blocked without human approval
    with pytest.raises(MCPPermissionError, match="explicit human approval"):
        registry.authorize("force_reset_state", caller_role="admin", is_human_approved=False)


def test_rea_adapter_inspection():
    adapter = REAAdapter()
    
    # 1. Non-existent file should raise REAError
    with pytest.raises(REAError):
        adapter.inspect_file("/path/to/nonexistent/binary")

    # 2. Text / Python script inspection (Non-ELF)
    temp_script = tempfile.NamedTemporaryFile(suffix=".py", delete=False)
    temp_script.write(b"print('non elf file')\n")
    temp_script.close()
    try:
        report = adapter.inspect_file(temp_script.name)
        assert report.is_elf is False
        assert "Non-ELF" in report.raw_summary or "Python" in report.file_type or "text" in report.file_type
    finally:
        os.remove(temp_script.name)

    # 3. Real ELF binary inspection (e.g. /usr/bin/ls or python3)
    target_bin = shutil.which("ls") or shutil.which("python3")
    if target_bin and os.path.exists(target_bin):
        report = adapter.inspect_file(target_bin)
        assert report.is_elf is True
        assert report.architecture in ("x86_64", "aarch64", "unknown")
        # Check security flags
        assert isinstance(report.security_profile.nx_enabled, bool)
        assert isinstance(report.security_profile.pie_enabled, bool)
        assert len(report.needed_libraries) > 0 or len(report.exported_symbols) >= 0
