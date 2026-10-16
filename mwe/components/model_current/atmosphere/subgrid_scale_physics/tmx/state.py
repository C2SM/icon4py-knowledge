from typing import Any

from model_current.common.components.component_state import ComponentState


class State(ComponentState):
    def as_component_input(self, state: Any) -> dict[str, Any]:
        return {"temperature": state.diagnostics.temperature, "u": state.diagnostics.u}
