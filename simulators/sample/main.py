"""WTVB01-485 Modbus TCP simulator.

Emulates the vibration-sensor side of the bus so the app + doover_modbus_iface
can be exercised locally. Populates holding registers 0x34..0x46 with
plausible synthetic vibration data and honours writes to config registers
after the WitMotion unlock sequence (0xB588 -> reg 0x69).
"""

import asyncio
import logging
import math
import os
import random
import time

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import StartAsyncTcpServer

log = logging.getLogger(__name__)

UNLOCK_REG = 0x69
UNLOCK_KEY = 0xB588
UNLOCK_VALID_SECS = 10.0

SAVE_REG = 0x00
BAUD_REG = 0x04
SLAVE_ID_REG = 0x1A
SAMPLE_RATE_REG = 0x65

READ_BLOCK_START = 0x34  # AX
VELOCITY_OFFSET = 6      # VX at 0x3A
TEMP_OFFSET = 12         # TEMP at 0x40
DISPLACEMENT_OFFSET = 13 # DX at 0x41
FREQUENCY_OFFSET = 16    # HZX at 0x44


def signed_to_u16(v: int) -> int:
    v = int(v)
    if v < 0:
        v += 0x10000
    return v & 0xFFFF


class UnlockAwareSlaveContext(ModbusSlaveContext):
    """Rejects writes to protected registers unless unlock was issued <10 s ago.

    Matches the WitMotion firmware behaviour: write 0xB588 to reg 0x69, then
    you have a short window to write config registers before they are locked
    again.
    """

    PROTECTED = {SAVE_REG, BAUD_REG, SLAVE_ID_REG, SAMPLE_RATE_REG}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.unlocked_until: float = 0.0

    def setValues(self, fx, address, values):
        for i, v in enumerate(values):
            addr = address + i
            if addr == UNLOCK_REG and v == UNLOCK_KEY:
                self.unlocked_until = time.monotonic() + UNLOCK_VALID_SECS
                log.info("Unlock received — config writes accepted for %ss", UNLOCK_VALID_SECS)
            elif addr in self.PROTECTED and time.monotonic() > self.unlocked_until:
                log.warning("Rejected locked write to reg 0x%02X=%s", addr, v)
                return
        return super().setValues(fx, address, values)

    def seed(self, address, values):
        """Bypass the lock to set firmware defaults at boot."""
        return super().setValues(0x03, address, list(values))


class WitmotionSim:
    def __init__(self, host: str, port: int, slave_id: int):
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self.started = time.monotonic()
        self.context: UnlockAwareSlaveContext | None = None
        self.is_ready = asyncio.Event()

    def _synthesise(self):
        """Generate synthetic vibration values and write them into holding regs."""
        t = time.monotonic() - self.started

        # Acceleration X/Y/Z in raw LSB: raw = g_value * 32768 / 16
        accel_g = [
            0.05 * math.sin(2 * math.pi * 0.3 * t),
            0.04 * math.cos(2 * math.pi * 0.25 * t),
            1.0 + 0.02 * math.sin(2 * math.pi * 0.5 * t),  # gravity on Z
        ]
        accel_raw = [int(v * 32768 / 16) for v in accel_g]

        # Slow 15 s envelope that lifts velocity from ~5 mm/s to ~20 mm/s
        envelope = 5.0 + 15.0 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 15.0))
        velocity_mm_s = [
            envelope * 0.6 + random.uniform(-0.3, 0.3),
            envelope * 0.8 + random.uniform(-0.3, 0.3),
            envelope * 1.0 + random.uniform(-0.3, 0.3),
        ]
        # Units already mm/s -> write as raw int16.
        velocity_raw = [int(v) for v in velocity_mm_s]

        # Displacement in um, small values.
        displacement_raw = [
            int(50 + 20 * math.sin(2 * math.pi * 0.1 * t)),
            int(60 + 25 * math.cos(2 * math.pi * 0.1 * t)),
            int(70 + 30 * math.sin(2 * math.pi * 0.12 * t)),
        ]

        # Frequency: sensor stores Hz * 10.
        frequency_raw = [int(25.0 * 10), int(30.5 * 10), int(45.0 * 10)]

        # Temperature: °C * 100, drifting around 25 °C.
        temp_raw = int((25.0 + 2.0 * math.sin(2 * math.pi * t / 60.0)) * 100)

        block = [0] * 19
        for i, v in enumerate(accel_raw):
            block[i] = signed_to_u16(v)
        # offsets 3..5 reserved -> 0
        for i, v in enumerate(velocity_raw):
            block[VELOCITY_OFFSET + i] = signed_to_u16(v)
        # offsets 9..11 reserved -> 0
        block[TEMP_OFFSET] = signed_to_u16(temp_raw)
        for i, v in enumerate(displacement_raw):
            block[DISPLACEMENT_OFFSET + i] = signed_to_u16(v)
        for i, v in enumerate(frequency_raw):
            block[FREQUENCY_OFFSET + i] = signed_to_u16(v)

        self.context.setValues(0x03, READ_BLOCK_START, block)

    async def _run_loop(self):
        await self.is_ready.wait()
        while True:
            try:
                self._synthesise()
            except Exception:
                log.exception("Failed to synthesise values")
            await asyncio.sleep(0.2)

    async def start(self):
        self.context = UnlockAwareSlaveContext(
            hr=ModbusSequentialDataBlock(0x00, [0] * 256),
            ir=ModbusSequentialDataBlock(0x00, [0] * 256),
            co=ModbusSequentialDataBlock(0x00, [0] * 256),
            di=ModbusSequentialDataBlock(0x00, [0] * 256),
        )
        # Seed realistic defaults for config registers (bypass the lock).
        self.context.seed(BAUD_REG, [2])          # 9600
        self.context.seed(SLAVE_ID_REG, [self.slave_id])
        self.context.seed(SAMPLE_RATE_REG, [100]) # 100 Hz

        server_context = ModbusServerContext(slaves=self.context, single=True)
        identity = ModbusDeviceIdentification(info_name={
            "VendorName": "Doover",
            "ProductCode": "WTVB01SIM",
            "ProductName": "WTVB01-485 Simulator",
            "ModelName": "WTVB01-485",
            "MajorMinorRevision": "1.0.0",
        })

        loop_task = asyncio.create_task(self._run_loop())
        self.is_ready.set()
        try:
            await StartAsyncTcpServer(
                context=server_context,
                identity=identity,
                address=(self.host, self.port),
                framer="socket",
            )
        finally:
            loop_task.cancel()


def main():
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("DEBUG") else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.environ.get("MODBUS_HOST", "127.0.0.1")
    port = int(os.environ.get("MODBUS_PORT", "5020"))
    slave_id = int(os.environ.get("SLAVE_ID", "80"))
    sim = WitmotionSim(host=host, port=port, slave_id=slave_id)
    asyncio.run(sim.start())


if __name__ == "__main__":
    main()
