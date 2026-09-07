# The sloped race, V1.3

Two deliberate corrections were asked for. One is a large advance and still not
production; the other was built, measured and falsified. Both are reported with
their mechanism rather than their intention.

`docs/sloped_race_v13_basin.md` is the basin's full account.
`docs/sloped_race_v12_findings.md` is the previous session's, and its two
mechanisms both survived this one.

---

## 1. What changed, and what did not

| | V1.2 | **V1.3** |
|---|---|---|
| start architecture | taper | **taper** - the basin was built and is worse |
| blue-route finish | 97.69% | **97.69%** - unchanged, and unchanged on purpose |
| slot win ratio | 18.42 | **18.42** |
| orange, full field | 0.312 finish / 0.635 escape | **0.823 / 0.156** |
| orange route share | 57% | 32-36% |
| orange route completion | not measurable | **46.7%** |

The blue route is byte-identical to V1.2's: nothing this session touched it, and
the 600-seed benchmark reproduces its numbers exactly, down to the event digest
of the selected seed. That is worth stating plainly rather than presenting a
re-run as a result.

---

## 2. The start: the basin was built, and it is worse

Everything section 3 asked for was built - eight bays on a flat shelf, one wide
congruent ramp, a shallow stadium dish the whole field is in at once, a single
common exit, a chute to the launch - and it runs: **all eight marbles drain,
every seed, with no jam.** `START_LIFT` raises the start deck 1.90 layout units,
the local macro adjustment the brief allows, because V1.2's start had 0.63 units
of drop for everything between the gate and the course.

Two fairness properties in it are genuinely new and genuinely right. The feed is
**congruent** - one flat ramp, so every marble reaches the basin with the same
speed and heading. And the shelf's pan is **flat**, where the taper's trough is
a dish that rests its outer bays 0.10 units higher than its inner ones, a
systematic per-bay energy difference that had been under three sessions of
measurement without being noticed.

It is still worse. 100 seeds of the real course, blue route, everything else
identical:

| start | finish | win ratio | win spread |
|---|---|---|---|
| **taper (shipped)** | **0.985** | **11.50** | 21.0 points |
| basin | 0.968 | 29.00 | 28.0 points |
| basin + central island | 0.965 | 16.00 | 30.0 points |

Win rate by bay:

    taper           2.0   5.0  23.0  19.0  16.0  12.0  14.0   9.0
    basin           1.0   1.0  13.0  12.0  29.0  28.0  14.0   2.0
    basin + island  3.0   8.0  23.0   2.0   2.0  32.0  23.0   7.0

### The mechanism

**A single common exit orders the field by distance to that exit, and distance
to the exit is a function of which bay a marble started in.**

The basin is what proves that is about the *exit* rather than about the taper.
It supplies everything section 4 asked for - room for eight abreast, physical
collisions, a wide shallow floor, no immediate single-file funnel - and none of
it matters, because the ordering is not created inside the basin. It is created
at the notch, where eight marbles that entered spread across 5.5 layout units
have to leave through one 1.9-unit gap, and the ones that entered nearest it
reach it first. Room to mill is not a reason to mill.

The island is the clearest evidence: it does not flatten the profile, it
*relabels* it, moving the advantage from bays 4 and 5 to bays 5 and 6 while
leaving the spread where it was.

Breaking this needs equal path lengths from every bay to the exit - the bays
arranged **about** the exit rather than beside it, eight feeds around a ring
draining at its centre. That is not a local adjustment to the start; it is a
different start, and the eight racers would no longer be side by side, which
section 3 requires.

Twenty-four geometries have now been measured across three sessions. The finding
has not moved.

---

## 3. The orange fork: transformed, still not shippable

V1.2 left a precise diagnosis and it was correct as far as it went. Two things
were wrong at the seam and the second is the one it missed.

**The mouth was a channel's floor offset too low.** V1.2 put orange's
*centreline* on leg3's east lip; a channel's running floor sits `FLOOR_Y` - 0.26
layout units, 0.456 simulation - below its centreline, so orange's floor began
0.456 under the surface a marble crosses from.

**The held gradient was the centreline's, not the lip's.** leg3's east lip sits
0.59 to 0.62 above its own centreline through the window - the bank times the
half width - and neither the bank nor the width is constant there.

Orange's floor against leg3's east lip, in world height:

| leg3 sample | before | after |
|---|---|---|
| 82 | −0.461 | **−0.009** |
| 86 | −0.735 | −0.239 |
| 88 | −0.764 | −0.264 |

### What that bought, and what it did not

Twelve seeds, both routes, by how far leg3's east guard opens:

| window | finish | escape | blue / orange |
|---|---|---|---|
| shut | 0.990 | 0.010 | 95 / 0 |
| open 8 | 0.781 | 0.177 | 60 / 34 |
| **open 12** | **0.823** | 0.156 | 63 / 32 |
| open 26 | 0.854 | 0.135 | 72 / 22 |

against V1.2's 0.312 and 0.635 at the same window. **200 seeds** at open 12:

| | share | completion | median time | win rate |
|---|---|---|---|---|
| blue | 64.3% | 95.0% | 18.10 s | 13.9% |
| orange | 35.6% | **46.7%** | 17.83 s | 10.7% |

Route *usage* is inside section 13's 25-75% band and the slot win ratio actually
**improves to 7.8** with two routes, because the branch adds variance the single
route does not have. But orange completes 46.7% of what enters it, which is
section 14's death route, and the whole-field finish rate is 76%.

The remaining losses are concentrated rather than spread: `orange_lead[0..29]`
takes 172 of about 370, `final[0..19]` 64, `orange[100..119]` 44. That is a
much smaller and better-localised problem than the one V1.2 handed over, and it
is where a fourth attempt should start.

So `routes="blue"` still ships. Not because the fork is abandoned - it is in the
tree, it works, and its numbers are above - but because a race in which two
marbles of eight do not finish is not a race.

---

## 4. Reliability

600 seeds, 4800 racers, 34-second window, `routes="blue"`.

| | V1 | V1.1 | V1.2 | **V1.3** |
|---|---|---|---|---|
| finished | 84.35% | 91.96% | 97.69% | **97.69%** |
| escaped | 8.33% | 1.12% | 1.23% | **1.23%** |
| stopped | 7.31% | 6.92% | 1.08% | **1.08%** |
| all eight finished | 26.8% | 54.0% | 82.3% | **82.3%** |

Unchanged, because the blue route is unchanged. Section 15's two named hotspots
survive at the same size: `leg2[80..99]` 52 of 4800, `leg1[80..99]` 32. They
were not reached this session - the start and the fork took it - and they remain
the obstacle corridor and the hairpin feeding it.

---

## 5. Fairness

**Slot win ratio 18.42**, unchanged. Spearman, bay against finish rank, −0.075.

| bay | win | podium | finish | rank at 9% | at 50% | at 75% |
|---|---|---|---|---|---|---|
| 0 | 1.33% | 20.0% | 97.3% | 6.24 | 5.43 | 5.41 |
| 1 | 6.33% | 33.5% | 98.7% | 5.13 | 4.72 | 4.75 |
| 2 | **24.50%** | 50.5% | 97.0% | **2.91** | 3.69 | 3.81 |
| 3 | 15.67% | 38.7% | 97.5% | 4.61 | 4.45 | 4.42 |
| 4 | 18.33% | 43.3% | 96.3% | 3.81 | 4.13 | 4.20 |
| 5 | 11.67% | 32.0% | 98.0% | 4.86 | 4.82 | 4.72 |
| 6 | 16.17% | 46.5% | 98.2% | 3.65 | 4.08 | 4.05 |
| 7 | 6.00% | 35.5% | 98.5% | 4.80 | 4.68 | 4.63 |

One number here is worth more than the ratio: with the fork built, the ratio
falls to **7.8**. The second route is the only thing measured in three sessions
that reduces slot bias, because it adds a branch whose outcome is not a function
of where a marble started. That is an argument for finishing the fork rather
than for abandoning it.

---

## 6. Entertainment

| | V1.2 | **V1.3** |
|---|---|---|
| lead changes a race | 4.09 | **4.09** |
| overtakes a race | 38.7 | 38.7 |
| winner lock fraction | 0.141 | **0.133** |
| winner's worst rank | 1.77 | 1.77 |
| median final margin | 0.433 s | **0.433 s** |

---

## 7. The selected seed

**Seed 569**, from 494 all-eight-finisher races - the same seed V1.2 selected,
and it is the same seed because the blue course did not change. It was
re-selected by the same scoring on a fresh 600-seed benchmark rather than
carried over, which section 19 asks for, and it wins on the same merits:
thirteen lead changes, an 0.083 s margin, and the winner starting in **slot 0**,
the bay that wins 1.33% of the time, with slot 2 - the bay that wins 24.5% -
second.

---

## 8. Determinism

Seed 569, 20 in-process and 20 fresh-child repeats: identical state digest,
event digest, finish order, route assignment and finish times.
`docs/validation/sloped_race_v1/determinism_v13.json`.

The replay's contact check is clean apart from four brief `leg2[108]` findings
where a spinner blade throws a marble up to 0.22 simulation units clear of the
floor - the obstacle working, not a containment failure.

---

## 9. Remaining issues

1. **The start bias is 18.42 and is a property of the layout, not a tuning
   gap.** Any start that feeds eight laterally-separated bays into one exit
   orders them by distance to that exit. Two topologies and twenty-four
   geometries now say so. Fixing it needs the bays arranged about the exit
   rather than beside it, which changes the side-by-side presentation.
2. **Orange completes 46.7% of its traffic.** The fork itself is fixed - the
   seam is continuous and route usage is 36% - and the remaining losses are
   concentrated at `orange_lead[0..29]` (172 of 370). That is the next piece of
   work and it is well localised.
3. **`leg2[80..99]` and `leg1[80..99]`** still take 84 of 4800 between them, and
   were not reached this session.
