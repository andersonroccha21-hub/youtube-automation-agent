"""CLI for local interaction, durable server approvals and independent skill execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.approvals import PendingApproval
from pipeline.config import load_config
from pipeline.models import STAGES
from pipeline.orchestrator import Orchestrator
from pipeline.preflight import check
from pipeline.registry import SKILLS
from pipeline.skill import Context
from pipeline.storage import read_json, run_lock, write_json


def parser():
    cli = argparse.ArgumentParser(description="Seven-skill YouTube production pipeline")
    cli.add_argument("--channel", type=Path, required=True, help="Channel config YAML")
    cli.add_argument("--topic", help="Optional video topic (only when creating a run)")
    cli.add_argument("--run-dir", type=Path, help="Resume or review an existing run directory")
    cli.add_argument(
        "--demo", action="store_true", help="Synthetic offline fixtures, not publishable content"
    )
    action = cli.add_mutually_exclusive_group()
    action.add_argument("--approve", choices=STAGES, help="Record a human approval and exit")
    action.add_argument("--reject", choices=STAGES, help="Record a rejection and exit")
    action.add_argument(
        "--revise", choices=STAGES, help="Invalidate this stage and its successors, then exit"
    )
    action.add_argument("--status", action="store_true", help="Show persisted run status")
    action.add_argument(
        "--skill",
        choices=STAGES,
        help="Execute one isolated skill, without orchestrating a pipeline",
    )
    action.add_argument(
        "--validate", action="store_true", help="Validate channel config without API calls"
    )
    action.add_argument(
        "--check",
        action="store_true",
        help="Check local binaries, files and API key presence without network calls",
    )
    cli.add_argument("--select", help="Candidate ID for title/thumbnail approval")
    cli.add_argument("--reviewer", help="Name of the human reviewer")
    cli.add_argument("--feedback", default="", help="Revision or rejection instructions")
    cli.add_argument("--input", type=Path, help="Typed JSON input for an isolated skill")
    cli.add_argument("--output", type=Path, help="JSON output for an isolated skill")
    cli.add_argument("--assets-dir", type=Path, help="Artifact root for an isolated skill")
    return cli


def main(argv=None) -> int:
    cli = parser()
    args = cli.parse_args(argv)
    try:
        config = load_config(args.channel)
        if args.validate:
            print(f"Valid config: {config.channel.id}")
            return 0
        if args.check:
            check(config, args.demo)
            print("Local readiness checks passed (provider access has not been tested).")
            return 0
        if args.skill:
            if not all((args.input, args.output, args.assets_dir)):
                cli.error("--skill requires --input, --output and --assets-dir")
            skill = SKILLS[args.skill]
            root = args.assets_dir.resolve()
            if (root / "state.json").exists():
                raise ValueError("Isolated skills cannot write into an orchestrated run")
            previous = skill.input_model.model_validate(read_json(args.input))
            with run_lock(root):
                output = skill(previous, Context(config, root, args.demo, args.feedback))
                write_json(args.output, output)
            print(args.output.resolve())
            return 0
        if any((args.approve, args.reject, args.revise, args.status)) and not args.run_dir:
            cli.error("Review, revision and status require --run-dir")
        if (args.approve or args.reject) and not args.reviewer:
            cli.error("Approval/rejection requires --reviewer")
        if args.run_dir:
            run = Orchestrator(config, args.run_dir)
            state = run.state()
            if args.topic and args.topic != state.brief.topic:
                raise ValueError("--topic cannot change on resume; start a new run")
            if args.demo and not state.demo:
                raise ValueError("Production runs cannot switch to demo on resume")
        else:
            check(config, args.demo)
            run = Orchestrator.create(config, args.topic, args.demo)
        print(f"Run directory: {run.root}", flush=True)
        if args.status:
            print(json.dumps(run.state().model_dump(mode="json"), ensure_ascii=False, indent=2))
        elif args.approve or args.reject:
            run.decide(
                args.approve or args.reject,
                args.reviewer,
                bool(args.approve),
                args.select,
                args.feedback,
            )
            print("Human decision recorded. Resume with --run-dir to continue.")
        elif args.revise:
            run.revise(args.revise, args.feedback)
            print("Stage and downstream approvals invalidated. Resume with --run-dir.")
        else:
            output = run.run()
            print(f"Completed: {run.root / output.video.file.path}")
        return 0
    except PendingApproval as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Resume using --run-dir.", file=sys.stderr)
        return 130
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
