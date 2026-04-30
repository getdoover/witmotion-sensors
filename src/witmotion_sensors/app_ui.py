from pathlib import Path

from pydoover import ui

from .app_tags import WitmotionSensorTags


class WitmotionSensorUI(ui.UI):
    temperature = ui.NumericVariable(
        "Temperature",
        value=WitmotionSensorTags.temperature,
        name="temperature",
        precision=1,
        ranges=[
            ui.Range("Cold", -20, 10, ui.Colour.blue),
            ui.Range("Normal", 10, 60, ui.Colour.green),
            ui.Range("Hot", 60, 120, ui.Colour.red),
        ],
    )

    velocity_peak = ui.NumericVariable(
        "Peak Velocity (mm/s)",
        value=WitmotionSensorTags.velocity_peak,
        name="velocity_peak",
        precision=2,
        ranges=[
            ui.Range("Good", 0, 2.8, ui.Colour.green),
            ui.Range("Caution", 2.8, 7.1, ui.Colour.yellow),
            ui.Range("Warning", 7.1, 18.0, ui.Colour.orange),
            ui.Range("Alarm", 18.0, 100.0, ui.Colour.red),
        ],
    )

    displacement_peak = ui.NumericVariable(
        "Peak Displacement (um)",
        value=WitmotionSensorTags.displacement_peak,
        name="displacement_peak",
        precision=0,
    )

    frequency_dominant = ui.NumericVariable(
        "Dominant Frequency (Hz)",
        value=WitmotionSensorTags.frequency_dominant,
        name="frequency_dominant",
        precision=1,
    )

    link_state = ui.BooleanVariable(
        "Link State",
        value=WitmotionSensorTags.link_state,
        name="link_state",
    )


def export():
    WitmotionSensorUI(None, None, None).export(
        Path(__file__).parents[2] / "doover_config.json",
        "witmotion_sensors",
    )


if __name__ == "__main__":
    export()
