# External Engineering Runner — hardening pass

Companion to `company_os_v1_external_engineering_runner.md`. That document
describes the runner; this one describes four defects an independent acceptance
review found in it, and what each fix actually changed. The architecture is
unchanged and was not revisited.

The review's verdict was **accept with nonblocking risks**, for single-user
local trusted development, with Claude Code as a trusted-but-fallible backend,
no automatic merge or deploy or publish, and CEO review before approval. That
frame is unchanged too.

---

## 1. The lease was not exclusive

### What was claimed

> A lease file is created with `O_EXCL`, so two processes racing for the same
> work order cannot both believe they won — the filesystem decides, not a
> check-then-write.

The first clause was true. The rest did not follow.

### What was actually happening

`os.open(..., O_CREAT | O_EXCL)` is atomic, but it creates an **empty** file.
The metadata went in on the next line, through a separate `write_json`. In
between, the lease existed and said nothing.

A contender arriving in that window did this:

```python
except FileExistsError:
    existing = self.lease(work_order_id)
    if existing is None:
        how = "reclaimed an unreadable lease"
```

`self.lease` returns `None` for a file that does not parse — and an empty file
does not parse. So the contender read a lease a winner was in the middle of
writing, concluded the holder was broken, and took a job somebody already held.

Reclaiming was worse, and did not need a window at all. Both the released and
the stale branches ended in `write_json(path, fresh.to_dict())`: a plain
overwrite after a plain read. Eight contenders read the same released lease,
eight decided they could have it, and eight wrote. The last writer's name was
in the file; all eight believed it was theirs.

### Measured, on the code this replaced

20 trials × 8 simultaneous threads, one work order per trial. The number that
should appear in every row of the middle column is the number of trials:

| starting state | expected grants | observed |
|---|---|---|
| no lease at all | 20 | **75** |
| held and fresh | 0 | 0 |
| released | 20 | **160** |
| stale (heartbeat 3 h old) | 20 | **160** |
| metadata present but unparseable | 0 | **157** |
| metadata present but empty | 0 | **149** |

160 out of 160 is every contender in every trial. The only state the old code
got right was the one where it never had to decide anything.

### The fix: ownership is a directory, and taking it is one syscall

```
<runner_dir>/runs/<work-order>/lease-000001/lease.json
```

Ownership of a work order is ownership of generation *N*, and generation *N* is
owned by whoever `os.mkdir`s `lease-<N>`. That call either creates the directory
or raises `FileExistsError`, with nothing in between, on POSIX and on Windows
alike. Exactly one contender can create one name.

A directory is **complete the instant it exists**. That is the whole difference
from `O_EXCL`: there is no state in which a work order is owned and the
filesystem does not say so. The `lease.json` written inside afterwards describes
an ownership already held; it cannot establish one, so nothing depends on when
it lands.

**Reclaiming is a create too, never an overwrite.** A contender that finds
generation *G* released or stale does not write over it — it races to create
*G+1*. Everyone reads the same *G* and everyone attempts the same `mkdir`, and
the filesystem picks one. The check-then-act is gone because there is no act to
guard: the decision only chooses *whether to enter* a race it cannot win twice.

Losing is handled by re-reading, never by falling through:

```python
try:
    claimed.mkdir()
except FileExistsError:
    continue          # somebody took this generation; re-read and find them fresh
```

### The recovery rule for an unreadable lease

An unreadable lease must not mean "therefore I won" — that was the original
defect — but it also must not mean "therefore nobody may ever have this", or a
crash wedges a job forever.

A winner that has not yet written its metadata and a winner that died before
writing it are **indistinguishable from outside**. So neither is guessed at: the
generation directory's own mtime decides, against the same lease window the
heartbeat uses.

- younger than the lease window → treated as **held**. `ClaimUnavailable`.
- older than a whole lease window with still no metadata → reclaimed as stale,
  by creating the next generation, so exactly one contender gets it.

The filesystem's own timestamp is used rather than a written one, because the
case being answered is precisely the one where nothing was written.

### Measured, after

Same harness, same 20 × 8:

| starting state | expected | observed |
|---|---|---|
| no lease at all | 20 | **20** |
| held and fresh | 0 | **0** |
| released | 20 | **20** |
| stale (heartbeat 3 h old) | 20 | **20** |
| metadata unparseable, inside the window | 0 | **0** |
| metadata empty, inside the window | 0 | **0** |
| metadata absent, directory aged past the window | 20 | **20** |

Six threads in six **separate processes**, released together on a file that
appears after they have all started, also produce exactly one `WON`.

### Two things that fell out of it

**A superseded runner must not scribble.** A holder reclaimed as stale keeps
running until it notices. Its `Lease` now carries the generation it owns, and
its heartbeats and its release address *that* directory — which nobody reads any
more — rather than the metadata of the runner that replaced it.

**The upgrade must not double-claim.** A `lease.json` sitting directly in the
job directory is a lease from the previous layout. It is read as generation 0:
respected while fresh, superseded by generation 1. A job left in flight by an
older runner is not claimed twice across the change.

### A note on the test method

Every sequential test of the old lease passed, and they were not wrong — the
defect only exists between two operations, and a test that never opens that
window cannot see it. The new tests run real simultaneous contenders and *count
grants*. The stale case needs one more care: setting `lease_seconds=0` to age
the holder ages the winner's own brand-new lease too, so each contender
supersedes the last and the number measures the clock instead of the lock. The
holder's heartbeat is backdated instead, under a normal window.

---

## 2. The child environment was inherited

`child_environment` forwarded `os.environ` and removed three names. On this
machine that handed every coding session, among 100 variables:

```
BINANCE_API_KEY
BINANCE_API_SECRET
CLAUDE_CODE_MESSAGING_TOKEN
```

None of which is in any work order, and none of which the runner has any
business passing on. A denylist has to predict the names, and an operator adds
new ones faster than the runner can learn them.

### The replacement

An allowlist, in three deliberate classes.

**1. A base safe environment** — what a process needs to *be* a process. Paths
(`PATH`, `PATHEXT`, `COMSPEC`, `SYSTEMROOT`, `TEMP`), the user's own
configuration directories (`USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `HOME`),
where software is installed, the machine's shape and locale, the Python the
tests run under, the Node a coding CLI runs under, git's own variables, and
proxy settings. Nothing in this class carries an authorisation to do anything.

`USERPROFILE` and `APPDATA` matter more than they look: that is where Claude
Code keeps the credentials it manages itself, which is why the backend still
authenticates with no auth variable forwarded at all.

**2. The backend's own variables, named one at a time** — `ANTHROPIC_API_KEY`,
`ANTHROPIC_AUTH_TOKEN`, `ANTHROPIC_BASE_URL`, the model overrides,
`CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CONFIG_DIR`, and the `codex` backend's
`OPENAI_API_KEY` and `CODEX_HOME`.

A prefix rule was the obvious shortcut and it is exactly wrong.
`CLAUDE_CODE_MESSAGING_TOKEN` shares its prefix with every Claude Code setting
and is a credential; `CLAUDE_CODE_OAUTH_TOKEN` shares it and is the backend's
own. A prefix cannot tell them apart, so there is no prefix.

**3. A cloud provider's credentials, conditionally** — the AWS set travels only
when `CLAUDE_CODE_USE_BEDROCK` is set, and the GCP set only when
`CLAUDE_CODE_USE_VERTEX` is. These are real credentials, and they cross because
a configuration needs them, not because they were in the shell.

Plus one value the runner sets itself, `PYTHONIOENCODING=utf-8`, for the reason
it always did.

The three nested-session markers are named in a never-forwarded set as well as
being absent from the allowlist, so that adding one of them later reads as a
visible contradiction rather than a quiet win.

### What it costs

34 of this machine's 100 variables cross the boundary. `claude --version`
answers, `git --version` answers, a Python child runs, and a **real
authenticated Claude Code session** completes a prompt and returns its answer —
all under the allowlist and with no authentication variable set anywhere in the
environment.

There is no escape hatch. A variable a backend needs and does not have makes it
fail its own `available()` probe, before a work order is claimed, which is the
right place to find out. Adding a name is a code change, deliberately.

---

## 3. `dependencies_added` was hardcoded to `[]`

`build_receipt` wrote the field as a literal empty list. Meanwhile
`company/engineering/review.py` has always held this:

```python
if receipt.dependencies_added:
    findings.append(ReviewFinding(
        finding_id="dependency-added",
        severity=FindingSeverity.BLOCKING,
        summary="new dependency declared (...); permissions.yaml requires "
                "architecture_and_security_review",
    ))
```

`mandatory_review_triggers.new_dependency` in `permissions.yaml` makes a new
dependency an architecture-and-security review rather than a diff to skim. The
finding was correct, required, and unreachable: an attempt could add a
production dependency inside its own authorized scope, and the deterministic
review had nothing to fire on.

### Measured, not reported

The measurement reads the repository, never the session's account of itself. A
session trusted to describe its own dependency changes is a session whose
*forgetting* to mention one is indistinguishable from not making one.

For each manifest the project actually has, the runner reads the file at the
authorized base commit and at the implementation commit — `git show <sha>:<path>`,
both sides from git — and compares declared distribution **names**, normalised
per PEP 503.

`DEPENDENCY_MANIFESTS` is `("requirements.txt",)`, because that is what this
project has. There is no `pyproject.toml` and no lock file, and supporting
manifests the repository does not carry would be a second policy with no
subject. Company OS's own dependency rule is stricter and separate — it may
import nothing but stdlib, which `company/integration/checks.py` decides by
reading imports — and it is not restated here.

### The distinction the policy relies on, preserved

| the attempt did | `files_changed` | `dependencies_added` |
|---|---|---|
| nothing to the manifest | — | `[]` |
| reordered it | `requirements.txt` | `[]` |
| raised a version floor | `requirements.txt` | `[]` |
| added `requests>=2.31` | `requirements.txt` | `["requests"]` |
| touched it without authorisation | *blocked before any commit* | `[]` |

A manifest that changed is a **scope** question, already answered by `may_write`
and the authority verdict. A dependency that was added is a **review trigger**.
Collapsing them would make every routine version bump an architecture review,
and that is a good way to teach people to route around the trigger.

Names only, for the same reason: `pygame>=2.6` becoming `pygame>=2.7` adds
nothing, and `Pillow` and `pillow` are one dependency.

Both facts are written to `dependencies.json` in the stage directory, and the
governed one goes into the receipt.

---

## 4. `report.json` was the one persisted developer channel with no redactor

Everything else a session produces reaches disk through `CommandRunner.run`,
which scrubs on the way in — that is why `CommandResult.stdout` is already
redacted and the raw bytes are not offered to callers.

The developer report does not take that path. The session writes it itself, to a
file path the runner names, and the runner then builds the receipt, the
attestation, the Company OS record and the committed evidence out of it. The
existing dogfood reports happened to be clean.

The fix is one call, at the boundary, before anything reads the file:

```python
session = backend.launch(attempt)
if report_path is not None:
    sanitize_json_file(report_path, self._redactor)
```

It uses the **same `Redactor`** as every transcript and every command result. A
second secret-matching implementation would drift from the first, and the first
is the one the transcripts are checked against.

The scrub runs over the file's text, so it covers a report that does not parse
as well as one that does. Every replacement substitutes a run of non-structural
characters, so valid JSON stays valid; a parsed-and-scrubbed form is written
instead if that ever proved otherwise.

Tested with synthetic credential-shaped values only: a sentinel placed in the
report's `summary` and `unresolved_risks` appears in neither `report.json` on
disk nor the receipt handed to Company OS, while the summary's real content, the
notes and the invariants come through unchanged.

---

## 5. What this pass deliberately did not do

**No OS-level sandboxing.** The coding backend has host-level access while it
runs. Authority is enforced strongly on the **repository result** — the diff,
the protected digests read by bytes, the branch, the worktree identity, the base
ancestry — and not through a process jail. That is unchanged, and remains the
V2 item.

The acceptance-review frame is unchanged and stays explicit: a trusted
single-user local machine, a trusted-but-fallible coding backend, and no
automatic integration, deployment or publishing.

**Recorded follow-ups, not addressed here**, because none of the four fixes
needed them: gitignored out-of-scope side effects, the text-guard architecture
cleanup, the `blocked_attempt --repo-dir` inconsistency, and the zero
`required_tests` policy.

---

## 6. Regression, at `021a618`

| | |
|---|---|
| runner targeted (`test_external_engineering_runner.py`) | 122 passed |
| the two halves pinned (`test_company_external_engineering_runner.py`) | 35 passed |
| engineering execution + the 11 required Company OS suites | 875 passed |
| integration gate | **READY** — `integration-readiness-2026-09-18-9b018bfc521fd82d`, 34/34 required checks pass, 0 blockers |
| full repository suite | 6 failed, 4429 passed, 337 skipped |
| new failures | **0** |
| pre-existing failures | 6, unchanged: `test_neon_proof.py` and the two `test_sloped_v25*_world.py` modules, all gitignored render artefacts |

The base `44fbfb1` reported 4389 passing and the same 6 failures. This branch
adds 40 passing tests and breaks none.

**Eight files changed, all of them the runner or its tests.** `company/`,
`tools/youtube_fetch/`, `ai_platform/`, `knowledge/`, `intelligence/`, every
race and visual-production package, `requirements.txt` and
`company/permissions.yaml` are untouched — the diff against `44fbfb1` names no
file outside `tools/engineering_runner/` and two test modules.

`production.no_publishing_capability` is **pass**, still required, and its
implementation is still asserted by value. Company OS still contains no
process-spawning capability. The runner still holds no code that merges, no code
that writes a CEO decision, and no code that publishes.

---

## 7. The final-HEAD dogfood, and why it is not in this file

The acceptance review noted that no complete dogfood job had run on the exact
shipped HEAD — every previous one ran on code that changed afterwards.

So this commit is the frozen HEAD, and the dogfood runs **from it**. Which means
this document cannot contain the result: writing the outcome down here would
produce a new commit, and the shipped HEAD would once again not be the HEAD that
completed a request.

The run's evidence is where the runner puts it — the briefing, the authority
check, the session records, the changes, the dependency measurement, the tests,
the receipt, the attestation and the gate report, under the runner directory —
and its identifiers are in the session report that accompanies this branch.
