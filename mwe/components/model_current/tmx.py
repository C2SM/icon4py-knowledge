from datetime import datetime
from typing import Any

from model_current.common.states import FieldMetaData
from model_current.physics_driver import CELL_K, EntryState
import ops

INPUTS_PROPERTIES: dict[str, FieldMetaData] = {
    "temperature": {"standard_name": "air_temperature", "units": "K"},
    "u": {"standard_name": "eastward_wind", "units": "m s-1"},
}
OUTPUTS_PROPERTIES: dict[str, FieldMetaData] = {
    "tend_temperature": {"kind": "tendency", "dims": "cell_k", "units": "K s-1"},
    "tend_u": {"kind": "tendency", "dims": "cell_k", "units": "m s-2"},
}


class TmxState:
    def as_component_input(self, entry: EntryState) -> dict[str, Any]:
        return {"temperature": entry.temperature, "u": entry.u}


class TmxComponent:
    inputs_properties = INPUTS_PROPERTIES
    outputs_properties = OUTPUTS_PROPERTIES

    def __init__(self) -> None:
        self._tendencies = {"tend_temperature": ops.field(CELL_K), "tend_u": ops.field(CELL_K)}

    def bind_output_buffers(self, buffers: dict[str, ops.Field]) -> None:
        pass

    def __call__(self, state: dict[str, Any], step_start_datetime: datetime) -> dict[str, Any]:
        ops.tmx(state["temperature"], state["u"], self._tendencies["tend_temperature"], self._tendencies["tend_u"])
        return dict(self._tendencies)
