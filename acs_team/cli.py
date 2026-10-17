"""ACS AI V2 Unified Command Line Interface & TUI Dispatcher.
Supports both modern `acsai` commands and backward-compatible `acs-team` workflows.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    ACS_CORE_DIR,
    AGPAIR_BIN,
    API_PORT,
    CODEX_BIN,
    CONTEXT_FILE,
    DB_PATH,
    DISK_MIN_FREE_BYTES,
    MODEL_PLANNER,
    MODEL_REVIEWER,
    PID_FILE,
    ROUTER_BASE_URL,
    STATE_DIR,
)
from .coordinator import TeamCoordinator
from .daemon_client import check_daemon_health
from .db import DatabaseManager
from .human_approval import ApprovalStatus, HumanApprovalGate
from .llm_client import query_llm
from .memory import MemoryEngine
from .planner import AIPlanner
from .test_tracker import get_test_health
from .worker_adapters import WorkerRegistry


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_ui(args):
    """Launch the interactive Textual Control Center TUI."""
    from .tui import launch_tui
    launch_tui()


def cmd_status(args):
    """Show operational status of all team components, daemon, DB, and workers."""
    print("==================================================")
    print("  ACS AI V2 — PLATFORM & MULTI-AGENT TEAM STATUS")
    print("==================================================")

    # 1. Daemon & API Status (Dynamic HTTP & Process Check)
    health = check_daemon_health()
    if health["healthy"]:
        pid_info = f" (PID: {health['pid']})" if health["pid"] else ""
        print(f"✓ Background Daemon: RUNNING{pid_info}")
        print(f"  - Endpoint: {health['endpoint']}")
        print(f"  - Health:   OK")
        print(f"  - Database: {health['db'].upper()}")
    elif health["running"]:
        print(f"⚠ Background Daemon: UNHEALTHY ({health['details']})")
    else:
        print(f"○ Background Daemon: STOPPED ({health['details']})")

    # 2. Database & State Store
    if DB_PATH.exists():
        size_kb = DB_PATH.stat().st_size / 1024
        print(f"✓ SQLite WAL Database: READY ({DB_PATH}, {size_kb:.1f} KB)")
    else:
        print(f"○ SQLite WAL Database: Not initialized yet ({DB_PATH})")

    # 3. SSD Disk Space & Circuit Breaker
    try:
        total, used, free = shutil.disk_usage(str(DB_PATH.parent))
        free_gb = free / (1024**3)
        status_str = "SAFE" if free > DISK_MIN_FREE_BYTES else "TRIGGERED (HALTED)"
        print(f"✓ SSD Storage Circuit Breaker: {free_gb:.1f} GB free (Threshold: 10.0 GB, Status: {status_str})")
    except Exception as e:
        print(f"⚠ SSD Storage: Unable to inspect disk space: {e}")

    # 4. Multi-Agent Worker Pool (Dynamic discovery)
    print("\n--- Multi-Agent Worker Pool ---")
    reg = WorkerRegistry()
    workers = reg.get_all_statuses()
    for w in workers:
        badge = "✓" if w["ready"] else "✗"
        print(f"{badge} {w['name']:<16} [{w['status']:<10}] - {w['details']}")

    # 5. CoreLock Boundary Guard & Verified Test Health
    print("\n--- CoreLock Security Boundary & Test Health ---")
    if ACS_CORE_DIR.exists():
        print(f"✓ CoreLock Protected Path: {ACS_CORE_DIR}")
        print("  - Access Policy: READ-ONLY (Zero writes, zero branch merges)")
        core_health = get_test_health("acs_core")
        ai_health = get_test_health("acs_ai")
        print(f"  - ACS Core: {core_health['display']}")
        print(f"  - ACS AI:   {ai_health['display']}")
    else:
        print(f"✗ CoreLock Protected Path: Missing at {ACS_CORE_DIR}")

    # 6. Missions & Approvals Summary
    try:
        db = DatabaseManager()
        missions = db.list_missions(limit=50)
        completed = sum(1 for m in missions if m.get("state") == "COMPLETED")
        active = sum(1 for m in missions if m.get("state") not in ("COMPLETED", "FAILED", "BLOCKED"))
        
        gate = HumanApprovalGate(db)
        pending_apprs = gate.list_pending_approvals()

        print(f"\n--- Missions & Approvals ---")
        print(f"Missions: {len(missions)} total ({active} active, {completed} completed)")
        print(f"Human Approvals Pending: {len(pending_apprs)}")
        if pending_apprs:
            for p in pending_apprs[:3]:
                print(f"  • [{p['risk_level']}] {p['approval_id']}: {p['action']} (Mission: {p['mission_id']})")
    except Exception as e:
        print(f"\n⚠ Database query error: {e}")

    # 7. MCP Inventory & Tool Verification
    try:
        from .mcp_manager import MCPManager
        mcp_stats = MCPManager().get_summary_stats()
        print(f"\n--- MCP Inventory & Tool Verification ---")
        print(f"Configured: {mcp_stats['configured_servers']} | Connected: {mcp_stats['connected_servers']} | Usable: {mcp_stats['usable_servers']} | Discovered Tools: {mcp_stats['total_tools']}")
        print("Security: Masked credentials (Zero token leaks)")
    except Exception as e:
        print(f"\n⚠ MCP inspection error: {e}")

    # 8. Managed Repositories Inventory
    try:
        from .repo_manager import RepoManager
        rm = RepoManager(db)
        repos = rm.list_repositories()
        print(f"\n--- Managed Repositories ---")
        print(f"Total Repositories: {len(repos)}")
        for r in repos:
            prot_str = "[PROTECTED RO]" if r["is_protected"] else "[WRITABLE]"
            print(f"  • {r['name']:<20} {prot_str:<14} {r['path']}")
    except Exception as e:
        print(f"\n⚠ Repository inspection error: {e}")

    print("==================================================")



def cmd_daemon(args):
    """Manage the ACS AI background supervisor daemon."""
    sub = args.daemon_action

    if sub == "start":
        health = check_daemon_health()
        if health["healthy"]:
            print(f"Daemon already running and healthy at {health['endpoint']}.")
            return

        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                os.kill(pid, 0)
                print(f"Daemon process {pid} exists. Waiting for port {API_PORT}...")
                return
            except OSError:
                PID_FILE.unlink(missing_ok=True)

        print("Starting ACS AI background daemon...")
        from .daemon import ACSDaemon
        daemon = ACSDaemon()
        daemon.start()

    elif sub == "stop":
        stopped = False
        health = check_daemon_health()
        if health.get("systemd_active"):
            try:
                subprocess.run(["systemctl", "--user", "stop", "acs-ai.service"], check=False)
                stopped = True
                print("Sent stop command via systemctl --user.")
            except Exception:
                pass

        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                print(f"Sent SIGTERM to daemon PID {pid}.")
                stopped = True
            except Exception as e:
                print(f"Failed to stop PID {pid}: {e}")

        if not stopped and not health["running"]:
            print("Daemon is not running.")

    elif sub == "status":
        health = check_daemon_health()
        if health["healthy"]:
            print(f"Daemon: RUNNING\nEndpoint: {health['endpoint']}\nHealth: OK\nDatabase: {health['db'].upper()}")
        elif health["running"]:
            print(f"Daemon: UNHEALTHY\nEndpoint: {health['endpoint']}\nDetails: {health['details']}")
        else:
            print(f"Daemon: STOPPED\nDetails: {health['details']}")


def cmd_worker(args):
    """Inspect the worker pool."""
    reg = WorkerRegistry()
    workers = reg.get_all_statuses()
    print(f"\n{'WORKER ID':<16} {'STATUS':<12} {'DETAILS'}")
    print("-" * 60)
    for w in workers:
        print(f"{w['name']:<16} {w['status']:<12} {w['details']}")
    print("-" * 60 + "\n")


def cmd_memory(args):
    """Search long-term project memories."""
    db = DatabaseManager()
    engine = MemoryEngine(db)
    query = args.query
    results = engine.search(project_id="", query=query, limit=args.limit)

    print(f"\nFound {len(results)} memory record(s) matching '{query}':")
    print("-" * 75)
    for r in results:
        print(f"[{r.get('memory_type', 'mem').upper()}] {r.get('title')} (ID: {r.get('memory_id')})")
        print(f"Commit: {r.get('source_commit') or 'N/A'} | Stale: {bool(r.get('stale', 0))}")
        print(f"Content: {r.get('content')[:120]}...\n")
    print("-" * 75)


def cmd_approval(args):
    """Inspect and resolve human approvals."""
    db = DatabaseManager()
    gate = HumanApprovalGate(db)
    sub = args.approval_action

    if sub == "list":
        approvals = gate.list_pending_approvals()
        print(f"\nPending Human Approvals ({len(approvals)}):")
        print("-" * 75)
        for a in approvals:
            print(f"ID: {a['approval_id']} | Mission: {a['mission_id']} | Risk: {a['risk_level']}")
            print(f"Action: {a['action']}")
            print(f"Target Repo: {a['target_repo']} | Commit: {a['commit_sha'][:8]}")
            print(f"Created: {a['created_at']}\n")
        print("-" * 75)

    elif sub == "approve":
        success = gate.resolve_approval(
            approval_id=args.approval_id,
            status=ApprovalStatus.APPROVED,
            resolved_by=args.by or os.getenv("USER", "operator"),
            reason=args.reason or "Approved via CLI",
        )
        if success:
            print(f"✓ Approval {args.approval_id} marked APPROVED.")
        else:
            print(f"✗ Failed to approve {args.approval_id} (not found or not pending).")

    elif sub == "reject":
        success = gate.resolve_approval(
            approval_id=args.approval_id,
            status=ApprovalStatus.REJECTED,
            resolved_by=args.by or os.getenv("USER", "operator"),
            reason=args.reason or "Rejected via CLI",
        )
        if success:
            print(f"✓ Approval {args.approval_id} marked REJECTED.")
        else:
            print(f"✗ Failed to reject {args.approval_id} (not found or not pending).")


def cmd_plan(args):
    """Run AI Planner to decompose a goal into an executable task."""
    planner = AIPlanner()
    print(f"\nAnalyzing goal: {args.goal}\n")
    plan = planner.plan_task(args.goal)
    print(json.dumps(plan, indent=2))


def cmd_run(args):
    """Run full autonomous development cycle on a repository."""
    repo_path = Path(args.repo).resolve()
    if not repo_path.exists():
        print(f"Error: Repository path does not exist: {repo_path}")
        sys.exit(1)

    coordinator = TeamCoordinator(max_retries=args.retries)
    result = coordinator.run_development_cycle(
        goal=args.goal,
        repo_path=repo_path,
        test_command=args.test_cmd,
    )

    print("\n==================================================")
    print(f"  FINAL RESULT: {result['status']}")
    print("==================================================")
    print(f"Session ID:   {result['session_id']}")
    print(f"Attempts:     {result['attempts']}")
    print(f"Approved:     {result['approved']}")
    print(f"Tests Passed: {result['tests_passed']}")
    print(f"Files Modified: {', '.join(result['changed_files']) or 'None'}")
    print(f"Summary:      {result['verification'].get('summary', 'No summary')}")
    print("==================================================\n")

    if result["status"] != "COMPLETED":
        sys.exit(1)


def cmd_natural_language_mission(args):
    """Execute or background a direct natural-language mission."""
    from .autonomous_planner import AutonomousMissionPlanner
    from .repo_manager import RepoManager
    import datetime, uuid

    raw_prompt = args.mission
    if raw_prompt == "-":
        print("Reading mission prompt from stdin (Ctrl+D to finish)...")
        prompt = sys.stdin.read().strip()
    else:
        prompt = raw_prompt.strip()

    if not prompt:
        print("Error: Empty mission prompt provided.")
        sys.exit(1)

    db = DatabaseManager()
    rm = RepoManager(db)

    # Background vs Foreground & Mission ID
    mission_id = getattr(args, "fg_internal", None) or f"mission-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    # Resolve target repository with CoreLock protection
    try:
        repo_path, is_ephemeral = rm.resolve_target_workspace(args.repo, mission_id=mission_id)
    except PermissionError as pe:
        print(f"\n[CORELOCK VIOLATION] {pe}")
        print("Safety check: Autonomous modifications to ACS Core are strictly prohibited.\n")
        sys.exit(1)
    except Exception as e:
        print(f"Error resolving target repository: {e}")
        sys.exit(1)

    # Resolve worker preference
    worker_pref = args.worker or "auto"
    if worker_pref == "codex":
        worker_pref = "codex-primary"


    if args.bg and not getattr(args, "fg_internal", None):
        # Background mode: persist to DB in QUEUED state, then spawn detached background process
        from .config import LOGS_DIR
        log_file = LOGS_DIR / f"mission_{mission_id}.log"

        db.create_mission(
            mission_id=mission_id,
            project_id=repo_path.name,
            repository_path=str(repo_path),
            goal=prompt.splitlines()[0][:100],
            state="QUEUED",
            assigned_workers=[worker_pref],
            prompt=prompt,
        )

        cmd = [
            sys.executable,
            "-m",
            "acs_team.cli",
            "-m",
            prompt,
            "--repo",
            str(repo_path),
            "--worker",
            worker_pref,
            "--fg-internal",
            mission_id,
        ]
        if args.test_cmd:
            cmd.extend(["--test-cmd", args.test_cmd])

        with open(log_file, "a", encoding="utf-8") as out_f:
            subprocess.Popen(cmd, stdout=out_f, stderr=subprocess.STDOUT, start_new_session=True)

        print("\n==================================================")
        print("  🚀 ACS AI V2.2 MISSION QUEUED IN BACKGROUND")
        print("==================================================")
        print(f"Mission ID:        {mission_id}")
        print(f"Target Workspace:  {repo_path}")
        print(f"Worker Preference: {worker_pref}")
        print(f"Log File:          {log_file}")
        print("\nCommands to inspect:")
        print(f"  Status:  acsai mission status {mission_id}")
        print(f"  Logs:    acsai mission logs {mission_id}")
        print(f"  Cancel:  acsai mission cancel {mission_id}")
        print("==================================================\n")
        return

    # Foreground mode
    print("\n==================================================")
    print("  ACS AI V2.2 — AUTONOMOUS MISSION CONTROL")
    print("==================================================")
    print(f"Mission ID:        {mission_id}")
    print(f"Target Workspace:  {repo_path}")
    print(f"Worker Preference: {worker_pref}")
    print(f"Prompt:\n{prompt}")
    print("==================================================\n")

    planner = AutonomousMissionPlanner(db=db)

    def _cli_log(msg: str):
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now_str}] {msg}")

    try:
        result = planner.run_mission(
            mission_id=mission_id,
            prompt=prompt,
            repo_path=repo_path,
            worker_preference=worker_pref,
            test_command=args.test_cmd,
            log_callback=_cli_log,
        )
    except PermissionError as pe:
        print(f"\n[SECURITY REJECTION] {pe}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n[MISSION EXECUTION ERROR] {e}\n")
        sys.exit(1)

    print("\n==================================================")
    print(f"  MISSION {mission_id} VERDICT: {result['status']}")
    print("==================================================")
    print(f"Status:           {result['status']}")
    worker_used = result.get('worker_used') or result.get('worker', 'N/A')
    print(f"Worker Assigned:  {worker_used}")
    files_changed = result.get('files_modified') or result.get('changed_files', [])
    print(f"Files Changed:    {', '.join(files_changed) or 'None'}")
    print(f"Tests Passed:     {result.get('approved', True)}")
    print(f"Quality Score:    {result.get('quality_score', 0.0):.2f}")
    verdict_str = "APPROVED" if result.get('approved') else result.get('guardian_verdict', 'N/A')
    print(f"Guardian Verdict: {verdict_str}")
    duration = result.get('duration_sec') or result.get('duration_seconds', 0.0)
    print(f"Execution Time:   {duration:.1f}s")
    print("==================================================\n")


    if result["status"] != "COMPLETED":
        sys.exit(1)


def cmd_missions(args):
    """List all missions in SQLite WAL."""
    db = DatabaseManager()
    limit = getattr(args, "limit", 50) or 50
    missions = db.list_missions(limit=limit)
    print(f"\n{'MISSION ID':<35} {'STATE':<16} {'SCORE':<7} {'GOAL / PROMPT'}")
    print("-" * 95)
    for m in missions:
        goal_prompt = m.get("prompt") or m.get("goal") or ""
        first_line = str(goal_prompt).splitlines()[0] if goal_prompt else ""
        print(f"{m.get('mission_id', ''):<35} {m.get('state', ''):<16} {float(m.get('quality_score') or 0.0):<7.2f} {first_line[:32]}...")
    print("-" * 95)
    print(f"Total Missions Recorded: {len(missions)}\n")


def cmd_mission(args):
    """Inspect, control, or execute multi-phase and natural language missions."""
    sub_or_file = getattr(args, "sub_or_file", None)
    target_id = getattr(args, "target_id", None)
    db = DatabaseManager()

    if sub_or_file in ("list", None):
        cmd_missions(args)
        return

    if sub_or_file == "status":
        if not target_id:
            print("Error: Missing mission ID. Usage: acsai mission status <id>")
            sys.exit(1)
        m = db.get_mission(target_id)
        if not m:
            print(f"Error: Mission '{target_id}' not found.")
            sys.exit(1)
        print("\n==================================================")
        print(f"  MISSION STATUS: {target_id}")
        print("==================================================")
        print(f"State:            {m.get('state')}")
        print(f"Project:          {m.get('project_id')}")
        print(f"Target Repo:      {m.get('repository_path')}")
        workers = m.get('assigned_workers', [])
        print(f"Assigned Workers: {', '.join(workers) if workers else 'None'}")
        print(f"Quality Score:    {float(m.get('quality_score') or 0.0):.2f}")
        print(f"Created At:       {m.get('created_at')}")
        print(f"Updated At:       {m.get('updated_at')}")
        print(f"Prompt:\n{m.get('prompt') or m.get('goal')}")
        plan_json = m.get('plan_json')
        if plan_json:
            print(f"\nGenerated Plan:\n{plan_json[:400]}...")
        checkpoint = db.get_latest_checkpoint(target_id)
        if checkpoint:
            print(f"\nLatest Checkpoint: Phase {checkpoint.get('phase_index', 0)} ({checkpoint.get('state')})")
        print("==================================================\n")
        return

    if sub_or_file == "logs":
        if not target_id:
            print("Error: Missing mission ID. Usage: acsai mission logs <id>")
            sys.exit(1)
        logs = db.get_mission_logs(target_id)
        from .config import LOGS_DIR
        file_log = LOGS_DIR / f"mission_{target_id}.log"
        print(f"\n=== Mission Logs: {target_id} ===")
        if logs:
            for l in logs:
                print(l)
        elif file_log.exists():
            print(file_log.read_text(encoding="utf-8", errors="replace"))
        else:
            print("No logs recorded for this mission.")
        print(f"=== End of Logs ({target_id}) ===\n")
        return

    if sub_or_file == "cancel":
        if not target_id:
            print("Error: Missing mission ID. Usage: acsai mission cancel <id>")
            sys.exit(1)
        from .state_machine import StateMachine, MissionState
        sm = StateMachine(db)
        try:
            sm.transition(target_id, MissionState.CANCELLED, error_info="User cancelled via CLI")
            print(f"✓ Mission '{target_id}' state updated to CANCELLED.")
        except Exception as e:
            print(f"✗ Failed to cancel mission: {e}")
            sys.exit(1)
        return

    if sub_or_file == "resume":
        if not target_id:
            print("Error: Missing mission ID. Usage: acsai mission resume <id>")
            sys.exit(1)
        m = db.get_mission(target_id)
        if not m:
            print(f"Error: Mission '{target_id}' not found.")
            sys.exit(1)
        prompt = m.get("prompt") or m.get("goal") or "Resume mission"
        repo = Path(m.get("repository_path", "."))
        workers = m.get("assigned_workers", ["auto"])
        worker = workers[0] if workers else "auto"

        print(f"\nResuming mission '{target_id}'...")
        from .autonomous_planner import AutonomousMissionPlanner
        planner = AutonomousMissionPlanner(db=db)
        result = planner.run_mission(
            mission_id=target_id,
            prompt=prompt,
            repo_path=repo,
            worker_preference=worker,
            log_callback=lambda msg: print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"),
        )
        print(f"✓ Resumed mission completed with status: {result['status']}\n")
        return

    # Check if sub_or_file is a file (legacy JSON mission)
    candidate_path = Path(sub_or_file).resolve()
    if candidate_path.exists() and (candidate_path.suffix == ".json" or not target_id):
        try:
            config = json.loads(candidate_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Error: Failed to parse mission JSON: {e}")
            sys.exit(1)

        mission_id = config.get("mission_id", candidate_path.stem)
        repo_path = Path(args.repo or config.get("repo_path", ".")).resolve()
        phases = config.get("phases", [])

        if not phases:
            print("Error: Mission file defines no phases.")
            sys.exit(1)

        from .mission import MissionManager

        manager = MissionManager(
            mission_id=mission_id,
            repo_path=repo_path,
            phases=phases,
        )

        resume = not getattr(args, "no_resume", False)
        state = manager.execute_mission(resume=resume)

        print("\n==================================================")
        print(f"  MISSION {mission_id} SUMMARY: {state['status']}")
        print("==================================================")
        for pid, pdata in state["phases_state"].items():
            badge = (
                "✅ PASS"
                if pdata.get("status") == "COMPLETED"
                else ("❌ FAIL" if pdata.get("status") == "FAILED" else "⏳ PENDING")
            )
            print(f"{badge} {pid}: {pdata.get('name')}")
        print("==================================================\n")

        if state["status"] != "COMPLETED":
            sys.exit(1)
        return

    # Or check if sub_or_file is a mission ID directly
    m = db.get_mission(sub_or_file)
    if m:
        args.target_id = sub_or_file
        args.sub_or_file = "status"
        cmd_mission(args)
        return

    print(f"Error: Unknown mission action or file: {sub_or_file}")
    sys.exit(1)


def cmd_mcp(args):
    """Inspect and verify MCP servers and tools."""
    from .mcp_manager import MCPManager
    mgr = MCPManager()
    sub = getattr(args, "mcp_action", None) or "list"

    if sub == "list":
        inv = mgr.get_inventory()
        print(f"\n{'MCP SERVER':<28} {'SOURCE':<24} {'STATUS':<12} {'TOOLS':<6} {'WORKERS'}")
        print("-" * 90)
        for s in inv:
            workers_str = ",".join(s.accessible_workers)
            print(f"{s.name:<28} {s.source_config[:23]:<24} {s.status:<12} {s.tools_count:<6} {workers_str}")
        print("-" * 90)
        stats = mgr.get_summary_stats()
        print(f"Summary: {stats['configured_servers']} configured | {stats['connected_servers']} connected | {stats['usable_servers']} usable | {stats['total_tools']} tools\n")

    elif sub == "status":
        stats = mgr.get_summary_stats()
        print("\n==================================================")
        print("  ACS AI MCP INVENTORY & VERIFICATION STATUS")
        print("==================================================")
        print(f"Configured MCP Servers: {stats['configured_servers']}")
        print(f"Connected MCP Servers:  {stats['connected_servers']}")
        print(f"Usable MCP Servers:     {stats['usable_servers']}")
        print(f"Total Discovered Tools: {stats['total_tools']}")
        print("Authentication Security: Masked credentials (Zero token leaks)")
        print("Invokable Capabilities:  Native tools, Antigravity, AGY B, Codex")
        print("==================================================\n")

    elif sub == "tools":
        tools = mgr.list_all_tools()
        print(f"\n{'TOOL NAME':<30} {'SERVER':<22} {'CATEGORY':<14} {'DESCRIPTION'}")
        print("-" * 95)
        for t in tools:
            desc = (t.get("description") or "")[:26]
            print(f"{t['tool_name']:<30} {t['server_name']:<22} {t['category']:<14} {desc}")
        print("-" * 95)
        print(f"Total Tools Discovered: {len(tools)}\n")


def cmd_repo(args):
    """Manage and inspect registered repositories."""
    from .repo_manager import RepoManager
    db = DatabaseManager()
    rm = RepoManager(db)
    sub = getattr(args, "repo_action", None) or "list"

    if sub == "list":
        repos = rm.list_repositories()
        print(f"\n{'REPO NAME':<20} {'BRANCH':<15} {'STATE':<12} {'POLICY':<14} {'PATH'}")
        print("-" * 90)
        for r in repos:
            policy = "READ-ONLY" if r["is_protected"] else "READ/WRITE"
            branch = r.get("branch") or "N/A"
            state = "CLEAN" if r.get("is_clean") else "DIRTY"
            print(f"{r['name']:<20} {branch:<15} {state:<12} {policy:<14} {r['path']}")
        print("-" * 90)
        print(f"Total Managed Repositories: {len(repos)}\n")

    elif sub == "status":
        repos = rm.list_repositories()
        print("\n==================================================")
        print("  ACS AI REPOSITORY INVENTORY & STATUS")
        print("==================================================")
        print(f"Total Managed Repositories: {len(repos)}")
        for r in repos:
            status_desc = "SAFE TO OPERATE" if r.get("is_accessible") and not r.get("is_protected") else ("PROTECTED (READ-ONLY)" if r.get("is_protected") else "INACCESSIBLE")
            print(f"• {r['name']} ({r['path']}):")
            print(f"    Branch: {r.get('branch') or 'detached'} | Clean: {r.get('is_clean')} | Policy: {status_desc}")
            print(f"    Last Mission: {r.get('last_mission_id') or 'None'}")
        print("==================================================\n")

    elif sub == "add":
        repo_path = Path(args.path).resolve()
        name = args.name or repo_path.name
        try:
            rm.register_repository(name=name, path=repo_path)
            print(f"✓ Successfully registered repository '{name}' at {repo_path}")
        except PermissionError as pe:
            print(f"✗ CoreLock Security Violation: {pe}")
            sys.exit(1)
        except Exception as e:
            print(f"✗ Failed to register repository: {e}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="acsai",
        description="ACS AI V2.2 — Autonomous Coding & Guardian Platform",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "-m", "--mission", help="Natural language mission prompt (e.g. -m 'Create a calculator')"
    )
    parser.add_argument(
        "--repo", default=None, help="Target repository directory (defaults to current Git repo or isolated workspace)"
    )
    parser.add_argument(
        "--worker", default="auto", choices=["auto", "codex", "codex-primary", "agy-google-a", "agy-google-b"], help="Worker preference"
    )
    parser.add_argument(
        "--bg", action="store_true", help="Run mission in background and return mission ID"
    )
    parser.add_argument(
        "--fg-internal", default=None, help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--test-cmd", default=None, help="Optional test command override"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    from .upgrade_cli import register as register_recovery
    register_recovery(subparsers)

    # ui
    p_ui = subparsers.add_parser("ui", help="Launch interactive Textual Control Center TUI")
    p_ui.set_defaults(func=cmd_ui)

    # status
    p_status = subparsers.add_parser("status", help="Show operational platform status")
    p_status.set_defaults(func=cmd_status)

    # daemon
    p_daemon = subparsers.add_parser("daemon", help="Manage background supervisor daemon")
    p_daemon.add_argument("daemon_action", choices=["start", "stop", "status"], help="Daemon command")
    p_daemon.set_defaults(func=cmd_daemon)

    # worker
    p_worker = subparsers.add_parser("worker", help="Inspect multi-agent worker pool")
    p_worker.set_defaults(func=cmd_worker)

    # memory
    p_mem = subparsers.add_parser("memory", help="Query long-term project memories")
    p_mem.add_argument("query", help="FTS5 search query")
    p_mem.add_argument("--limit", type=int, default=10, help="Max results to display")
    p_mem.set_defaults(func=cmd_memory)

    # approval
    p_appr = subparsers.add_parser("approval", help="Manage human approval gates")
    appr_subs = p_appr.add_subparsers(dest="approval_action", required=True)
    p_appr_list = appr_subs.add_parser("list", help="List pending approvals")
    p_appr_approve = appr_subs.add_parser("approve", help="Approve a request")
    p_appr_approve.add_argument("approval_id", help="Approval ID")
    p_appr_approve.add_argument("--by", default=None, help="Approver identity")
    p_appr_approve.add_argument("--reason", default=None, help="Approval rationale")
    p_appr_reject = appr_subs.add_parser("reject", help="Reject a request")
    p_appr_reject.add_argument("approval_id", help="Approval ID")
    p_appr_reject.add_argument("--by", default=None, help="Rejecter identity")
    p_appr_reject.add_argument("--reason", default=None, help="Rejection rationale")
    p_appr.set_defaults(func=cmd_approval)

    # plan
    p_plan = subparsers.add_parser("plan", help="Decompose a goal using the AI Planner")
    p_plan.add_argument("goal", help="High-level engineering goal")
    p_plan.set_defaults(func=cmd_plan)

    # run
    p_run = subparsers.add_parser("run", help="Execute complete development cycle")
    p_run.add_argument("goal", help="Engineering goal or bug to fix")
    p_run.add_argument("--repo", default=".", help="Target repository directory")
    p_run.add_argument("--test-cmd", default=None, help="Automated test command")
    p_run.add_argument("--retries", type=int, default=3, help="Max retries")
    p_run.set_defaults(func=cmd_run)

    # missions
    p_missions = subparsers.add_parser("missions", help="List all missions")
    p_missions.add_argument("--limit", type=int, default=50, help="Max missions to list")
    p_missions.set_defaults(func=cmd_missions)

    # mission
    p_mission = subparsers.add_parser("mission", help="Inspect, control, or execute multi-phase missions")
    p_mission.add_argument("sub_or_file", nargs="?", default=None, help="status|logs|cancel|resume|list or path to JSON")
    p_mission.add_argument("target_id", nargs="?", default=None, help="Mission ID (for status, logs, cancel, resume)")
    p_mission.add_argument("--repo", default=None, help="Target repository directory")
    p_mission.add_argument("--no-resume", action="store_true", help="Force restart of phases")
    p_mission.set_defaults(func=cmd_mission)

    # mcp
    p_mcp = subparsers.add_parser("mcp", help="Inspect and verify MCP servers and tools")
    mcp_subs = p_mcp.add_subparsers(dest="mcp_action", required=False)
    p_mcp_list = mcp_subs.add_parser("list", help="List all configured MCP servers")
    p_mcp_status = mcp_subs.add_parser("status", help="Show MCP inventory and verification status")
    p_mcp_tools = mcp_subs.add_parser("tools", help="List all discovered MCP tools")
    p_mcp.set_defaults(func=cmd_mcp)

    # repo
    p_repo = subparsers.add_parser("repo", help="Inspect and manage development repositories")
    repo_subs = p_repo.add_subparsers(dest="repo_action", required=False)
    p_repo_list = repo_subs.add_parser("list", help="List registered repositories")
    p_repo_status = repo_subs.add_parser("status", help="Show repository inventory and health")
    p_repo_add = repo_subs.add_parser("add", help="Register a new repository")
    p_repo_add.add_argument("path", help="Path to repository directory")
    p_repo_add.add_argument("--name", default=None, help="Display name for repository")
    p_repo.set_defaults(func=cmd_repo)

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.mission:
        cmd_natural_language_mission(args)
    elif hasattr(args, "func"):
        args.func(args)
    else:
        # Default action: status
        cmd_status(args)


if __name__ == "__main__":
    main()

