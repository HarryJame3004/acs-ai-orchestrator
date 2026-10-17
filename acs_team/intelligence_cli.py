"""Explicit advisory lesson operations and disposable benchmark runs."""

import json
from pathlib import Path

from .benchmarks import compare_benchmark, run_benchmarks
from .db import DatabaseManager
from .intelligence import Lessons
from .recovery import private_write


def execute(args):
    if args.command == "bench":
        result = run_benchmarks(args.suite, args.workers)
        if args.baseline:
            result["regressions"] = compare_benchmark(
                json.loads(Path(args.baseline).read_text()), result
            )
        if args.report:
            private_write(
                Path(args.report), (json.dumps(result, indent=2) + "\n").encode()
            )
        print(json.dumps(result))
        if result["status"] != "PASS" or result.get("regressions"):
            raise SystemExit(1)
        return
    lessons = Lessons(DatabaseManager())
    if args.lesson_action == "confirm":
        lessons.human_confirm(
            args.project,
            args.lesson_id,
            operator_confirmed=args.confirm,
            reference=args.reference,
        )
    elif args.lesson_action == "reject":
        lessons.reject(args.project, args.lesson_id)
    elif args.lesson_action == "show":
        print(lessons.advisory(args.project, args.tags))


def register(subparsers):
    bench = subparsers.add_parser(
        "bench", help="Golden benchmarks in disposable repositories"
    )
    runs = bench.add_subparsers(dest="bench_action", required=True)
    run = runs.add_parser("run")
    run.add_argument("--suite", choices=["smoke", "full"], default="smoke")
    run.add_argument("--workers", choices=["fake", "real"], required=True)
    run.add_argument("--report")
    run.add_argument("--baseline")
    run.set_defaults(func=execute)
    parent = subparsers.add_parser("lessons", help="Evidence-backed advisory memory")
    actions = parent.add_subparsers(dest="lesson_action", required=True)
    for name in ("show", "confirm", "reject"):
        child = actions.add_parser(name)
        child.add_argument("--project", required=True)
        if name == "show":
            child.add_argument("--tags", nargs="+", required=True)
        else:
            child.add_argument("lesson_id")
        if name == "confirm":
            child.add_argument("--confirm", action="store_true")
            child.add_argument("--reference", required=True)
        child.set_defaults(func=execute)
