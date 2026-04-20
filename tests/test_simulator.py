"""End-to-end simulator test — spin up the pymodbus TCP slave in-process and
round-trip a read through a pymodbus client.

Slow (starts a server), so it lives in a separate module so fast unit tests
stay speedy.
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Make the simulator's main module importable.
SIM_DIR = Path(__file__).parents[1] / "simulators" / "sample"
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

from main import WitmotionSim  # noqa: E402

from witmotion_sensors.registers import (
    READ_BLOCK_COUNT,
    READ_BLOCK_START,
    UNLOCK_KEY,
    UNLOCK_REG,
    SAMPLE_RATE_REG,
    decode_block,
)


@pytest.mark.asyncio
async def test_simulator_roundtrip():
    """Start sim, connect a pymodbus client, read the burst, decode it."""
    from pymodbus.client import AsyncModbusTcpClient

    sim = WitmotionSim(host="127.0.0.1", port=15020, slave_id=80)
    server_task = asyncio.create_task(sim.start())

    try:
        await asyncio.wait_for(sim.is_ready.wait(), timeout=5)
        # Give the pymodbus server a moment to start listening.
        await asyncio.sleep(0.5)

        client = AsyncModbusTcpClient("127.0.0.1", port=15020)
        await client.connect()
        try:
            rr = await client.read_holding_registers(
                address=READ_BLOCK_START, count=READ_BLOCK_COUNT, slave=80
            )
            assert not rr.isError(), f"Modbus error: {rr}"
            assert len(rr.registers) == READ_BLOCK_COUNT

            reading = decode_block(rr.registers)
            # Acceleration bounded by sensor full scale 16 g.
            assert -16.0 < reading.accel_x < 16.0
            assert -16.0 < reading.accel_y < 16.0
            # Temperature drifts around 25 °C.
            assert 15.0 < reading.temperature < 35.0
            # Synthetic velocity envelope ranges 0..40 mm/s.
            assert 0 <= reading.velocity_peak <= 40
            # Dominant frequency is one of the three axis frequencies.
            assert reading.frequency_dominant > 0
        finally:
            client.close()
    finally:
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_simulator_rejects_locked_writes():
    """Protected config registers should reject writes when not unlocked."""
    from pymodbus.client import AsyncModbusTcpClient

    sim = WitmotionSim(host="127.0.0.1", port=15021, slave_id=80)
    server_task = asyncio.create_task(sim.start())

    try:
        await asyncio.wait_for(sim.is_ready.wait(), timeout=5)
        await asyncio.sleep(0.5)

        client = AsyncModbusTcpClient("127.0.0.1", port=15021)
        await client.connect()
        try:
            # Attempt a locked write — sim should ignore it.
            await client.write_register(address=SAMPLE_RATE_REG, value=55, slave=80)
            rr = await client.read_holding_registers(
                address=SAMPLE_RATE_REG, count=1, slave=80
            )
            assert rr.registers[0] == 100  # seed value, unchanged

            # Unlock then write — should now stick.
            await client.write_register(address=UNLOCK_REG, value=UNLOCK_KEY, slave=80)
            await client.write_register(address=SAMPLE_RATE_REG, value=55, slave=80)
            rr = await client.read_holding_registers(
                address=SAMPLE_RATE_REG, count=1, slave=80
            )
            assert rr.registers[0] == 55
        finally:
            client.close()
    finally:
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass
