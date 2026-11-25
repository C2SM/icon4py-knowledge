import dataclasses

from icon4py.model.common import field_type_aliases as fa, type_alias as ta

import ops


@dataclasses.dataclass
class DiagnosticState:
    temperature: fa.CellKField[ta.wpfloat]
    u: fa.CellKField[ta.wpfloat]


def initialize_diagnostic_state() -> DiagnosticState:
    return DiagnosticState(temperature=ops.field(ops.CELL_K), u=ops.field(ops.CELL_K))
