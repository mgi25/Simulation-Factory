"""One run, reduced to the few strings two machines can be compared on.

The pipeline does not need cross-machine determinism and is built so that it
never will: a seed is chosen on the machine that simulates it, and what travels
to the machine that renders it is the *replay*, not the seed. Godot replays; it
never re-solves. So a disagreement between two computers about what seed 7 does
cannot put a marble in the wrong place in a finished clip.

That is a reason not to *depend* on cross-machine determinism. It is not a
reason not to know. If two machines diverge, every number measured on one of
them - the bowl revolutions, the drain order, the finish spread - is a number
about that machine, and the physics report should say so. The only way to find
that out is for somebody to run this on a second computer and compare six lines
of output, so this exists to make that a two-minute job rather than a project.

    python -m tools.marble3d_determinism_probe --seed 7

Nothing here re-derives anything. The digests are the replay's own, the
environment block is `marble3d.simulation.environment_metadata`, and the
configuration digest is a hash of `CoreConfig.to_json()` - so the probe cannot
drift from the thing it is probing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marble3d.config import DEFAULT_CONFIG  # noqa: E402
from marble3d.machines import start_bowl_curve  # noqa: E402
from marble3d.simulation import environment_metadata, simulate  # noqa: E402

DEFAULT_SEED = 7


def config_digest(config: Any = DEFAULT_CONFIG) -> str:
    """A hash of every physics number, so a retune cannot masquerade as drift.

    Two machines reporting different state digests have either disagreed about
    the arithmetic or been asked different questions, and this is what tells
    the two apart. Sorted keys and a compact separator because the digest has
    to survive being computed by two different Python builds.
    """
    payload = json.dumps(config.to_json(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def probe(seed: int) -> dict[str, Any]:
    """Simulate one seed and report only what is comparable."""
    replay = simulate(seed=seed, machine=start_bowl_curve())
    environment = environment_metadata()
    return {
        "seed": seed,
        "state_digest": replay.digest(),
        "event_digest": replay.event_digest(),
        "drain_order": list(replay.summary["finish_order"]),
        "physics_hz": DEFAULT_CONFIG.physics.physics_hz,
        "config_digest": config_digest(),
        "frames": len(replay.frames),
        "python": environment["python"],
        "pybullet_api": environment["pybullet_api"],
        "platform": environment["platform"],
        "machine": environment["machine"],
    }


def format_probe(result: dict[str, Any]) -> str:
    """Six lines and a header, in a fixed order, so a diff is readable."""
    return "\n".join(
        [
            f"marble3d determinism probe  seed {result['seed']}",
            f"  state digest   {result['state_digest']}",
            f"  event digest   {result['event_digest']}",
            f"  drain order    {result['drain_order']}",
            f"  frames         {result['frames']}",
            f"  physics        {result['physics_hz']} Hz"
            f"  config {result['config_digest']}",
            f"  python         {result['python']}"
            f"  pybullet api {result['pybullet_api']}",
            f"  platform       {result['platform']} ({result['machine']})",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="report one seed's digests and the machine that produced them"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the same fields as JSON, for comparing more than two runs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = probe(args.seed)
    if args.json:
        print(json.dumps(result, indent=1, sort_keys=True))
    else:
        print(format_probe(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
