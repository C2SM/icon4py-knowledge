import dataclasses

from icon4py.model.common import field_type_aliases as fa, type_alias as ta

import ops


@dataclasses.dataclass
class PrognosticState:
    rho: fa.CellKField[ta.wpfloat]
    w: fa.CellKField[ta.wpfloat]
    vn: fa.EdgeKField[ta.wpfloat]
    exner: fa.CellKField[ta.wpfloat]
    theta_v: fa.CellKField[ta.wpfloat]


def initialize_prognostic_state() -> PrognosticState:
    return PrognosticState(
        rho=ops.field(ops.CELL_K, "rho"),
        w=ops.field(ops.CELL_K, "w"),
        vn=ops.field(ops.EDGE_K, "vn"),
        exner=ops.field(ops.CELL_K, "exner"),
        theta_v=ops.field(ops.CELL_K, "theta_v"),
    )
