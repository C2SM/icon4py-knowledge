from typing import Final

from model_current.common.states import data as state_data, prognostic_state as prognostics
import ops

PROGNOSTIC_VARIABLES: Final[list[str]] = [
    "air_density",
    "exner_function",
    "virtual_potential_temperature",
    "upward_air_velocity",
    "normal_velocity",
]


def prognostic_state_to_dataarrays(prognostic_state: prognostics.PrognosticState) -> dict[str, ops.Field]:
    state: dict[str, ops.Field] = {}
    for name in PROGNOSTIC_VARIABLES:
        metadata = state_data.PROGNOSTIC_CF_ATTRIBUTES[name]
        assert metadata.icon_var_name is not None
        state[name] = getattr(prognostic_state, metadata.icon_var_name)
    return state


class DiagnosticsComputer:
    def __init__(self) -> None:
        self._temperature = ops.field(ops.CELL_K)
        self._u = ops.field(ops.CELL_K)

    def compute(self, prognostic_state: prognostics.PrognosticState) -> dict[str, ops.Field]:
        ops.compute_temperature(prognostic_state.theta_v, prognostic_state.exner, self._temperature)
        ops.edge_2_cell_vector_rbf_interpolation(prognostic_state.vn, self._u)
        return {"eastward_wind": self._u, "temperature": self._temperature}
