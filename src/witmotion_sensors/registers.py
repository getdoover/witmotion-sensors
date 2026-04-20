"""WTVB01-485 Modbus register map and decoder.

All registers are 16-bit signed holding registers (Modbus function 0x03).
Cross-checked against WitMotion manual v2.5 and the Concordia MTCAdapters driver.
"""

from dataclasses import dataclass

REGISTER_TYPE_HOLDING = 4

SAVE_REG = 0x00
BAUD_REG = 0x04
SLAVE_ID_REG = 0x1A
UNLOCK_REG = 0x69
SAMPLE_RATE_REG = 0x65

UNLOCK_KEY = 0xB588
SAVE_KEY = 0x0000
RESTART_KEY = 0x00FF
FACTORY_RESET_KEY = 0x0001

READ_BLOCK_START = 0x34
READ_BLOCK_COUNT = 19

ACCEL_SCALE_G_PER_LSB = 16.0 / 32768.0
TEMPERATURE_DIVISOR = 100.0


@dataclass
class SensorReading:
    accel_x: float
    accel_y: float
    accel_z: float
    velocity_x: float
    velocity_y: float
    velocity_z: float
    displacement_x: float
    displacement_y: float
    displacement_z: float
    frequency_x: float
    frequency_y: float
    frequency_z: float
    temperature: float

    @property
    def velocity_peak(self) -> float:
        return max(abs(self.velocity_x), abs(self.velocity_y), abs(self.velocity_z))

    @property
    def displacement_peak(self) -> float:
        return max(
            abs(self.displacement_x),
            abs(self.displacement_y),
            abs(self.displacement_z),
        )

    @property
    def frequency_dominant(self) -> float:
        axes = [
            (abs(self.velocity_x), self.frequency_x),
            (abs(self.velocity_y), self.frequency_y),
            (abs(self.velocity_z), self.frequency_z),
        ]
        return max(axes, key=lambda pair: pair[0])[1]


def to_signed16(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def decode_block(
    regs: list[int],
    *,
    velocity_scale: float = 1.0,
    displacement_scale: float = 1.0,
    frequency_scale: float = 0.1,
) -> SensorReading:
    """Decode a 19-register burst starting at 0x34.

    Layout (offsets from 0x34):
        0: AX, 1: AY, 2: AZ
        3..5: reserved
        6: VX, 7: VY, 8: VZ
        9..11: reserved
        12: TEMP
        13: DX, 14: DY, 15: DZ
        16: HZX, 17: HZY, 18: HZZ
    """
    if len(regs) < READ_BLOCK_COUNT:
        raise ValueError(
            f"Expected at least {READ_BLOCK_COUNT} registers, got {len(regs)}"
        )

    s = [to_signed16(r) for r in regs[:READ_BLOCK_COUNT]]

    return SensorReading(
        accel_x=s[0] * ACCEL_SCALE_G_PER_LSB,
        accel_y=s[1] * ACCEL_SCALE_G_PER_LSB,
        accel_z=s[2] * ACCEL_SCALE_G_PER_LSB,
        velocity_x=s[6] * velocity_scale,
        velocity_y=s[7] * velocity_scale,
        velocity_z=s[8] * velocity_scale,
        temperature=s[12] / TEMPERATURE_DIVISOR,
        displacement_x=s[13] * displacement_scale,
        displacement_y=s[14] * displacement_scale,
        displacement_z=s[15] * displacement_scale,
        frequency_x=s[16] * frequency_scale,
        frequency_y=s[17] * frequency_scale,
        frequency_z=s[18] * frequency_scale,
    )
