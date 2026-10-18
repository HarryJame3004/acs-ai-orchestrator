"""Explicit local checks/import and MCP approval audit commands."""

import json
from pathlib import Path

from .config import STATE_DIR
from .local_verification import import_local_report, verify_local
from .mcp_audit import audit_catalog, load_policy, save_catalog
from .mcp_protocol import MCPBroker
from .recovery import private_write


def execute(args):
    if args.command == 'provider-usage':
        from .config import DB_PATH
        from .db import DatabaseManager
        from .provider_ledger import provider_usage
        print(json.dumps(provider_usage(DatabaseManager(Path(args.database) if args.database else DB_PATH, read_only=True))))
        return
    if args.command == 'verify-team':
        if not args.execute_probe:
            raise SystemExit('Real team evaluation requires explicit --execute-probe; it consumes provider quota')
        if Path(args.report).exists() or Path(args.report).is_symlink():
            raise FileExistsError('Local team report destination must be new')
        from .local_team_probe import run_local_team_probe
        import time
        started = time.monotonic()
        try:
            result = run_local_team_probe(Path(args.output))
        except Exception as exc:
            from datetime import datetime, timezone
            from .local_verification import LocalReport, LocalCheck
            result = LocalReport(generated_at=datetime.now(timezone.utc).isoformat(),repo_commit='UNKNOWN',
                environment={'probe_root':args.output},checks=[LocalCheck(id='multiagent.real_e2e',status='FAIL',
                    evidence=f'Activation prerequisites or actual team execution failed ({type(exc).__name__}); elapsed={time.monotonic()-started:.3f}s; duration field capped at 3600s; inspect retained artifacts if created',
                    duration_s=min(time.monotonic()-started,3600.))],
                summary={'pass':0,'fail':1,'skipped':0,'error':0}).model_dump()
        private_write(Path(args.report),(json.dumps(result,indent=2)+'\n').encode())
        print(json.dumps({'report':args.report,'summary':result['summary'],'label':'LOCAL_VERIFICATION_REQUIRED'}))
        if result['summary']['fail']:
            raise SystemExit(1)
        return
    if args.command == 'provider-activate':
        if not args.execute_probe:
            raise SystemExit('Activation requires explicit --execute-probe on the local host')
        from .providers import load_catalog, ProviderRuntime, Activations
        from .config import AUTH_TOKEN_PATH, PROTECTED_PATHS
        from .auth import get_or_create_auth_token
        catalog = load_catalog(Path(args.contracts))
        contract = next((p for p in catalog.providers if p.worker_id == args.worker_id), None)
        if contract is None:
            raise ValueError('Provider is not in the approved catalog')
        runtime = ProviderRuntime((STATE_DIR, AUTH_TOKEN_PATH, *PROTECTED_PATHS,
                                   *(Path(p.auth_home) for p in catalog.providers if p != contract)))
        key = get_or_create_auth_token(STATE_DIR/'evidence.key')
        receipt = Activations(key).verify(contract, runtime,valid_for_seconds=args.valid_for_seconds)
        target = STATE_DIR/'provider-activation'
        target.mkdir(mode=0o700, exist_ok=True)
        import os
        if target.is_symlink() or target.stat().st_uid != os.getuid() or target.stat().st_mode & 0o077:
            raise PermissionError('Activation directory is not private and owned')
        # A new output is mandatory; revocation/renewal is an explicit operator action.
        private_write(target/f'{contract.worker_id}.json', (json.dumps(receipt)+'\n').encode())
        print(json.dumps({'worker':contract.worker_id, 'status':'PASS', 'label':'LOCAL_VERIFICATION_REQUIRED',
                          'expires_at':receipt['expires_at']}))
        return
    if args.command == "verify-local":
        result = verify_local(
            Path(args.repository),
            execute_probes=args.execute_probes,
            run_local_tests=args.run_local_tests,
            database=Path(args.database) if args.database else None,
            operational_dir=Path(args.operational_dir)
            if args.operational_dir
            else None,
        )
        private_write(Path(args.report), (json.dumps(result, indent=2) + "\n").encode())
        print(json.dumps({"report": str(args.report), "summary": result["summary"]}))
        if result["summary"]["fail"] or result["summary"]["error"]:
            raise SystemExit(1)
        return
    if args.command == "import-local-report":
        with Path(args.file).open("rb") as stream:
            raw = stream.read(131073)
        print(json.dumps(import_local_report(raw, Path(args.output))))
        return
    if args.mcp_action == "audit":
        if args.catalog:
            with Path(args.catalog).open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValueError("Catalog too large")
            data = json.loads(raw)
            tools = data["tools"]
            name = data.get("name", "explicit-catalog")
            if args.approve:
                if not args.output:
                    raise ValueError("Approval requires a new explicit output path")
                result = save_catalog(
                    Path(args.output), name, tools, operator_confirmed=True
                )
            else:
                result = audit_catalog(name, tools, args.approved_hash)
            print(json.dumps(result))
        else:
            from .mcp_manager import MCPManager

            print(
                json.dumps(
                    [
                        audit_catalog(s.name, s.tools)
                        for s in MCPManager().get_inventory()
                    ]
                )
            )
    elif args.mcp_action == "verify":
        policy = load_policy(Path(args.policy))
        results = []
        # Execution is additionally gated by ACS_ENABLE_MCP_EXTERNAL=1. This
        # command never enables it or auto-installs a server.
        for server in policy.servers:
            try:
                with MCPBroker(
                    server, Path(args.workspace), private_paths=(STATE_DIR,)
                ) as broker:
                    result = broker.call(
                        server.harmless_tool, server.harmless_arguments
                    )
                    results.append(
                        {
                            "name": server.name,
                            "status": "CLOUD_PASS_LOCAL_PENDING",
                            "startup_tools_call": "PASS",
                            "label": "LOCAL_VERIFICATION_REQUIRED",
                            "tool_result_present": bool(result),
                            "timeout_recovery_worker_visibility": "NOT_TESTED",
                        }
                    )
            except Exception as exc:
                results.append(
                    {
                        "name": server.name,
                        "status": "FAIL",
                        "label": "LOCAL_VERIFICATION_REQUIRED",
                        "error_type": type(exc).__name__,
                    }
                )
        report = {
            "schema_version": 1,
            "servers": results,
            "note": "A successful call alone is not full MCP acceptance",
        }
        private_write(Path(args.report), (json.dumps(report, indent=2) + "\n").encode())
        print(json.dumps(report))
        if not results or any(r["status"] == "FAIL" for r in results):
            raise SystemExit(1)


def register(subparsers, mcp_subs):
    usage = subparsers.add_parser('provider-usage',help='Read-only durable session reservations; no provider calls or cost estimates')
    usage.add_argument('--database')
    usage.set_defaults(func=execute)
    team = subparsers.add_parser('verify-team',help='Explicit real-provider two-task evaluation on a new retained fixture repo')
    team.add_argument('--output',required=True,help='New private probe directory; never an existing user repo')
    team.add_argument('--report',required=True,help='New private local-report JSON file')
    team.add_argument('--execute-probe',action='store_true')
    team.set_defaults(func=execute)
    activation = subparsers.add_parser('provider-activate', help='Explicit local sandbox/auth challenge and signed activation')
    activation.add_argument('worker_id', choices=['codex-primary','agy-google-a','agy-google-b'])
    activation.add_argument('--contracts', required=True)
    activation.add_argument('--execute-probe', action='store_true')
    activation.add_argument('--valid-for-seconds',type=int,default=3600,help='Explicit signed activation lifetime, 900–86400 seconds; default 3600')
    activation.set_defaults(func=execute)
    verify = subparsers.add_parser(
        "verify-local",
        help="Read-only environment inspection; optional disposable probes",
    )
    verify.add_argument(
        "--repository", default=str(Path(__file__).resolve().parents[1])
    )
    verify.add_argument("--report", default="local_verification_report.json")
    verify.add_argument("--execute-probes", action="store_true")
    verify.add_argument(
        "--run-local-tests",
        action="store_true",
        help="Explicitly execute local_only tests in disposable runtime state",
    )
    verify.add_argument("--database")
    verify.add_argument("--operational-dir")
    verify.set_defaults(func=execute)
    imported = subparsers.add_parser(
        "import-local-report",
        help="Validate untrusted local evidence into a new private review package",
    )
    imported.add_argument("--file", required=True)
    imported.add_argument("--output", required=True)
    imported.set_defaults(func=execute)
    audit = mcp_subs.add_parser(
        "audit",
        help="Hash declared tool definitions; changed definitions need explicit re-approval",
    )
    audit.add_argument("--catalog")
    audit.add_argument("--approved-hash")
    audit.add_argument("--approve", action="store_true")
    audit.add_argument("--output")
    audit.set_defaults(func=execute)
    mcp = mcp_subs.add_parser(
        "verify",
        help="Explicit sandboxed calls for already-approved mission MCP policies",
    )
    mcp.add_argument("--policy", required=True)
    mcp.add_argument("--workspace", required=True)
    mcp.add_argument("--report", required=True)
    mcp.set_defaults(func=execute)
