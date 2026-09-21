"""The boundary: the only module here that knows Company OS exists.

The runner never imports Company OS. `tools/` is a declared production root
and `architecture.production_does_not_import_company_os` is a required gate
check, so an import would fail the gate this milestone has to keep passing.
The dependency is therefore a *command line*, exactly as
`tools/youtube_fetch` depends on `company/youtube` through a JSON artifact and
not through a name.

    runner   -- argv and JSON files -->   python -m company.engineering <stage>
             <-- JSON on stdout, plus an exit code --

That is not a workaround. It is the property that makes the two halves
separable: every stage the runner drives is a stage a human can drive by
typing the same command, and every answer the runner acts on is an answer
Company OS produced and would produce again.

## The exit code is the answer

`company.engineering` documents three: 0 advanced, 1 stopped on evidence, 2
refused. This module preserves all three rather than collapsing them into
"failed", because the difference between "the review says changes are
required" and "the receipt is malformed" is the difference between the
correction loop and a bug.

## What this module may not do

It builds no records, decides nothing, and has no branch on the *content* of a
reply beyond reading the fields a caller asked for. Anything that looks like
judgment belongs to Company OS on one side or to the runner's authorization
checks on the other. A helper here that decided whether a review passed would
be a second adjudicator, and the whole design refuses one.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .errors import ControlPlaneRefusal, IntegrityFailure
from .process import CommandResult, CommandRunner


# The Company OS entry points the runner drives, by module path. Named here
# once so a reader can see the whole surface the execution plane touches.
ENGINEERING_MODULE = "company.engineering"
INTEGRATION_MODULE = "company.integration"

# `company.integration.__main__._EXIT`, inverted. The gate CLI's exit code *is*
# its verdict, and it is the only place the verdict appears as one word: the
# report carries the checks, not a summary field. Reading it is what lets the
# runner pass `--reported-readiness`, which makes `GateVerdict` compare what
# the gate said with what the report's own required checks say and refuse the
# pair if they differ. Without it that cross-check silently does not run.
GATE_READINESS_BY_EXIT: Mapping[int, str] = {
    0: "ready",
    1: "blocked",
    2: "insufficient_evidence",
}

# `company.engineering` exit codes, as its own CLI documents them.
ADVANCED = 0
STOPPED = 1
REFUSED = 2


@dataclass(frozen=True)
class StageReply:
    """One Company OS command's answer: its exit code and its JSON."""

    command: str
    exit_code: int
    payload: dict[str, Any]
    raw: CommandResult

    @property
    def advanced(self) -> bool:
        return self.exit_code == ADVANCED

    @property
    def stopped(self) -> bool:
        return self.exit_code == STOPPED

    @property
    def refused(self) -> bool:
        return self.exit_code >= REFUSED

    def require(self) -> "StageReply":
        """Raise unless Company OS advanced. A refusal is never reinterpreted."""
        if self.refused:
            raise ControlPlaneRefusal(
                self.command,
                self.exit_code,
                self.raw.stderr.strip() or self.raw.tail(1200),
            )
        return self


class ControlPlane:
    """A thin, typed front door to the Company OS command line."""

    def __init__(
        self,
        runner: CommandRunner,
        *,
        python_executable: str,
        repo_root: Path,
        state_dir: Path,
        timeout_s: float,
    ) -> None:
        self._runner = runner
        self._python = python_executable
        self._repo_root = Path(repo_root)
        self._state_dir = Path(state_dir)
        self._timeout = float(timeout_s)

    # --- engineering stages ------------------------------------------------

    def request(self, request_file: Path, *, work_order_id: str = "") -> StageReply:
        args = [
            "request",
            "--request-file",
            str(request_file),
            "--repo-root",
            str(self._repo_root),
        ]
        if work_order_id:
            args += ["--work-order-id", work_order_id]
        return self._engineering(args)

    def status(self, work_order_id: str) -> StageReply:
        return self._engineering(["status", "--work-order", work_order_id])

    def listing(self) -> StageReply:
        return self._engineering(["list"])

    def developer_brief(self, work_order_id: str, *, executor: str) -> StageReply:
        return self._engineering(
            ["brief", "--work-order", work_order_id, "--executor", executor]
        )

    def submit_receipt(
        self, work_order_id: str, receipt_file: Path, *, repo_dir: Path | None = None
    ) -> StageReply:
        args = [
            "receipt",
            "--work-order",
            work_order_id,
            "--receipt-file",
            str(receipt_file),
        ]
        if repo_dir is not None:
            args += ["--repo-dir", str(repo_dir)]
        return self._engineering(args)

    def review_brief(
        self, work_order_id: str, *, implementer: str, executor: str
    ) -> StageReply:
        return self._engineering(
            [
                "review-brief",
                "--work-order",
                work_order_id,
                "--implementer",
                implementer,
                "--executor",
                executor,
            ]
        )

    def submit_review(
        self,
        work_order_id: str,
        attestation_file: Path,
        *,
        implementer: str,
        repo_root: Path,
    ) -> StageReply:
        """Adjudicate a review against the checkout the work actually happened in.

        `--repo-root` is where `company.engineering.review` re-reads the
        protected governance surface and compares it with the digests taken at
        authorization - the one check that can catch a change no receipt
        mentions. So it has to be the **task worktree**, not the operator's
        checkout: pointing it at a tree the session never touched would make
        that check re-read files nobody could have edited and pass every time.
        """
        return self._engineering(
            [
                "review",
                "--work-order",
                work_order_id,
                "--attestation-file",
                str(attestation_file),
                "--implementer",
                implementer,
                "--repo-root",
                str(repo_root),
            ]
        )

    def submit_gate(
        self,
        work_order_id: str,
        gate_report: Path,
        *,
        reported_readiness: str,
        implementation_commit: str,
    ) -> StageReply:
        args = [
            "gate",
            "--work-order",
            work_order_id,
            "--gate-report",
            str(gate_report),
            "--reported-readiness",
            reported_readiness,
        ]
        if implementation_commit:
            args += ["--implementation-commit", implementation_commit]
        return self._engineering(args)

    def execution_stop(self, work_order_id: str, *, reason: str) -> StageReply:
        """Persist an external-session stop so a restart cannot spend again."""
        return self._engineering(
            [
                "execution-stop",
                "--work-order",
                work_order_id,
                "--reason",
                reason,
            ]
        )

    def result(self, work_order_id: str, *, risks: Sequence[str] = ()) -> StageReply:
        args = ["result", "--work-order", work_order_id, "--json"]
        for risk in risks:
            args += ["--risk", risk]
        return self._engineering(args)

    def result_text(self, work_order_id: str) -> CommandResult:
        """The CEO page as the CEO sees it, without recording a second copy."""
        return self._runner.run(
            [
                self._python,
                "-m",
                ENGINEERING_MODULE,
                "result",
                "--work-order",
                work_order_id,
                "--state-dir",
                str(self._state_dir),
                "--no-store",
            ],
            cwd=self._repo_root,
            timeout_s=self._timeout,
        )

    # --- the integration gate, run by its own CLI --------------------------

    def gate_check(
        self,
        *,
        gate_repo_root: Path,
        suite_evidence: Path,
        timeout_s: float,
    ) -> tuple[CommandResult, dict[str, Any], str]:
        """Run the gate over a checkout and return its report and its verdict.

        The verdict comes from the exit code, not from the report: the report
        holds the checks and names no summary field, so a caller that looked
        for one would find nothing and would quietly stop cross-checking.

        The report is the gate's output and the runner is its courier. Nothing
        here reads a check, weighs a status or computes a readiness: that is
        `company.integration`'s job on one side and
        `company.engineering.gate_evidence`'s on the other, and a third opinion
        living in the execution plane is precisely what a gate must not have.
        """
        result = self._runner.run(
            [
                self._python,
                "-m",
                INTEGRATION_MODULE,
                "check",
                "--repo-root",
                str(gate_repo_root),
                "--json",
                "--suite-evidence",
                str(suite_evidence),
                "--state-dir",
                str(self._state_dir),
            ],
            cwd=gate_repo_root,
            timeout_s=timeout_s,
        )
        if result.timed_out or not result.stdout.strip():
            raise ControlPlaneRefusal(
                "company.integration check", result.exit_code, result.stderr.strip()
            )
        readiness = GATE_READINESS_BY_EXIT.get(result.exit_code, "")
        if not readiness:
            raise ControlPlaneRefusal(
                "company.integration check",
                result.exit_code,
                "the gate exited with a code that is not one of its three verdicts",
            )
        return result, _parse_json(result.stdout, "company.integration check"), readiness

    # --- internals ---------------------------------------------------------

    def _engineering(self, args: Sequence[str]) -> StageReply:
        argv = [
            self._python,
            "-m",
            ENGINEERING_MODULE,
            *args,
            "--state-dir",
            str(self._state_dir),
        ]
        result = self._runner.run(argv, cwd=self._repo_root, timeout_s=self._timeout)
        command = f"python -m {ENGINEERING_MODULE} {args[0]}"
        payload: dict[str, Any] = {}
        text = result.stdout.strip()
        if text.startswith("{"):
            payload = _parse_json(text, command)
        elif result.exit_code >= REFUSED:
            raise ControlPlaneRefusal(
                command, result.exit_code, result.stderr.strip() or text[:1200]
            )
        return StageReply(
            command=command, exit_code=result.exit_code, payload=payload, raw=result
        )


def _parse_json(text: str, command: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IntegrityFailure(
            f"{command} did not answer with JSON: {text[:400]!r}"
        ) from exc
    if not isinstance(data, Mapping):
        raise IntegrityFailure(
            f"{command} answered with {type(data).__name__}, not an object"
        )
    return dict(data)


__all__ = [
    "ADVANCED",
    "GATE_READINESS_BY_EXIT",
    "ENGINEERING_MODULE",
    "INTEGRATION_MODULE",
    "REFUSED",
    "STOPPED",
    "ControlPlane",
    "StageReply",
]
