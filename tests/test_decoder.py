"""Register decoder unit tests — no I/O, pure functions."""

import pytest

from witmotion_sensors.registers import (
    READ_BLOCK_COUNT,
    SensorReading,
    decode_block,
    to_signed16,
)


def test_to_signed16_positive():
    assert to_signed16(0) == 0
    assert to_signed16(1) == 1
    assert to_signed16(0x7FFF) == 32767


def test_to_signed16_negative():
    assert to_signed16(0x8000) == -32768
    assert to_signed16(0xFFFF) == -1
    assert to_signed16(0xFFFE) == -2


def test_to_signed16_truncates_out_of_range():
    # Values >16 bits get masked first.
    assert to_signed16(0x1FFFF) == -1


def _make_block(
    ax=0, ay=0, az=0, vx=0, vy=0, vz=0,
    temp=0, dx=0, dy=0, dz=0, fx=0, fy=0, fz=0,
):
    """Build a 19-register block with values at the correct offsets."""
    def u(v):
        return v & 0xFFFF
    return [
        u(ax), u(ay), u(az),        # 0..2 accel
        0, 0, 0,                     # 3..5 reserved
        u(vx), u(vy), u(vz),         # 6..8 velocity
        0, 0, 0,                     # 9..11 reserved
        u(temp),                     # 12 temp
        u(dx), u(dy), u(dz),         # 13..15 displacement
        u(fx), u(fy), u(fz),         # 16..18 frequency
    ]


def test_decode_block_basic_scaling():
    # Accel: raw 32768/2 -> 0.5 * 16 = 8.0 g (but 32768 is out of int16; use 16384 -> 8g/2=8.0 at scale 16/32768)
    # 16384 * 16/32768 = 8.0
    regs = _make_block(ax=16384, ay=0, az=-16384, temp=2543)
    reading = decode_block(regs)
    assert reading.accel_x == pytest.approx(8.0, rel=1e-6)
    assert reading.accel_y == 0
    assert reading.accel_z == pytest.approx(-8.0, rel=1e-6)
    assert reading.temperature == pytest.approx(25.43, rel=1e-6)


def test_decode_block_velocity_and_frequency_scaling():
    # Velocity raw is µm/s (1 LSB = 0.001 mm/s); default trim is 1.0 so output is mm/s.
    # Frequency raw is Hz * 10 — default frequency_scale=0.1.
    regs = _make_block(vx=5000, vy=10000, vz=15000, fx=250, fy=305, fz=450)
    reading = decode_block(regs)
    assert reading.velocity_x == pytest.approx(5.0)
    assert reading.velocity_y == pytest.approx(10.0)
    assert reading.velocity_z == pytest.approx(15.0)
    assert reading.frequency_x == pytest.approx(25.0)
    assert reading.frequency_y == pytest.approx(30.5)
    assert reading.frequency_z == pytest.approx(45.0)


def test_decode_block_peak_and_dominant():
    regs = _make_block(
        vx=3000, vy=20000, vz=-10000,
        fx=200, fy=350, fz=500,
        dx=40, dy=60, dz=-80,
    )
    reading = decode_block(regs)
    assert reading.velocity_peak == pytest.approx(20.0)  # |vy| largest -> 20 mm/s
    assert reading.displacement_peak == 80  # |dz| largest
    # Dominant frequency corresponds to axis with largest |velocity| -> fy
    assert reading.frequency_dominant == pytest.approx(35.0)


def test_decode_block_custom_scales():
    # velocity_scale is a dimensionless trim on top of the 0.001 mm/s/LSB native scaling.
    regs = _make_block(vx=100, dx=200, fx=400)
    reading = decode_block(
        regs,
        velocity_scale=2.0,
        displacement_scale=0.5,
        frequency_scale=0.1,
    )
    assert reading.velocity_x == pytest.approx(0.2)  # 100 * 0.001 * 2.0
    assert reading.displacement_x == pytest.approx(100.0)
    assert reading.frequency_x == pytest.approx(40.0)


def test_decode_block_rejects_short_input():
    with pytest.raises(ValueError):
        decode_block([0] * (READ_BLOCK_COUNT - 1))


def test_sensor_reading_is_dataclass():
    assert isinstance(
        SensorReading(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        SensorReading,
    )
