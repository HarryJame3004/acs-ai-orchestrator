"""Opt-in local recovery commands; no live installation activation."""

import json
import os
from pathlib import Path

from .recovery import create_backup, migrate, preflight, restore_backup, stage_upgrade, verify_backup


def execute(args):
    if os.environ.get("ACS_ENABLE_RECOVERY") != "1":
        raise SystemExit("Recovery tools are disabled; set ACS_ENABLE_RECOVERY=1 after reviewing BACKUP_AND_RECOVERY.md")
    if args.command == "backup":
        if args.action == "create":
            result = create_backup(Path(args.database), Path(args.target), tuple(Path(p) for p in args.reference), args.include_credentials)
        elif args.action == "verify":
            result = verify_backup(Path(args.backup))
        else:
            result = {"restored_to": str(restore_backup(Path(args.backup), Path(args.target)))}
    elif args.command == "migrate":
        if args.apply and args.confirm_target != str(Path(args.database).resolve()):
            raise SystemExit("Apply requires --confirm-target with the exact resolved database path")
        result = migrate(Path(args.database), dry_run=not args.apply,
                         backup_directory=Path(args.backup_target) if args.backup_target else None)
    elif args.command == "upgrade-preflight":
        result = preflight(Path(args.source), Path(args.database))
    else:
        result = stage_upgrade(Path(args.source), Path(args.target), Path(args.database))
    # Manifest exposes file metadata, never credential contents.
    print(json.dumps(result, indent=2))


def register(subparsers):
    backup = subparsers.add_parser("backup", help="Opt-in consistent SQLite backup/verify/scratch restore")
    actions = backup.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("--database", required=True)
    create.add_argument("--target", required=True)
    create.add_argument("--reference", action="append", default=[])
    create.add_argument("--include-credentials", action="store_true")
    verify = actions.add_parser("verify")
    verify.add_argument("backup")
    restore = actions.add_parser("restore")
    restore.add_argument("backup")
    restore.add_argument("--target", required=True)
    backup.set_defaults(func=execute)
    migration = subparsers.add_parser("migrate", help="Dry-run migrations on a copy by default")
    migration.add_argument("--database", required=True)
    migration.add_argument("--apply", action="store_true")
    migration.add_argument("--confirm-target")
    migration.add_argument("--backup-target")
    migration.set_defaults(func=execute)
    stage = subparsers.add_parser("upgrade-stage", help="Create a candidate app/database; never activate it")
    stage.add_argument("--source", required=True)
    stage.add_argument("--database", required=True)
    stage.add_argument("--target", required=True)
    stage.set_defaults(func=execute)
    check = subparsers.add_parser("upgrade-preflight", help="Read-only checks and migration dry-run on a copy")
    check.add_argument("--source", required=True)
    check.add_argument("--database", required=True)
    check.set_defaults(func=execute)
