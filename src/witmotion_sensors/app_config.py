from pathlib import Path

from pydoover import config
from pydoover.docker.modbus import ModbusConfig


class WitmotionSensorConfig(config.Schema):
    modbus_config = ModbusConfig()
    modbus_id = config.Integer(
        "Modbus Slave ID",
        default=80,
        description="Modbus slave address of the WTVB01-485 sensor (default 0x50 = 80)",
        name="modbus_id",
    )
    poll_period = config.Number(
        "Poll Period (s)",
        default=1.0,
        description="How often to read the sensor (seconds)",
        name="poll_period",
    )
    velocity_scale = config.Number(
        "Velocity Scale",
        default=1.0,
        description="Multiplier applied to raw velocity registers (mm/s per LSB)",
        name="velocity_scale",
    )
    displacement_scale = config.Number(
        "Displacement Scale",
        default=1.0,
        description="Multiplier applied to raw displacement registers (um per LSB)",
        name="displacement_scale",
    )
    frequency_scale = config.Number(
        "Frequency Scale",
        default=0.1,
        description="Multiplier applied to raw frequency registers (Hz per LSB)",
        name="frequency_scale",
    )
    read_failure_threshold = config.Integer(
        "Read Failure Threshold",
        default=3,
        description="Consecutive failed reads before link is marked errored",
        name="read_failure_threshold",
    )
    error_retry_seconds = config.Integer(
        "Error Retry (s)",
        default=30,
        description="Seconds in error state before attempting reconnection",
        name="error_retry_seconds",
    )


def export():
    WitmotionSensorConfig.export(
        Path(__file__).parents[2] / "doover_config.json",
        "witmotion_sensors",
    )


if __name__ == "__main__":
    export()
