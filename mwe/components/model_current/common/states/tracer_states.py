from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from typing import NamedTuple

from icon4py.model.common import field_type_aliases as fa, type_alias as ta

from model_current.common.states.data import COMMON_TRACER_CF_ATTRIBUTES
import ops


class TracerField(NamedTuple):
    name: str
    field: fa.CellKField[ta.wpfloat]


_TRACER_FIELDS: tuple[str, ...] = tuple(COMMON_TRACER_CF_ATTRIBUTES)


@dataclasses.dataclass
class TracerState:
    qv: fa.CellKField[ta.wpfloat] | None = None

    def active_fields(self) -> Iterator[TracerField]:
        for name in _TRACER_FIELDS:
            field = getattr(self, name)
            if field is not None:
                yield TracerField(name=name, field=field)

    def copy(self) -> TracerState:
        return TracerState(**{tracer.name: ops.copy(tracer.field) for tracer in self.active_fields()})


def initialize_tracer_state() -> TracerState:
    return TracerState(qv=ops.field(ops.CELL_K, "qv"))
