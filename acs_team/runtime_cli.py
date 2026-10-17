"""Explicit local operator emergency controls."""

import json
import os

from .db import DatabaseManager
from .runtime_control import RuntimeControl


def execute(args):
    if args.command != "emergency-status" and os.environ.get("ACS_ENABLE_EMERGENCY_STOP") != "1":
        raise SystemExit("Enable ACS_ENABLE_EMERGENCY_STOP=1 for explicit operator stop/resume actions")
    control = RuntimeControl(DatabaseManager(), initialize=args.command != "emergency-status")
    if args.command == "emergency-stop":
        control.stop()
    elif args.command == "emergency-resume":
        control.resume(operator_confirmed=args.confirm)
    print(json.dumps({"emergency_stop": control.stopped()}))


def register(subparsers):
    for name in ("emergency-stop", "emergency-status", "emergency-resume"):
        parser = subparsers.add_parser(name, help="Persistent local operator dispatch control")
        if name == "emergency-resume":
            parser.add_argument("--confirm", action="store_true", help="Explicit operator confirmation")
        parser.set_defaults(func=execute)
