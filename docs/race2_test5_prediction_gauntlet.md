# Race #2 — Test #5: PREDICTION GAUNTLET

**Status:** pre-production experiment contract  
**Branch:** `video-test5-prediction-gauntlet`  
**Base:** `main@65df08a3e22d692d2783ab6004ce6f3d4046f54e`  
**Previous release:** Race #2 V33.1 / Test #4, frozen and unchanged  
**Target:** an 18-second, six-racer vertical Short built around repeated prediction, readable surprise, and a late comeback.

---

## 1. Ownership and isolation

This video is **not** a Company OS / AI Company development job.

The Test #5 branch is a direct media-production branch. Company OS, delegation,
engineering-runner, token-efficiency, workforce, research-agent and autonomous
media-loop development continue separately and do not participate in designing,
implementing, reviewing, approving or routing this video.

This branch must not modify `company/`, `ai_platform/`, `intelligence/`,
`knowledge/company_os/` or `tools/engineering_runner/`.

Nothing in this experiment changes the frozen Test #4 release record.

---

## 2. Why Test #5 exists

Test #4 established a stronger opening and a readable shipped Race #2 product,
but the audience evidence indicates that the body of the race still loses
attention progressively.

The Test #5 hypothesis is:

> A viewer will stay longer when they choose one clearly trackable racer and
> repeatedly make a prediction that is challenged by visible, understandable
> physics before the result is known.

The objective is therefore **not** to add arbitrary activity. The race should
form a chain:

`choose -> predict -> obstacle state becomes readable -> outcome changes ->
reassess -> new threat -> comeback -> finish`.

A mechanism earns its place only if it changes the viewer's prediction or the
competitive state.

---

## 3. Experiment locks

### Changed for Test #5

- six racers instead of the current eight-racer Test #4 production setup;
- a new course identity rather than another SWITCHYARD wheel variation;
- new hero obstacle family;
- target runtime 18.0 s;
- denser consequential race-state changes;
- stronger midpoint uncertainty reset;
- deliberate late comeback opportunity;
- result-to-opening replay bridge;
- camera planned around continuous chosen-racer tracking and upcoming hazards.

### Locked unless measurement proves a blocker

- portrait 1080 x 1920 delivery;
- 60 fps;
- deterministic simulation/replay contract;
- physical cause-and-effect; no hidden winner scripting;
- no teleport cuts or fabricated race ordering;
- premium contained-stage visual language;
- racer-first visual hierarchy;
- phone-size readability requirement;
- existing V33.1/Test #4 remains untouched.

### Explicitly excluded

- Company OS participation;
- hidden random gates that choose outcomes independently of physics;
- forced winner manipulation;
- decorative motion with no race-state purpose;
- long countdown;
- generic like/subscribe card before payoff;
- large architecture rewrite;
- reusing four powered wheels as the main drama system.

---

## 4. Six-racer field

Initial field:

1. Blue
2. Orange
3. Yellow
4. Magenta
5. Violet
6. Lime

The exact material treatment is a later visual pass. The requirement is that
all six remain distinguishable at actual phone size and under the final
lighting/grade.

The production pipeline already accepts a marble count rather than requiring
eight at the simulation boundary, and the V33 bookend geometry was deliberately
written without depending on eight racers. Test #5 still requires a dedicated
six-racer regression because several historical release/QC tools and fixtures
are specific to Test #4's eight-racer artifacts.

---

## 5. Obstacle design rule

Every hero obstacle must pass all five questions:

1. **Readable state:** can the viewer see what the mechanism is about to do?
2. **Prediction:** can the viewer form a plausible expectation before contact?
3. **Non-monotone outcome:** can an early leader lose without arbitrary RNG?
4. **Cause:** after the event, is it obvious why the order changed?
5. **Beauty:** is the mechanism satisfying to watch even before knowing who wins?

The desired uncertainty is **deterministic but hard to forecast**, not hidden
randomness.

---

## 6. V0 course: PREDICTION GAUNTLET

The first physics prototype uses a **single continuous route**.

This is deliberate. Race #2's earlier Braid experiment showed that explicit
forks were expensive competitive drama: the two branches jammed frequently and
introduced route bias. A flip-flop diverter remains an R&D candidate, but it is
not the first Test #5 implementation.

### Hero A — Pendulum Cross

A large polished pendulum sweeps visibly across the racing line.

**Viewer question:** *Will my marble clear it before it comes back?*

Design intent:
- mechanism state visible before contact;
- leader can be punished by arrival phase;
- clean near-misses;
- one large silhouette rather than many small moving parts;
- contact changes momentum/order, never identifies a racer.

### Hero B — Memory Rocker

A broad balanced bridge or rocker rotates around a transverse pivot.

A marble entering the bridge shifts its angle; the changed angle then affects
the racers immediately behind it.

**Viewer question:** *Did the first marble just make this easier or worse for mine?*

This is the primary new mechanic because the obstacle carries **physical
memory**: one racer's interaction changes the state encountered by the next.
The state must arise from physics or a deterministic mechanical response to
load/contact, not from racer identity.

### Hero C — Fast Vortex

A shallow premium bowl/spiral recompresses the field and sends it toward one
clearly visible outlet.

**Viewer question:** *Who finds the inside line and escapes first?*

Constraints:
- target residence roughly 1.5-2.5 s, not a long decorative funnel;
- outlet visible or strongly implied;
- collisions/orbital lines may reorder the pack;
- no invisible suction or scripted exit order;
- containment and camera readability are mandatory.

### Hero D — Rising Floor Gate

A small set of large floor paddles / blockers rises and falls through the
single lane on a deterministic mechanical cycle.

**Viewer question:** *Which racer reaches the opening at the right instant?*

This must visually differ from SWITCHYARD's powered wheel family:
- no spinning-wheel silhouette;
- state read primarily as floor height/opening;
- few large moving pieces;
- synchronized mechanical motion;
- leader can be delayed while a following racer passes.

### Finish — Clean S Sprint

No new complex mechanic after the final gate.

The final section narrows the remaining contenders into a readable two- or
three-racer sprint through an S-shaped or gently converging channel.

The last seconds should answer only one question:

> **Who wins?**

---

## 7. Initial 18-second attention map

| Time | Race event | Viewer job |
|---|---|---|
| 0.00-0.55 | six racers visible, `PICK YOUR COLOR`; mechanism already alive | choose |
| 0.55-2.80 | release + Pendulum Cross | first prediction / first upset |
| 2.80-5.60 | Memory Rocker | understand state carried from racer to racer |
| 5.60-8.70 | Fast Vortex | recompress field; uncertainty reset |
| 8.70-11.80 | Rising Floor Gate | largest late-order reversal candidate |
| 11.80-15.90 | clean S sprint / closing battle | track contender and anticipate finish |
| 15.90-17.15 | winner crossing and run-out | payoff |
| 17.15-18.00 | minimal result + motion/audio bridge | replay without dead air |

These times are **prototype targets**, not editing cuts. The physical course
must be designed so the race naturally creates the sequence.

---

## 8. Competitive requirements

Before visual polish, a candidate seed/course must satisfy:

- 6/6 racers finish;
- no jam;
- no escape;
- no fixed start-slot advantage accepted without investigation;
- at least 3 meaningful lead/order changes;
- at least one leader-punishing event;
- at least one credible last-half comeback;
- no long section whose only event is travel;
- final winner not obvious too early;
- final 3-4 s remain competitive;
- obstacle outcomes come from physics/mechanical phase, not racer-specific code.

The intended hero replay should preferably contain an easy-to-understand
comeback story such as `6TH -> 1ST`, but **the winner and exact comeback are
not authored in advance**.

---

## 9. Visual rules

- Racers remain the most saturated/important objects.
- Machinery is premium neutral metal/ceramic/dark material with restrained
  architectural accent light.
- Each hero obstacle gets one unmistakable silhouette.
- Motion hierarchy: racers and the currently relevant obstacle dominate.
- Decorative background animation may not compete with the race.
- The next hazard should usually be visible before contact.
- All approval stills and motion reviews must be checked at phone size.

---

## 10. Camera rules

- Follow the competitive pack, not only the leader.
- Preserve the chosen-racer tracking task.
- Keep most/all racers recoverable quickly after every obstacle.
- Frame slightly ahead of motion so the next hazard can be predicted.
- Camera changes happen because the competitive event changes, not for variety.
- Preserve screen-direction grammar.
- No shot may hide the physical cause of a major rank change.
- The final sprint uses the simplest camera language in the film.

---

## 11. Audio rules

Sound is event feedback, not constant stimulation.

Initial grammar:

- release: mechanical clack/drop;
- pendulum: low swing + contact tick only when meaningful;
- rocker: tactile pivot/weight thunk;
- vortex: restrained rolling/orbital texture;
- floor gate: mechanical rise/drop snap;
- major pass: subtle accent;
- finish: one short, clear payoff cue.

Music/bed must remain subordinate to physical cause-and-effect.

---

## 12. Prototype order

### P0 — mechanism feasibility

Build ugly/no-art deterministic prototypes for:
1. Pendulum Cross;
2. Memory Rocker;
3. Fast Vortex;
4. Rising Floor Gate.

Measure finish rate, jams/escapes, mechanism events and order effects.

Do **not** build final environment, final camera or final audio here.

### P1 — course composition

Place only mechanisms that survived P0 into one continuous 18-second-scale
course. Tune travel length and slopes for event density, not visual scenery.

### P2 — seed/course evaluation

Run a multi-seed benchmark. Select a mechanically valid hero replay only after
the course itself is accepted.

### P3 — camera/readability

Develop pack tracking and obstacle anticipation on the accepted replay.

### P4 — visual system

Polish obstacle silhouettes, materials, lighting and environment while
protecting phone readability.

### P5 — audio/edit/loop

Add sparse synchronized audio, hook/result text and replay bridge.

### P6 — QC and upload candidate

Validate delivery, mobile viewing, physical continuity, finish/run-out,
readability and the experiment metadata.

---

## 13. Kill / redesign conditions

Redesign an obstacle rather than polishing it when any of these occur:

- repeated jam/escape behavior;
- obstacle is visually unpredictable because its state is hidden;
- outcome is effectively identical to input order;
- obstacle produces chaos with no understandable cause;
- a chosen marble is routinely lost behind the mechanism;
- the mechanism needs racer-specific assistance;
- it creates more than roughly 3 s of low-information waiting;
- visual complexity exceeds the racers' salience;
- six-racer conversion requires destabilizing frozen Test #4 behavior.

A mechanism can be removed. Test #5 does not need four hero obstacles if three
produce a stronger 18-second race.

---

## 14. Test #5 audience targets

Historical Test #4 baseline from the research review:

- Stayed to watch: ~48%;
- AVD: ~14 s on ~20 s;
- average viewed: ~70%.

Initial Test #5 success targets:

- Stayed to watch: **>=55%**;
- average viewed: **>=85%**;
- AVD: **>=15.3 s on 18 s**.

Strong result:

- Stayed: **58-60%+**;
- average viewed: **95%+**;
- AVD: **17.1 s+**.

These are evaluation thresholds, not physics tuning targets. The simulator must
not be manipulated to manufacture the analytics hypothesis.

---

## 15. First engineering action

The next code change should be **P0 mechanism prototypes only**.

Start with **Pendulum Cross** and **Memory Rocker**, because together they test
the two most important new ideas with the smallest conceptual overlap:

- arrival-phase prediction;
- persistent mechanical state caused by earlier racers.

Do not touch final camera, stage art or audio until both mechanisms have
measured competitive value.
