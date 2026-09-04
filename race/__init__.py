"""Obstacle-race simulation.

A sibling of `modes.power_battle`, not a replacement for it. The race owns
its own physics space because a race needs gravity, friction and a speed
limit, while a duel needs none of those - but everything below the rules is
shared with the fight system: the logical 9:16 canvas, `ObstacleSpec`
geometry, the salted-RNG-stream convention and the fixed-timestep clock.
"""
