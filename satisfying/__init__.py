"""Category 3 - satisfying simulations. First experiment: HIT EVERY TILE TO ESCAPE.

Category 3 is its own workstream. Nothing here imports `engine` (Category 1,
the ring duel), `race`/`race2`/`sloped`/`marble3d` (Category 2, the races) or
`company` (Company OS), and nothing there imports this. The three categories
share the repository, the test runner and the conventions - a seeds module per
package, a `tools/` driver, prose docstrings that say why - and share no code,
because a ball bouncing in a 2D polygon has nothing in common with a marble
rolling down a PyBullet course except the word "ball".

The experiment, stated as the viewer sees it:

    HIT EVERY TILE TO ESCAPE

A ball moves inside a segmented polygonal arena. Every wall tile it has not
touched yet lights up permanently the first time it is hit. The arena is
therefore the progress bar - there is no other progress bar - and the
simulation is complete when no dark tiles remain.

Three modules, one experiment:

- `satisfying.tile_arena` - the 16-sided arena and its 48 tiles, geometry only.
- `satisfying.tile_escape` - the ball, the collisions, the activation ledger
  and the instrumentation. Event-driven and exact: no fixed physics step, so
  no tunnelling to rule out.
- `satisfying.tile_render` - 9:16 stills, for reading the arena at phone size.

`satisfying.seeds` holds the deterministic streams, following the convention
`marble3d.seeds` set: one salt per concern, each deriving its own
`random.Random` from the run seed, and no import of another category's salts.

Phase 1 is a prototype. It proves the mechanic and measures what the natural
physics actually does. Audio, the musical-note system, particles, final
materials, the escape/climax sequence and multi-ball escalation are later
phases and are deliberately absent.
"""
