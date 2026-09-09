# V1.11 — leg2's pocket, and a fresh 600-race benchmark

Status: **the `leg2[99]` stall is diagnosed, fixed and benchmarked. Both of the
brief's reliability targets are now met.** The fix is a slew limit on leg2's
roll; see `sloped.track._slewed_bank` and `sloped.course.BANK_SLEWS`.

Read [`sloped_race_v19_production.md`](sloped_race_v19_production.md) for the
shipped baseline and [`sloped_race_v110_fork.md`](sloped_race_v110_fork.md) for
the fork work that precedes this. The route is unchanged: `routes="blue"`,
`START_KIND="floor"`, `course.check()` and `contract.check()` at zero findings
on both route configurations.

## What `leg2[99]` actually was

V1.9 recorded it as "a V1 limitation with no mechanism yet" — 41 of 56
non-finishers, **stuck** rather than escaped. `GUARD_BOOSTS`' comment guessed
that the racer scrubbed its speed against the raised rail and arrived at leg2's
shallowest grade too slow to carry on. That guess was wrong on both halves.

**It is a pocket, and it is on the outside of the inflection.** On this course
the outside of a turn is the low side, so a roll *coming off* raises whatever
rides it. At leg2's inflection the roll unwinds about five degrees a sample —
−19.64° at 98 to −0.59° at 102 — while the centreline falls at only 10%. Over
98 to 103 the centreline drops 0.3176 and the outside edge rises 0.2849: the
unwind eats **89.7% of the drop**, and what is left is not a weak gradient but a
closed basin. The deepest climb along the run, by lateral fraction of the half
width:

    fraction   0.00     0.40     0.55     0.60     0.70     0.80     0.95
    authored 0.0000   0.0000   0.0449   0.0685   0.1159   0.1637   0.2504
    limited  0.0000   0.0000   0.0000   0.0000   0.0000   0.0000   0.0000

A marble on the centreline runs downhill throughout, which is why this never
read as a gradient problem and why the continuity audit found no seam, no step
and no local minimum in the *centreline's* grade.

**What stops the marbles is each other, and the same inflection is why.** The
pocket cannot stop a moving marble: the climb asks 1.37 units per second and the
field runs at 30 to 70. But the inflection also sweeps every marble clean across
the channel, from a lateral fraction of −0.7 to +0.7, so samples 99 to 101 are
*both* where the field crosses and collides *and* where anything stopped is
kept. Traced, three racers went from +37.11, +35.74 and +37.95 units per second
of forward speed to −12.29, +3.17 and +2.32 in a single marble-to-marble contact
and then oscillated laterally, at 0.0 to 0.7 total speed, for the rest of the
race.

**And it is a trap, not a slow finish.** Re-run at 90 seconds — more than twice
the race duration — all seven of a sample were still there. That check mattered:
every trace ended exactly at the 40-second cutoff, which is what a slow finisher
also looks like.

## The fix, and the three things that are counter-intuitive about it

Requiring that **neither** channel edge ever rises along the run is two
inequalities on consecutive samples, and together they are one slew-rate limit
on the *signed* sine of the roll:

    abs(sin(b[s+1]) - sin(b[s])) <= drop(s) / half

`BANK_SLEWS` is `{"leg2": (98, 112, 1.0)}`. Twelve samples move, by at most
10.14°, and the pocket goes to 0.0000 at every lateral fraction.

1. **A margin of 1.0 is the best setting, not the weakest.** It is the
   least-restrictive rule that still forbids an edge rising; tightening it makes
   the pocket *worse* (0.0743 at a fraction of 0.6 for margin 0.8, 0.1391 for
   0.6) because the roll then lags far enough to have to catch up inside the
   window and digs a fresh climb where it does.
2. **The window must be wide enough for the limit to rejoin the authored curve
   unaided.** Ended at 108 it snaps back with a 0.95° step and leaves a residue.
   Given until 112 it rejoins at 110 on its own — and its roll *rate* is then
   smoother than the authored one: 2.54, 2.39, 2.26, 2.15, 2.05, 1.96, 1.80,
   1.58, 1.41, 1.29 degrees a sample, against an authored 2.95, 4.97, **6.02**,
   5.11, 2.49, −0.42, −1.78, −1.12, 0.53, 1.65 that reverses sign twice.
3. **A hold is not a substitute**, and this is the attempt that was written,
   committed to comments and then withdrawn. Holding the roll at sample 99 for
   eight samples moves the pocket from sample 102 to 112 at the same depth
   (0.0685 → 0.0613 at a fraction of 0.6) and left a marble hovering **0.84**
   above the floor at `leg2[104]` in contact validation — worse than the 0.3799
   hover V1.9 rejected a video seed for. It saved the traced racers only by
   moving the trap away from where the field crosses.

### Why this lever is available when bank, radius and slope are not

`sloped.contract` pins the centreline, the widths, the drops and the bank
**extreme** — `max(abs(banks))` over the run, and nothing about the profile
between. The limit only ever unwinds more slowly through an angle the run
already reaches, so `max(abs(banks))` stays 22.0000 and the contract stays at
zero findings. The same argument `guard_boost` is built on.

**It is windowed, and a global limit would not have been safe.** The rule is
stronger than "no pocket" — it is "no point on the section ever rises", which
also forbids winding *on* faster than the drop pays for. Applied to every run at
margin 1.0 it would move leg1 by 20.78° for a pocket of 0.0309.
`tools/sloped_pocket_survey.py` has the survey; leg2 is the defect, leg3 is
0.0809, leg1 0.0309, launch and final effectively zero.

**`leg1[80..99]` is a different mechanism.** leg1's own worst point is sample
110, not 80–99, and where marbles actually ride its climb is 0.0041 — which asks
0.34 units per second to leave. This fix does not touch that hotspot and should
not be expected to.

## The 600-race benchmark, fresh seeds 2001–2600, blue route

    metric              V1.9 (600)   V1.11 (600)   brief target
    per-racer finish       98.83%       99.50%      >= 99%    met
    all-eight races        91.0%        96.0%       >= 90%    met
    stuck                   0.92%        0.15%      near 0
    escape                  0.25%        0.35%      near 0

**`leg2[99]` is gone from the loss sites entirely.** What is left, of 4800
racers: `blue[100]` 8, `final[0]` 7, `blue[0]` 3, then single figures at
`blue[20]`, `blue_lead[20]`, `launch[20]`, `launch[60]`, `leg1[40]`.

Fixing the largest site promoted the next one: **`blue[100]` and `final[0]` are
the merge**, 15 of the 24 remaining non-finishers between them. `blue[100]` is
the sample blue's exit hands over on and the site V1 lost 319 of 747 marbles at.
That is the same apron [`sloped_race_v110_fork.md`](sloped_race_v110_fork.md)
names as orange's blocker, now the leading blue defect as well — which makes a
merge rebuild the single highest-value piece of work left on this course.

### Fairness — better on rank, worse on the win tail

    metric                  V1.9     V1.11
    win-rate ratio          5.04     6.618
    podium ratio            2.09     1.957     <= 2.5 target, met
    slot mean-rank SD       0.354    0.2997
    slot mean-rank span     1.161    0.854

    slot  win%  podium%  finish%  fin rank  descent  mixed  quarter   half  3/4
       0 16.83    45.00    99.33     4.174    3.953  3.937    3.942  4.095 4.220
       1 17.67    40.00    99.50     4.369    3.627  3.652    3.658  4.208 4.387
       2  2.67    23.00    99.83     5.013    5.705  5.715    5.720  5.025 5.022
       3 12.83    33.00    99.67     4.702    4.803  4.802    4.783  4.713 4.698
       4 12.50    43.33    99.33     4.268    4.287  4.297    4.297  4.292 4.292
       5  6.33    31.67    99.33     4.819    5.535  5.495    5.495  4.968 4.852
       6 13.67    39.33    99.33     4.352    4.417  4.412    4.413  4.467 4.357
       7 17.50    44.67    99.67     4.159    3.673  3.692    3.692  4.232 4.173

**The course dilutes the start more than it did**, not less: the slot mean-rank
span decays 2.078 at the 9% mark to 0.854 at the finish, against V1.9's 2.095 to
1.161. Slot/rank Spearman is −0.0145.

**But the win ratio rose 5.04 → 6.618, driven by slot 2 at 2.67%.** Read
together with the rest, the honest reading is that removing a *random* stopper
made the *systematic* bias easier to see: `leg2[99]` was scrambling roughly one
racer in a hundred out of contention at random, and a win is a tail event, so
noise that used to blur the tail no longer does. Slots 2 and 5 are the two that
arrive worst at the 9% mark (5.705 and 5.535 of eight) and they are the two with
depressed wins; slots 0, 1 and 7 arrive best and win most. That is the frozen
start's own residual bias, unchanged by this work, now measured against a
quieter course.

V1.9's warning stands and is worth repeating: **never report the win ratio
alone.** Three of the four fairness statistics improved.

### Entertainment

    metric                V1.3 baseline   V1.11
    lead changes                    ~4     3.995
    overtakes                      ~39    34.927
    winner lock                  ~0.13    0.2127
    final margin (mean)          ~0.43s   0.5293
    final margin (median)             -   0.4667
    mean collisions                   -   101.6
    winner's worst rank               -   2.027
    top speed                         -   65.437

Lead changes hold. Overtakes are down about a tenth, and **winner lock is up
from 0.13 to 0.21** — the winner is settled earlier in the race than the V1.3
figure the brief quotes. Whether that is this change or the two versions between
it is not established here: V1.9's report does not carry a winner-lock number,
so the only comparison available spans three versions of the start as well as
this fix. It is flagged rather than explained.

## Two validation thresholds that got worse and are not explained

    reading                       config budget   V1.9      V1.11
    max travel per tick                     0.5   0.53335   0.744
    worst actuator overlap                    -   -1.0396   -1.15252
    worst track penetration                   -   -1.0396   -0.38005
    worst marble-on-marble                    -   -         -0.23359

Track penetration improved by a factor of nearly three. **Travel per tick is now
49% over the budget `marble3d.config` sets for itself, against 7% in V1.9**, and
the actuator overlap is worse. Neither is traced to a site and neither shows as
a containment failure, but the travel figure is a real regression on a number
V1.9 had already flagged for attention before any V2. It may be the seed range
(2001–2600 here, against V1.9's own seeds) rather than the geometry; that has
not been separated and should not be assumed.

## Determinism, seed and video: not done

The benchmark names five candidates, best-scoring first:

    seed   score   lock     margin   lead changes
    2283   3.795   0.4971   0.0667   9
    2074   3.767   0.4800   0.0667   13
    2320   3.656   0.4933   0.3333   6
    2451   3.582   0.4842   0.1167   5
    2299   3.383   0.4850   0.0500   10

No seed is selected yet. V1.9's lesson is that the pick should be made on
**contact cleanliness rather than entertainment score** — it took 182 over the
higher-scoring 130 because 130 had four floating findings with a worst resting
gap of 0.3799 — and that validation has not been run on these five. The
determinism comparison (§20) and the replay render (§21) both wait on the pick.

## Tests

`tests/test_sloped_bank_slew.py`, 18 tests. The constraint on a synthetic run
(no edge rises, the sign flip is bounded, the extreme is never exceeded, the
window bounds what it touches); the pocket on the built run, before and after;
that the limit rejoins inside its window; that only leg2 carries one; and that
both trees hold the same table.

**The parity test is numeric, not textual.** The first version compared source
strings, which passes whenever two files share substrings and is not the same as
computing the same roll. `godot/scripts/sloped_slew_check.gd` now runs
`slewed_bank` headless and the test compares it against the Python: they agree
to **8.7e-07 degrees**, the GDScript's print precision. Verified to
discriminate — perturbing the margin by 0.1 shows as a 1.64° disagreement.

Full suite at the previous commit: 1599 passed, 1 skipped, 1 failed — the
pre-existing `test_neon_proof` missing-artifact failure, unrelated.

## Three unit and method errors this session made first

Recorded because each cost real time and each is the same shape as errors in
[`sloped_race_v19_production.md`](sloped_race_v19_production.md).

1. **A scan window too short to see the answer.** The first pocket measurement
   swept samples 94–109 and reported the hold as reducing the climb to 0.0146.
   Extended to 114 the same configuration reads 0.1849, because the hold had
   *moved* the pocket to sample 111 rather than removing it. The conclusion was
   written into code comments before the window was checked.
2. **A constraint on the magnitude where the sign mattered.** The first exact
   version bounded `abs(b)` rather than `sin(b)`, which permits the sign flip at
   sample 102 and lets the old low edge rise by the whole of it. It measured as
   changing the pocket by nothing at all, at every setting.
3. **A simulation-unit drop divided by a layout-unit half width**, which made
   the whole first margin sweep 1.754× too permissive and its recommended
   setting meaningless. The same mismatch then reappeared in the GDScript parity
   harness, where it showed as a 0.99° disagreement between two implementations
   that were in fact identical.
