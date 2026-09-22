import datetime

from model_current.atmosphere.subgrid_scale_physics.tmx import data as tmx_data, tmx_states
from model_current.common.states import model
import ops


class TmxComponent:
    inputs_properties = tmx_data.INPUTS_PROPERTIES
    outputs_properties = tmx_data.OUTPUTS_PROPERTIES

    def __init__(self) -> None:
        self._tendency_state = tmx_states.TmxTendencyState(
            ddt_temperature=ops.field(ops.CELL_K), ddt_u=ops.field(ops.CELL_K)
        )

    def __call__(self, state: dict[str, model.DataField], time_step: datetime.datetime) -> dict[str, model.DataField]:
        ops.tmx(state["temperature"], state["u"], self._tendency_state.ddt_temperature, self._tendency_state.ddt_u)
        return {key: getattr(self._tendency_state, port) for key, port in tmx_data.TENDENCY_GRANULE_PORTS.items()}

    def bind_output_buffers(self, buffers: dict[str, model.DataField]) -> None:
        pass
