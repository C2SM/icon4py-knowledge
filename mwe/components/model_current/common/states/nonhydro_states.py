import dataclasses

import icon4py.model.common.utils as common_utils
from icon4py.model.common import field_type_aliases as fa, type_alias as ta

import ops


@dataclasses.dataclass
class DiagnosticStateNonHydro:
    normal_wind_advective_tendency: common_utils.PredictorCorrectorPair[fa.EdgeKField[ta.wpfloat]]
    theta_v_at_cells_on_half_levels: fa.CellKHalfField[ta.wpfloat]


def initialize_solve_nonhydro_diagnostic_state() -> DiagnosticStateNonHydro:
    return DiagnosticStateNonHydro(
        normal_wind_advective_tendency=common_utils.PredictorCorrectorPair(
            ops.field(ops.EDGE_K), ops.field(ops.EDGE_K)
        ),
        theta_v_at_cells_on_half_levels=ops.field(ops.CELL_KHALF),
    )
