import logging

from pydoover.state import StateMachine

log = logging.getLogger(__name__)


class LinkState:
    state: str

    states = [
        {"name": "disconnected"},
        {"name": "connecting"},
        {"name": "online"},
        {"name": "error"},
    ]

    transitions = [
        {"trigger": "connect", "source": ["disconnected", "error"], "dest": "connecting"},
        {"trigger": "connected", "source": "connecting", "dest": "online"},
        {"trigger": "connect_failed", "source": "connecting", "dest": "error"},
        {"trigger": "read_failed", "source": "online", "dest": "error"},
        {"trigger": "disconnect", "source": "*", "dest": "disconnected"},
    ]

    def __init__(self, error_retry_seconds: int = 30):
        self.states_config = [dict(s) for s in self.states]
        for s in self.states_config:
            if s["name"] == "error":
                s["timeout"] = error_retry_seconds
                s["on_timeout"] = "connect"

        self.state_machine = StateMachine(
            states=self.states_config,
            transitions=self.transitions,
            model=self,
            initial="disconnected",
            queued=True,
        )

    async def on_enter_disconnected(self):
        log.info("Link state: disconnected")

    async def on_enter_connecting(self):
        log.info("Link state: connecting")

    async def on_enter_online(self):
        log.info("Link state: online")

    async def on_enter_error(self):
        log.warning("Link state: error")
