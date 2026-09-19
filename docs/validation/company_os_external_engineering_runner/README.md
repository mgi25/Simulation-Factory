# External Engineering Runner V1 — the dogfood records

Three real CEO requests, carried by the runner. Everything here was written by
`tools/engineering_runner` while it ran, through its redactor, and copied in
unchanged.

```
job1-attempt-ledger/      "what did each developer attempt cost?"
job2-scope-usage/         "how much of the scope I granted was used?"
job3-stage-timing/        "where does an engineering job actually wait?"
```

Each job holds its `00-request.json` — the whole of what the CEO typed — and
one directory per **run**. A run is one turn of the runner on one work order,
so a job with more than one run is a job the runner picked up again.

| file | what it is |
|---|---|
| `run.json` | the run: its stages, the state each one moved the job to, and the session ids |
| `result.txt` | the CEO page, exactly as the CEO sees it |
| `developer-NN/instructions.md` | what the coding session was actually handed |
| `developer-NN/briefing.json` | the Company OS brief the instructions were built from |
| `developer-NN/authority.json` | the envelope, the worktree, and the protected digests taken *before* |
| `developer-NN/session.json` | the session's identity, model, turns, duration and cost |
| `developer-NN/report.json` | the narrative the session returned — and nothing else it said |
| `developer-NN/changes.json` | what git reported, and the authority verdict over it |
| `developer-NN/tests.json` | the required tests, at the implementation commit |
| `developer-NN/receipt.json` | the `SessionReceipt` the runner built and submitted |
| `developer-NN/receipt-out.json` | Company OS's validation of it |
| `reviewer-NN/read_only.json` | HEAD and status, before and after the review |
| `reviewer-NN/attestation.json` | the `ReviewerAttestation` the runner built |
| `reviewer-NN/review-out.json` | the adjudication: attested, deterministic, and the worse of the two |
| `gate-NN/suites.json` | the 11 required suites as the gate reads them |
| `gate-NN/gate-report.json` | the gate's own report, unaltered |
| `outcomes/NNNNNN.json` | the append-only outcome log |

**One known blemish.** Every `result.txt` here holds one U+FFFD where the CEO
page has an em dash. The runner captured child output as UTF-8 while a Python
child on Windows wrote its stdout in the console codepage; `PYTHONIOENCODING`
is set for every child now, and these files are kept as the runner wrote them
rather than re-read with the fixed reader, because each one is the page *at the
end of its own run* and a later re-read would return the same page for all
three of job 1's runs.

**Not copied:** the session transcripts. They are the session's own output, they
run to tens of thousands of characters, and everything a record needs from them
is in `session.json`. They remain under the runner directory, outside the
repository, where the runner wrote them.

## Reading one of these

Start with `run.json`, which is the shape of what happened, then
`developer-01/changes.json`, which is the only place the runner decides
anything — and decides it from git rather than from what the session said.
`result.txt` is what the CEO was shown.

## What job 1's three runs mean

Job 1 was the first real run, and it found three defects in the runner: the
review packet's task id, the tree the protected surface is re-read in, and
whether a review can resume in a run later than the attempt it reviews. Each
one stopped a run, was fixed, and the runner was restarted — which is why job 1
has `run-000001` through `run-000003` and job 2 has one. `docs/company_os_v1_external_engineering_runner.md`
section 14 lists all of them.
