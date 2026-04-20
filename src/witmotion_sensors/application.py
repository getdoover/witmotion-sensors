import logging

from pydoover.docker import Application

from .app_config import WitmotionSensorConfig
from .app_state import LinkState
from .app_tags import WitmotionSensorTags
from .app_ui import WitmotionSensorUI
from .commands import apply_technician_commands
from .registers import (
    READ_BLOCK_COUNT,
    READ_BLOCK_START,
    REGISTER_TYPE_HOLDING,
    SensorReading,
    decode_block,
)

log = logging.getLogger(__name__)


class WitmotionSensorApp(Application):
    config_cls = WitmotionSensorConfig
    tags_cls = WitmotionSensorTags
    ui_cls = WitmotionSensorUI

    config: WitmotionSensorConfig
    tags: WitmotionSensorTags

    async def setup(self):
        self.link = LinkState(error_retry_seconds=self.config.error_retry_seconds.value)
        self.consecutive_failures = 0
        self.loop_target_period = float(self.config.poll_period.value)
        await self.link.connect()
        await self.tags.link_state.set(self.link.state)

    async def main_loop(self):
        # Keep loop period in sync with config in case the user edits it at runtime.
        self.loop_target_period = float(self.config.poll_period.value)

        await apply_technician_commands(self)

        regs = await self._read_sensor()
        if regs is None:
            await self._handle_read_failure()
            return

        reading = decode_block(
            regs,
            velocity_scale=float(self.config.velocity_scale.value),
            displacement_scale=float(self.config.displacement_scale.value),
            frequency_scale=float(self.config.frequency_scale.value),
        )
        await self._publish_reading(reading)
        await self._handle_read_success()

    async def _read_sensor(self) -> list[int] | None:
        bus_id = self.config.modbus_config.name.value
        modbus_id = int(self.config.modbus_id.value)
        try:
            values = await self.modbus_iface.read_registers(
                bus_id=bus_id,
                modbus_id=modbus_id,
                start_address=READ_BLOCK_START,
                num_registers=READ_BLOCK_COUNT,
                register_type=REGISTER_TYPE_HOLDING,
            )
        except Exception as exc:
            log.warning("Modbus read raised: %s", exc)
            return None

        if values is None:
            return None
        if isinstance(values, int):
            values = [values]
        if len(values) < READ_BLOCK_COUNT:
            log.warning("Short modbus read: got %d of %d regs", len(values), READ_BLOCK_COUNT)
            return None
        return list(values)

    async def _publish_reading(self, r: SensorReading):
        await self.tags.accel_x.set(r.accel_x)
        await self.tags.accel_y.set(r.accel_y)
        await self.tags.accel_z.set(r.accel_z)
        await self.tags.velocity_x.set(r.velocity_x)
        await self.tags.velocity_y.set(r.velocity_y)
        await self.tags.velocity_z.set(r.velocity_z)
        await self.tags.displacement_x.set(r.displacement_x)
        await self.tags.displacement_y.set(r.displacement_y)
        await self.tags.displacement_z.set(r.displacement_z)
        await self.tags.frequency_x.set(r.frequency_x)
        await self.tags.frequency_y.set(r.frequency_y)
        await self.tags.frequency_z.set(r.frequency_z)
        await self.tags.temperature.set(r.temperature)
        await self.tags.velocity_peak.set(r.velocity_peak)
        await self.tags.displacement_peak.set(r.displacement_peak)
        await self.tags.frequency_dominant.set(r.frequency_dominant)

    async def _handle_read_success(self):
        self.consecutive_failures = 0
        await self.tags.last_comms_ok.set(True)
        if self.link.state in ("disconnected", "connecting", "error"):
            # Force into connecting first if we're in error, then to online.
            if self.link.state == "error":
                await self.link.connect()
            if self.link.state == "connecting":
                await self.link.connected()
            elif self.link.state == "disconnected":
                await self.link.connect()
                await self.link.connected()
            await self.tags.link_state.set(self.link.state)

    async def _handle_read_failure(self):
        self.consecutive_failures += 1
        await self.tags.last_comms_ok.set(False)
        await self.tags.comms_error_count.set(self.consecutive_failures)

        threshold = int(self.config.read_failure_threshold.value)
        if self.link.state == "connecting":
            await self.link.connect_failed()
        elif self.link.state == "online" and self.consecutive_failures >= threshold:
            await self.link.read_failed()
        await self.tags.link_state.set(self.link.state)
