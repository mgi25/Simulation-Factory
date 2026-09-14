# V24: a payoff a stranger can read

*Lab branch `v24-payoff-lab`, off `origin/main` at `e697a12`. Nothing here is
merged and nothing here re-simulates: every proof is the delivered V22.1
master, frame for frame, with a card composited on top.*

---

## The short version

The brief asks for a stronger answer to **"did my colour win?"**, and it is
right that `FROM 6TH -> 1ST` is not one. But the wording turns out to be the
smaller half of the problem.

**The winner is not on screen when either of V22.1's winner marks is.**

Measured on the delivered master, looking for the racer's own hue in the pixels
rather than trusting the projection:

| window | seconds | winner |
| --- | --- | --- |
| 22.900 – 23.100 | 0.217 | **visible** — the crossing |
| 23.117 – 24.500 | 1.400 | hidden behind the finish gantry's rail |
| 24.517 – 25.667 | 1.167 | **visible** — back out, parked on the deck |
| 25.683 – 26.517 | 0.850 | hidden behind the FINISH sign |

Against that, what the film currently does:

| mark | runs | on a visible winner |
| --- | --- | --- |
| V22.1 winner ring | 23.100 – 23.800 | **0.017 s** of 0.700 |
| V22.1 end fact | 25.883 – 26.533 | **0.000 s** of 0.650 |

So the shipped ring spends 0.683 s drawing a gold circle and the word WINNER on
a rail with nothing inside it — and the nearest racer to it is the **emerald
that came second**. `ring_compare.png` is that frame beside the fix.

And the end card names the winner with a 27 px purple dot at a moment when
purple is not in the picture. Two other racers *are*: measured, **candy red**
crosses the card's own glyph band on 7 of its 40 frames and **warm yellow** on
9. In the delivered film there is a red ball sitting inside the payoff line,
two centimetres from the purple dot that is supposed to be the answer.

That is the mechanism. Both marks point at the winner while the winner is
behind a rail, and one of them has a different colour parked in the sentence.

---

## 1. The winner, and its name

**The winner is `PURPLE`. It is not red.**

Seed 5432's finish order is `5, 2, 7, 4, 1, 6, 3, 0`, reproduced twice:

* by re-running the race on `sloped_course(routes="both")`;
* by reading the `finish_line` events out of the locked `race_5432.json`.

Both say marble **5**, crossing at replay 20.85 — film second **22.900**.

| | |
| --- | --- |
| racer | 5 |
| hue | `#8E3FD4` = `(142, 63, 212)` |
| hue angle | 271.8° |
| label | **PURPLE** |
| from | **6TH** (`winner_worst_rank` = 6, held at the descent, mixed and quarter marks) |

**`routes` is not a detail.** `run_race(seed=5432)` on the *default* machine
puts all eight racers down the blue route and returns a different winner
altogether — marble 7, at 19.65 — because the default course has no fork in it.
The film's course does. A winner read off the wrong machine is the whole card
wrong, so `WINNER_INDEX` is pinned and tested against the shipped replay.

`COLOUR_NAMES` gives every racer a one-word human label, so a different seed
names its own winner instead of falling back on a guess. Each name is tested
against the hue angle it is allowed to sit in, so a palette edit that slid a
racer out of its own name fails loudly rather than shipping a card that says
BLUE over a green ball. Purple's nearest neighbours are cobalt at 219.2° and
pink at 332.9° — 52.6° and 61.1° clear.

---

## 2. Where the card can go

The shipped `end_fact` baseline of **1395** was measured on V19/V21's finish
lens and was never re-measured for this edit. V22.1 parks the camera *behind*
the line instead, so the approach channel — and the three racers still coming
down it — runs straight through that band. That is why red and yellow are in
the sentence.

Re-measured on the real tail: every second frame from 23.900 to the last, the
**maximum** luma of each row across the text corridor. The tallest run of rows
whose maximum never exceeds 130:

```
y 297 .. 548,  252 px,  peak luma 129.9
```

It is the dark shoulder of the backdrop between the pale mountain above and the
machine's gold top rail below, and it is clear of **all eight racers** for the
whole window: the settled field sits at y 670–900 and the arrivals sweep down
the middle below that. `PAYOFF_BAND` is derived by `--stage band`, not typed.

---

## 3. Luma carries the words, hue carries the colour

On that band the winner's own hue cannot be used for letterforms at all:

| | worst pixel | band mean |
| --- | --- | --- |
| warm white | 3.82:1 | 7.11:1 |
| `#8E3FD4` | **1.38:1** | **1.35:1** |
| `#8E3FD4` lifted 75% toward white | 2.65:1 | — and no longer purple |

Purple's relative luminance is 90.6 and the band's mean is 85. They are the
same *value*; a purple word there is invisible.

But the same purple as an **area** is unmistakable — against the backdrop
actually behind the card it is **ΔE 90.8, of which 89.8 is chroma**. Hue
separation is enormous exactly where luma separation is nil.

> **The rule: luma carries the words, hue carries the colour. Never ask one
> mark to do both.**

This is also why `end_fact`'s instinct — a ball of the racer's unmodified hue —
was right, and only its placement and size were wrong.

---

## 4. The three variants

All three carry the same two facts and differ only in **how the colour gets
in**. All three fit the band and hold a ~98 px gutter each side.

### A — `tint`: the colour word set in the colour

```
PURPLE WINS
6TH → 1ST
```

The obvious design, and the table above says it is the weak one. To reach even
2.26:1 the hue has to be lifted 65% toward white, at which point `#8E3FD4` is
`(215, 184, 229)` and reads as pale lilac rather than as the ball the viewer
was watching. Built anyway, because "set the word in the colour" is the first
thing anyone asks for and it is worth being able to look at the answer.

### B — `chip`: the ball stated, the words left alone

```
● PURPLE WINS
FROM 6TH → 1ST
```

`end_fact`'s instinct, moved somewhere it works and given a name beside it. The
ball is the racer's exact hue, 75 px across, and it is the leftmost thing on
the card so the colour is read before the word is.

### C — `plate`: the word reversed out of the colour  ← **recommended**

```
[ PURPLE ] WINS
6TH → 1ST
```

The lozenge is the racer's **exact** hue — no lift, no tint — so the sample the
viewer matches against their marble is the marble's own value. Warm white on it
is **5.26:1 whatever is behind the card**, because the background is no longer
in the comparison. `WINS` sits outside the plate so the colour reads as the
subject and the verb is not competing with it.

### Measured

| style | text contrast | on real frames (worst / median) | colour area |
| --- | --- | --- | --- |
| `tint` | 3.82:1 | 4.52:1 / 8.75:1 | 17 798 px |
| `chip` | 3.82:1 | 4.61:1 / 9.64:1 | 3 167 px |
| **`plate`** | **5.26:1** | 4.61:1 / 8.67:1 | **56 088 px** |
| *V22.1 `end_fact`* | — | — | *1 614 px* |

`plate` states the winner's colour in **35× the area** the shipped card does.

The "on real frames" column is measured, not tabulated: the card's warm-white
ink against the composited pixel beside it, at a 7 px standoff so the
measurement steps over the glyph's own antialiasing. All three clear 4.5:1 at
their worst point.

---

## 5. Recommended layout

**`plate`.** It is the only one of the three whose text contrast does not
depend on what the camera happens to be pointing at, and it gives the colour
the largest area — which is the thing the brief is actually asking for when it
says the payoff is not explicit enough.

```
            ┌──────────┐
            │  PURPLE  │  WINS
            └──────────┘
              6TH → 1ST
```

* headline fitted to a 98 px gutter and capped so the lozenge cannot leave the
  band — a short name like `RED` fits *wider* and so sets *larger*, which
  pushed the plate 13 px out of the top before the height cap was added;
* the fact line is capped at 0.60 of the headline, so the result is the payoff
  and the starting place is the setup. This is `overlays.end_fact`'s own V21
  hierarchy finding, reapplied;
* two shadow passes, wide-and-weak then tight-and-strong, built from a **mask**
  rather than by blurring a coloured layer — the per-channel trap `end_fact`
  documents.

---

## 6. Timing

```
22.900   winner crosses            ring opens ON the crossing
23.200   ring out
23.900   PURPLE WINS card up       ← crossing + 1.0 s
24.517   winner comes back out onto the deck, under the card
25.667   winner hidden again
25.700   card out
```

**The ring had to move.** The winner is on screen for 0.217 s and V22.1 opens
its ring 0.200 s *after* the crossing, so one frame of it has a subject. The
ring now opens on the crossing and runs 0.300 s: **0.217 s of it has a visible
marble, against 0.017 s**. Cutting it to the visible window exactly would be 13
frames, too short for `winner_ring`'s envelope to read as a pulse rather than a
blink — and the tail matters least, because the glow and the flash are both in
the first fifth, where the marble certainly is.

**The card cannot point at the winner, and that is why it names it.** Every
beat in the brief's 0.8–1.5 s band falls inside the 1.400 s the gantry has the
marble. That is not a reason to move the card — it is the reason the card says
the word.

**What the 1.0 s beat buys** is that the card is still up when the winner walks
back out at 24.517. Measured: **1.15 s of the card runs over a visible
winner.** The card names the colour while the ball is hidden, and the ball then
returns to the picture underneath a line that has already said PURPLE. That is
the payoff completing, and it is visible in `proof_plate_24900.png`.

The brief's whole 0.8–1.5 s band is accepted by `schedule()`; 1.0 s is the
recommendation. Anything outside it raises. Every cue is snapped to a whole
frame, for the reason `sloped_short` snaps its ring: an ffmpeg offset that is
not a whole tick lands between two frames and the first one is never
composited.

**For Session B:** the card needs **1.8 s** to reach the reunion at 24.517. If
the tail is cut shorter than that, the card still reads — it is self-sufficient
by construction — but it loses the moment where the colour and the ball meet.
The shortest cut that keeps it is **crossing + 1.0 + 0.7 = 24.600**; below
that, prefer shortening the beat to 0.8 s over shortening the card.

---

## 7. Phone proof

Reviewed at **270×480** — `phone_row.png` is the three side by side at that
size, and `phone_plate_23900.png` / `phone_plate_24900.png` are the recommended
one at both beats.

* the headline type is **20 px of cap height** in a 480 px frame (4.2%), and
  the headline's whole band stands **43 px** for `plate`. The suite asserts a
  floor on that rather than leaving it to the eye;
* the comeback fact sets at 0.60 of the headline in every style — 12.0 px of
  cap height on the phone for `plate`, 11.3 px for `chip`;
* `6TH → 1ST` is preferred over `FROM 6TH → 1ST`, and **not** because the
  longer one does not fit: at the same size it is 607 px of the 888 px line and
  fits comfortably. Dropping `FROM` is an economy — 38% less line for the same
  information, so the fact is taken in at a glance rather than read.
* the arrow is **drawn, not typed**. A reported glyph for U+2192 is not proof
  it is an arrow rather than the missing-character box, and the middle of the
  payoff is the worst place in the film to find that out.

At phone size the confusion risk the brief names is real and visible: at 23.900
the only marble on the deck is **pink**, the third-place racer. With `plate`
the purple lozenge is the most saturated thing in frame and wins the match;
with `tint` the pale lilac word loses it to the pink ball. That comparison is
the clearest argument for the recommendation.

---

## 8. Overlay compatibility

**No production overlay file is modified.** `sloped/overlays.py` is untouched;
`v24_payoff` imports from it and reuses `load_font`, `MARBLE_HUES`,
`WARM_WHITE`, `GRAPHITE` and `winner_ring` unchanged.

* **`winner_ring` is retained as-is** — only its *schedule* changes, and that
  is a constant in `v24_payoff`, not an edit to the ring;
* **`end_fact` is replaced, not extended.** Keeping both would put two payoffs
  in the last three seconds;
* **`pick_one` is untouched** — it is at the other end of the film.

Integration is two constants and one call, and the ring move is the part with
the measurable win.

---

## 9. Audio

**Recommend: one winner accent, nothing else.** Synthesized-only policy
unchanged; no audio was redesigned in this lab.

* the crossing cue already exists and already lands on the crossing;
* the **ring now moves onto that same frame**, so the existing cue and the
  visual mark become synchronous for the first time — that is free, and it is
  the single biggest audio improvement available here;
* a short accent on the **card's** entry at 23.900 would help mark it, but it
  must be an accent and not a sting: a sting reads as an outro and the film
  still has five racers to land;
* **no payoff sting.** The film ends on the machine, not on a button.

---

## 10. Tests

`tests/test_sloped_v24_payoff.py` — **32 passing.**

* the winner is marble 5, is `PURPLE`, and is **not** red — checked against the
  shipped replay's own finish events, skipped cleanly if the replay is absent;
* every colour name is checked against the hue angle it is allowed to occupy;
* `MARBLE_HUES` is still `lab_palette.MARBLE_COLOURS`;
* every style stays inside `PAYOFF_BAND` and inside the gutter — **for all
  eight possible winners**, which is the test that caught the short-name fit
  bug;
* the winner's hue fails contrast on the band and warm-white-on-hue passes, so
  the finding the design rests on cannot silently stop being true;
* the ring lands inside a winner-visible window; the card overlaps the second
  one; the whole 0.8–1.5 s band is accepted and anything outside it raises;
* every cue is on a whole frame;
* a guard on the *instrument*: a bright frame and a dark frame must not score
  alike. Three earlier versions of `measured_contrast` reported the same number
  for every frame because each was measuring the card against itself — once
  against its own drop shadow, once against its own antialiasing.

---

## 11. Integration instructions

Nothing is merged. To take this into a Short:

1. **Schedule.** `v24_payoff.schedule()` returns the ring and card spans in
   finished-film seconds, already frame-snapped. Feed `ring` to the existing
   `stage_overlays` ring loop in place of `WINNER_DELAY` / `WINNER_SECONDS`,
   and `card` to the `enable='between(t,...)'` the fact currently uses.
2. **Card.** `v24_payoff.build("plate").image` — a 1080×1920 RGBA, composited
   the same way `end_fact` is. Read the winner from the replay
   (`_winner_of`) and pass it, rather than the default, so a re-seed re-names
   itself.
3. **Drop `end_fact`** from the edition. Do not run both.
4. **Re-measure `WINNER_VISIBLE` if the finish camera moves.** It is the one
   constant here that is a property of *that* camera rig against *that*
   gantry. `--stage visibility` regenerates it in one pass; the numbers in
   `winner_visibility.json` are the current rig's.

### Reproducing

```bash
python tools/sloped_v24_payoff.py --stage all \
    --film ../Simulation\ Factory/exports/v221_integration/real_race_v221_master.mp4
```

Stages: `winner`, `visibility`, `band`, `cards`, `proof`, `ring`, `compare`.
The camera track is built once with
`v221.build_race_track(replay, sloped_course(routes="both"))`; the tool prints
the exact command if it is missing.

---

## Open questions for review

1. **`plate` versus `chip`** is the only real choice here. `plate` is stronger
   and `chip` is closer to the film's existing idiom. I recommend `plate`, but
   `chip` is the conservative pick if the lozenge reads as too much interface
   for a machine that has deliberately had no HUD for four versions.
2. **The gantry occlusion is a camera problem, not an overlay one.** This pass
   works around it. A finish lens that kept the winner in view for the second
   after it crossed would be worth more than any card, and that is a V22.1
   `FINISH` candidate question rather than a V24 one.
3. **The `FROM` wording** was dropped from the recommended variant for speed
   of reading, not because it does not fit — it does, at the same size, using
   607 px of the 888 px line. `chip` keeps it, so both are on the sheet.
