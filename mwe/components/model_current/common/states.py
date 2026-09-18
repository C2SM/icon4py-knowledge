import dataclasses
from typing import Any, Protocol

from icon4py.model.common import field_type_aliases as fa, type_alias as ta

FieldMetaData = dict[str, str]


@dataclasses.dataclass
class PrognosticState:
    vn: fa.EdgeKField[ta.wpfloat]
    w: fa.CellKField[ta.wpfloat]
    rho: fa.CellKField[ta.wpfloat]
    exner: fa.CellKField[ta.wpfloat]
    theta_v: fa.CellKField[ta.wpfloat]


@dataclasses.dataclass
class TracerState:
    qv: fa.CellKField[ta.wpfloat]


@dataclasses.dataclass
class PrepAdvection:
    mass_flux_e: fa.EdgeKField[ta.wpfloat]


class TimeStepPair[T]:
    def __init__(self, current: T, next: T) -> None:
        self.current, self.next = current, next

    def swap(self) -> None:
        self.current, self.next = self.next, self.current


class ComponentState(Protocol):
    def as_component_input(self, entry: Any) -> dict[str, Any]: ...
