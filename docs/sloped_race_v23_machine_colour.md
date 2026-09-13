# V23 — the machine's colour, and what a zone is allowed to cost

V21 asked whether the sloped race's picture was *readable* and fixed a machine
that was rendering as paper. V22 and V22.1 asked whether it was *edited* and
fixed the joins. Neither asked what the machine is **made of**, and this pass
does, on one question:

> Can the machine read as a premium toy product, colour-zoned by race section,
> without costing a single marble its silhouette?

Nothing about the race changed to find out. Seed 5432, the physics, the route
geometry, the replay, the camera track, the cut list, the omission, the
lighting rig, the environment, the grade, the country skins, the overlays and
the audio are all the ones V22.1 shipped, and **the control column of every
comparison below is byte-identical to a render taken before this branch
existed** — thirteen frames of thirteen, by SHA-256.

This is a lab. Nothing is integrated, nothing is merged, and no scene turns a
pass on by default.

| What | Where |
| --- | --- |
| Control beside the recommendation, one per moment | `docs/validation/sloped_race_v1/v23_machine/pair_*.png` |
| All four variants at one moment | `docs/validation/sloped_race_v1/v23_machine/zone_*.png` |
| Everything, small | `docs/validation/sloped_race_v1/v23_machine/contact.png` |
| Phone-size review | `.../v23_machine/phone.png`, `phone_b.png` |
| The racer rings the measurement uses | `.../v23_machine/detection.png` |
| The numbers | `.../v23_machine/measurements.md`, `measurements.json` |
| Moving proofs | `output/sloped_race_v1/v23/proofs/v23_{mixer,finish}_{pair,b}.mp4` |
| The same four, kept where a worktree removal cannot take them | `exports/v23_machine_colour/` |

`output/` and `*.mp4` are both gitignored, so the clips are not in the
branch; `exports/v23_machine_colour/` is the copy to watch, and it carries
the two phone sheets, the contact sheet and the numbers beside them.

---

## How to run

```bash
$env:GODOT_BIN = "...\Godot_v4.7.2-stable_win64_console.exe"
python tools/sloped_v23_machine.py all
```

`render` takes four builds of one scene through two camera tracks — 52 frames,
about 25 seconds on a 3050 — and `sheets`, `detection` and `measure` need no
Godot at all. The three inputs (`race_5432.json`, `cameras_v221_5432.json`,
`preview_v221_5432.json`, `start_contract_5432.json`) are outputs and are not in
the branch; the tool says so by name if one is missing.

---

## What the shipped machine actually is

Four things, measured on the thirteen frames rather than remembered:

**It is warm-neutral, and so is its sky.** The pearl family is cream — 
`pearl_shell` is `#CCC8BF`, R thirteen points over B — and the environment behind
it is a warm orange wedge that fills the top third of most cuts. The largest
object in frame shares a temperature with its own background, which is the
cheapest separation in the medium being left on the table.

**Its zone story is told in 6 cm of strip.** `course_machine.EDGE_LIGHTS` is a
real design and it is correct: cyan off the line, cyan through both first legs,
violet on the approach to the choice, the two route identities at the choice,
gold from the merge to the flag. But four of those five zones have the *same
cream body*, and at 270 px wide an emissive rim is a bright line, not a colour.
The field mean of the machine moves 10.4 ΔE across all five zones, which is
about one JND per zone pair.

**Orange means three different things.** `orange_machine` is asked for by the
orange route's shell, by the start rotor's blades and by the obstacle's sweep.
The measured consequence is in the accent table: on the shipped machine the
**mixer's strongest colour is 13.4 from the finish's and 37.8 from the split's**
— the three most distinct moments in the film are, in accent terms, neighbours.
A viewer at the mixer and a viewer at the fork are looking at the same orange.

**Its brightest surface is the one the racers have to beat.** 5.5% of the
machine's own pixels sit at or above 250 in a channel. Across the thirteen
frames a racer is 22 to 84 px across at 1080x1920 and a median of 54.6 - which
at the 270 px the Short is actually watched at is **5.5 to 21 px, median 13.6**.
That is the size the whole readability question is about.

---

## The three passes

`lab_palette.MACHINE_PASSES` is the whole of it — a second override layer
applied *after* the V21 retune and gated on its own flag, `--machine=`.

**A — subtle premium (`v23a`).** The temperature correction and two hue
corrections, and nothing else. The pearl family flips cool at constant
luminance (within 1% on every key, asserted). The rotor goes light lilac. The
split's own wedge line goes amber. Gold's specular comes up a hair. No
structure change, no route change, no body-value change.

**B — balanced signature (`v23b`), recommended.** The designed system.
Everything A does, plus: the body drops half a step so an eight-pixel racer has
somewhere to be bright while the lip caps stay up, so the track keeps its drawn
line; the running surface darkens and gains metal, so it reflects the zone it is
in instead of painting every zone the same pale grey; the structure deepens and
cools, which is the only version of "dark environment, bright machine"
available to a pass that is not allowed to touch the sky; the mixing chamber
becomes a violet room with lilac blades; the sweep drops half a step under the
split's orange so the choice is the brightest warm thing in the film; and the
finish's payoff is bought entirely from the body — see below.

**C — bold showcase (`v23c`).** B with the value range and the edge-light
energy pushed past where V21 left them. This is the upper bound the comparison
needs, not a candidate: it is the only variant that raises the two longest zone
lines, and it is the only one that measurably over-glows.

### The one rule all three keep

**A machine pass says what colour a surface is. It does not say how that
surface answers a light.** `roughness`, `clearcoat` and `clearcoat_roughness`
are V21's decisions; a pass sets `albedo`, `emission`, `metallic`/`specular`
and emissive `energy`. The two keys being *repainted* rather than recoloured —
`rotor_machine` and `hazard_machine` — may state their own gloss, and nothing
else may. `tests/test_sloped_v23_machine.py` asserts it key by key.

This is a correction, not tidiness. The first build of `v23b` also tightened
the track lip from roughness 0.29/clearcoat 0.58 to 0.27/0.64 — a rim highlight
sharpened along every metre of a 237-unit course — and it put clipping back on
frames V21 had cleaned. A colour pass that also re-narrows specular lobes is a
second readability pass wearing a palette's name, and it will undo the first one
somewhere nobody is looking.

### The three alias keys

`rotor_machine` and `hazard_machine` are built from `orange_machine`'s own three
numbers and carry `orange_machine`'s own V21 row; `acrylic_drum` is built from
`acrylic_guard`'s and carries its row. With no pass on they are the same
materials, which is how the control stays byte-identical. They exist because a
zone language cannot separate the mixer from the route while the mixer *is* the
route's key.

---

## How it is gated

`--machine=` is the only thing that turns any of it on, and **no scene sets a
default** — unlike `--contrast`, which `sloped_race_scene.gd` defaults to `v21`
because V21 was accepted. A colour language is a proposal until it is chosen.

Checked, not intended: rendering the thirteen frames with no `--machine=` flag
produces frames **byte-identical to the pre-branch renders, thirteen of
thirteen by SHA-256**, and that was re-verified after the last palette edit.

---

## What is measured, and why those things

`tools/sloped_v23_machine.py` has the long version. Four things matter:

**The reachable set.** A whole-frame clipping figure on these cuts is dominated
by the sky, which no machine pass touches: 6.56% of the shipped frame is clipped
and about five of those six points are environment. So every machine statistic
is taken over **the pixels a pass can move at all** — those that differ by more
than 3/255 between the control and the loudest variant — computed once per
moment and shared by all four columns, so no variant is judged over a footprint
of its own choosing. It averages 28.4% of a frame and it *includes the glow each
emissive spills*, which is precisely what an over-glow measure should count.

**Racers are projected, not detected.** A racer's disc is `presentation.project`
applied to the replay's own position through the camera track's own pose — the
projection the renderer used. A detector would have had to be trusted not to
answer differently under the colours it was measuring. `detection.png` is the
rings drawn on the control frames, and every one of them sits on a marble.
`marble dL*` is the lightness step from a racer to an annulus of machine 1.9 to
3.2 radii out, median and tenth percentile over 76 racer-instances - the
racers on screen at the thirteen moments, which is eight at eight of them and
fewer as the field strings out towards the flag.

**Zones are measured twice, because one measure lies.** The *field mean* is the
machine's mean a\*b\* over the reachable set; the *accent* is the mean a\*b\* of
its top decile by chroma. A viewer reads the field and looks at the salient
thing, and neither number is the whole answer — the field mean cannot see a
rotor that is 5% of the pixels, and the accent cannot see that the other 95%
went silver.

**Lightness is dropped from both.** A zone language is a claim about hue and
saturation. Including L\* would score "this zone is brighter" as zone identity,
and brightness is the lighting rig's to decide, not this pass's.

---

## Results

| | shipped | A | **B** | C |
| --- | --- | --- | --- | --- |
| machine mean L\* | 55.8 | 55.9 | **53.3** | 51.9 |
| machine 99th pct L\* | 96.1 | 95.9 | **95.7** | 96.4 |
| machine clipped % | 5.49 | 5.25 | **4.98** | 6.23 |
| zone spread ΔE, field | 10.4 | 11.4 | **12.3** | 13.4 |
| zone spread ΔE, accent | 40.9 | 49.8 | **52.5** | 54.0 |
| marble ΔL\* median | 10.4 | 10.5 | **10.8** | 11.7 |
| marble ΔL\* p10 | 4.4 | 4.5 | **4.4** | 4.9 |
| marble ΔE median | 56.5 | 56.6 | **56.5** | 57.0 |
| achromatic % of lit | 4.4 | 4.4 | **3.6** | 3.5 |
| warm % | 34.6 | 34.1 | **34.5** | 34.6 |
| whole frame clipped % | 6.56 | 6.49 | **6.37** | 6.78 |

B is better than the shipped machine on every axis it was built to move and
worse on none of them. It clips **9% less** of its own machine while carrying
more colour, its zones are 18% further apart in the field and 28% in the accent,
and the racers are not paying for it: the median step from a marble to the
machine around it goes *up* 0.4 L\*, and the tenth percentile — the marble that
is hardest to see — does not move.

C buys another 3% of accent spread for 25% more clipping. That trade is the
reason it is the upper bound and not the recommendation.

---

## The four findings

### 1. The shipped machine's mixer is orange, and orange already means "choice"

This is the largest measured effect in the pass and the one that justifies a new
palette key. On the shipped machine the mixer's strongest accent is **13.4 from
the finish's and 37.8 from the split's**; under B it is **73.0 and 92.2**. The
gain is not from adding violet — it is from *removing a collision*. Three of the
film's most distinct moments were painted from one pot.

### 2. A violet rotor collides with the purple racer, and value is the way out

The first render of this pass painted the blades `#8E63D8`. The field's purple
is `#8E3FD4`: same hue family, same value, and the blades are the largest thing
in the mixer's frame. A racer against a wall of itself is the exact failure the
brief names, and it is invisible in a summary statistic because the median
marble was fine.

The fix is not less violet, it is *lighter* violet. The blades are `#B69FEA`, a
light lilac 2.9× the racer's luminance, and the zone's violet *energy* comes
from the drum tint and the crown line, which no marble is ever in front of.
`test_the_rotor_stays_clear_of_the_purple_racer` holds the floor at 2.5×.

### 3. Per-channel clipping is a saturation measure as much as a brightness one

`blue_machine` from `#2A83C6` to `#2380CC` is a *darker* blue — luminance down —
and by itself it put **0.29 of a point of extra clipping on the merge frame**,
more than any other row in B's table, found by rebuilding B thirteen times with
one row each. The clip test is `max channel ≥ 250`, and that blue bought its
chroma by raising the channel the test looks at.

The rule that follows: **saturate downwards.** Both route bodies now gain chroma
by pulling their other two channels down, and their dominant channel never
moves. The whole regression went away.

### 4. Cooling every neutral costs the cool zones their differences from each other

The honest one. Under B the three cool zones converge in field mean:
`mixer vs descent` falls from 5.9 to 1.1 and `start vs descent` from 2.7 to 0.9.
On the accent measure `mixer vs descent` falls from 44.4 to 4.7.

Two things are true about it. The separation that was lost was **bought with the
collision in finding 1** — the shipped machine told the mixer from the descent
by putting the split's orange in it. And the start pan and the mixing drum are
*one module*, in frame together in every start cut, so a hard cyan/violet border
between "start" and "mixer" is not a thing the geometry can carry; `start vs
mixer` at 9.2 accent ΔE is close to the most those two can honestly be.

What remains genuinely weaker is `mixer vs descent`, and the lever that fixed it
as far as it goes was the drum tint: `#AEB2F2` to `#B78FF2` moved that pair from
3.1 to 4.7 and `start vs mixer` from 6.6 to 9.2 at no cost in clipping. Going
further would mean tinting the pan lines or the chamber kerb, and both are keys
the whole course shares.

---

## Recommendation

**B — `v23b`, balanced signature.**

It is the only variant that improves clipping, zone separation, marble contrast
and achromatic share at once. A is safe and does too little: at phone size the
temperature flip alone is hard to see, and its zone accent gain comes almost
entirely from the rotor. C is a real look and a real risk — it is the only
variant that raises the two longest edge lights, and 6.23% machine clipping is
above where V21 left the shipped machine.

Where B shows best, in order: **the finish** (the checker stops blowing out and
reads as a checker again — machine clipping 6.83 → 5.39 at the winner and
6.72 → 4.74 at the final), **the mixer** (a violet room instead of an orange one,
and 3.64% → 0.90% clipping because the shipped orange blades were the thing
clipping), and **the start gate** (1.41% → 0.43%).

---

## Risks and what is not fixed

**Three frames of thirteen clip more under B.** `merge` 8.18 → 10.41, `branch`
6.18 → 7.49, `obstacle` 5.42 → 6.27, on the masked measure. The net across all
thirteen is −0.51 and the whole-frame net is −0.19, but the merge is a real
regression and it was not traced to any single row — rebuilding B one row at a
time put every remaining candidate under 0.02 points. The merge's machine is
almost entirely rim-lit strip already sitting at 240-249, and on that frame any
small brightening anywhere pushes some of it over.

**The environment is still the brighter half of the frame.** The brief's "dark
environment, bright premium machine" is only half available here: the sky wedge
is the environment's and a machine pass may not touch it. B does the machine's
half — the structure deepens, the body comes down — but a frame whose top third
is a lit orange cliff will keep reading as a bright background. That is a
question for `v23-environment-direction`, not for this branch, and the two
passes are orthogonal by construction: this one names no environment key and
`tests` asserts it.

**Nothing here is measured in motion.** Every statistic is on thirteen stills.
The two proof clips exist for exactly this reason and they are the thing to
watch before accepting: the mixer's blades and the finish's checker are the two
surfaces whose behaviour under motion a still cannot show.

**The obstacle is not one of the brief's zones and has been given a colour
anyway.** `hazard_machine` at `#C2702F` is a judgement: the sweep reads as the
split's warning shot rather than as a second choice. If that reads wrong, the
key exists and one row changes it.

---

## Integration notes

Nothing in this branch is on. To ship B:

1. `sloped_race_scene.gd` grows a `DEFAULT_MACHINE := "v23b"` beside its
   `DEFAULT_CONTRAST := "v21"`, set before `super()` for the same reason —
   the palette is built inside it. That is the whole switch;
   `test_only_the_command_line_turns_a_pass_on` is the test that then has to
   change, deliberately.
2. Every committed proof of every earlier lab keeps reproducing either way: no
   other scene constructs a palette with a machine pass, and the aliases build
   identically without one.
3. The three alias call-sites in `course_modules.gd` are already in place and
   are inert until a pass names them.
4. Re-render the master and the preview and re-run `tools/sloped_short_qc.py`.
   **The pass changes the picture's luma, so the Short's own contrast gates and
   any duplicate-frame check that uses mean luma have to be re-read, not
   assumed.** Machine mean L\* moves 55.8 → 53.3.
5. The audio, the overlays and the country skins are untouched and stay so —
   but the overlay legibility gates run against a picture that is now half a
   step darker under the text, which is a *help* and should be confirmed rather
   than assumed.

---

## Reproducing

```bash
$env:GODOT_BIN = "...\Godot_v4.7.2-stable_win64_console.exe"

# the four columns, the sheets, the rings and the numbers
python tools/sloped_v23_machine.py all

# one column on its own
python tools/sloped_v23_machine.py render --only v23b

# the gate: render with no pass and compare to a pre-branch render
& $env:GODOT_BIN --path godot res://scenes/SlopedRaceRender.tscn -- `
    --out-dir=<abs>/output/sloped_race_v1/v23/control/race `
    --replay=<abs>/output/sloped_race_v1/race_5432.json `
    --cameras=<abs>/output/sloped_race_v1/cameras_v221_5432.json `
    --start-contract=<abs>/output/sloped_race_v1/start_contract_5432.json `
    --at=1.0,3.35,4.35,6.05,10.25,13.75,15.45,16.55,18.85,20.35 `
    --width=1080 --height=1920 --layout=b --detail=hero

python -m pytest tests/test_sloped_v23_machine.py tests/test_sloped_contrast.py
```

The thirteen output seconds and the replay instants they land on are printed by
the renderer as it goes; `tools/sloped_v23_machine.MOMENTS` is the list and the
name each one goes by.
