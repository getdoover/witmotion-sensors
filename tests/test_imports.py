"""Smoke tests: modules import, classes wire up to pydoover base classes."""

import json

from pydoover.config import Schema
from pydoover.tags import Tags
from pydoover.ui import UI


def test_import_app():
    from witmotion_sensors.application import WitmotionSensorApp

    assert WitmotionSensorApp.config_cls is not None
    assert WitmotionSensorApp.tags_cls is not None
    assert WitmotionSensorApp.ui_cls is not None


def test_config_is_schema():
    from witmotion_sensors.app_config import WitmotionSensorConfig

    assert issubclass(WitmotionSensorConfig, Schema)


def test_tags_is_tags():
    from witmotion_sensors.app_tags import WitmotionSensorTags

    assert issubclass(WitmotionSensorTags, Tags)


def test_ui_is_ui():
    from witmotion_sensors.app_ui import WitmotionSensorUI

    assert issubclass(WitmotionSensorUI, UI)


def test_config_export(tmp_path):
    from witmotion_sensors.app_config import WitmotionSensorConfig

    fp = tmp_path / "doover_config.json"
    WitmotionSensorConfig.export(fp, "witmotion_sensors")
    data = json.loads(fp.read_text())
    assert "witmotion_sensors" in data
    schema = data["witmotion_sensors"]["config_schema"]
    assert "modbus_config" in schema["properties"]
    assert "modbus_id" in schema["properties"]
    assert "poll_period" in schema["properties"]


def test_ui_export(tmp_path):
    from witmotion_sensors.app_ui import WitmotionSensorUI

    fp = tmp_path / "doover_config.json"
    WitmotionSensorUI(None, None, None).export(fp, "witmotion_sensors")
    data = json.loads(fp.read_text())
    ui_schema = data["witmotion_sensors"]["ui_schema"]
    assert ui_schema["type"] == "uiApplication"
    children = ui_schema["children"]
    assert "velocity_peak" in children
    assert "displacement_peak" in children
    assert "frequency_dominant" in children
    assert "temperature" in children
    assert "link_state" in children
