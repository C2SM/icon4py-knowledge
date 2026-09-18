from datetime import datetime
from typing import Any

from model_current.common.states import FieldMetaData
from model_current.physics_driver import CELL, CELL_K, EntryState
import ops

INPUTS_PROPERTIES: dict[str, FieldMetaData] = {
    "te": {"standard_name": "air_temperature", "units": "K"},
    "qv": {"standard_name": "specific_humidity", "units": "kg kg-1"},
}
OUTPUTS_PROPERTIES: dict[str, FieldMetaData] = {
    "tend_temperature": {"kind": "tendency", "dims": "cell_k", "units": "K s-1"},
    "tend_qv": {"kind": "tendency", "dims": "cell_k", "units": "kg kg-1 s-1"},
    "pflx": {"kind": "diagnostic", "dims": "cell", "units": "kg m-2 s-1"},
}


class MuphysState:
    def as_component_input(self, entry: EntryState) -> dict[str, Any]:
        return {"te": entry.temperature, "qv": entry.tracers.qv}


class MuphysComponent:
    inputs_properties = INPUTS_PROPERTIES
    outputs_properties = OUTPUTS_PROPERTIES

    def __init__(self) -> None:
        self._tendencies = {"tend_temperature": ops.field(CELL_K), "tend_qv": ops.field(CELL_K)}
        self._pflx = ops.field(CELL)

    def bind_output_buffers(self, buffers: dict[str, ops.Field]) -> None:
        self._pflx = buffers["pflx"]

    def __call__(self, state: dict[str, Any], step_start_datetime: datetime) -> dict[str, Any]:
        ops.muphys(state["te"], state["qv"], self._tendencies["tend_temperature"], self._tendencies["tend_qv"], self._pflx)
        return {**self._tendencies, "pflx": self._pflx}
