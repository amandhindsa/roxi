"""
python -m roxi <command> [vertical]

Commands:
  run      Run the full pipeline for a vertical (collect → score → research → draft → deliver)
  evals    Run the eval harness for a vertical
  report   Print reply-rate report for a vertical
  serve    Start the approval webhook server
  compile  Interview wizard to build a new vertical YAML
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from roxi.logging_config import configure as _configure_logging


def cli() -> None:
    _configure_logging(level=os.environ.get("ROXI_LOG_LEVEL", "INFO"))

    parser = argparse.ArgumentParser(prog="roxi")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the pipeline for a vertical")
    run_p.add_argument("vertical", nargs="?", default="hauler_ai")
    run_p.add_argument("--dry-run", action="store_true", help="Skip delivery to Slack")
    run_p.add_argument("--org-id", default=None, help="Organisation identifier for trace")

    eval_p = sub.add_parser("evals", help="Run the eval harness")
    eval_p.add_argument("vertical", nargs="?", default="hauler_ai")

    rep_p = sub.add_parser("report", help="Print reply-rate report")
    rep_p.add_argument("vertical", nargs="?", default="hauler_ai")
    rep_p.add_argument("--days", type=int, default=30)

    serve_p = sub.add_parser("serve", help="Start the approval webhook server")
    serve_p.add_argument("--port", type=int, default=8080)
    serve_p.add_argument("--host", default="0.0.0.0")

    compile_p = sub.add_parser("compile", help="Interview wizard to build a new vertical YAML")
    compile_p.add_argument("--output", default=None, help="Path to write the vertical YAML")

    args = parser.parse_args()

    if args.command == "run":
        _cmd_run(args)
    elif args.command == "evals":
        _cmd_evals(args)
    elif args.command == "report":
        _cmd_report(args)
    elif args.command == "serve":
        _cmd_serve(args)
    elif args.command == "compile":
        _cmd_compile(args)


def _resolve_vertical(name: str):
    from roxi.config import load_vertical
    candidates = [
        Path(f"verticals/{name}.yaml"),
        Path(f"verticals/{name}"),
        Path(name),
    ]
    for p in candidates:
        if p.exists():
            return load_vertical(p)
    print(f"error: vertical '{name}' not found (tried {[str(c) for c in candidates]})", file=sys.stderr)
    sys.exit(1)


def _cmd_run(args) -> None:
    import logging
    from roxi import pipeline, store

    log = logging.getLogger("roxi.cli")
    vertical = _resolve_vertical(args.vertical)
    store.init_db()

    if args.dry_run:
        os.environ["SLACK_WEBHOOK_URL"] = ""
        log.info("dry-run mode — Slack delivery disabled")

    try:
        leads = pipeline.run(vertical, org_id=getattr(args, "org_id", None))
        print(f"Done — {len(leads)} leads delivered")
    except Exception as exc:
        log.error("pipeline run failed: %s", exc, exc_info=True)
        sys.exit(1)


def _cmd_evals(args) -> None:
    import subprocess
    _resolve_vertical(args.vertical)
    result = subprocess.run(
        [sys.executable, "evals/run_evals.py"],
        check=False,
    )
    sys.exit(result.returncode)


def _cmd_report(args) -> None:
    from scripts.report_outcomes import print_report
    from roxi import store
    store.init_db()
    vertical = _resolve_vertical(args.vertical)
    print_report(vertical.vertical_id, days=args.days)


def _cmd_serve(args) -> None:
    import logging
    import uvicorn
    from roxi.api.app import app
    log = logging.getLogger("roxi.cli")
    log.info("starting API server on %s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


def _cmd_compile(args) -> None:
    from roxi.agents.compiler import run_compiler
    output_path = Path(args.output) if args.output else None
    config = run_compiler(output_path=output_path)
    if config:
        print(f"\nVertical compiled: {config.vertical_id}")
