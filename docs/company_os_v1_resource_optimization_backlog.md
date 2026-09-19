# Company OS — Resource-Optimization Research Backlog

No scheduled benchmark. These are reopening triggers only — conditions
under which a future CEO request to reopen one specific question would be
justified by new evidence, not a plan or a timeline. See
`docs/company_os_v1_resource_optimization_closure.md` for the research
this backlog follows from.

## TREE-SITTER REOPEN TRIGGER

Reconsider only if real Company OS production work repeatedly shows
GDScript structural-navigation context cost or latency that built-ins
handle poorly. "Repeatedly" and "real production work" matter: C4's own
finding was that tree-sitter's benefit is real but workload-dependent
(strong on large-file structural localization, a wash on multi-file
same-name comparison), so a single anecdote is not sufficient — the
trigger is a *pattern* observed in actual sessions working on `godot/`,
not a new synthetic task designed to favor the provider.

## CTAGS REOPEN TRIGGER

Reconsider only if exact symbol-location workloads become frequent enough
to justify another evaluation. Ctags remains deferred rather than
rejected specifically because C4 never re-tested it under C4's own (more
rigorous) two-condition design — its only evidence is C3's inconclusive
run. A reopening would be a *new* evaluation under current standards, not
a resurrection of C3's numbers.

## SERENA REOPEN TRIGGER

Eligible only after lightweight/native options (built-ins, and Ctags/
tree-sitter if either is later reconsidered) demonstrably fail an
important recurring semantic/reference-navigation requirement — something
neither Ctags nor tree-sitter has ever claimed to support for GDScript
(both are confirmed, live, to have no caller/reference graph). Serena is
categorically heavier tooling; the bar for even testing it is a
demonstrated capability gap, not a preference.

## Standing policy (unaffected by any of the above until a trigger fires)

- Default GDScript/repository navigation remains native: `Read`, `Grep`,
  `Glob`, `Bash`.
- No provider-adjacent MCP server, index-build step, or isolated venv is
  part of any Company OS or production session's default tool surface.
- Prefer deterministic software, bounded context, caching, retrieval, and
  better task scoping over adding more AI/tooling infrastructure — the
  same preference this whole research line was testing an exception to,
  and did not find sufficient grounds to grant.
