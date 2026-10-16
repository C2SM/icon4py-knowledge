from typing import Any

from model_current.common.components.component_state import ComponentState


class State(ComponentState):
    def as_component_input(self, state: Any) -> dict[str, Any]:
        return {"te": state.diagnostics.temperature, "qv": state.tracers.qv}
