# Production repository measurement (deterministic, read-only)

Measured 2026-09-19 against `origin/main` @ `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f`,
via `git ls-tree -r --long`. No checkout of `main` performed; read directly from
git objects from the `company-os-v1-resource-optimization-research` worktree.
Does not include `company/`, `ai_platform/`, or `tools/engineering_runner/`
(those are Company OS, not on `main` — see `company_os_ai_resource_optimization_research.md`
§1 for that side).

## File count and byte size by extension, `main` tree

| ext | files | bytes |
|---|---:|---:|
| png | 612 | 517,776,976 |
| json | 281 | 14,578,450 |
| py | 403 | 7,364,683 |
| jpg | 20 | 2,991,475 |
| noext | 2 | 1,672,067 |
| md | 77 | 1,614,448 |
| gd | 81 | 1,604,131 |
| txt | 48 | 204,023 |
| tscn | 12 | 2,477 |

Python outnumbers GDScript 403:81 by file count (5:1), consistent with
[[repository-exploration-efficiency-v1-stop-condition]]'s repo-wide 593:76
measurement at an earlier commit that also counted `company/`/`tests/`.
Binary assets (png/jpg) dominate byte size but are irrelevant to token cost —
they are never read into a model context as text.

## Largest Python files, `main`

| bytes | lines | path |
|---:|---:|---|
| 125,327 | 2,617 | `sloped/stations.py` |
| 89,418 | 1,723 | `sloped/cameras.py` |
| 88,912 | 2,068 | `audio/asmr.py` |
| 75,524 | 1,638 | `sloped/v24_hook.py` |
| 74,054 | — | `tools/race2_v321_geometry.py` |
| 73,563 | — | `tools/race2_v301_stage.py` |
| 69,152 | — | `tools/race2_v33_bookends.py` |
| 68,097 | — | `sloped/chase_camera.py` |
| 67,863 | — | `race2/bookends.py` |

## Largest GDScript files, `main`

| bytes | path |
|---:|---|
| 129,898 | `godot/scripts/neon_scene.gd` |
| 84,899 | `godot/scripts/race_scene.gd` |
| 81,672 | `godot/scripts/toy_scene.gd` |
| 71,635 | `godot/assets/marble_machine/environment/environment_world.gd` |
| 61,591 | `godot/assets/marble_machine/lab_palette.gd` |
| 48,879 | `godot/assets/marble_machine/environment/environment_stage.gd` |
| 43,646 | `godot/scripts/replay_viewer.gd` |
| 43,249 | `godot/assets/marble_machine/course/course_modules.gd` |
| 40,205 | `godot/scripts/race2_scene.gd` |

## Reading

The single largest source file in the entire production tree is GDScript
(`neon_scene.gd`, 129,898 bytes), not Python — larger than the largest Python
file (`stations.py`, 125,327 bytes / 2,617 lines). Python's stdlib `ast`
module, which `tools/engineering_runner/repo_map.py` already uses for the
Company OS side, cannot parse either file's GDScript siblings at all — it has
no GDScript grammar. This is the concrete evidence behind classifying
"local file navigation cost" and "cross-language navigation" as
CURRENTLY MATERIAL for the GDScript half of the repository (§3 of the main
report) and behind Benchmark C / Benchmark E in the proposed suite.

No render output, generated artifact, or `output/` directory was read or
measured — this is a static tree listing only.
