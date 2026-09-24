# P6B — full repository suite, and every failure classified

## The run

```
6767 tests collected
22 failed, 6358 passed, 441 skipped in 2565.34s (0:42:45)
```

Branch `p6b-contract-test-repo-intelligence-v1`, on the tree as it stood at
`93d9bd9`, run with `-p no:randomly` so the order is reproducible.

## How each failure was classified

Not by reading the name. Each failing **node id** was re-run in
`wt-p6b-baseline`, a worktree detached at
`39fbd44ee7d9c755ba2059b5ab9a467e9c399f30` — the `origin/main` this branch was
cut from. A failure that reproduces there is pre-existing; one that passes
there is P6B's until shown otherwise.

That is also why the baseline was not run in full. Classifying twenty-two
failures needs twenty-two baseline results, not six thousand: the other 6,745
tests pass on the branch, so their baseline status cannot change any verdict.
The full baseline run was started and abandoned for a second reason as well —
two concurrent full suites on this machine stalled each other in
`tests/test_external_engineering_runner.py`, which spawns real git worktrees
and takes 21 minutes for its 185 tests on its own.

## Result

| classification | count |
| --- | ---: |
| pre-existing — fails identically on `39fbd44` | 18 |
| **P6B-introduced — fixed in `66ab1df`** | **1** |
| branch-scope guard — fires on any branch with a production diff | 3 |

### The one real defect, and why the review missed it

`tests/test_company_session_execution.py::test_company_os_remains_removable_and_production_does_not_import_it`

It greps every module under a production root for the raw strings `from
company`, `import company`, `from ai_platform` and two more. Documenting the
resolver's package-facade rule meant writing an example import line into a
`repo_map.py` docstring, and the guard — correctly — could not tell that from
an import.

The adversarial review pass had asserted the same boundary and passed, because
it walked the AST and the module imports nothing. The repository has **two**
forms of this rule and only the stricter one caught it. Both are now pinned in
`tests/test_company_dependency_graph.py`: one says what the module does, the
other says what the file may contain. The second is the one a docstring breaks
first.

`tools/youtube_fetch/__init__.py` had already written this down — "their names
are deliberately not spelled out in this file" — which is where the fixed
docstring now points.

### The three branch-scope guards

`test_this_branch_changed_no_race_fight_or_v30_code`, in
`test_company_os_research.py`, `test_company_os_research_batches.py` and
`test_company_os_research_ingestion.py`.

Each asserts `_production_changes(git diff --name-status origin/main...HEAD)
== []`. That is a statement about which branch you are standing on, not about
P6B's code: any branch touching a production root fires it, and P6B modifies
`tools/engineering_runner` by design. Every *other* test in those three files
passes on the branch.

They pass in `wt-p6b-baseline`, whose HEAD equals `origin/main` and whose diff
is therefore empty. Post-merge the same holds by construction. That is the
modelled half of the gate evidence and it is labelled as modelled in
`suites-post-merge-modelled.json`; the real branch result is BLOCKED and is in
`gate-report-on-branch.json`.

### The eighteen pre-existing failures

All reproduce on `39fbd44`. Twelve are branch-scope or content-lock guards
from earlier video milestones; six are the parametrised
`test_no_locked_file_moved` / `test_no_locked_package_moved` cases. One,
`test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`, is
environmental — Godot is not on `PATH` in this environment.

```
tests/test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised
tests/test_race2_v301_stage.py::test_this_branch_changes_no_physics_camera_or_course_module
tests/test_race2_v30_stage.py::test_this_branch_changes_no_physics_camera_or_course_module
tests/test_race2_v311_track.py::test_the_branch_changes_only_render_and_measurement
tests/test_race2_v311_track.py::test_no_locked_package_moved[race2/]
tests/test_race2_v321_geometry.py::test_the_branch_changes_only_render_and_measurement
tests/test_race2_v32_final.py::test_the_branch_adds_only_presentation
tests/test_race2_v32_final.py::test_no_locked_file_moved[race2/race.py]
tests/test_race2_v32_final.py::test_no_locked_file_moved[race2/parts.py]
tests/test_race2_v32_final.py::test_no_locked_file_moved[race2/kit.py]
tests/test_race2_v32_final.py::test_no_locked_file_moved[godot/scripts/race2_scene.gd]
tests/test_race2_v32_final.py::test_no_locked_file_moved[godot/assets/marble_machine/course/race2_track_surface.gd]
tests/test_race2_v33_bookends.py::test_the_branch_adds_bookends_and_touches_nothing_else
tests/test_sloped_v251_world.py::test_the_siting_tool_uses_the_scenes_own_edit_map
tests/test_sloped_v251_world.py::test_the_projector_puts_each_node_in_the_frame_named_for_it
tests/test_sloped_v251_world.py::test_every_authored_site_lands_in_at_least_one_frame
tests/test_sloped_v251_world.py::test_the_analytic_parallax_finds_a_spread_in_every_chase
tests/test_sloped_v252_world.py::test_the_geometric_parallax_field_is_identical_to_v251s
```

## The derived required set, run individually

All 45 suites were run one at a time, which is what produces `suites.json` in
the format the gate consumes. **42 green, 3 red**, the three being the
branch-scope guards above.

`tests/test_external_engineering_runner.py` accounts for 21 of the 24 minutes:
185 tests, each building a real git worktree.

## What this does not establish

The full baseline suite was not run to completion, so this says nothing about
the baseline status of the 6,745 tests that pass on the branch. It does not
need to: a test passing on P6B cannot be a P6B regression.
