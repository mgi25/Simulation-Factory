# Category 3 MULTIPLYING SHELL — Phase 3B redesign evidence

This is a human-review candidate phase, not production approval. No upload
master was created.

## Provenance and isolation

- source branch: `category3-multiplying-shell-av-v3`
- fetched source tip: `cc125c01c25a57c8b670f72edda2556dbaf0b4bf`
- work branch: `category3-multiplying-shell-adjust-v3b`
- historical Phase 1, Visual 2A, Audio 2B, and A/V 3 branches and evidence were
  not rewritten

## Apparent concentric misalignment

The collision rings were mathematically concentric. The old perspective camera
was translated laterally to place the arena at the Shorts-safe composition
point. The five slabs extend backward by different depths, so their midplanes
and rear rims acquired different perspective parallax toward the viewport
centre. The result looked like five different centres even though every front
collision plane used the origin.

The camera eye now remains on the invariant world centre and uses a centred
asymmetric perspective frustum to put the principal point at `(0.42 W, 0.44 H)`.
Frontier changes alter only eye distance. Thick slabs, chamfers, front faces,
rear rims, and the depth ramp remain.

The 60 fps Python audit projects every shell's slab mid-depth at every rendered
frame. Its maximum disagreement is **0.000 px at 1080×1920**. The independent
Godot walk of all 1,233 frames at 60 fps measured a maximum disagreement of
**0.000061 px**, with `4.29e-13` world-unit maximum ball-position error and zero
panel-state mismatches. It exports all five projected centres per frame.
Diagnostic renders cover frame zero, each transition midpoint, each
settled frontier, and the final outer-shell section with a crosshair, centre
markers, and outlines; these temporary images are not committed.

## Controlled retuning

The committed sweep evidence records named changes rather than a blind product
search. The selected configuration is:

| shell | panels | openings × slots | open fraction | break threshold | surface speed |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 12 | 3 × 2 | 0.500 | 1.8 | 3.720 |
| 2 | 24 | 3 × 2 | 0.250 | 2.8 | 4.121 |
| 3 | 28 | 2 × 2 | 0.143 | 4.4 | 4.398 |
| 4 | 38 | 2 × 2 | 0.105 | 6.6 | 4.612 |
| 5 | 46 | 2 × 1 | 0.043 | 9.0 | 4.789 |

Directions alternate. The modest `omega_falloff = 0.82` ramp raises timing
pressure without turning openings into blur. The visually obvious segmentation,
opening ratio, and toughness ramp do most of the work.

Damage remains deterministic shared panel state. A contact contributes
normal-impact kinetic-energy proxy above the chip floor; tangential velocity
does not leak into damage. Integrity states now correspond to approximately
`>76%`, `48–76%`, `22–48%`, `0–22%`, and zero. Damage from different balls
persists on one ledger. At zero, the panel breaks once, invalidates cached
contacts, becomes permanently passable, and remains absent. Contributor ball
IDs, generations, largest contributor, and triggering ball are evaluator
metadata, avoiding event-schema churn.

The reproduction law, lineage, parent/child tracking, spawn geometry,
anti-farming credit, deterministic trajectories, and disabled ball-ball
collisions are unchanged. The emergency population ceiling remains 32.

## Final 20,000-seed population

Config digest: `1803a066cc67ed08088294e64dd42b7264e2bcc210f055ab225d9983e2725d38`.

| measurement | result |
| --- | ---: |
| escaped / timeout / collision cap | 7,491 / 12,509 / 0 |
| escape / timeout rate | 37.455% / 62.545% |
| shell pass rates, inner → outer | 96.80%, 85.54%, 55.94%, 32.56%, 10.15% |
| escaped duration p5 / p25 / p50 / p75 / p95 | 7.76 / 13.59 / 18.24 / 22.29 / 25.23 s |
| preferred 21–24 s / acceptable 20–26 s | 1,539 / 2,962 |
| population p5 / p25 / p50 / p75 / p95 | 4 / 7 / 8 / 10 / 13 |
| maximum observed population / cap hits | 20 / 0 |
| collision/s p50 / p95 | 6.23 / 11.89 |
| meaningful events/s p50 / p95 | 12.58 / 21.92 |
| meaningful late/early p50 / runs above 1 | 2.44× / 98.36% |
| breaks p50 / p95 | 9 / 18 |
| runs with shared breaks | 19,790 |
| cooperative outer breaks / runs | 1,171 / 1,105 |
| max break contributors p50 / p95 | 4 / 6 |
| outer shell reached / crossed | 75.65% / 37.67% |
| opening-led / break-led final escapes | 6,726 / 765 |

Average population rises from `1.00` to `8.45` over the eleven normalized
samples; within the 20–26 s band it reaches `10.34`. First spawn is 1.45 s at
the median and no run fails to reproduce. There are no reproduction violations,
anomalous crossings, Newton failures, ball-ball contacts, or population-cap
hits. Maximum penetration is `1.01e-11`; minimum spawn clearance remains
positive at `1.16e-6`. Twenty-one runs flagged repetitive-orbit behaviour and
41 flagged clone-like trajectory spread for exclusion, rather than being hidden
inside the success headline.

## Screening and human-review set

Sixteen successful seeds entered the deep screen. Seeds 15009, 19945, and
17970 were rejected for severe triple-ball merges lasting 1.167 s, 1.300 s,
and 2.800 s. The remaining thirteen are the committed engineering shortlist;
all have strictly rising population, collision, and meaningful-event thirds.
Their worst severe merge is 0.583 s.

Six synchronized 9:16 review candidates were rendered:

| seed | duration | population | final route | cooperative outer break | event/s | max polyphony | severe merge |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 15793 | 20.54 s | 12 | break, descendant g3 | yes | 9.70 | 8 | 0.350 s |
| 8292 | 22.46 s | 8 | break, descendant g2 | yes | 8.04 | 8 | 0.000 s |
| 17251 | 22.85 s | 13 | break, descendant g4 | yes | 9.16 | 10 | 0.033 s |
| 16733 | 23.24 s | 8 | break, descendant g2 | yes | 6.66 | 7 | 0.267 s |
| 12197 | 25.86 s | 11 | break, descendant g3 | yes | 8.19 | 8 | 0.433 s |
| 14705 | 21.91 s | 12 | opening, founder | no | 8.96 | 7 | 0.567 s |

Each candidate has a ten-frame contact sheet: frame zero, first spawn, four-ball
state, first critical panel, first break, cooperative damage, late high
population, outer attack, final break/opening, and first final escape. The six
sheets are under `docs/validation/category3_multiplying_shell_adjust_v3b/contact_sheets/`.
Visual review confirms the intended early → middle → late → climax → payoff
story while retaining readable individual trajectories. Full-resolution top-two
renders were skipped because the measured 540×960 render cost made the 8×
pixel-frame workload non-trivial; this phase requires review media, not masters.

## Audio and A/V

The `open_quartal` system is unchanged and scores are regenerated from each new
canonical playback. Across the six 48 kHz masters, integrated loudness is
−20.25 to −19.12 LUFS, true peak is −2.90 to −2.49 dBTP, and clipped samples
are zero. Scheduled event density is 6.66–9.70/s, maximum polyphony is 7–10,
harsh-pair incidence is zero, and maximum canonical-to-video cue error remains
below one frame. Phone-band and mono measurements are committed with the A/V
validation data.

## Evidence index

- `phase3b_controlled_sweep_500.json`, `phase3b_tighter_sweep_1000.json`,
  `phase3b_aggressive_sweep_1000.json`, `phase3b_finalist_sweep_1000.json`
- `phase3b_population_20k.json`
- `phase3b_shortlist.json`, `phase3b_screening.json`, `phase3b_candidates.json`,
  `alignment_audit.json`
- `av_candidates.json`, per-seed `detail/`, `phone_validation.json`, review mux
  inventory, and six contact sheets

The Category 3 focused suite covers projected-centre alignment, invariant
camera centre, difficulty monotonicity, deterministic physics, integrity and
normal-impact damage, weak-vs-strong impacts, shared damage, one-time permanent
breaks, cache invalidation and ghost-wall absence, reproduction and anti-farming,
lineage, population safety, regenerated audio timing, A/V sync, clipping, and
Shorts-safe composition.

Final focused result: **379 passed, 0 failed, 0 skipped** in 110.73 s.
