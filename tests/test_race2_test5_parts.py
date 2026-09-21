import math

import pytest

from marble3d.geometry import quat_rotate
from race2 import concepts
from race2.test5_parts import PendulumArm, PendulumCross
from sloped.scale import to_sim


def _run():
    return concepts.build("cascade").runs["corr1"]


def test_pendulum_pose_is_a_pure_function_of_tick():
    module = PendulumCross("pendulum", _run(), at=20)
    arm = module.local_actuators()[0]
    dt = 1.0 / 240.0

    first = arm.pose_at(137, dt)
    _ = arm.pose_at(991, dt)
    again = arm.pose_at(137, dt)

    assert first == again


def test_pendulum_angle_stays_inside_authored_arc():
    module = PendulumCross("pendulum", _run(), at=20)
    arm = module.local_actuators()[0]
    dt = 1.0 / 240.0

    angles = [arm.angle_at(tick, dt) for tick in range(0, 2400)]
    assert max(angles) <= module.amplitude + 1e-12
    assert min(angles) >= -module.amplitude - 1e-12
    assert max(angles) > 0.99 * module.amplitude
    assert min(angles) < -0.99 * module.amplitude


def test_pendulum_hangs_down_at_zero_phase():
    run = _run()
    module = PendulumCross("pendulum", run, at=20, phase=0.0)
    arm = module.local_actuators()[0]
    pose = arm.pose_at(0, 1.0 / 240.0)

    _lateral, up, _forward = run.frames[module.index]
    long_axis = quat_rotate(pose.rotation, (1.0, 0.0, 0.0))
    assert long_axis == pytest.approx(tuple(-v for v in up), abs=1e-9)


def test_pendulum_is_one_large_readable_actuator():
    module = PendulumCross("pendulum", _run(), at=20)
    actuators = module.local_actuators()

    assert len(actuators) == 1
    assert actuators[0].name == "arm"
    assert actuators[0].half_extents[0] == pytest.approx(
        0.5 * to_sim(module.ARM_LENGTH * module.run.scale)
    )


def test_pendulum_metadata_cannot_select_a_racer():
    data = PendulumCross("pendulum", _run(), at=20).describe()

    assert data["reactive"] is False
    assert data["selection"] == "arrival_phase_only"
    forbidden = {"winner", "racer", "marble", "colour", "color", "slot"}
    assert forbidden.isdisjoint(data)


def test_pendulum_rejects_nonphysical_configuration():
    with pytest.raises(ValueError):
        PendulumArm(
            "bad",
            pivot=(0, 0, 0),
            lateral=(1, 0, 0),
            up=(0, 1, 0),
            forward=(0, 0, 1),
            length=1.0,
            thickness=0.1,
            depth=0.1,
            amplitude=math.pi / 2,
            rate=1.0,
        )
