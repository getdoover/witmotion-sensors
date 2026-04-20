"""Technician command tag handler.

Command tags (not exposed in UI) let field technicians reconfigure the sensor
without changing firmware. When a tag is non-None, we run the WitMotion
unlock-write-save sequence and then clear the tag.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .registers import (
    BAUD_REG,
    FACTORY_RESET_KEY,
    REGISTER_TYPE_HOLDING,
    SAMPLE_RATE_REG,
    SAVE_KEY,
    SAVE_REG,
    SLAVE_ID_REG,
    UNLOCK_KEY,
    UNLOCK_REG,
)

if TYPE_CHECKING:
    from .application import WitmotionSensorApp

log = logging.getLogger(__name__)


async def apply_technician_commands(app: WitmotionSensorApp) -> None:
    slave_id = app.tags.cmd_set_slave_id.get()
    if slave_id is not None:
        if 0x01 <= int(slave_id) <= 0x7F:
            await _write_unlocked(app, SLAVE_ID_REG, int(slave_id), label="slave_id")
        else:
            log.error("cmd_set_slave_id %s out of range [1, 127]", slave_id)
        await app.tags.cmd_set_slave_id.set(None)

    sample_rate = app.tags.cmd_set_sample_rate.get()
    if sample_rate is not None:
        if 1 <= int(sample_rate) <= 200:
            await _write_unlocked(app, SAMPLE_RATE_REG, int(sample_rate), label="sample_rate")
        else:
            log.error("cmd_set_sample_rate %s out of range [1, 200]", sample_rate)
        await app.tags.cmd_set_sample_rate.set(None)

    baud_code = app.tags.cmd_set_baud_code.get()
    if baud_code is not None:
        if 1 <= int(baud_code) <= 7:
            await _write_unlocked(app, BAUD_REG, int(baud_code), label="baud_code")
        else:
            log.error("cmd_set_baud_code %s out of range [1, 7]", baud_code)
        await app.tags.cmd_set_baud_code.set(None)

    if app.tags.cmd_factory_reset.get():
        await _write_unlocked(app, SAVE_REG, FACTORY_RESET_KEY, label="factory_reset")
        await app.tags.cmd_factory_reset.set(None)

    if app.tags.cmd_save_config.get():
        await _write_register(app, SAVE_REG, SAVE_KEY, label="save")
        await app.tags.cmd_save_config.set(None)


async def _write_unlocked(
    app: WitmotionSensorApp, address: int, value: int, *, label: str
) -> bool:
    """Full unlock → write → save sequence for persistent config changes."""
    if not await _write_register(app, UNLOCK_REG, UNLOCK_KEY, label=f"unlock({label})"):
        return False
    if not await _write_register(app, address, value, label=label):
        return False
    return await _write_register(app, SAVE_REG, SAVE_KEY, label=f"save({label})")


async def _write_register(
    app: WitmotionSensorApp, address: int, value: int, *, label: str
) -> bool:
    bus_id = app.config.modbus_config.name.value
    modbus_id = int(app.config.modbus_id.value)
    try:
        ok = await app.modbus_iface.write_registers(
            bus_id=bus_id,
            modbus_id=modbus_id,
            start_address=address,
            values=[int(value) & 0xFFFF],
            register_type=REGISTER_TYPE_HOLDING,
        )
    except Exception as exc:
        log.error("write_registers(%s=0x%04X) raised: %s", label, value, exc)
        return False
    if not ok:
        log.error("write_registers(%s=0x%04X) failed", label, value)
        return False
    log.info("Technician command applied: %s=0x%04X", label, value)
    return True
