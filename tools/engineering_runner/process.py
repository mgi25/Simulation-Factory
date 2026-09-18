"""The one place this package spawns a process.

Every subprocess the runner starts - git, pytest, the Company OS CLI, a coding
session - goes through `run`. That is deliberate: `subprocess` is the whole
reason this package lives under `tools/` instead of under `company/`, so it is
worth being able to point at a single function and say "this is the execution
plane, and it is forty lines".

## What every call records

A `CommandResult` carries the argv, the working directory, the exit code, the
wall time and the redacted output. The argv is kept as a list rather than a
string because a command reconstructed by joining on spaces is a command
nobody can re-run, and because a shell was never involved: `run` never passes
`shell=True`, so nothing here interprets a metacharacter.

## Output is redacted on the way in, not on the way out

`CommandResult.stdout` is already scrubbed. A caller that wants the raw bytes
does not get them, because the only reason to want them is to write them
somewhere, and the run directory is exactly where a credential must not land.

## Timeouts are required

Every call names one. A coding session that hangs would otherwise hold the
work order's lease until the operator noticed, and the watch loop's whole
promise is that it keeps going.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
import subprocess
import time
from typing import Mapping, Sequence

from .errors import ConfigurationError
from .redaction import Redactor, child_environment


@dataclass(frozen=True)
class CommandResult:
    """One finished command: what ran, where, how it ended, and what it said."""

    argv: tuple[str, ...]
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def display(self) -> str:
        """The command as one readable line, for a record a person will read."""
        return " ".join(self.argv)

    def to_dict(self) -> dict[str, object]:
        return {
            "argv": list(self.argv),
            "cwd": self.cwd,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 3),
            "timed_out": self.timed_out,
            "stdout_chars": len(self.stdout),
            "stderr": self.stderr[-4000:],
        }

    def tail(self, limit: int = 4000) -> str:
        return self.stdout[-limit:]


@dataclass(frozen=True)
class CommandRunner:
    """Runs commands with a fixed redactor, so no call site can forget one."""

    redactor: Redactor = field(default_factory=Redactor)

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | str,
        timeout_s: float,
        env: Mapping[str, str] | None = None,
        stdin: str | None = None,
    ) -> CommandResult:
        args = [str(item) for item in argv]
        if not args:
            raise ConfigurationError("a command needs at least a program name")
        directory = Path(cwd)
        if not directory.is_dir():
            raise ConfigurationError(f"{directory}: not a directory to run a command in")
        # Never the bare inherited environment: `child_environment` is the one
        # answer to "what does a child get", and it is the same answer for git,
        # for pytest, for the Company OS CLI and for a coding session.
        environment = dict(env) if env is not None else child_environment()
        started = time.monotonic()
        timed_out = False
        try:
            completed = subprocess.run(  # noqa: S603 - argv list, never a shell
                args,
                cwd=str(directory),
                env=environment,
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
                shell=False,
                check=False,
            )
            exit_code = completed.returncode
            out = completed.stdout or ""
            err = completed.stderr or ""
        except subprocess.TimeoutExpired as expired:
            timed_out = True
            exit_code = 124
            out = _decode(expired.stdout)
            err = _decode(expired.stderr) + f"\ntimed out after {timeout_s:.0f}s"
        except FileNotFoundError as missing:
            raise ConfigurationError(
                f"{args[0]}: not found on PATH; the runner cannot start it"
            ) from missing
        return CommandResult(
            argv=tuple(args),
            cwd=str(directory),
            exit_code=exit_code,
            stdout=self.redactor.scrub(out),
            stderr=self.redactor.scrub(err),
            duration_s=time.monotonic() - started,
            timed_out=timed_out,
        )


def _decode(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def resolve_executable(name: str) -> str:
    """The absolute path of `name`, or a refusal naming it.

    Resolved once and recorded, so a run record says which binary ran rather
    than which name was typed. On Windows this is what turns `claude` into
    `claude.CMD`, which `subprocess` needs and a bare name does not give it.
    """
    found = shutil.which(name)
    if not found:
        raise ConfigurationError(
            f"{name!r} is not on PATH. The runner launches it as a child process; "
            "install it or point the runner at another backend."
        )
    return found


__all__ = ["CommandResult", "CommandRunner", "resolve_executable"]
