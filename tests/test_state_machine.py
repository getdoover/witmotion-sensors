"""Link state machine transition tests."""

import pytest

from witmotion_sensors.app_state import LinkState


@pytest.mark.asyncio
async def test_initial_state_is_disconnected():
    link = LinkState()
    assert link.state == "disconnected"


@pytest.mark.asyncio
async def test_happy_path_connect_to_online():
    link = LinkState()
    await link.connect()
    assert link.state == "connecting"
    await link.connected()
    assert link.state == "online"


@pytest.mark.asyncio
async def test_online_to_error_on_read_failed():
    link = LinkState()
    await link.connect()
    await link.connected()
    await link.read_failed()
    assert link.state == "error"


@pytest.mark.asyncio
async def test_connect_failed_in_connecting():
    link = LinkState()
    await link.connect()
    await link.connect_failed()
    assert link.state == "error"


@pytest.mark.asyncio
async def test_reconnect_from_error():
    link = LinkState(error_retry_seconds=30)
    await link.connect()
    await link.connected()
    await link.read_failed()
    assert link.state == "error"
    # Manual recovery via connect() (timeout would do the same in production)
    await link.connect()
    assert link.state == "connecting"


@pytest.mark.asyncio
async def test_disconnect_from_any_state():
    link = LinkState()
    await link.connect()
    await link.connected()
    await link.disconnect()
    assert link.state == "disconnected"
