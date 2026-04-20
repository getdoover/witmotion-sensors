"""Technician-command tag handler tests.

Verifies the unlock -> write target -> save sequence is emitted for each
command tag, and that the command tag is reset to None after processing.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from witmotion_sensors.commands import apply_technician_commands
from witmotion_sensors.registers import (
    BAUD_REG,
    FACTORY_RESET_KEY,
    SAMPLE_RATE_REG,
    SAVE_KEY,
    SAVE_REG,
    SLAVE_ID_REG,
    UNLOCK_KEY,
    UNLOCK_REG,
)


class FakeTag:
    def __init__(self, initial=None):
        self._value = initial

    def get(self):
        return self._value

    async def set(self, value):
        self._value = value


def _build_app(cmd_overrides=None):
    cmd_overrides = cmd_overrides or {}
    tags = SimpleNamespace(
        cmd_set_slave_id=FakeTag(cmd_overrides.get("cmd_set_slave_id")),
        cmd_set_sample_rate=FakeTag(cmd_overrides.get("cmd_set_sample_rate")),
        cmd_set_baud_code=FakeTag(cmd_overrides.get("cmd_set_baud_code")),
        cmd_factory_reset=FakeTag(cmd_overrides.get("cmd_factory_reset")),
        cmd_save_config=FakeTag(cmd_overrides.get("cmd_save_config")),
    )
    modbus_iface = SimpleNamespace(write_registers=AsyncMock(return_value=True))
    config = SimpleNamespace(
        modbus_config=SimpleNamespace(name=SimpleNamespace(value="default")),
        modbus_id=SimpleNamespace(value=80),
    )
    return SimpleNamespace(tags=tags, modbus_iface=modbus_iface, config=config)


def _write_calls(app):
    """Return list of (address, value) tuples in call order."""
    return [
        (call.kwargs["start_address"], call.kwargs["values"][0])
        for call in app.modbus_iface.write_registers.await_args_list
    ]


@pytest.mark.asyncio
async def test_no_commands_no_writes():
    app = _build_app()
    await apply_technician_commands(app)
    app.modbus_iface.write_registers.assert_not_called()


@pytest.mark.asyncio
async def test_set_slave_id_emits_unlock_write_save():
    app = _build_app({"cmd_set_slave_id": 42})
    await apply_technician_commands(app)

    assert _write_calls(app) == [
        (UNLOCK_REG, UNLOCK_KEY),
        (SLAVE_ID_REG, 42),
        (SAVE_REG, SAVE_KEY),
    ]
    assert app.tags.cmd_set_slave_id.get() is None


@pytest.mark.asyncio
async def test_set_sample_rate():
    app = _build_app({"cmd_set_sample_rate": 50})
    await apply_technician_commands(app)
    assert _write_calls(app) == [
        (UNLOCK_REG, UNLOCK_KEY),
        (SAMPLE_RATE_REG, 50),
        (SAVE_REG, SAVE_KEY),
    ]


@pytest.mark.asyncio
async def test_set_baud_code():
    app = _build_app({"cmd_set_baud_code": 6})
    await apply_technician_commands(app)
    assert _write_calls(app) == [
        (UNLOCK_REG, UNLOCK_KEY),
        (BAUD_REG, 6),
        (SAVE_REG, SAVE_KEY),
    ]


@pytest.mark.asyncio
async def test_factory_reset_emits_reset_key():
    app = _build_app({"cmd_factory_reset": True})
    await apply_technician_commands(app)
    assert _write_calls(app) == [
        (UNLOCK_REG, UNLOCK_KEY),
        (SAVE_REG, FACTORY_RESET_KEY),
        (SAVE_REG, SAVE_KEY),
    ]
    assert app.tags.cmd_factory_reset.get() is None


@pytest.mark.asyncio
async def test_save_config_emits_save_only():
    app = _build_app({"cmd_save_config": True})
    await apply_technician_commands(app)
    assert _write_calls(app) == [(SAVE_REG, SAVE_KEY)]
    assert app.tags.cmd_save_config.get() is None


@pytest.mark.asyncio
async def test_slave_id_out_of_range_skipped_but_tag_cleared():
    app = _build_app({"cmd_set_slave_id": 0xFF})
    await apply_technician_commands(app)
    app.modbus_iface.write_registers.assert_not_called()
    assert app.tags.cmd_set_slave_id.get() is None


@pytest.mark.asyncio
async def test_unlock_failure_aborts_sequence():
    app = _build_app({"cmd_set_slave_id": 10})
    app.modbus_iface.write_registers = AsyncMock(return_value=False)
    await apply_technician_commands(app)
    # Only the unlock is attempted; write + save are skipped.
    assert app.modbus_iface.write_registers.await_count == 1
    assert app.tags.cmd_set_slave_id.get() is None


@pytest.mark.asyncio
async def test_multiple_commands_processed_in_order():
    app = _build_app({
        "cmd_set_slave_id": 10,
        "cmd_set_sample_rate": 200,
    })
    await apply_technician_commands(app)

    calls = _write_calls(app)
    # Each command runs its own unlock-write-save.
    assert calls == [
        (UNLOCK_REG, UNLOCK_KEY), (SLAVE_ID_REG, 10), (SAVE_REG, SAVE_KEY),
        (UNLOCK_REG, UNLOCK_KEY), (SAMPLE_RATE_REG, 200), (SAVE_REG, SAVE_KEY),
    ]
