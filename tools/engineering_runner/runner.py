"""The loop: read the lifecycle, do the machine part, hand the evidence back.

This is the actuator Company OS structurally cannot contain. Every stage here
is a stage a person used to perform by hand - launch a coding session, run
pytest, launch a review session, run the gate, write the receipt - and the
whole of the runner's contribution is doing them and recording what happened.

    company state says          the runner does                and hands back
    ------------------------------------------------------------------------
    planning                    brief, task worktree,          a SessionReceipt
                                developer session, commit,
                                required tests, push
    developing                  (a run died here) resume the   a SessionReceipt
                                same packet's session
    testing                     review-brief, reviewer         a ReviewerAttestation
                                session in a new process
    reviewing                   (a run died here) resume       a ReviewerAttestation
    gate                        the 11 required suites, then   the gate's own report
                                `company.integration check`
    ready_for_approval          nothing. It is the CEO's.
    decision_required/blocked   nothing. Also the CEO's.

## The queue is the lifecycle

There is no pending list. `JobState` already answers "what does this work
order need next", and a second list would be a second answer. That is also
what makes the runner restart-safe without a journal: a process that dies
mid-stage leaves the job in a state that says which stage was in flight, and
the next run reads it rather than remembering it.

## Why every stage ends by handing something back

The runner never advances a job. It produces evidence and gives it to
Company OS, which validates it and moves the state itself. So there is no
path here that can make a job ready: `record_gate` does that, from a report
the gate wrote, and this module cannot write one.

## BLOCKED is not a failure and not a retry

`AuthorityViolation` - a changed path outside `may_write`, a protected file
that moved, a branch that is not the authorized one - stops the run without
committing and without pushing. The truthful evidence still goes to Company
OS, as a *rejected* receipt naming the violation, because an attempt that
exceeded its scope is a fact the history has to hold. What the runner will not
do is try again: widening is not a mistake a second attempt fixes, and the
next move belongs to the CEO.

## What the runner cannot do, by construction rather than by policy

It holds no code that merges, tags, deploys or publishes; `Workspace` has one
outward call, `push`, of one branch to one remote, which the completion
protocol requires. It holds no code that writes a CEO decision: `ControlPlane`
has no `decide`. And it computes no verdict of its own - not a readiness, not
a review outcome - because both of those are read from a reply it did not
produce.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import datetime as dt
import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping

from .authorization import (
    AuthorityEnvelope,
    AuthorityVerdict,
    digest_paths,
    verify_developer_changes,
    verify_reviewer_left_no_trace,
)
from .backends import CodingBackend, SessionOutcome, SessionRequest, build_backend, executor_hint
from .resources import ResourceStrategy
from .briefs import (
    DEVELOPER_REPORT_NAME,
    REVIEW_DIFF_NAME,
    developer_instructions,
    repair_instructions,
    review_instructions,
)
from .repo_map import RepoMap, build_repo_map
from .config import RunnerConfig
from .controlplane import ControlPlane
from .errors import (
    AuthorityViolation,
    BackendUnavailable,
    ClaimUnavailable,
    IntegrityFailure,
    RunnerError,
)
from .evidence import (
    DEPENDENCY_MANIFESTS,
    REQUIRED_SUITES,
    GitObservation,
    TestRun,
    assert_reviewer_report,
    build_attestation,
    build_receipt,
    manifest_changes,
    normalised_changes,
    parse_json_object,
    read_json_object,
    run_tests,
    suite_evidence,
)
from .process import CommandRunner
from .queue import RunStore, utcnow, write_json, write_text
from .redaction import Redactor, sanitize_json_file
from .workspace import Workspace


# `JobState` in company/engineering/lifecycle.py, by value. The runner reads
# these strings out of a CLI reply; it never constructs one.
PLANNING = "planning"
DEVELOPING = "developing"
TESTING = "testing"
REVIEWING = "reviewing"
GATE = "gate"
READY_FOR_APPROVAL = "ready_for_approval"
DECISION_REQUIRED = "decision_required"
BLOCKED = "blocked"
FAILED = "failed"
CLOSED = "closed"

# States the runner can move off. Everything else belongs to the CEO or is
# terminal, and the runner leaves it exactly where it is.
ACTIONABLE: frozenset[str] = frozenset({PLANNING, DEVELOPING, TESTING, REVIEWING, GATE})

# How many stages one run may perform before it stops and says so. A bounded
# correction loop cannot exceed this, so reaching it means the lifecycle is
# cycling and the runner should stop rather than keep paying for sessions.
#
# This is the outer bound. The active resource profile may name a smaller one -
# consumer mode does - and the runner tightens to it the moment it reads its
# first briefing. It never loosens: a strategy cannot buy a run more stages
# than the runner was started willing to perform.
MAX_STAGES_PER_RUN = 16

# What a run writes when it stops at a ceiling instead of finishing. The point
# is that the *next* session starts from this file and not from a transcript:
# a checkpoint is what the next session needs, and a conversation is what the
# last one happened to contain.
CHECKPOINT_NAME = "checkpoint.json"

# Run outcomes, as the outcome log records them.
COMPLETED = "completed"
RUN_BLOCKED = "blocked"
RUN_FAILED = "failed"
SKIPPED = "skipped"


@dataclass(frozen=True)
class StageRecord:
    """One stage of one run: what it was, what moved, and what it produced."""

    stage: str
    state_before: str
    state_after: str
    ok: bool
    detail: str = ""
    artifacts: tuple[str, ...] = ()
    session_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "ok": self.ok,
            "detail": self.detail,
            "artifacts": list(self.artifacts),
            "session_ids": list(self.session_ids),
        }


@dataclass(frozen=True)
class RunReport:
    """One run of one work order, start to stop."""

    work_order_id: str
    outcome: str
    final_state: str
    stages: tuple[StageRecord, ...]
    run_dir: str
    started_at: str
    finished_at: str
    reason: str = ""
    lease_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_order_id": self.work_order_id,
            "outcome": self.outcome,
            "final_state": self.final_state,
            "stages": [item.to_dict() for item in self.stages],
            "run_dir": self.run_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "reason": self.reason,
            "lease_note": self.lease_note,
        }


class EngineeringRunner:
    """One operator's runner: a control-plane client, a workspace, and backends."""

    def __init__(
        self,
        config: RunnerConfig,
        *,
        command_runner: CommandRunner | None = None,
        control_plane: ControlPlane | None = None,
        workspace: Workspace | None = None,
        store: RunStore | None = None,
        backend_factory: Callable[[str], CodingBackend] | None = None,
        today: Callable[[], dt.date] | None = None,
    ) -> None:
        config.ensure_directories()
        self.config = config
        self._redactor = Redactor()
        self._stage_limit = MAX_STAGES_PER_RUN
        self._commands = command_runner or CommandRunner(redactor=self._redactor)
        self._control = control_plane or ControlPlane(
            self._commands,
            python_executable=config.python_executable,
            repo_root=config.repo_root,
            state_dir=config.state_dir,
            timeout_s=config.control_plane_timeout_s,
        )
        self._workspace = workspace or Workspace(
            self._commands,
            repo_root=config.repo_root,
            worktree_root=config.worktree_root,
            remote=config.remote,
            timeout_s=config.git_timeout_s,
        )
        self._store = store or RunStore(config.runner_dir)
        self._backend_factory = backend_factory or (
            lambda name: build_backend(name, self._commands, redactor=self._redactor)
        )
        self._today = today or (lambda: dt.date.today())
        self._backends: dict[str, CodingBackend] = {}

    # --- what there is to do ----------------------------------------------

    def backend(self, name: str) -> CodingBackend:
        if name not in self._backends:
            self._backends[name] = self._backend_factory(name)
        return self._backends[name]

    def preflight(self) -> dict[str, Any]:
        """Everything the operator should know before the watch loop starts."""
        checks: dict[str, Any] = {"config": self.config.to_dict()}
        listing = self._control.listing()
        checks["control_plane"] = {
            "exit_code": listing.exit_code,
            "work_orders": listing.payload.get("work_orders", []),
        }
        checks["repository"] = {
            "head": self._workspace.require_git(["rev-parse", "HEAD"]),
            "branch": self._workspace.require_git(["rev-parse", "--abbrev-ref", "HEAD"]),
            "common_dir": str(self._workspace.common_dir()),
        }
        backends: dict[str, Any] = {}
        for name in sorted({self.config.backend, self.config.reviewer_backend_name}):
            try:
                ok, detail = self.backend(name).available()
            except RunnerError as exc:
                ok, detail = False, str(exc)
            backends[name] = {"available": ok, "detail": detail}
        checks["backends"] = backends
        checks["required_suites"] = list(REQUIRED_SUITES)
        return checks

    def actionable(self) -> tuple[dict[str, Any], ...]:
        """Every work order whose state the runner can move, oldest id first."""
        listing = self._control.listing().require()
        rows = listing.payload.get("work_orders", [])
        return tuple(
            dict(row)
            for row in rows
            if isinstance(row, Mapping) and str(row.get("state", "")) in ACTIONABLE
        )

    # --- one work order ----------------------------------------------------

    def _preflight(self) -> str:
        """Refuse configurations that would spend a session and discard its work.

        The receipt contract requires the authorized branch to be verifiable on
        the remote: `GitObservation.remote_verified` is false without it, and the
        receipt is then rejected however good the change is. With `--no-push`
        the runner never pushes, so `remote_sha` stays empty and **every**
        attempt is rejected after the developer session has already been paid
        for.

        That is not hypothetical. The first end-to-end delegation pilot lost a
        developer session worth USD 0.86 to exactly this: 183 tests passing, an
        attested reviewer pass, and a receipt rejected because the branch was
        not on the remote. The session cost is spent before the receipt is
        validated, so the only place this can be caught cheaply is here, before
        anything starts.
        """
        if not self.config.push:
            return (
                "--no-push is incompatible with the receipt contract: the "
                "completion protocol requires the authorized branch to be "
                "verifiable on the remote, so every attempt would be rejected "
                "after its session had already been paid for. Run with push "
                "enabled, or change the receipt contract deliberately."
            )
        return ""

    def run_one(self, work_order_id: str) -> RunReport:
        """Drive one work order as far as the runner is allowed to take it."""
        started = utcnow()
        refusal = self._preflight()
        if refusal:
            return RunReport(
                work_order_id=work_order_id,
                outcome=BLOCKED,
                final_state="",
                stages=(),
                run_dir="",
                started_at=started.isoformat(),
                finished_at=utcnow().isoformat(),
                reason=refusal,
            )
        try:
            lease, note = self._store.acquire(
                work_order_id, lease_seconds=self.config.lease_seconds, stage="starting"
            )
        except ClaimUnavailable as exc:
            return RunReport(
                work_order_id=work_order_id,
                outcome=SKIPPED,
                final_state="",
                stages=(),
                run_dir="",
                started_at=started.isoformat(),
                finished_at=utcnow().isoformat(),
                reason=str(exc),
            )

        run_dir = self._store.run_dir(work_order_id, lease.run_sequence)
        run_dir.mkdir(parents=True, exist_ok=True)
        stages: list[StageRecord] = []
        outcome = COMPLETED
        reason = ""
        state = ""
        try:
            state = self._state(work_order_id)
            # The correction loop lives here, and it is Company OS's loop, not
            # the runner's. A review that requires changes sends the job back
            # to `planning`, which is actionable, so the next turn of this loop
            # issues the next attempt - and stops when the work order's attempt
            # ceiling is spent, because `record_review` then moves the job to
            # `decision_required` instead, which is not actionable.
            #
            # Continuing on a stage that did not pass is therefore correct, and
            # the thing that must not be continued is a stage that did not
            # *move* the job: that is a stall, not a correction, and repeating
            # it would spend sessions on the same state forever.
            previous = ""
            self._stage_limit = MAX_STAGES_PER_RUN
            performed = 0
            while True:
                if performed >= self._stage_limit:
                    outcome = RUN_FAILED
                    reason = (
                        f"this run performed {performed} stages, which is the "
                        f"ceiling the active resource profile allows; stopping "
                        "with a checkpoint rather than continuing to spend sessions"
                    )
                    break
                if state not in ACTIONABLE:
                    break
                if state == previous:
                    outcome = RUN_FAILED
                    reason = (
                        f"the {state} stage left the job in {state}; stopping rather "
                        "than repeating a stage that did not move it"
                    )
                    break
                previous = state
                lease = self._store.heartbeat(lease, stage=state)
                record = self._stage(work_order_id, state, run_dir)
                stages.append(record)
                performed += 1
                state = record.state_after or self._state(work_order_id)
        except AuthorityViolation as exc:
            outcome, reason = RUN_BLOCKED, str(exc)
        except (RunnerError, OSError) as exc:
            outcome, reason = RUN_FAILED, f"{type(exc).__name__}: {exc}"
        finally:
            try:
                state = state or self._state(work_order_id)
            except RunnerError:
                pass
            self._store.release(lease)

        # The run's outcome is the job's state, not the last stage's verdict. A
        # review that required changes is a stage that did not pass and a run
        # that may still reach `ready_for_approval` two stages later; and a run
        # that stopped anywhere short of it did not finish, whichever stage
        # stopped short.
        if outcome == COMPLETED and state in (BLOCKED, DECISION_REQUIRED):
            outcome = RUN_BLOCKED
            reason = reason or f"the job is {state} and waits for the CEO"
        elif outcome == COMPLETED and state != READY_FOR_APPROVAL:
            outcome = RUN_FAILED
            reason = reason or (
                stages[-1].detail
                if stages
                else f"the job is {state or 'unknown'} and the runner cannot move it"
            )

        if outcome != COMPLETED:
            self._write_checkpoint(work_order_id, run_dir, state=state, reason=reason)

        report = RunReport(
            work_order_id=work_order_id,
            outcome=outcome,
            final_state=state,
            stages=tuple(stages),
            run_dir=str(run_dir),
            started_at=started.isoformat(),
            finished_at=utcnow().isoformat(),
            reason=self._redactor.scrub(reason) if reason else "",
            lease_note=note,
        )
        write_json(run_dir / "run.json", report.to_dict())
        self._store.record_outcome(report.to_dict())
        self._publish_result(work_order_id, run_dir)
        return report

    # --- the watch loop ----------------------------------------------------

    def watch(
        self,
        *,
        once: bool = False,
        max_runs: int | None = None,
        stop_after_s: float | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> tuple[RunReport, ...]:
        """Poll the lifecycle and run whatever is ready, until told to stop.

        One job failing never stops the loop. That is the whole reason a watch
        loop exists rather than a script: the operator starts it once, and a
        work order that goes wrong becomes a recorded outcome and a line in the
        log, not an ended session.
        """
        emit = on_event or (lambda event, data: None)
        reports: list[RunReport] = []
        deadline = None if stop_after_s is None else time.monotonic() + stop_after_s
        emit("started", {"runner_id": self._store.runner_id, **self.config.to_dict()})
        while True:
            try:
                pending = self.actionable()
            except (RunnerError, OSError) as exc:
                emit("poll_failed", {"error": str(exc)})
                pending = ()
            for row in pending:
                work_order_id = str(row.get("work_order_id", ""))
                if not work_order_id:
                    continue
                emit("claiming", {"work_order_id": work_order_id, "state": row.get("state")})
                report = self.run_one(work_order_id)
                if report.outcome != SKIPPED:
                    reports.append(report)
                emit("finished", report.to_dict())
                if max_runs is not None and len(reports) >= max_runs:
                    emit("stopped", {"reason": f"reached max_runs={max_runs}"})
                    return tuple(reports)
                if deadline is not None and time.monotonic() >= deadline:
                    emit("stopped", {"reason": "reached the time limit"})
                    return tuple(reports)
            if once:
                emit("stopped", {"reason": "one pass requested"})
                return tuple(reports)
            if deadline is not None and time.monotonic() >= deadline:
                emit("stopped", {"reason": "reached the time limit"})
                return tuple(reports)
            emit("idle", {"sleep_s": self.config.poll_interval_s, "pending": len(pending)})
            time.sleep(self.config.poll_interval_s)

    # --- checkpoints ---------------------------------------------------------

    def _write_checkpoint(
        self, work_order_id: str, run_dir: Path, *, state: str, reason: str
    ) -> Path | None:
        """What the next fresh session needs, and deliberately nothing else.

        A session that stops at a ceiling has to be continuable, or the ceiling
        just throws the work away. The continuation is a *fresh* session: it
        reads this file and the repository, and it does not inherit the last
        session's conversation. That is the whole point - carrying the
        conversation forward is what made a continuation cost more than the
        attempt it continued, because the transcript is the expensive part and
        almost none of it is load-bearing.

        Six things go in, and they are the six the milestone brief names: the
        work order, what is already done, where the code is, what is failing,
        what the reviewer is still unhappy about, and which references matter.
        No transcript, no tool output, no session id, no narrative.
        """
        developer = _latest_stage_dir(run_dir, "developer")
        briefing = _read_json(developer / "briefing.json") if developer else {}
        order = briefing.get("work_order", {}) if isinstance(briefing, Mapping) else {}
        efficiency = briefing.get("efficiency", {}) if isinstance(briefing, Mapping) else {}
        context = efficiency.get("context", {}) if isinstance(efficiency, Mapping) else {}
        receipt = _read_json(developer / "receipt.json") if developer else {}
        tests = _read_json(developer / "tests.json") if developer else {}
        changes = _read_json(developer / "changes.json") if developer else {}

        failing = [
            {
                "command": run.get("command"),
                "summary": run.get("summary"),
                "failure_detail": run.get("failure_detail", "")[:2000],
            }
            for run in (tests.get("runs", ()) if isinstance(tests, Mapping) else ())
            if isinstance(run, Mapping) and run.get("exit_code") not in (0, None)
        ]

        checkpoint = {
            "checkpoint_version": 1,
            "work_order": {
                "work_order_id": work_order_id,
                "work_order_fingerprint": order.get("work_order_fingerprint", ""),
                "objective": order.get("objective", ""),
                "authorized_branch": order.get("authorized_branch", ""),
                "authorized_paths": order.get("authorized_paths", []),
                "acceptance_criteria": order.get("acceptance_criteria", []),
                "required_tests": order.get("required_tests", []),
            },
            "stopped": {"state": state, "reason": self._redactor.scrub(reason or "")},
            "completed_work": {
                "summary": self._redactor.scrub(str(receipt.get("summary", "")))[:1200],
                "files_changed": receipt.get("files_changed", []),
                "invariants_preserved": receipt.get("invariants_preserved", []),
            },
            "git": {
                "base_commit": order.get("base_commit", ""),
                "commit_sha": receipt.get("commit_sha", ""),
                "uncommitted": changes.get("uncommitted", [])
                if isinstance(changes, Mapping)
                else [],
            },
            "failing_tests": failing,
            "unresolved_reviewer_findings": list(self._prior_findings(work_order_id)),
            "context_refs": context.get("refs", []) if isinstance(context, Mapping) else [],
            "next_session": (
                "Start a fresh session from this file and the repository. Do not "
                "carry the previous conversation: it is the expensive part and "
                "almost none of it is load-bearing. Continuing needs the operator "
                "or the CEO to authorize it; this file does not authorize anything."
            ),
        }
        return write_json(run_dir / CHECKPOINT_NAME, checkpoint)

    # --- the resource strategy ----------------------------------------------

    def _resource_plan(
        self, payload: Mapping[str, Any], *, role: str
    ) -> tuple[ResourceStrategy, dict[str, Any]]:
        """Read the briefing's resource strategy and decide what to apply.

        The strategy is validated before anything else looks at it, so a
        briefing that carries an unreadable one stops the stage rather than
        being run at whatever the operator's defaults happen to be. The
        returned mapping is the *applied* settings, written beside the stage so
        a later reader can tell what was recommended from what was used.
        """
        strategy = ResourceStrategy.parse(payload)
        configured = (
            self.config.developer_model
            if role == "developer"
            else self.config.reviewer_model
        )
        default_timeout = (
            self.config.developer_timeout_s
            if role == "developer"
            else self.config.reviewer_timeout_s
        )

        applied: dict[str, Any] = {
            "role": role,
            "recommended": strategy.summary(),
            "applied_model": configured,
            "model_source": "operator",
            "applied_timeout_s": default_timeout,
            "timeout_source": "runner_config",
            "applied_cost_ceiling": 0.0,
            "cost_ceiling_enforced": False,
            "not_enforced": [
                "max_turns: no backend this runner drives accepts a turn ceiling; "
                "it is carried into the session's instructions as guidance only",
            ],
        }
        if not self.config.apply_resource_strategy:
            applied["model_source"] = "operator (strategy recorded, not applied)"
            return strategy, applied

        # The profile's stage ceiling tightens this run, and only tightens it.
        stage_ceiling = _stage_ceiling_of(strategy)
        if stage_ceiling and stage_ceiling < self._stage_limit:
            self._stage_limit = stage_ceiling
        applied["stage_limit"] = self._stage_limit

        if not configured:
            model = strategy.model_for(self.config.tier_models())
            if model:
                applied["applied_model"] = model
                applied["model_source"] = f"tier:{strategy.model_tier}"

        # The ceiling only ever tightens. A strategy may not buy a session more
        # wall-clock than the operator started the runner with.
        wall = float(strategy.max_wall_seconds)
        if wall < default_timeout:
            applied["applied_timeout_s"] = wall
            applied["timeout_source"] = "resource_strategy"

        ceiling = strategy.cost_ceiling()
        if ceiling is not None and self._backend_accepts_cost_ceiling():
            applied["applied_cost_ceiling"] = float(ceiling)
            applied["cost_ceiling_enforced"] = True
        elif ceiling is not None:
            applied["not_enforced"].append(
                f"session_cost: backend {self.config.backend!r} accepts no spend "
                "flag, so the ceiling is recorded and measured after the fact"
            )
        return strategy, applied

    def _backend_accepts_cost_ceiling(self) -> bool:
        """Only the Claude Code adapter passes a spend ceiling to the provider."""
        return self.config.backend == "claude_code"

    # --- stages ------------------------------------------------------------

    def _stage(self, work_order_id: str, state: str, run_dir: Path) -> StageRecord:
        if state in (PLANNING, DEVELOPING):
            return self._developer_stage(work_order_id, run_dir, resume=state == DEVELOPING)
        if state in (TESTING, REVIEWING):
            return self._review_stage(work_order_id, run_dir, resume=state == REVIEWING)
        if state == GATE:
            return self._gate_stage(work_order_id, run_dir)
        return StageRecord(
            stage="none",
            state_before=state,
            state_after=state,
            ok=False,
            detail=f"state {state!r} is not one the runner acts on",
        )

    def _developer_stage(
        self, work_order_id: str, run_dir: Path, *, resume: bool
    ) -> StageRecord:
        stage_dir = _next_stage_dir(run_dir, "developer")
        state_before = DEVELOPING if resume else PLANNING

        if resume:
            payload = self._resume_briefing(work_order_id, run_dir, "developer")
        else:
            reply = self._control.developer_brief(
                work_order_id, executor=executor_hint(self.config.backend)
            ).require()
            payload = reply.payload
        write_json(stage_dir / "briefing.json", payload)
        envelope = AuthorityEnvelope.parse(payload)
        strategy, applied = self._resource_plan(payload, role="developer")
        write_json(stage_dir / "resources.json", applied)

        worktree = self._workspace.ensure_worktree(
            envelope.authorized_branch, envelope.base_commit
        )
        before = self._workspace.status(worktree)
        protected_before = digest_paths(worktree, envelope.protected_paths)
        write_json(
            stage_dir / "authority.json",
            {
                "envelope": envelope.summary(),
                "worktree": str(worktree),
                "head_before": before.head,
                "protected_before": protected_before,
            },
        )

        report_path = stage_dir / DEVELOPER_REPORT_NAME
        instructions = developer_instructions(
            envelope,
            report_path=report_path,
            worktree=worktree,
            attempt=envelope.packet_attempt,
            prior_findings=self._prior_findings(work_order_id),
            strategy=strategy,
            repo_map=self._repo_map(worktree),
        )
        write_text(stage_dir / "instructions.md", instructions)

        session, narrative = self._session_with_report(
            backend_name=self.config.backend,
            request=SessionRequest(
                role="developer",
                cwd=worktree,
                instructions=instructions,
                timeout_s=applied["applied_timeout_s"],
                allowed_tools=self.config.developer_tools,
                disallowed_tools=self.config.disallowed_tools,
                model=applied["applied_model"],
                read_only=False,
                extra_dirs=(stage_dir,),
                max_cost=applied["applied_cost_ceiling"],
            ),
            stage_dir=stage_dir,
            report_path=report_path,
            what="the developer report",
        )

        after = self._workspace.status(worktree)
        uncommitted = self._workspace.uncommitted_paths(worktree)
        committed = self._workspace.changed_paths(
            envelope.base_commit, after.head, cwd=worktree
        )
        changed = normalised_changes({*uncommitted, *committed})
        protected_after = digest_paths(worktree, envelope.protected_paths)
        verdict = verify_developer_changes(
            envelope,
            changed_paths=changed,
            branch=after.branch,
            head_commit=after.head,
            base_is_ancestor=self._workspace.is_ancestor(
                envelope.base_commit, after.head, cwd=worktree
            ),
            protected_before=protected_before,
            protected_after=protected_after,
            worktree_identity_ok=worktree == self._workspace.worktree_path(
                envelope.authorized_branch
            ),
        )
        write_json(
            stage_dir / "changes.json",
            {
                "uncommitted": list(uncommitted),
                "committed": list(committed),
                "changed": list(changed),
                "verdict": verdict.to_dict(),
                "protected_after": protected_after,
            },
        )
        if not verdict.ok:
            return self._blocked_attempt(
                work_order_id,
                envelope,
                stage_dir=stage_dir,
                state_before=state_before,
                verdict=verdict,
                session=session,
                narrative=narrative,
                observation=GitObservation(
                    branch=after.branch,
                    base_commit=envelope.base_commit,
                    commit_sha="",
                    remote_branch_sha="",
                    remote_verified=False,
                    working_tree_clean=after.clean,
                    files_changed=changed,
                ),
            )

        commit_sha = self._workspace.commit_all(
            cwd=worktree, message=self._commit_message(envelope, narrative)
        )
        # A session that left the tree exactly as it found it has not done the
        # work, whatever its report says. Without this the attempt commits
        # nothing, the diff is empty, the required tests pass because they
        # passed before, and an empty attempt reads as a success.
        changed_nothing = not commit_sha
        if changed_nothing:
            commit_sha = after.head
        settled = self._workspace.status(worktree)
        committed = self._workspace.changed_paths(
            envelope.base_commit, commit_sha, cwd=worktree
        )
        changed = normalised_changes(committed)
        verdict = verify_developer_changes(
            envelope,
            changed_paths=changed,
            branch=settled.branch,
            head_commit=commit_sha,
            base_is_ancestor=self._workspace.is_ancestor(
                envelope.base_commit, commit_sha, cwd=worktree
            ),
            protected_before=protected_before,
            protected_after=digest_paths(worktree, envelope.protected_paths),
            worktree_identity_ok=True,
        )
        if not verdict.ok:
            return self._blocked_attempt(
                work_order_id,
                envelope,
                stage_dir=stage_dir,
                state_before=state_before,
                verdict=verdict,
                session=session,
                narrative=narrative,
                observation=GitObservation(
                    branch=settled.branch,
                    base_commit=envelope.base_commit,
                    commit_sha=commit_sha,
                    remote_branch_sha="",
                    remote_verified=False,
                    working_tree_clean=settled.clean,
                    files_changed=changed,
                ),
            )

        # What the attempt did to the project's dependency manifests, read from
        # git rather than from the report. `dependencies_added` is a governed
        # field - a non-empty one is a BLOCKING finding in the deterministic
        # review - so it is measured from the two commits the attempt sits
        # between, and the session is not asked.
        dependencies = manifest_changes(
            {
                path: self._workspace.file_at(envelope.base_commit, path, cwd=worktree)
                for path in DEPENDENCY_MANIFESTS
            },
            {
                path: self._workspace.file_at(commit_sha, path, cwd=worktree)
                for path in DEPENDENCY_MANIFESTS
            },
        )
        write_json(stage_dir / "dependencies.json", dependencies)

        tests = run_tests(
            self._commands,
            python_executable=self.config.python_executable,
            worktree=worktree,
            commands=envelope.required_tests,
            commit=commit_sha,
            timeout_s=self.config.test_timeout_s,
        )
        write_json(stage_dir / "tests.json", {"runs": [run.to_dict() for run in tests]})

        remote_sha = ""
        if self.config.push:
            push = self._workspace.push(envelope.authorized_branch, cwd=worktree)
            write_json(stage_dir / "push.json", push.to_dict())
            remote_sha = self._workspace.remote_head(
                envelope.authorized_branch, cwd=worktree
            )

        observation = GitObservation(
            branch=settled.branch,
            base_commit=envelope.base_commit,
            commit_sha=commit_sha,
            remote_branch_sha=remote_sha,
            remote_verified=bool(remote_sha) and remote_sha == commit_sha,
            working_tree_clean=settled.clean,
            files_changed=changed,
        )
        accepted = (
            not changed_nothing
            and str(narrative.get("outcome", "accepted")).strip().lower() != "rejected"
            and all(run.green for run in tests)
            and observation.remote_verified
        )
        receipt = build_receipt(
            envelope,
            observation=observation,
            tests=tests,
            narrative=narrative,
            session=session,
            completed_at=utcnow(),
            accepted=accepted,
            rejection_reason=(
                ""
                if accepted
                else _rejection(tests, observation, narrative, changed_nothing)
            ),
            dependencies_added=dependencies["dependencies_added"],
        )
        receipt_path = write_json(stage_dir / "receipt.json", receipt)
        reply = self._control.submit_receipt(
            work_order_id, receipt_path, repo_dir=worktree
        )
        write_json(stage_dir / "receipt-out.json", reply.payload or {"exit_code": reply.exit_code})
        if reply.refused:
            reply.require()
        state_after = str(reply.payload.get("state", "")) or self._state(work_order_id)
        failures = list(reply.payload.get("failures", ()))
        return StageRecord(
            stage="developer",
            state_before=state_before,
            state_after=state_after,
            ok=bool(reply.payload.get("accepted", False)),
            detail=(
                f"attempt {envelope.packet_attempt} by {envelope.employee}, commit "
                f"{commit_sha[:12]}, {len(changed)} path(s)"
                + ("" if not failures else "; receipt failures: " + "; ".join(failures[:3]))
            ),
            artifacts=(str(receipt_path),),
            session_ids=(session.session_id,),
        )

    def _review_stage(
        self, work_order_id: str, run_dir: Path, *, resume: bool
    ) -> StageRecord:
        stage_dir = _next_stage_dir(run_dir, "reviewer")
        state_before = REVIEWING if resume else TESTING
        developer_dir = _latest_stage_dir(run_dir, "developer")
        if developer_dir is None:
            raise IntegrityFailure(
                "a review needs the attempt it reviews, and this run performed no "
                "developer stage. Re-run the work order from a state the runner can "
                "start from."
            )
        developer_briefing = json.loads(
            (developer_dir / "briefing.json").read_text(encoding="utf-8")
        )
        developer_envelope = AuthorityEnvelope.parse(developer_briefing)
        receipt = read_json_object(developer_dir / "receipt.json", "the submitted receipt")
        receipt_out = read_json_object(
            developer_dir / "receipt-out.json", "the receipt's validation reply"
        )
        receipt_fingerprint = str(receipt_out.get("receipt_fingerprint", ""))
        if not receipt_fingerprint:
            raise IntegrityFailure(
                "the receipt reply carries no receipt_fingerprint, so the attestation "
                "cannot name the attempt it reviews"
            )

        if resume:
            payload = self._resume_briefing(work_order_id, run_dir, "reviewer")
        else:
            payload = self._control.review_brief(
                work_order_id,
                implementer=developer_envelope.employee,
                executor=executor_hint(self.config.reviewer_backend_name),
            ).require().payload
        write_json(stage_dir / "briefing.json", payload)
        envelope = AuthorityEnvelope.parse(payload)
        strategy, applied = self._resource_plan(payload, role="reviewer")
        write_json(stage_dir / "resources.json", applied)
        reviewer = envelope.employee
        if reviewer == developer_envelope.employee:
            raise AuthorityViolation(
                f"the review routed to {reviewer!r}, who implemented the work; a "
                "review is an independent employee"
            )

        worktree = self._workspace.worktree_path(developer_envelope.authorized_branch)
        self._workspace.assert_identity(worktree, developer_envelope.authorized_branch)
        head_before = self._workspace.status(worktree).head
        diff_path = write_text(
            stage_dir / REVIEW_DIFF_NAME,
            self._workspace.diff_text(
                developer_envelope.base_commit,
                str(receipt.get("commit_sha", head_before)),
                cwd=worktree,
            ),
        )
        developer_report = read_json_object(
            developer_dir / DEVELOPER_REPORT_NAME, "the developer report"
        )
        instructions = review_instructions(
            envelope,
            diff_path=diff_path,
            worktree=worktree,
            receipt=receipt,
            developer_report=developer_report,
            strategy=strategy,
            repo_map=self._repo_map(worktree),
        )
        write_text(stage_dir / "instructions.md", instructions)

        session, reported = self._session_with_report(
            backend_name=self.config.reviewer_backend_name,
            request=SessionRequest(
                role="reviewer",
                cwd=worktree,
                instructions=instructions,
                timeout_s=applied["applied_timeout_s"],
                allowed_tools=self.config.reviewer_tools,
                disallowed_tools=self.config.disallowed_tools
                + ("Write", "Edit", "NotebookEdit", "Bash"),
                model=applied["applied_model"],
                read_only=True,
                extra_dirs=(stage_dir,),
                max_cost=applied["applied_cost_ceiling"],
            ),
            stage_dir=stage_dir,
            report_path=None,
            what="the reviewer attestation",
            validate=assert_reviewer_report,
        )

        developer_session = _session_id_of(developer_dir)
        if developer_session and developer_session == session.session_id:
            raise AuthorityViolation(
                "the review ran in the developer's session; review must be a "
                "separate session with none of the developer's conversation"
            )
        after = self._workspace.status(worktree)
        trace = verify_reviewer_left_no_trace(
            head_before=head_before,
            head_after=after.head,
            status_after=after.dirty_paths,
        )
        write_json(stage_dir / "read_only.json", trace.to_dict())
        if not trace.ok:
            raise AuthorityViolation(
                "the review session was not read-only: " + "; ".join(trace.violations)
            )

        attestation = build_attestation(
            envelope,
            review_id=_review_id(work_order_id, developer_envelope.packet_attempt),
            reviewer=reviewer,
            reviewed_packet_fingerprint=developer_envelope.packet_fingerprint,
            receipt_fingerprint=receipt_fingerprint,
            reviewed_on=self._today(),
            reported=reported,
        )
        attestation_path = write_json(stage_dir / "attestation.json", attestation)
        reply = self._control.submit_review(
            work_order_id,
            attestation_path,
            implementer=developer_envelope.employee,
            repo_root=worktree,
        )
        write_json(
            stage_dir / "review-out.json", reply.payload or {"exit_code": reply.exit_code}
        )
        if reply.refused:
            reply.require()
        review = reply.payload.get("review", {})
        review = review if isinstance(review, Mapping) else {}
        state_after = str(reply.payload.get("state", "")) or self._state(work_order_id)
        return StageRecord(
            stage="reviewer",
            state_before=state_before,
            state_after=state_after,
            ok=str(review.get("outcome", "")) == "pass",
            detail=(
                f"{reviewer} returned {reported.get('verdict', '?')}; Company OS "
                f"adjudicated {review.get('outcome', '?')} "
                f"(attested {review.get('attested_outcome', '?')}, deterministic "
                f"{review.get('deterministic_outcome', '?')})"
            ),
            artifacts=(str(attestation_path),),
            session_ids=(session.session_id,),
        )

    def _gate_stage(self, work_order_id: str, run_dir: Path) -> StageRecord:
        stage_dir = _next_stage_dir(run_dir, "gate")
        developer_dir = _latest_stage_dir(run_dir, "developer")
        if developer_dir is None:
            raise IntegrityFailure("the gate needs the implementation it evaluates")
        receipt = read_json_object(developer_dir / "receipt.json", "the submitted receipt")
        briefing = json.loads((developer_dir / "briefing.json").read_text(encoding="utf-8"))
        envelope = AuthorityEnvelope.parse(briefing)
        commit = str(receipt.get("commit_sha", ""))
        worktree = self._workspace.worktree_path(envelope.authorized_branch)
        self._workspace.assert_identity(worktree, envelope.authorized_branch)
        head = self._workspace.status(worktree).head
        if commit and head != commit:
            raise IntegrityFailure(
                f"the task worktree is at {head[:12]} and the implementation is "
                f"{commit[:12]}; the gate would describe a different tree"
            )

        suites = self.config.gate_suites or REQUIRED_SUITES
        runs = run_tests(
            self._commands,
            python_executable=self.config.python_executable,
            worktree=worktree,
            commands=suites,
            commit=head,
            timeout_s=self.config.test_timeout_s,
        )
        write_json(stage_dir / "suite-runs.json", {"runs": [run.to_dict() for run in runs]})
        evidence_path = write_json(
            stage_dir / "suites.json",
            suite_evidence(
                runs,
                observed_on=self._today(),
                reported_by=f"external-engineering-runner/{self.config.operator}",
            ),
        )
        result, report, readiness = self._control.gate_check(
            gate_repo_root=worktree,
            suite_evidence=evidence_path,
            timeout_s=self.config.gate_timeout_s,
        )
        report_path = write_json(stage_dir / "gate-report.json", report)
        write_json(
            stage_dir / "gate-command.json",
            {**result.to_dict(), "readiness": readiness},
        )
        reply = self._control.submit_gate(
            work_order_id,
            report_path,
            reported_readiness=readiness,
            implementation_commit=commit or head,
        )
        write_json(stage_dir / "gate-out.json", reply.payload or {"exit_code": reply.exit_code})
        if reply.refused:
            reply.require()
        state_after = str(reply.payload.get("state", "")) or self._state(work_order_id)
        green = sum(1 for run in runs if run.green)
        return StageRecord(
            stage="gate",
            state_before=GATE,
            state_after=state_after,
            ok=state_after == READY_FOR_APPROVAL,
            detail=(
                f"{green}/{len(runs)} required suites green; gate says {readiness} at "
                f"{(commit or head)[:12]}"
            ),
            artifacts=(str(report_path), str(evidence_path)),
        )

    # --- helpers -----------------------------------------------------------

    def _blocked_attempt(
        self,
        work_order_id: str,
        envelope: AuthorityEnvelope,
        *,
        stage_dir: Path,
        state_before: str,
        verdict: AuthorityVerdict,
        session: SessionOutcome,
        narrative: Mapping[str, Any],
        observation: GitObservation,
    ) -> StageRecord:
        """Record an out-of-scope attempt truthfully, then stop.

        The evidence is submitted - a rejected receipt naming the violation, at
        no commit and with nothing pushed - because an attempt that exceeded
        its scope is a fact the history has to hold, and a runner that simply
        went quiet would leave the job looking unattempted. What is not done is
        a retry: `AuthorityViolation` ends the run, and the next move is the
        CEO's.
        """
        reason = "authority violation: " + "; ".join(verdict.violations)
        receipt = build_receipt(
            envelope,
            observation=observation,
            tests=(),
            narrative=narrative,
            session=session,
            completed_at=utcnow(),
            accepted=False,
            rejection_reason=reason,
        )
        receipt_path = write_json(stage_dir / "receipt.json", receipt)
        reply = self._control.submit_receipt(work_order_id, receipt_path)
        write_json(
            stage_dir / "receipt-out.json", reply.payload or {"exit_code": reply.exit_code}
        )
        raise AuthorityViolation(reason)

    def _session_with_report(
        self,
        *,
        backend_name: str,
        request: SessionRequest,
        stage_dir: Path,
        report_path: Path | None,
        what: str,
        validate: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> tuple[SessionOutcome, dict[str, Any]]:
        """Launch a session and read its structured answer, with one repair try.

        `validate` runs against the decoded answer, so a reply that parses but
        does not fit the contract Company OS will hold it to is repaired here -
        by the session that made the judgment - instead of being refused a
        stage later, when the judgment is already gone.
        """
        backend = self.backend(backend_name)
        available, detail = backend.available()
        if not available:
            raise BackendUnavailable(f"{backend_name}: {detail}")
        attempt = request
        problem = ""
        for index in range(self.config.max_stage_retries + 1):
            session = backend.launch(attempt)
            # The report is the one channel the session writes straight to
            # disk, and everything downstream - the receipt, the attestation,
            # the Company OS record, the committed evidence - is built from it.
            # Scrub it where it lands, before anything reads it, so there is no
            # arrangement of later code that can persist a credential a session
            # happened to quote back.
            if report_path is not None:
                sanitize_json_file(report_path, self._redactor)
            write_json(stage_dir / f"session-{index + 1}.json", session.to_dict())
            write_text(
                stage_dir / f"session-{index + 1}.transcript.txt",
                self._redactor.scrub(session.transcript),
            )
            write_json(stage_dir / "session.json", session.to_dict())
            if session.exploration is not None:
                # The bounded, normalised trace `exploration_report.py` and a
                # human read for "what did this session actually explore" -
                # separate from `session.json` so that file stays the same
                # small shape it always was. Never the raw transcript: the
                # events here are already reduced to a tool name, a category
                # and a repo-relative path or pattern.
                write_json(
                    stage_dir / "exploration.json",
                    {**session.exploration, "events": list(session.exploration_events)},
                )
            try:
                if report_path is not None and report_path.is_file():
                    answer = read_json_object(report_path, what)
                else:
                    answer = parse_json_object(session.result_text, what)
                if validate is not None:
                    validate(answer)
                return session, answer
            except IntegrityFailure as exc:
                problem = str(exc)
                if index >= self.config.max_stage_retries:
                    raise
                attempt = SessionRequest(
                    role=request.role,
                    cwd=request.cwd,
                    instructions=repair_instructions(request.instructions, problem),
                    timeout_s=request.timeout_s,
                    allowed_tools=request.allowed_tools,
                    disallowed_tools=request.disallowed_tools,
                    model=request.model,
                    read_only=request.read_only,
                    extra_dirs=request.extra_dirs,
                )
        raise IntegrityFailure(problem or f"{what}: no usable answer")

    def _resume_briefing(
        self, work_order_id: str, run_dir: Path, role: str
    ) -> dict[str, Any]:
        """The briefing a previous run already obtained, so no packet is re-issued.

        A run that died after `brief` left the job in `developing`: a packet
        exists and an attempt is already spent. Asking Company OS for another
        brief would spend a second attempt for a session that never ran, so the
        saved payload is reused instead, and a job with no saved payload is
        reported rather than guessed at.
        """
        for directory in sorted(run_dir.parent.glob("run-*"), reverse=True):
            for stage in sorted(directory.glob(f"{role}*"), reverse=True):
                candidate = stage / "briefing.json"
                if candidate.is_file():
                    return json.loads(candidate.read_text(encoding="utf-8"))
        raise IntegrityFailure(
            f"{work_order_id} is mid-{role} and this runner holds no briefing for it. "
            "The packet was issued by another process or another machine; the job "
            "needs a person to decide whether to continue it."
        )

    def _prior_findings(self, work_order_id: str) -> tuple[str, ...]:
        """What the last review asked for, so a correction attempt can see it."""
        history = self._control.status(work_order_id).payload
        reviews = history.get("reviews", ())
        attestations = history.get("attestations", ())
        if not isinstance(reviews, Sequence) or not reviews:
            return ()
        rendered = [
            f"review {item.get('review_id')}: {item.get('outcome')}"
            for item in reviews
            if isinstance(item, Mapping)
        ]
        if isinstance(attestations, Sequence):
            rendered += [
                f"{item.get('reviewer')} returned {item.get('verdict')}"
                for item in attestations
                if isinstance(item, Mapping)
            ]
        return tuple(rendered[-6:])

    def _repo_map(self, worktree: Path) -> RepoMap | None:
        """The deterministic map of the worktree the session is about to read.

        Built fresh per stage rather than cached across work orders: each
        work order's worktree can sit at a different commit, a stale map
        naming a file that moved is worse than no map, and a full `ast` parse
        of `company/` + `tools/` + `tests/` measures at about two seconds -
        negligible beside a session that runs for minutes. Best-effort: a map
        that failed to build is a missing convenience, never a reason to stop
        an authorized session.
        """
        try:
            return build_repo_map(worktree)
        except OSError:
            return None

    def _state(self, work_order_id: str) -> str:
        reply = self._control.status(work_order_id)
        if reply.refused:
            reply.require()
        return str(reply.payload.get("state", ""))

    def _publish_result(self, work_order_id: str, run_dir: Path) -> None:
        """Record the CEO page for whatever state the job ended in."""
        try:
            reply = self._control.result(work_order_id)
            write_json(run_dir / "result.json", reply.payload)
            text = self._control.result_text(work_order_id)
            write_text(run_dir / "result.txt", text.stdout)
        except (RunnerError, OSError):
            return

    def _commit_message(
        self, envelope: AuthorityEnvelope, narrative: Mapping[str, Any]
    ) -> str:
        subject = str(narrative.get("summary", "")).strip().splitlines()
        head = subject[0][:72] if subject else envelope.objective[:72]
        body = [
            "",
            envelope.objective,
            "",
            f"Work-Order: {envelope.work_order_id} ({envelope.work_order_fingerprint})",
            f"Packet: {envelope.packet_fingerprint} attempt {envelope.packet_attempt}",
            f"Authority: {envelope.authority_fingerprint}",
            f"Employee: {envelope.employee}",
            f"Runner: external-engineering-runner ({self.config.backend})",
        ]
        return "\n".join([head, *body]) + "\n"


def _rejection(
    tests: Sequence[TestRun],
    observation: GitObservation,
    narrative: Mapping[str, Any],
    changed_nothing: bool = False,
) -> str:
    if changed_nothing:
        return (
            "the session changed nothing: the working tree is identical to the "
            "authorized base commit, so there is no work to review"
        )
    failing = [run.command for run in tests if not run.green]
    if failing:
        return "required test(s) failed at the implementation commit: " + ", ".join(failing)
    if not observation.remote_verified:
        return (
            "the branch was not verified on the remote, so the completion protocol "
            "is incomplete"
        )
    return str(narrative.get("rejection_reason", "")) or "the session reported a rejection"


def _next_stage_dir(run_dir: Path, role: str) -> Path:
    index = 1 + sum(1 for _ in run_dir.glob(f"{role}-*"))
    path = run_dir / f"{role}-{index:02d}"
    path.mkdir(parents=True, exist_ok=True)
    return path



def _stage_ceiling_of(strategy: "ResourceStrategy") -> int:
    """The profile's stage ceiling, as the strategy carries it."""
    terms = strategy.raw.get("profile_terms")
    if not isinstance(terms, Mapping):
        return 0
    value = terms.get("stage_ceiling")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return 0
    return value


def _read_json(path: Path | None) -> dict[str, Any]:
    """Whatever is there, or nothing. A checkpoint is best-effort by design.

    It is written on the failure path, and a checkpoint that raised while
    reporting a failure would replace the failure with its own.
    """
    if path is None or not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}

def _latest_stage_dir(run_dir: Path, role: str) -> Path | None:
    """The most recent stage of this role, searching earlier runs if needed.

    A review does not have to happen in the same *run* as the attempt it
    reviews. A runner that died between the two - or was restarted, or hit a
    bug and was fixed - resumes from `testing`, in a new run directory, and the
    receipt it must review is in the previous one. Looking only at the current
    run made a resumed review impossible for a reason that has nothing to do
    with the work; the dogfood run found it.
    """
    runs = sorted(run_dir.parent.glob("run-*"), reverse=True)
    for directory in ([run_dir] + [item for item in runs if item != run_dir]):
        for path in sorted(directory.glob(f"{role}-*"), reverse=True):
            if (path / "briefing.json").is_file():
                return path
    return None


def _session_id_of(stage_dir: Path) -> str:
    path = stage_dir / "session.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""
    return str(data.get("session_id", "")) if isinstance(data, Mapping) else ""


def _review_id(work_order_id: str, attempt: int) -> str:
    stem = "".join(
        char if char.isalnum() or char in "._-" else "-" for char in work_order_id.lower()
    ).strip("-.")
    return f"rev-{stem}-{max(attempt, 1):02d}"[:64]


__all__ = [
    "ACTIONABLE",
    "COMPLETED",
    "MAX_STAGES_PER_RUN",
    "RUN_BLOCKED",
    "RUN_FAILED",
    "SKIPPED",
    "EngineeringRunner",
    "RunReport",
    "CHECKPOINT_NAME",
    "StageRecord",
]
