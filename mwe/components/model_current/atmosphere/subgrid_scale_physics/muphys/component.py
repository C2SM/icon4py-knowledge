import datetime

from icon4py.model.common import field_type_aliases as fa, type_alias as ta

from model_current.atmosphere.subgrid_scale_physics.muphys import data as muphys_data
from model_current.common.states import model
import ops


class MuphysComponent:
    inputs_properties = muphys_data.INPUTS_PROPERTIES
    outputs_properties = muphys_data.OUTPUTS_PROPERTIES

    def __init__(self) -> None:
        self._pflx: fa.CellField[ta.wpfloat] = ops.field(ops.CELL)
        self._tendencies: dict[str, fa.CellKField[ta.wpfloat]] = {
            "tend_temperature": ops.field(ops.CELL_K),
            "tend_qv": ops.field(ops.CELL_K),
        }

    def __call__(self, state: dict[str, model.DataField], time_step: datetime.datetime) -> dict[str, model.DataField]:
        ops.muphys(state["te"], state["qv"], self._tendencies["tend_temperature"], self._tendencies["tend_qv"], self._pflx)
        return {**self._tendencies, "pflx": self._pflx}

    def bind_output_buffers(self, buffers: dict[str, fa.CellField[ta.wpfloat]]) -> None:
        self._pflx = buffers["pflx"]
