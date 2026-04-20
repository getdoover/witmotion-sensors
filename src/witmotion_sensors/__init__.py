from pydoover.docker import run_app

from .application import WitmotionSensorApp


def main():
    run_app(WitmotionSensorApp())
