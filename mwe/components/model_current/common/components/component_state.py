from typing import Any, Protocol


class ComponentState(Protocol):
    def as_component_input(self, state: Any) -> dict[str, Any]: ...
