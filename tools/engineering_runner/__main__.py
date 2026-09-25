"""The operator's command line. Four commands, and none of them decides anything.

    python -m tools.engineering_runner doctor  --repo-root . --state-dir S --runner-dir R
    python -m tools.engineering_runner watch   --repo-root . --state-dir S --runner-dir R
    python -m tools.engineering_runner run-one WO --repo-root . --state-dir S --runner-dir R
    python -m tools.engineering_runner status  --repo-root . --state-dir S --runner-dir R

`watch` is the one the operator actually uses, once. It polls the Company OS
lifecycle, runs whatever is ready, and keeps going when a job fails. `run-one`
exists for debugging a single work order, and `doctor` answers "would watch
work right now" without spending a session on the question.

## There is no `submit` here, and no `approve`

Submitting a request is `python -m company.engineering request`, which is the
CEO's existing command and belongs to the control plane. Approving is
`python -m company.engineering decide`, which is the CEO's and belongs to
nobody else. A runner that could do either would be a runner that could
originate work or bless it, and this one can do neither - not by policy, but
because the code to do it is not here.

## Exit codes

0 when every run the command performed completed, 1 when at least one was
blocked or failed, 2 when the runner could not start at all. `watch` returns 0
when it is stopped cleanly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from .config import RunnerConfig
from .resources import DEFAULT_TIER_MODELS, ECONOMY, STANDARD, STRONGEST
from .errors import ConfigurationError, RunnerError
from .queue import RunStore
from .runner import COMPLETED, SKIPPED, EngineeringRunner


_OK = 0
_STOPPED = 1
_REFUSED = 2


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m tools.engineering_runner")
    commands = root.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("doctor", "check that the runner could work, without running anything"),
        ("watch", "poll the lifecycle and execute authorized work as it appears"),
        ("run-one", "execute exactly one work order, then stop"),
        ("status", "what this runner knows about its jobs"),
    ):
        parser = commands.add_parser(name, help=help_text)
        _common(parser)
        if name == "run-one":
            # Two spellings, on purpose. `status` takes `--work-order` and
            # `run-one` took a bare positional, and that inconsistency cost two
            # operator invocations in the discovery pilot - one passing
            # `--work-order-id` and getting "unrecognized arguments", one
            # omitting it and getting a bare "required: work_order_id" with no
            # hint of the accepted shape. Neither spent money, and both are the
            # kind of thing that will happen again at 2am. Accept both, name
            # both in the error.
            parser.add_argument(
                "work_order_id",
                nargs="?",
                default="",
                metavar="WORK_ORDER_ID",
                help="the work order to execute, e.g. wo-my-work-order",
            )
            parser.add_argument(
                "--work-order-id",
                "--work-order",
                dest="work_order_id_flag",
                default="",
                metavar="WORK_ORDER_ID",
                help="the same value as the positional argument; either spelling works",
            )
        if name == "status":
            parser.add_argument("--work-order", dest="work_order_id", default="")
        if name == "watch":
            parser.add_argument(
                "--once", action="store_true", help="one pass over the lifecycle, then stop"
            )
            parser.add_argument("--max-runs", type=int, default=None)
            parser.add_argument(
                "--stop-after",
                type=float,
                default=None,
                metavar="SECONDS",
                help="stop the loop after this long; the run in flight still finishes",
            )
    return root


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--state-dir",
        type=Path,
        required=True,
        help="the Company OS state directory; never defaulted, exactly as the "
        "engineering CLI never defaults it",
    )
    parser.add_argument("--runner-dir", type=Path, required=True)
    parser.add_argument(
        "--worktree-root",
        type=Path,
        default=None,
        help="where per-work-order worktrees are cut; defaults beside the repository",
    )
    parser.add_argument("--operator", default="MGI")
    parser.add_argument("--backend", default="claude_code")
    parser.add_argument("--reviewer-backend", default="")
    parser.add_argument("--developer-model", default="")
    parser.add_argument("--reviewer-model", default="")
    parser.add_argument(
        "--economy-model",
        default=DEFAULT_TIER_MODELS[ECONOMY],
        help="which vendor model the economy tier means; used only after the "
        "deterministic P5 downshift gate passes",
    )
    parser.add_argument(
        "--standard-model",
        default=DEFAULT_TIER_MODELS[STANDARD],
        help="which vendor model the standard tier means; an alias by default, so "
        "the account's current model of that strength is what runs",
    )
    parser.add_argument(
        "--strongest-model",
        default=DEFAULT_TIER_MODELS[STRONGEST],
        help="which vendor model the strongest tier means",
    )
    parser.add_argument(
        "--ignore-resource-strategy",
        action="store_true",
        help="record the resource strategy Company OS recommended and run the "
        "operator's own settings instead; a debugging seam, not a way to spend "
        "more, since the runner's own timeouts still bind",
    )
    parser.add_argument(
        "--no-experience-advice",
        action="store_true",
        help="do not ask Company OS for prior-experience advice before a developer "
        "session; the advice is navigation only, so this changes no authority",
    )
    parser.add_argument("--python", dest="python_executable", default=sys.executable)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--poll-interval", type=float, default=20.0)
    parser.add_argument("--lease-seconds", type=float, default=3600.0)
    parser.add_argument("--developer-timeout", type=float, default=3600.0)
    parser.add_argument("--reviewer-timeout", type=float, default=1800.0)
    parser.add_argument("--test-timeout", type=float, default=1800.0)
    parser.add_argument("--gate-timeout", type=float, default=900.0)
    parser.add_argument(
        "--gate-suite",
        action="append",
        default=[],
        dest="gate_suites",
        help="run this suite instead of the gate's required set; for debugging only, "
        "since a smaller set makes the gate answer INSUFFICIENT_EVIDENCE",
    )
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="skip `git push`. The completion protocol requires a verified remote "
        "SHA, so a receipt produced this way is recorded as rejected.",
    )


def configuration(args: argparse.Namespace) -> RunnerConfig:
    repo_root = Path(args.repo_root).resolve()
    worktree_root = (
        Path(args.worktree_root).resolve()
        if args.worktree_root
        else repo_root.parent / f"{repo_root.name}-runner-worktrees"
    )
    return RunnerConfig(
        repo_root=repo_root,
        state_dir=Path(args.state_dir),
        runner_dir=Path(args.runner_dir),
        worktree_root=worktree_root,
        operator=args.operator,
        backend=args.backend,
        reviewer_backend=args.reviewer_backend,
        developer_model=args.developer_model,
        reviewer_model=args.reviewer_model,
        economy_model=args.economy_model,
        standard_model=args.standard_model,
        strongest_model=args.strongest_model,
        apply_resource_strategy=not args.ignore_resource_strategy,
        experience_advice=not args.no_experience_advice,
        python_executable=args.python_executable,
        remote=args.remote,
        poll_interval_s=args.poll_interval,
        lease_seconds=args.lease_seconds,
        developer_timeout_s=args.developer_timeout,
        reviewer_timeout_s=args.reviewer_timeout,
        test_timeout_s=args.test_timeout,
        gate_timeout_s=args.gate_timeout,
        gate_suites=tuple(args.gate_suites),
        push=not args.no_push,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = configuration(args)
        runner = EngineeringRunner(config)
    except (ConfigurationError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return _REFUSED
    try:
        if args.command == "doctor":
            return _doctor(runner)
        if args.command == "watch":
            return _watch(runner, args)
        if args.command == "run-one":
            return _run_one(runner, args)
        return _status(runner, config, args)
    except RunnerError as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return _REFUSED


def _doctor(runner: EngineeringRunner) -> int:
    checks = runner.preflight()
    _emit(checks)
    backends = checks.get("backends", {})
    ready = all(item.get("available") for item in backends.values())
    return _OK if ready else _STOPPED


def _watch(runner: EngineeringRunner, args: argparse.Namespace) -> int:
    def emit(event: str, data: dict[str, Any]) -> None:
        print(json.dumps({"event": event, **data}, sort_keys=True), flush=True)

    try:
        reports = runner.watch(
            once=args.once,
            max_runs=args.max_runs,
            stop_after_s=args.stop_after,
            on_event=emit,
        )
    except KeyboardInterrupt:
        emit("stopped", {"reason": "interrupted by the operator"})
        return _OK
    return _OK if all(item.outcome == COMPLETED for item in reports) else _STOPPED


def resolve_work_order_id(args: argparse.Namespace) -> str:
    """One id from the two accepted spellings, or a refusal that names both.

    Separate from `_run_one` so the rule is testable without building a runner
    or touching a repository.
    """
    positional = (getattr(args, "work_order_id", "") or "").strip()
    flag = (getattr(args, "work_order_id_flag", "") or "").strip()
    if positional and flag and positional != flag:
        raise RunnerError(
            f"two different work order ids were given: {positional!r} positionally "
            f"and {flag!r} as a flag. Pass one."
        )
    chosen = positional or flag
    if not chosen:
        raise RunnerError(
            "run-one needs a work order id. Either spelling works:\n"
            "  python -m tools.engineering_runner run-one WO_ID "
            "--repo-root . --state-dir S --runner-dir R\n"
            "  python -m tools.engineering_runner run-one --work-order-id WO_ID "
            "--repo-root . --state-dir S --runner-dir R\n"
            "`python -m tools.engineering_runner status` lists the ids this "
            "runner knows about."
        )
    return chosen


def _run_one(runner: EngineeringRunner, args: argparse.Namespace) -> int:
    report = runner.run_one(resolve_work_order_id(args))
    _emit(report.to_dict())
    if report.outcome == SKIPPED:
        return _STOPPED
    return _OK if report.outcome == COMPLETED else _STOPPED


def _status(
    runner: EngineeringRunner, config: RunnerConfig, args: argparse.Namespace
) -> int:
    store = RunStore(config.runner_dir)
    work_orders = (
        (args.work_order_id,) if args.work_order_id else store.known_work_orders()
    )
    rows = []
    for work_order_id in work_orders:
        lease = store.lease(work_order_id)
        rows.append(
            {
                "work_order_id": work_order_id,
                "lease": lease.to_dict() if lease else None,
                "lease_age_s": round(lease.age_s(), 1) if lease else None,
                "outcomes": [
                    {
                        "outcome": item.get("outcome"),
                        "final_state": item.get("final_state"),
                        "finished_at": item.get("finished_at"),
                        "reason": item.get("reason"),
                    }
                    for item in store.outcomes(work_order_id)
                ],
            }
        )
    _emit({"runner_dir": str(config.runner_dir), "jobs": rows, "actionable": list(runner.actionable())})
    return _OK


def _emit(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
